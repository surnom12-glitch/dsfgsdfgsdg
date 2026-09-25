# FRACTURE — низкополигональные модели для карты «Долина» (Blender 5.2).
# Запуск: blender -b --factory-startup --python models/blender/fracture_models.py -- \
#   [--only key1,key2] [--cat vehicle] [--render DIR] [--lineup DIR --name NAME] [--export DIR]
# Оси Blender: Z вверх, перед модели смотрит в -Y, начало координат — на земле по центру.
import bpy, bmesh, math, random, sys, os, json
from mathutils import Matrix, Vector, Euler

# Цвета в sRGB — те же значения уходят в игру (она не делает гамма-коррекцию).
PAL = {
 'paint':(.62,.16,.14),'paint_d':(.48,.12,.11),'glass':(.15,.19,.23),'tire':(.09,.09,.1),'rim':(.6,.62,.64),
 'black':(.11,.11,.12),'dgray':(.26,.27,.28),'gray':(.5,.51,.52),'lgray':(.72,.73,.72),'white':(.9,.9,.88),
 'light':(.98,.95,.8),'tail':(.72,.1,.08),'amber':(.95,.6,.12),'plate':(.92,.92,.88),'chrome':(.78,.8,.82),
 'char':(.08,.075,.07),'rust':(.45,.22,.11),'rust_d':(.3,.15,.09),'khaki':(.34,.37,.25),'khaki_d':(.25,.27,.19),
 'canvas':(.4,.41,.3),'bark':(.34,.25,.17),'bark_d':(.26,.19,.13),'leaf1':(.25,.43,.16),'leaf2':(.32,.52,.2),
 'leaf3':(.19,.35,.13),'pine1':(.13,.29,.17),'pine2':(.18,.36,.21),'birch':(.88,.87,.82),'birch_m':(.13,.13,.12),
 'bleaf1':(.43,.59,.21),'bleaf2':(.53,.65,.25),'rock1':(.47,.46,.44),'rock2':(.38,.37,.35),'moss':(.34,.41,.22),
 'concrete':(.66,.65,.61),'concrete_d':(.54,.53,.5),'wood':(.55,.38,.22),'wood_l':(.68,.5,.31),'wood_d':(.37,.25,.14),
 'metal':(.42,.44,.46),'metal_d':(.23,.24,.25),'sand':(.63,.55,.37),'hay':(.8,.68,.37),'hay_d':(.64,.53,.26),
 'fabric':(.36,.43,.56),'cream':(.9,.86,.76),'screen':(.05,.06,.07),'red':(.75,.16,.13),'blue':(.18,.33,.6),
 'yellow':(.92,.74,.16),'green':(.22,.46,.26),'orange':(.92,.44,.11),'signblue':(.1,.3,.66),
}
# шероховатость, металличность, свечение (только для рендера превью)
SPEC = {'glass':(.06,0,0),'chrome':(.22,1,0),'rim':(.35,.85,0),'metal':(.4,.8,0),'metal_d':(.45,.7,0),'light':(.3,0,1.2),
        'tail':(.3,0,.6),'amber':(.3,0,.5),'screen':(.08,0,0),'paint':(.35,0,0),'paint_d':(.4,0,0),'tire':(.9,0,0)}
PAINT_KEYS = ('paint', 'paint_d')

REG = []
def model(key, ru, cat, paint=None):
    def deco(fn): REG.append(dict(key=key, ru=ru, cat=cat, fn=fn, paint=paint)); return fn
    return deco

def srgb2lin(c): return c/12.92 if c <= .04045 else ((c+.055)/1.055)**2.4
def TR(loc=(0,0,0), rot=(0,0,0), scale=None):
    M = Matrix.Translation(Vector(loc)) @ Euler(rot, 'XYZ').to_matrix().to_4x4()
    if scale: M = M @ Matrix.Diagonal((scale[0], scale[1], scale[2], 1))
    return M
def lerp(a, b, t): return a+(b-a)*t

# ---------- примитивы (каждый возвращает отдельный bmesh) ----------
def p_box(sx, sy, sz, bevel=0, top=None):
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1)
    for v in bm.verts:
        v.co.x *= sx; v.co.y *= sy; v.co.z *= sz
        if top and v.co.z > 0:
            v.co.x = v.co.x*top[0]+(top[2] if len(top) > 2 else 0); v.co.y = v.co.y*top[1]+(top[3] if len(top) > 3 else 0)
    if bevel > 0: bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bevel, segments=1, affect='EDGES', profile=.5)
    return bm
def p_cyl(r, h, seg=12, r2=None):
    bm = bmesh.new(); bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg, radius1=r, radius2=(r if r2 is None else r2), depth=h); return bm
def p_ico(r, sub=1, sc=(1,1,1), jit=0, rnd=None):
    bm = bmesh.new(); bmesh.ops.create_icosphere(bm, subdivisions=sub, radius=r)
    for v in bm.verts:
        j = 1+(rnd.uniform(-jit, jit) if jit else 0)
        v.co.x *= sc[0]*j; v.co.y *= sc[1]*j; v.co.z *= sc[2]*j
    return bm
def p_cone(r, h, seg=8, jit=0, rnd=None, tip=(0, 0)):
    """Конус с одной вершиной (без вырожденных граней); jit — неровный край."""
    bm = bmesh.new(); ring = []
    for i in range(seg):
        a = 2*math.pi*i/seg; rr = r*(1+(rnd.uniform(-jit, jit) if jit else 0))
        ring.append(bm.verts.new((rr*math.cos(a), rr*math.sin(a), -h/2+(rnd.uniform(-jit, jit)*h*.3 if jit else 0))))
    top = bm.verts.new((tip[0], tip[1], h/2))
    for i in range(seg): bm.faces.new([ring[i], ring[(i+1) % seg], top])
    bm.faces.new(ring[::-1]); return bm
def p_prism(pts, depth, axis='X'):
    bm = bmesh.new(); a = []; b = []
    for (u, w) in pts:
        if axis == 'X': a.append(bm.verts.new((-depth/2, u, w))); b.append(bm.verts.new((depth/2, u, w)))
        elif axis == 'Y': a.append(bm.verts.new((u, -depth/2, w))); b.append(bm.verts.new((u, depth/2, w)))
        else: a.append(bm.verts.new((u, w, -depth/2))); b.append(bm.verts.new((u, w, depth/2)))
    bm.faces.new(a); bm.faces.new(b[::-1])
    for i in range(len(pts)):
        j = (i+1) % len(pts); bm.faces.new([a[i], a[j], b[j], b[i]])
    return bm
def p_loft(secs, fmat=None, caps=(True, True), capmat=(0, 0)):
    bm = bmesh.new(); rows = [[bm.verts.new(p) for p in s] for s in secs]; n = len(secs[0])
    for k in range(len(rows)-1):
        for i in range(n):
            j = (i+1) % n
            try: f = bm.faces.new([rows[k][i], rows[k][j], rows[k+1][j], rows[k+1][i]])
            except ValueError: continue
            f.material_index = fmat(k, i) if fmat else 0
    if caps[0]: f = bm.faces.new(rows[0]); f.material_index = capmat[0]
    if caps[1]: f = bm.faces.new(rows[-1][::-1]); f.material_index = capmat[1]
    return bm

# ---------- сборщик модели ----------
class Mb:
    def __init__(s, key, paint=None):
        s.key = key; s.bm = bmesh.new(); s.keys = []; s.remap = {}; s.offset = Vector((0, 0, 0)); s.paint = paint
        s.rnd = random.Random(sum(ord(ch)*(i+7) for i, ch in enumerate(key)))
    def mi(s, k):
        k = s.remap.get(k, k)
        if k not in s.keys: s.keys.append(k)
        return s.keys.index(k)
    def put(s, part, mat, T=None):
        bmesh.ops.recalc_face_normals(part, faces=part.faces[:])
        T = Matrix.Translation(s.offset) @ (T if T is not None else Matrix.Identity(4))
        vm = {v: s.bm.verts.new(T @ v.co) for v in part.verts}
        flip = T.to_3x3().determinant() < 0
        for f in part.faces:
            vs = [vm[v] for v in f.verts]
            if flip: vs.reverse()
            try: nf = s.bm.faces.new(vs)
            except ValueError: continue
            k = mat(f) if callable(mat) else (mat[f.material_index] if isinstance(mat, (list, tuple)) else mat)
            nf.material_index = s.mi(k)
        part.free(); return s
    def box(s, mat, c, sz, rot=(0,0,0), bevel=0, top=None): return s.put(p_box(*sz, bevel=bevel, top=top), mat, TR(c, rot))
    def cyl(s, mat, c, r, h, seg=12, r2=None, rot=(0,0,0)): return s.put(p_cyl(r, h, seg, r2), mat, TR(c, rot))
    def cylx(s, mat, c, r, h, seg=12, r2=None): return s.cyl(mat, c, r, h, seg, r2, rot=(0, math.pi/2, 0))
    def cyly(s, mat, c, r, h, seg=12, r2=None): return s.cyl(mat, c, r, h, seg, r2, rot=(math.pi/2, 0, 0))
    def ico(s, mat, c, r, sub=1, sc=(1,1,1), jit=0, rot=(0,0,0)): return s.put(p_ico(r, sub, sc, jit, s.rnd), mat, TR(c, rot))
    def cone(s, mat, c, r, h, seg=8, jit=0, rot=(0,0,0), tip=(0, 0)): return s.put(p_cone(r, h, seg, jit, s.rnd, tip), mat, TR(c, rot))
    def pick(s, *keys):
        """Случайный цвет для каждой грани — «фасеточный» вид листвы и камня."""
        return lambda f: s.rnd.choice(keys)
    def prism(s, mat, pts, depth, axis='X', c=(0,0,0), rot=(0,0,0)): return s.put(p_prism(pts, depth, axis), mat, TR(c, rot))
    def beam(s, mat, a, b, w, d=None, seg=0, w2=None):
        """Брусок (seg=0) или труба между точками a и b; w2 — радиус на конце b (сужение)."""
        a = Vector(a); b = Vector(b); v = b-a; q = Vector((0, 0, 1)).rotation_difference(v.normalized())
        T = Matrix.Translation((a+b)/2) @ q.to_matrix().to_4x4()
        return s.put(p_cyl(w, v.length, seg, w2) if seg else p_box(w, d or w, v.length), mat, T)
    def wheel(s, c, r, w, seg=12, tire='tire', rim='rim', rr=None, hub=True):
        s.cylx(tire, c, r, w, seg); s.cylx(rim, c, rr or r*.6, w+.024, 8)
        if hub: s.cylx('dgray', c, (rr or r*.6)*.35, w+.05, 6)
        return s

def interp(st, y, i):
    if y <= st[0][0]: return st[0][i]
    for a, b in zip(st, st[1:]):
        if a[0] <= y <= b[0]: return lerp(a[i], b[i], (y-a[0])/(b[0]-a[0]) if b[0] > a[0] else 0)
    return st[-1][i]

def car_body(m, st, wheels, ra, zc, ch=.09, low='paint_d'):
    """Нижняя часть кузова: лофт по станциям (y, полуширина, низ, верх) с арками колёс."""
    ys = set(round(s[0], 4) for s in st)
    for yw in wheels:
        for k in range(7): ys.add(round(yw-ra*math.cos(math.pi*k/6), 4))
        ys.add(round(yw-ra-.012, 4)); ys.add(round(yw+ra+.012, 4))
    secs = []
    for y in sorted(y for y in ys if st[0][0] <= y <= st[-1][0]):
        hw, zb, zt = interp(st, y, 1), interp(st, y, 2), interp(st, y, 3)
        for yw in wheels:
            d = abs(y-yw)
            if d <= ra+1e-6: zb = max(zb, zc+math.sqrt(max(0, ra*ra-d*d)))
        c = min(ch, (zt-zb)*.3)
        secs.append([(-hw+c*.8, y, zb), (-hw, y, zb+c), (-hw, y, zt-c), (-hw+c, y, zt), (hw-c, y, zt), (hw, y, zt-c), (hw, y, zb+c), (hw-c*.8, y, zb)])
    m.put(p_loft(secs, fmat=lambda k, i: 2 if i == 7 else 1 if i in (0, 6) else 0), ['paint', low, 'black'])
    for yw in wheels: m.box('black', (0, yw, zc+.1), (2*st[2][1]-.34, 2*ra-.04, .5))

def cabin(m, yb0, yt0, yt1, yb1, zb, zt, hb, ht, cuts=(), belt=None, inset=.055, mat='paint', glass='glass', rear=True, front=True):
    """Салон: шестигранник со скошенными стёклами, окна — вставки (inset) в грани."""
    s0 = [(-hb, yb0, zb), (-ht, yt0, zt), (ht, yt0, zt), (hb, yb0, zb)]
    s1 = [(-hb, yb1, zb), (-ht, yt1, zt), (ht, yt1, zt), (hb, yb1, zb)]
    bm = p_loft([s0, s1]); bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    for y in cuts: bmesh.ops.bisect_plane(bm, geom=bm.verts[:]+bm.edges[:]+bm.faces[:], dist=1e-5, plane_co=(0, y, 0), plane_no=(0, 1, 0))
    if belt: bmesh.ops.bisect_plane(bm, geom=bm.verts[:]+bm.edges[:]+bm.faces[:], dist=1e-5, plane_co=(0, 0, belt), plane_no=(0, 0, 1))
    bm.normal_update(); win = []
    for f in bm.faces:
        n = f.normal; c = f.calc_center_median()
        if belt and c.z < belt: continue
        side = abs(n.x) > .6; cap = abs(n.y) > .35 and abs(n.z) < .95 and abs(n.x) < .6
        if side or (cap and ((n.y < 0 and front) or (n.y > 0 and rear))): win.append(f)
    for f in bm.faces: f.material_index = 0
    bmesh.ops.inset_individual(bm, faces=win, thickness=inset, depth=-.012, use_even_offset=True)
    for f in win: f.material_index = 1
    m.put(bm, [mat, glass])

def roof_loft(m, y0, y1, hw, zb, zt, ch=.12, mat='white'):
    secs = [[(-hw+ch, y, zb), (-hw, y, zb+ch*.5), (-hw, y, zt-ch), (-hw+ch, y, zt), (hw-ch, y, zt), (hw, y, zt-ch), (hw, y, zb+ch*.5), (hw-ch, y, zb)] for y in (y0, y1)]
    m.put(p_loft(secs), mat)

def mirror(m, x, y, z, mat='paint'):
    """Боковое зеркало на кронштейне, прижатое к двери у передней стойки."""
    s = 1 if x > 0 else -1
    m.box('black', (x-s*.05, y, z-.02), (.1, .04, .03)); m.box(mat, (x+s*.02, y, z), (.1, .09, .1))

def burn(m):
    """Сгоревшая версия: ржавчина пятнами, копоть."""
    m.bm.normal_update()
    for f in m.bm.faces:
        if m.keys[f.material_index] == 'rust':
            c = f.calc_center_median(); h = (math.sin(c.x*12.9+c.y*78.2+c.z*37.7)*43758.5) % 1
            if f.normal.z < .6 and h < .55: f.material_index = m.mi('char')

# =====================================================================================
# ТРАНСПОРТ
# =====================================================================================
def sedan_geo(m, burnt=False):
    st = [(-2.25, .78, .34, .64), (-2.16, .86, .27, .76), (-1.6, .895, .25, .84), (-.7, .9, .25, .9), (.9, .9, .25, .92), (1.75, .895, .27, .9), (2.18, .86, .31, .86), (2.25, .78, .37, .76)]
    W = [-1.40, 1.42]; ra, zc = .37, .32
    if burnt:
        m.remap = {'paint': 'rust', 'paint_d': 'char', 'glass': 'char', 'light': 'dgray', 'tail': 'char', 'plate': 'rust_d', 'black': 'char'}
        m.offset = Vector((0, 0, -.12))
    car_body(m, st, W, ra, zc)
    cabin(m, -.72, -.05, .95, 1.62, .88, 1.40, .84, .67, cuts=[.42])
    for sx in (-1, 1):
        m.box('light', (sx*.56, -2.19, .68), (.36, .1, .12)); m.box('tail', (sx*.58, 2.21, .76), (.36, .1, .12))
        mirror(m, sx*.9, -.6, .95); m.box('black', (sx*.905, .4, .72), (.02, .16, .03))
    m.box('black', (0, -2.23, .5), (.72, .08, .13)); m.box('black', (0, -2.27, .36), (1.62, .12, .15), bevel=.03); m.box('black', (0, 2.28, .4), (1.62, .12, .15), bevel=.03)
    m.box('plate', (0, -2.34, .37), (.44, .02, .11)); m.box('plate', (0, 2.345, .52), (.44, .02, .11))
    if burnt:
        m.offset = Vector((0, 0, 0))
        for y in W:
            for sx in (-1, 1): m.cylx('rust_d', (sx*.74, y, .2), .2, .2, 8)
        burn(m)
    else:
        for y in W:
            for sx in (-1, 1): m.wheel((sx*.77, y, zc), .32, .21)

@model('sedan', 'Седан', 'vehicle', paint=(.62, .16, .14))
def m_sedan(m): sedan_geo(m)

@model('sedan_burnt', 'Сгоревший седан', 'vehicle')
def m_sedan_burnt(m): sedan_geo(m, burnt=True)

@model('hatchback', 'Хэтчбек', 'vehicle', paint=(.2, .36, .58))
def m_hatch(m):
    st = [(-1.95, .76, .34, .64), (-1.86, .84, .27, .76), (-1.35, .87, .25, .84), (-.55, .875, .25, .9), (1.55, .875, .26, .93), (1.93, .85, .3, .9), (2.0, .78, .36, .84)]
    W = [-1.22, 1.3]; ra, zc = .36, .31
    car_body(m, st, W, ra, zc)
    cabin(m, -.58, .02, 1.62, 1.93, .88, 1.46, .82, .66, cuts=[.62])
    for sx in (-1, 1):
        m.box('light', (sx*.55, -1.9, .68), (.32, .1, .12)); m.box('tail', (sx*.66, 1.97, .98), (.14, .06, .3))
        mirror(m, sx*.88, -.46, .95)
    m.box('black', (0, -1.93, .5), (.64, .08, .12)); m.box('black', (0, -1.97, .36), (1.56, .12, .15), bevel=.03); m.box('black', (0, 2.03, .4), (1.56, .12, .15), bevel=.03)
    m.box('plate', (0, -2.04, .37), (.44, .02, .11)); m.box('plate', (0, 2.095, .5), (.44, .02, .11))
    for y in W:
        for sx in (-1, 1): m.wheel((sx*.75, y, zc), .31, .2)

@model('pickup', 'Пикап', 'vehicle', paint=(.36, .42, .38))
def m_pickup(m):
    st = [(-2.65, .86, .46, .84), (-2.55, .93, .37, .99), (-1.9, .95, .35, 1.04), (-1.0, .95, .35, 1.06), (2.55, .95, .37, 1.06), (2.65, .92, .43, 1.0)]
    W = [-1.65, 1.62]; ra, zc = .46, .41
    car_body(m, st, W, ra, zc)
    cabin(m, -1.0, -.42, .38, .58, 1.04, 1.8, .9, .74, cuts=[-.2])
    m.box('dgray', (0, 1.6, 1.08), (1.74, 1.92, .04))
    for sx in (-1, 1): m.box('paint', (sx*.905, 1.6, 1.28), (.09, 1.96, .44), bevel=.02)
    m.box('paint', (0, .66, 1.28), (1.9, .08, .44), bevel=.02); m.box('paint', (0, 2.56, 1.26), (1.9, .08, .4), bevel=.02)
    m.box('black', (0, -2.665, .7), (1.2, .04, .24)); m.box('chrome', (0, -2.7, .46), (1.86, .14, .2), bevel=.04); m.box('dgray', (0, 2.68, .5), (1.86, .14, .18), bevel=.03)
    for sx in (-1, 1):
        m.box('light', (sx*.74, -2.66, .78), (.28, .04, .14)); m.box('tail', (sx*.93, 2.62, 1.2), (.08, .06, .34))
        mirror(m, sx*.95, -.9, 1.14)
    m.box('plate', (0, -2.775, .45), (.44, .02, .11))
    for y in W:
        for sx in (-1, 1): m.wheel((sx*.8, y, zc), .41, .27)

@model('van', 'Фургон', 'vehicle', paint=(.86, .86, .83))
def m_van(m):
    st = [(-2.45, .92, .4, .8), (-2.36, .98, .31, .98), (-1.8, 1.0, .29, 1.06), (2.36, 1.0, .29, 1.06), (2.45, .96, .35, 1.02)]
    W = [-1.58, 1.48]; ra, zc = .41, .36
    car_body(m, st, W, ra, zc)
    cabin(m, -2.24, -1.6, 2.38, 2.44, 1.04, 2.18, .98, .9, cuts=[-1.0, .15, 1.3], inset=.07)
    for sx in (-1, 1):
        m.box('light', (sx*.66, -2.42, .8), (.34, .08, .16)); m.box('tail', (sx*.9, 2.45, .9), (.14, .06, .34))
        m.box('black', (sx*1.03, -1.9, 1.3), (.06, .06, .24))
    m.box('black', (0, -2.43, .6), (.9, .06, .18)); m.box('dgray', (0, -2.49, .4), (1.9, .14, .18), bevel=.03); m.box('dgray', (0, 2.5, .42), (1.9, .12, .16), bevel=.03)
    m.box('black', (1.005, .15, .7), (.02, .04, .62)); m.box('plate', (0, -2.565, .42), (.44, .02, .11))
    m.box('dgray', (0, .4, 2.24), (1.2, 2.2, .08)); m.box('red', (0, 2.465, 1.62), (1.2, .02, .14))
    for y in W:
        for sx in (-1, 1): m.wheel((sx*.84, y, zc), .36, .23)

@model('bus', 'Автобус', 'vehicle', paint=(.9, .7, .15))
def m_bus(m):
    st = [(-5.25, 1.2, .42, .9), (-5.15, 1.25, .34, 1.22), (5.15, 1.25, .34, 1.26), (5.25, 1.2, .42, 1.1)]
    W = [-3.1, 2.7]; ra, zc = .58, .5
    car_body(m, st, W, ra, zc, ch=.12)
    cabin(m, -5.2, -5.08, 5.1, 5.2, 1.22, 2.6, 1.25, 1.2, cuts=[-3.75+i*1.3 for i in range(7)], inset=.08)
    roof_loft(m, -5.12, 5.14, 1.21, 2.56, 2.98)
    m.box('black', (0, -5.21, 2.47), (1.9, .05, .24)); m.box('amber', (0, -5.24, 2.47), (1.5, .02, .12))
    for yd in (-4.45, .45):
        m.box('glass', (1.265, yd, 1.42), (.03, 1.1, 2.05)); m.box('black', (1.27, yd, 1.42), (.035, .06, 2.05)); m.box('black', (1.27, yd, 2.46), (.035, 1.14, .06))
    for sx in (-1, 1):
        m.box('light', (sx*.85, -5.26, .72), (.36, .06, .16)); m.box('tail', (sx*1.0, 5.25, .82), (.18, .06, .36))
        m.box('black', (sx*1.35, -5.0, 2.1), (.08, .08, .36))
    m.box('dgray', (0, -5.28, .44), (2.3, .12, .2), bevel=.03); m.box('dgray', (0, 5.28, .46), (2.3, .12, .2), bevel=.03); m.box('black', (0, -5.26, .9), (1.2, .04, .18))
    m.box('paint_d', (0, 0, 1.1), (2.52, 9.9, .1))
    for y in W:
        for sx in (-1, 1): m.wheel((sx*1.02, y, zc), .5, .32)

@model('truck', 'Грузовик', 'vehicle', paint=(.9, .45, .12))
def m_truck(m):
    for sx in (-1, 1): m.box('black', (sx*.45, .2, .82), (.16, 7.2, .26))
    cabin(m, -3.8, -3.56, -1.86, -1.86, 1.1, 3.05, 1.24, 1.2, belt=2.0, inset=.07)
    m.box('black', (0, -3.84, 1.55), (1.5, .06, .6)); m.box('dgray', (0, -3.9, .95), (2.4, .2, .3), bevel=.04)
    for sx in (-1, 1):
        m.box('light', (sx*.95, -3.86, 1.5), (.28, .06, .2)); m.box('black', (sx*1.36, -3.55, 2.35), (.06, .1, .4)); m.beam('black', (sx*1.24, -3.6, 2.6), (sx*1.36, -3.55, 2.5), .025, seg=4)
        m.box('black', (sx*1.0, -2.85, 1.18), (.55, 1.3, .06))
    m.box('wood_d', (0, 1.05, 1.36), (2.44, 5.1, .14))
    for sx in (-1, 1): m.box('paint', (sx*1.2, 1.05, 1.66), (.06, 5.1, .46))
    m.box('paint', (0, 3.58, 1.66), (2.44, .06, .46)); m.box('paint', (0, -1.47, 1.66), (2.44, .06, .46))
    secs = [[(-1.2, y, 1.88), (-1.2, y, 2.85), (-.95, y, 3.12), (.95, y, 3.12), (1.2, y, 2.85), (1.2, y, 1.88)] for y in (-1.44, 3.55)]
    m.put(p_loft(secs), 'canvas')
    m.cyly('metal', (1.05, -.7, .85), .26, 1.2, 10); m.cyl('black', (-1.12, -1.7, 2.6), .07, 2.0, 8)
    for sx in (-1, 1): m.wheel((sx*1.0, -2.85, .54), .54, .42)
    for y in (1.35, 2.75):
        for sx in (-1, 1): m.wheel((sx*.92, y, .54), .54, .6)
    m.box('tail', (-.95, 3.62, 1.2), (.24, .04, .12)); m.box('tail', (.95, 3.62, 1.2), (.24, .04, .12))

@model('tank', 'Танк', 'vehicle')
def m_tank(m):
    m.prism('khaki', [(-3.45, .45), (-3.62, .88), (-2.35, 1.36), (3.3, 1.36), (3.46, 1.15), (3.36, .45)], 2.2, 'X')
    front = [(-2.78+.52*math.cos(t), .52+.52*math.sin(t)) for t in [math.pi/2+math.pi*k/6 for k in range(7)]]
    back = [(2.72+.52*math.cos(t), .52+.52*math.sin(t)) for t in [-math.pi/2+math.pi*k/6 for k in range(7)]]
    for sx in (-1, 1):
        m.prism('tire', front+back, .6, 'X', c=(sx*1.4, 0, 0))
        m.box('khaki_d', (sx*1.42, 0, 1.08), (.66, 6.9, .05))
        for k in range(6): m.cylx('khaki_d', (sx*1.71, -2.5+k*1.0, .42), .34, .06, 10)
        m.cylx('khaki_d', (sx*1.71, -2.85, .82), .14, .07, 8); m.cylx('khaki_d', (sx*1.71, 2.95, .72), .2, .07, 8)
    m.cyl('khaki', (0, .25, 1.63), 1.34, .55, 8, 1.02)
    m.cyl('khaki_d', (.5, .45, 2.02), .36, .24, 8, .3); m.cyl('khaki_d', (-.45, .7, 1.95), .28, .1, 8)
    m.cyly('khaki_d', (0, -1.3, 1.72), .22, .8, 8); m.cyly('khaki', (0, -3.4, 1.74), .085, 4.2, 8); m.cyly('khaki_d', (0, -3.0, 1.74), .13, .6, 8)
    for sx in (-1, 1):
        for k in range(3):
            a = math.radians(32+k*9); m.cyl('khaki_d', (sx*1.12*math.sin(a), .25-1.12*math.cos(a), 1.86), .05, .3, 6, rot=(-1.1, 0, -sx*a))
        for k in range(3): m.box('khaki_d', (sx*(.35+k*.34), -2.9+k*.05, 1.18), (.3, .5, .12), rot=(.6, 0, 0))
    m.cylx('khaki_d', (0, 3.2, 1.62), .3, 1.6, 10)
    m.box('black', (0, 3.4, 1.1), (1.2, .1, .22))

@model('tractor', 'Трактор', 'vehicle', paint=(.72, .14, .12))
def m_tractor(m):
    for sx in (-1, 1):
        m.wheel((sx*.86, .75, .78), .78, .46, seg=14, rr=.45); m.wheel((sx*.74, -1.45, .45), .45, .26, seg=12, rr=.26)
        outer = [(.9*math.cos(t), .78+.9*math.sin(t)) for t in [math.pi*k/6 for k in range(7)]]
        inner = [(.84*math.cos(t), .78+.84*math.sin(t)) for t in [math.pi*k/6 for k in range(6, -1, -1)]]
        m.prism('paint', outer+inner, .5, 'X', c=(sx*.86, .75, 0))
    m.box('paint', (0, -1.05, 1.05), (.8, 1.9, .62), top=(.9, .98)); m.box('black', (0, -2.0, 1.02), (.62, .04, .44))
    m.box('dgray', (0, -.3, .7), (.62, 2.8, .36)); m.box('dgray', (0, -1.45, .45), (1.3, .2, .16))
    m.box('paint', (0, .72, 1.42), (1.36, 1.5, .1))
    for sx in (-1, 1):
        for y in (.02, 1.42): m.box('black', (sx*.64, y, 2.05), (.06, .06, 1.24))
        m.box('glass', (sx*.64, .72, 2.05), (.02, 1.36, 1.1))
    m.box('glass', (0, .02, 2.05), (1.26, .02, 1.1)); m.box('glass', (0, 1.42, 2.1), (1.26, .02, .9))
    m.box('paint', (0, .72, 2.72), (1.46, 1.66, .12), bevel=.03); m.box('white', (0, .72, 2.81), (1.3, 1.5, .06))
    m.cyl('black', (.28, -.35, 1.95), .05, 1.5, 8); m.cyl('dgray', (0, .9, 1.62), .22, .3, 8)
    for sx in (-1, 1): m.box('light', (sx*.3, -2.02, 1.18), (.12, .04, .1))

# =====================================================================================
# ПРИРОДА
# =====================================================================================
@model('tree_oak', 'Лиственное дерево', 'nature')
def m_oak(m):
    m.cyl('bark', (0, 0, 1.25), .26, 2.5, 6, .17)
    for a, b, w in (((0, 0, 1.9), (.95, .35, 3.0), .1), ((0, 0, 2.15), (-.85, -.45, 3.2), .09), ((0, 0, 2.3), (.1, -.8, 3.4), .08)):
        m.beam('bark', a, b, w, seg=5, w2=w*.5)
    leaf = m.pick('leaf1', 'leaf1', 'leaf2', 'leaf3')
    for c, r in (((0, 0, 4.1), 1.75), ((1.1, .45, 3.55), 1.25), ((-1.0, -.5, 3.7), 1.3), ((.25, -1.0, 3.85), 1.15), ((-.25, .9, 4.35), 1.15), ((.4, .1, 5.1), 1.0)):
        m.ico(leaf, c, r, sub=1, jit=.14, rot=(m.rnd.uniform(0, 3), m.rnd.uniform(0, 3), m.rnd.uniform(0, 3)))

@model('tree_pine', 'Ель', 'nature')
def m_pine(m):
    pine_geo(m)

def pine_geo(m, snow=False):
    m.cyl('bark_d', (0, 0, .75), .2, 1.5, 6, .15)
    needles = m.pick('pine1', 'pine1', 'pine2')
    for i, (z, r, h) in enumerate(((1.0, 1.95, 2.3), (2.15, 1.6, 2.1), (3.2, 1.25, 1.9), (4.15, .9, 1.7), (5.0, .55, 1.5))):
        mat = needles if not snow else (lambda f, i=i: 'white' if f.normal.z > .35 and (i >= 2 or m.rnd.random() < .5) else m.rnd.choice(('pine1', 'pine2')))
        m.cone(mat, (0, 0, z+h/2), r, h, 9, jit=.1, rot=(0, 0, m.rnd.uniform(0, 1)))

@model('tree_pine_snow', 'Ель в снегу', 'nature')
def m_pine_snow(m): pine_geo(m, snow=True)

@model('tree_birch', 'Берёза', 'nature')
def m_birch(m):
    m.cyl('birch', (0, 0, 2.0), .15, 4.0, 6, .09, rot=(.03, .04, 0))
    for z in (.55, 1.25, 1.95, 2.7, 3.3): m.cyl('birch_m', (z*.04, -z*.03, z), .158-z*.016, .07, 6)
    for a, b in (((0, 0, 2.6), (.7, .2, 3.6)), ((0, 0, 3.0), (-.6, -.3, 4.0))): m.beam('birch', a, b, .055, seg=5, w2=.025)
    leaf = m.pick('bleaf1', 'bleaf1', 'bleaf2')
    for c, r in (((.1, 0, 4.6), 1.05), ((.7, .25, 3.9), .8), ((-.6, -.3, 4.1), .85), ((0, .5, 5.4), .75)):
        m.ico(leaf, c, r, sub=1, sc=(1, 1, 1.45), jit=.12, rot=(0, 0, m.rnd.uniform(0, 3)))

@model('tree_dead', 'Сухое дерево', 'nature')
def m_dead(m):
    m.beam('bark_d', (0, 0, 0), (.1, -.08, 3.7), .21, seg=6, w2=.07)
    for a, b, w in (((.04, -.03, 1.5), (1.05, .3, 2.6), .085), ((.06, -.05, 2.1), (-.95, -.25, 3.15), .075), ((.08, -.06, 2.7), (.45, -.85, 3.85), .06),
                    ((.62, .17, 2.1), (.95, .8, 2.85), .04), ((-.52, -.14, 2.6), (-.7, .45, 3.45), .035), ((.1, -.08, 3.5), (-.25, .25, 4.35), .045)):
        m.beam('bark_d', a, b, w, seg=5, w2=w*.35)

@model('bush', 'Куст', 'nature')
def m_bush(m):
    leaf = m.pick('leaf1', 'leaf2', 'leaf3')
    for c, r in (((0, 0, .55), .75), ((.55, .2, .42), .55), ((-.5, -.15, .45), .6), ((.1, -.45, .38), .5)):
        m.ico(leaf, c, r, sub=1, sc=(1, 1, .75), jit=.15, rot=(0, 0, m.rnd.uniform(0, 3)))

def rock_mat(m):
    def f(face):
        n = face.normal
        if n.z > .55 and m.rnd.random() < .45: return 'moss'
        return 'rock1' if m.rnd.random() < .6 else 'rock2'
    return f

@model('rock', 'Камень', 'nature')
def m_rock(m):
    m.ico(rock_mat(m), (0, 0, .42), 1.0, sub=2, sc=(1.35, 1.0, .72), jit=.16)
    m.ico(rock_mat(m), (.95, .55, .22), .45, sub=1, sc=(1.2, 1, .8), jit=.2)

@model('boulder', 'Валун', 'nature')
def m_boulder(m):
    m.ico(rock_mat(m), (0, 0, .9), 1.35, sub=2, sc=(1.1, .95, .9), jit=.2)
    m.ico(rock_mat(m), (-.9, .9, .35), .6, sub=1, sc=(1.3, 1, .7), jit=.2)
    m.ico(rock_mat(m), (1.0, -.6, .25), .4, sub=1, jit=.2)

@model('stump', 'Пень', 'nature')
def m_stump(m):
    m.cyl('bark', (0, 0, .25), .34, .5, 7, .3); m.cyl('wood_l', (0, 0, .505), .29, .02, 7)
    for a in (0, 2.2, 4.1): m.beam('bark', (.2*math.cos(a), .2*math.sin(a), .14), (.6*math.cos(a), .6*math.sin(a), .02), .11, seg=5, w2=.04)

# =====================================================================================
# УЛИЦА, ФЕРМА, ВОЕННОЕ
# =====================================================================================
@model('street_lamp', 'Фонарь', 'prop')
def m_street_lamp(m):
    m.box('concrete_d', (0, 0, .15), (.42, .42, .3)); m.cyl('metal_d', (0, 0, 3.1), .1, 5.9, 8, .065)
    m.beam('metal_d', (0, 0, 5.8), (0, -.55, 6.12), .05, seg=6); m.beam('metal_d', (0, -.55, 6.12), (0, -1.35, 6.18), .045, seg=6)
    m.box('metal_d', (0, -1.55, 6.12), (.36, .66, .16), top=(.75, .85)); m.box('light', (0, -1.55, 6.035), (.26, .52, .02))

@model('power_pole', 'Столб ЛЭП', 'prop')
def m_power_pole(m):
    m.box('concrete', (0, .17, .9), (.18, .16, 1.8)); m.cyl('wood_d', (0, 0, 4.0), .15, 8.0, 8, .11)
    m.box('wood_d', (0, 0, 7.45), (2.5, .14, .14))
    for sx in (-1, 1):
        m.beam('wood_d', (0, 0, 6.75), (sx*.75, 0, 7.38), .045); m.cyl('white', (sx*1.05, 0, 7.66), .06, .26, 6, .04)
    m.cyl('white', (0, 0, 8.12), .06, .26, 6, .04)

@model('bench', 'Скамейка', 'prop')
def m_bench(m):
    for sx in (-1, 1):
        m.box('metal_d', (sx*.85, 0, .22), (.06, .46, .06)); m.box('metal_d', (sx*.85, -.18, .22), (.06, .06, .44)); m.box('metal_d', (sx*.85, .18, .22), (.06, .06, .44))
        m.box('metal_d', (sx*.85, .24, .66), (.06, .06, .5), rot=(-.22, 0, 0)); m.box('metal_d', (sx*.85, 0, .43), (.06, .5, .04))
    for y in (-.15, 0, .15): m.box('wood', (0, y, .47), (1.95, .12, .045))
    for z in (.62, .8): m.box('wood', (0, .27+(z-.62)*.2, z), (1.95, .1, .045), rot=(-.22, 0, 0))

@model('bus_stop', 'Остановка', 'prop')
def m_bus_stop(m):
    m.box('concrete_d', (0, 0, .06), (4.4, 1.9, .12))
    for x in (-1.95, 1.95):
        for y in (-.55, .65): m.box('metal_d', (x, y, 1.32), (.08, .08, 2.4))
    m.box('metal', (0, .05, 2.58), (4.3, 1.75, .1), rot=(-.06, 0, 0)); m.box('metal_d', (0, -.82, 2.5), (4.3, .06, .16))
    m.box('glass', (0, .65, 1.35), (3.82, .03, 1.9)); m.box('metal_d', (0, .65, .42), (3.9, .05, .06)); m.box('metal_d', (0, .65, 2.3), (3.9, .05, .06))
    for sx in (-1, 1): m.box('glass', (sx*1.95, .05, 1.35), (.03, 1.12, 1.9))
    m.box('wood', (0, .38, .47), (3.0, .38, .05))
    for x in (-1.2, 0, 1.2): m.box('metal_d', (x, .4, .24), (.05, .3, .44))
    m.box('metal_d', (2.25, -.75, 1.3), (.06, .06, 2.6)); m.box('signblue', (2.25, -.78, 2.45), (.04, .46, .46)); m.box('white', (2.225, -.78, 2.45), (.02, .2, .26))
    m.box('yellow', (-2.0, .67, 1.35), (.02, .02, .02))

@model('dumpster', 'Мусорный контейнер', 'prop', paint=(.2, .42, .28))
def m_dumpster(m):
    m.box('paint', (0, 0, .6), (1.6, .95, .9), top=(1.08, 1.12)); m.box('paint_d', (0, 0, 1.03), (1.78, 1.1, .07))
    m.box('paint_d', (0, .08, 1.1), (1.8, 1.16, .05), rot=(.14, 0, 0))
    for sx in (-1, 1):
        m.box('metal_d', (sx*.93, 0, .75), (.08, .3, .08))
        for sy in (-1, 1): m.cylx('black', (sx*.68, sy*.36, .08), .08, .06, 8)

@model('trash_bin', 'Урна', 'prop')
def m_trash_bin(m):
    m.cyl('concrete', (0, 0, .32), .24, .64, 8, .28); m.cyl('black', (0, 0, .645), .21, .02, 8); m.cyl('concrete_d', (0, 0, .05), .26, .1, 8)

@model('barrier', 'Бетонный блок', 'prop')
def m_barrier(m):
    m.prism('concrete', [(-.31, 0), (.31, 0), (.31, .08), (.13, .32), (.1, .82), (-.1, .82), (-.13, .32), (-.31, .08)], 2.0, 'Y')
    for y in (-.6, .6): m.box('metal_d', (0, y, .86), (.04, .12, .08))
    m.box('red', (0, -1.001, .45), (.24, .005, .2)); m.box('white', (0, -1.002, .45), (.1, .005, .2))

@model('sandbags', 'Мешки с песком', 'prop')
def m_sandbags(m):
    bag = m.pick('sand', 'sand', 'hay_d')
    for row, (n, z) in enumerate(((4, .1), (4, .29), (3, .48))):
        for i in range(n):
            x = (i-(n-1)/2)*.62+(.16 if row == 1 else 0)
            m.put(p_box(.6, .38, .2, bevel=.06), bag, TR((x, (row % 2)*.03, z), (0, 0, m.rnd.uniform(-.08, .08))))

@model('hedgehog', 'Противотанковый ёж', 'prop')
def m_hedgehog(m):
    q = Vector((1, 1, 1)).rotation_difference(Vector((0, 0, 1)))
    for ax in ((1, 0, 0), (0, 1, 0), (0, 0, 1)):
        v = q @ Vector(ax)*.95; c = Vector((0, 0, .62))
        m.beam('rust_d', c-v, c+v, .13, .05); m.beam('rust', c-v, c+v, .05, .13)

@model('barrel', 'Бочка', 'prop', paint=(.18, .33, .6))
def m_barrel(m):
    m.cyl('paint', (0, 0, .45), .3, .9, 12); m.cyl('paint_d', (0, 0, .905), .27, .02, 12); m.cyl('metal_d', (.14, 0, .92), .04, .03, 6)
    for z in (.22, .68): m.cyl('paint_d', (0, 0, z), .314, .05, 12)

@model('container', 'Морской контейнер', 'prop', paint=(.62, .25, .18))
def m_container(m):
    m.box('paint', (0, 0, 1.3), (2.34, 5.92, 2.44))
    for sx in (-1, 1):
        for i in range(10): m.box('paint_d', (sx*1.18, -2.6+i*.578, 1.3), (.04, .2, 2.28))
    for sx in (-1, 1):
        for sy in (-1, 1): m.box('paint_d', (sx*1.17, sy*2.98, 1.3), (.1, .1, 2.6))
        m.box('paint_d', (sx*1.17, 0, 2.55), (.1, 6.0, .1)); m.box('paint_d', (sx*1.17, 0, .06), (.1, 6.0, .12))
    for sy in (-1, 1): m.box('paint_d', (0, sy*2.98, 2.55), (2.44, .1, .1)); m.box('paint_d', (0, sy*2.98, .06), (2.44, .1, .12))
    m.box('black', (0, 2.965, 1.3), (.03, .02, 2.3))
    for x in (-.8, -.35, .35, .8): m.box('metal', (x, 2.99, 1.3), (.05, .05, 2.3))

@model('hay_bale', 'Рулон сена', 'prop')
def m_hay_bale(m):
    m.cylx('hay', (0, 0, .72), .72, 1.2, 12); m.cylx('hay_d', (0, 0, .72), .52, 1.22, 10); m.cylx('hay_d', (0, 0, .72), .22, 1.24, 8)
    for x in (-.3, .3): m.cylx('hay_d', (x, 0, .72), .726, .05, 12)

@model('fence', 'Забор', 'prop')
def m_fence(m):
    for sx in (-1, 1): m.box('wood_d', (sx*1.0, 0, .62), (.1, .1, 1.24))
    for z in (.35, .88): m.box('wood_d', (0, .07, z), (2.1, .04, .08))
    for i in range(9):
        x = -.88+i*.22
        m.prism(m.pick('wood', 'wood', 'wood_l'), [(-.075, .06), (.075, .06), (.075, 1.08+(i % 2)*.04), (0, 1.17+(i % 2)*.04), (-.075, 1.08+(i % 2)*.04)], .025, 'Y', c=(x, .105, 0))

@model('fuel_pump', 'Колонка АЗС', 'prop')
def m_fuel_pump(m):
    m.box('concrete', (0, 0, .1), (1.1, .7, .2)); m.box('white', (0, 0, .92), (.72, .44, 1.44)); m.box('red', (0, 0, 1.53), (.74, .46, .38))
    for sy in (-1, 1): m.box('screen', (0, sy*.225, 1.15), (.42, .02, .24)); m.box('amber', (0, sy*.232, 1.52), (.5, .02, .12))
    for sx in (-1, 1):
        m.box('black', (sx*.38, 0, 1.0), (.05, .14, .22)); m.beam('black', (sx*.38, .05, .9), (sx*.5, .12, .35), .025, seg=4); m.beam('black', (sx*.5, .12, .35), (sx*.4, .05, 1.2), .025, seg=4)

@model('road_sign', 'Знак «Главная дорога»', 'prop')
def m_road_sign(m):
    m.cyl('gray', (0, 0, 1.35), .035, 2.7, 6)
    m.box('white', (0, -.04, 2.35), (.62, .025, .62), rot=(0, math.pi/4, 0)); m.box('yellow', (0, -.055, 2.35), (.42, .01, .42), rot=(0, math.pi/4, 0))
    m.box('metal_d', (0, .01, 2.35), (.66, .02, .66), rot=(0, math.pi/4, 0))

@model('traffic_cone', 'Дорожный конус', 'prop')
def m_traffic_cone(m):
    m.box('black', (0, 0, .02), (.42, .42, .04)); m.cone('orange', (0, 0, .39), .17, .72, 10); m.cyl('white', (0, 0, .42), .105, .1, 10, .085)

@model('water_tower', 'Водонапорная башня', 'prop')
def m_water_tower(m):
    for sx in (-1, 1):
        for sy in (-1, 1): m.beam('metal_d', (sx*1.9, sy*1.9, 0), (sx*1.25, sy*1.25, 10.2), .09, seg=6, w2=.07)
    for z0, z1 in ((.4, 3.6), (3.6, 6.8), (6.8, 10.0)):
        t0 = 1.9-(1.9-1.25)*z0/10.2; t1 = 1.9-(1.9-1.25)*z1/10.2
        for s in (-1, 1):
            m.beam('metal_d', (-t0, s*t0, z0), (t1, s*t1, z1), .035, seg=4); m.beam('metal_d', (s*t0, -t0, z0), (s*t1, t1, z1), .035, seg=4)
    m.cyl('metal_d', (0, 0, 10.2), 2.7, .12, 12); m.cyl('metal', (0, 0, 11.8), 2.35, 3.1, 14); m.cyl('metal_d', (0, 0, 10.6), 2.38, .12, 14)
    m.cone('metal_d', (0, 0, 14.0), 2.5, 1.3, 14); m.cyl('metal_d', (0, 0, 14.7), .12, .3, 6)
    for z in range(1, 10): m.box('metal_d', (1.62-z*.063, -1.62+z*.063, z), (.5, .05, .05), rot=(0, 0, math.pi/4))

@model('radio_mast', 'Вышка связи', 'prop')
def m_radio_mast(m):
    H = 24.0; legs = [2*math.pi*k/3+math.pi/6 for k in range(3)]; R = lambda z: 1.6-1.1*z/H
    P = lambda k, z: (R(z)*math.cos(legs[k]), R(z)*math.sin(legs[k]), z)
    for k in range(3): m.beam('red' if False else 'metal_d', P(k, 0), P(k, H), .07, seg=5, w2=.045)
    for i in range(8):
        z0, z1 = H*i/8, H*(i+1)/8
        for k in range(3):
            j = (k+1) % 3; col = 'red' if i % 2 else 'white'
            m.beam(col, P(k, z0), P(j, z1), .03, seg=4); m.beam('metal_d', P(k, z1), P(j, z1), .03, seg=4)
    m.cyl('metal_d', (0, 0, H+.05), .75, .1, 6)
    for k in range(3): x, y, _ = P(k, H); m.box('white', (x*.9, y*.9, H+.9), (.3, .1, 1.5), rot=(0, 0, legs[k]))
    m.cyl('metal_d', (0, 0, H+2.0), .04, 4.0, 5); m.box('red', (0, 0, H+4.0), (.12, .12, .12))

@model('log_pile', 'Штабель брёвен', 'prop')
def m_log_pile(m):
    for row, n in enumerate((4, 3, 2)):
        for i in range(n):
            x = (i-(n-1)/2)*.32; z = .16+row*.28
            m.cyly('bark', (x, 0, z), .16, 3.0, 7); m.cyly('wood_l', (x, 0, z), .12, 3.02, 7)

@model('crate', 'Деревянный ящик', 'prop')
def m_crate(m):
    m.box('wood_l', (0, 0, .5), (.96, .96, .96))
    for sx in (-1, 1):
        for sy in (-1, 1): m.box('wood_d', (sx*.47, sy*.47, .5), (.1, .1, 1.0))
        for z in (.05, .95): m.box('wood_d', (sx*.47, 0, z), (.1, .9, .1)); m.box('wood_d', (0, sx*.47, z), (.9, .1, .1))
    for sy in (-1, 1): m.box('wood_d', (0, sy*.485, .5), (.1, .03, 1.2), rot=(0, math.pi/4, 0))
    for sx in (-1, 1): m.box('wood_d', (sx*.485, 0, .5), (.03, .1, 1.2), rot=(math.pi/4, 0, 0))

@model('well', 'Колодец', 'prop')
def m_well(m):
    for layer in range(5):
        z = .09+layer*.17
        if layer % 2 == 0:
            for sy in (-1, 1): m.cylx('bark', (0, sy*.55, z), .09, 1.34, 6)
        else:
            for sx in (-1, 1): m.cyly('bark', (sx*.55, 0, z), .09, 1.34, 6)
    m.box('black', (0, 0, .78), (.96, .96, .02))
    for sx in (-1, 1): m.box('wood_d', (sx*.62, 0, 1.15), (.1, .1, 2.1))
    for sy in (-1, 1): m.box('wood', (0, sy*.34, 2.27), (1.55, .9, .05), rot=(-sy*.72, 0, 0))
    m.box('wood_d', (0, 0, 2.2), (1.3, .08, .08)); m.box('wood_d', (0, 0, 2.58), (1.6, .08, .08)); m.cylx('wood_d', (0, 0, 1.4), .08, 1.2, 6)
    m.box('wood_d', (.72, 0, 1.25), (.04, .04, .3)); m.box('wood_d', (.78, 0, 1.1), (.12, .04, .04))
    m.beam('black', (0, 0, 1.33), (0, 0, 1.0), .01, seg=4); m.cyl('metal', (0, 0, .9), .12, .2, 8, .15)

@model('tire_stack', 'Покрышки', 'prop')
def m_tire_stack(m):
    for i in range(4):
        z = .11+i*.22; ox = m.rnd.uniform(-.05, .05)
        m.cyl('tire', (ox, 0, z), .34, .21, 10); m.cyl('black', (ox, 0, z), .2, .215, 10)

@model('billboard', 'Рекламный щит', 'prop')
def m_billboard(m):
    for sx in (-1, 1): m.box('metal_d', (sx*1.6, .1, 2.5), (.18, .18, 5.0))
    m.box('metal_d', (0, .12, 4.9), (6.2, .1, 3.2)); m.box('white', (0, .05, 4.9), (6.0, .04, 3.0))
    m.box('red', (-.9, .02, 5.35), (3.8, .02, 1.2)); m.box('yellow', (1.6, .02, 4.3), (2.4, .02, 1.3)); m.box('blue', (-1.9, .02, 4.2), (1.6, .02, .9))
    m.box('metal_d', (0, -.3, 3.3), (6.0, .6, .06)); m.box('metal_d', (0, -.6, 3.55), (6.0, .03, .5))

@model('kiosk', 'Ларёк', 'prop', paint=(.2, .45, .55))
def m_kiosk(m):
    m.box('concrete_d', (0, 0, .08), (3.2, 2.2, .16)); m.box('paint', (0, 0, 1.36), (3.0, 2.0, 2.4))
    m.box('glass', (0, -1.005, 1.55), (2.5, .02, 1.1)); m.box('white', (0, -1.01, 2.35), (2.8, .02, .36)); m.box('red', (0, -1.015, 2.35), (1.6, .02, .2))
    m.box('black', (1.505, .3, 1.1), (.02, .8, 1.9)); m.box('paint_d', (0, 0, 2.62), (3.2, 2.2, .12))
    m.box('orange', (0, -1.35, 2.3), (3.1, .9, .06), rot=(-.35, 0, 0)); m.box('paint_d', (0, -1.06, .9), (2.6, .12, .06))

# =====================================================================================
# МЕБЕЛЬ (перед смотрит в -Y, спинка у стены — в +Y)
# =====================================================================================
@model('table', 'Обеденный стол', 'furniture')
def m_table(m):
    m.box('wood', (0, 0, .735), (1.4, .8, .05))
    for sx in (-1, 1):
        for sy in (-1, 1): m.box('wood_d', (sx*.63, sy*.33, .36), (.06, .06, .71))
        m.box('wood_d', (0, sx*.36, .66), (1.2, .03, .1)); m.box('wood_d', (sx*.66, 0, .66), (.03, .6, .1))

@model('chair', 'Стул', 'furniture')
def m_chair(m):
    m.box('wood', (0, 0, .45), (.44, .44, .04))
    for sx in (-1, 1):
        m.box('wood_d', (sx*.19, -.19, .215), (.04, .04, .43)); m.box('wood_d', (sx*.19, .19, .47), (.04, .04, .94))
    for z in (.66, .84): m.box('wood', (0, .19, z), (.36, .025, .08))

def seat_block(m, w, arms=True):
    m.box('paint_d', (0, 0, .24), (w, .9, .3), bevel=.03); m.box('paint_d', (0, .39, .62), (w, .14, .72), bevel=.03)
    n = max(1, round((w-.3)/.62)); cw = (w-(.3 if arms else .06))/n
    for i in range(n):
        x = -((n-1)/2-i)*cw
        m.box('paint', (x, -.06, .47), (cw-.03, .72, .16), bevel=.04); m.box('paint', (x, .27, .74), (cw-.04, .2, .44), rot=(-.14, 0, 0), bevel=.05)
    if arms:
        for sx in (-1, 1): m.box('paint_d', (sx*(w/2-.08), 0, .5), (.16, .9, .38), bevel=.04)
    for sx in (-1, 1):
        for sy in (-1, 1): m.box('wood_d', (sx*(w/2-.08), sy*.36, .045), (.06, .06, .09))

@model('sofa', 'Диван', 'furniture', paint=(.36, .43, .56))
def m_sofa(m): seat_block(m, 2.0)

@model('armchair', 'Кресло', 'furniture', paint=(.52, .36, .22))
def m_armchair(m): seat_block(m, .95)

@model('bed', 'Кровать', 'furniture', paint=(.55, .18, .2))
def m_bed(m):
    m.box('wood', (0, 0, .2), (1.64, 2.1, .24)); m.box('white', (0, -.02, .41), (1.54, 1.98, .2), bevel=.04)
    m.box('paint', (0, -.32, .525), (1.6, 1.38, .06), bevel=.02); m.box('paint_d', (0, .38, .525), (1.6, .1, .07), bevel=.02)
    for sx in (-1, 1): m.box('cream', (sx*.38, .74, .57), (.6, .36, .14), bevel=.05)
    m.box('wood_d', (0, 1.07, .55), (1.72, .07, .95)); m.box('wood_d', (0, -1.07, .33), (1.72, .06, .5))
    for sx in (-1, 1):
        for sy in (-1, 1): m.box('wood_d', (sx*.8, sy*1.0, .05), (.07, .07, .1))

@model('wardrobe', 'Шкаф', 'furniture')
def m_wardrobe(m):
    m.box('wood', (0, 0, 1.08), (1.2, .6, 2.0)); m.box('wood_d', (0, 0, .04), (1.16, .56, .08)); m.box('wood_d', (0, 0, 2.105), (1.26, .64, .05))
    for sx in (-1, 1):
        m.box('wood_l', (sx*.296, -.305, 1.1), (.57, .012, 1.88)); m.box('chrome', (sx*.05, -.322, 1.12), (.02, .02, .2))

@model('bookshelf', 'Книжный стеллаж', 'furniture')
def m_bookshelf(m):
    for sx in (-1, 1): m.box('wood_d', (sx*.44, 0, .95), (.03, .32, 1.9))
    m.box('wood_d', (0, .15, .95), (.86, .02, 1.9))
    for z in (.02, .47, .93, 1.39, 1.87): m.box('wood_d', (0, 0, z), (.86, .32, .03))
    cols = ('red', 'blue', 'green', 'yellow', 'cream', 'orange', 'wood_l', 'dgray', 'paint_d')
    for z0 in (.035, .485, .945, 1.405):
        x = -.41
        while x < .36:
            w = m.rnd.uniform(.05, .1); h = m.rnd.uniform(.24, .38)
            if m.rnd.random() < .12: x += w; continue
            if x+w > .415: break
            m.box(m.rnd.choice(cols), (x+w/2, -.01, z0+h/2), (w-.005, m.rnd.uniform(.2, .26), h)); x += w

@model('kitchen', 'Кухонный гарнитур', 'furniture')
def m_kitchen(m):
    m.box('white', (0, 0, .46), (2.4, .58, .8)); m.box('dgray', (0, .02, .04), (2.36, .5, .08)); m.box('lgray', (0, -.01, .885), (2.44, .62, .05))
    for i, x in enumerate((-.9, -.3, .3, .9)):
        m.box('cream' if i != 2 else 'black', (x, -.296, .47), (.56, .012, .7)); m.box('chrome', (x, -.31, .75), (.18, .02, .02))
    m.box('black', (.3, -.01, .912), (.58, .55, .004))
    for dx in (-.14, .14):
        for dy in (-.13, .12): m.cyl('dgray', (.3+dx, -.01+dy, .918), .08, .012, 10)
    m.box('metal', (-.6, -.01, .911), (.52, .42, .006)); m.box('metal_d', (-.6, -.01, .914), (.44, .34, .004))
    m.beam('chrome', (-.6, .19, .91), (-.6, .19, 1.15), .014, seg=6); m.beam('chrome', (-.6, .19, 1.15), (-.6, .05, 1.15), .014, seg=6)
    m.box('white', (0, .12, 1.78), (2.4, .34, .7))
    for x in (-.9, -.3, .9): m.box('cream', (x, -.055, 1.78), (.56, .012, .64))
    m.box('metal', (.3, .08, 1.52), (.6, .44, .16), top=(.6, .6))

@model('fridge', 'Холодильник', 'furniture')
def m_fridge(m):
    m.box('white', (0, 0, .86), (.6, .62, 1.66), bevel=.04); m.box('lgray', (0, -.312, 1.18), (.56, .012, .012))
    m.box('chrome', (.22, -.33, 1.38), (.03, .03, .24)); m.box('chrome', (.22, -.33, .95), (.03, .03, .3)); m.box('dgray', (0, -.3, .07), (.5, .02, .08))

@model('tv_stand', 'Тумба с телевизором', 'furniture')
def m_tv_stand(m):
    m.box('wood_d', (0, 0, .26), (1.4, .46, .5)); m.box('wood', (-.35, -.235, .3), (.62, .012, .34)); m.box('wood', (.35, -.235, .3), (.62, .012, .34))
    for x in (-.35, .35): m.box('chrome', (x, -.25, .36), (.12, .02, .02))
    m.box('dgray', (0, .03, .8), (.68, .52, .56), top=(.8, .7)); m.box('black', (0, -.235, .8), (.56, .02, .44)); m.box('screen', (-.04, -.248, .8), (.44, .01, .34))
    m.box('gray', (.23, -.25, .75), (.05, .01, .2))
    for sx in (-1, 1): m.beam('black', (0, .05, 1.08), (sx*.28, .12, 1.5), .008, seg=4)

@model('desk', 'Письменный стол с компьютером', 'furniture')
def m_desk(m):
    m.box('wood_l', (0, 0, .74), (1.3, .66, .04)); m.box('wood', (-.44, 0, .36), (.4, .62, .72)); m.box('wood', (.62, 0, .36), (.04, .62, .72))
    m.box('wood', (.1, .3, .45), (1.0, .02, .5))
    for z in (.2, .44, .64): m.box('wood_l', (-.44, -.315, z), (.36, .012, .18)); m.box('chrome', (-.44, -.33, z), (.1, .02, .02))
    m.box('black', (0, .14, 1.0), (.56, .04, .35)); m.box('screen', (0, .118, 1.0), (.5, .01, .29)); m.box('black', (0, .17, .82), (.05, .05, .14)); m.box('black', (0, .17, .765), (.22, .16, .01))
    m.box('dgray', (0, -.14, .77), (.44, .15, .02)); m.box('dgray', (.3, -.12, .765), (.06, .1, .03))
    m.box('lgray', (.4, .02, .23), (.19, .44, .44)); m.box('black', (.4, -.205, .3), (.14, .01, .1))

@model('shop_shelf', 'Стеллаж магазина', 'furniture')
def m_shop_shelf(m):
    m.box('metal', (0, 0, .08), (2.0, .9, .16)); m.box('lgray', (0, 0, .92), (2.0, .04, 1.62))
    cols = ('red', 'blue', 'yellow', 'green', 'orange', 'white', 'cream')
    for z in (.16, .56, .96, 1.36):
        for sy in (-1, 1):
            if z > .2: m.box('metal', (0, sy*.22, z), (2.0, .4, .02))
            for i in range(4): m.box(m.rnd.choice(cols), (-.72+i*.48, sy*.24, z+.13), (.42, .3, m.rnd.uniform(.18, .26)))

@model('counter', 'Касса', 'furniture', paint=(.3, .42, .5))
def m_counter(m):
    m.box('paint', (0, 0, .47), (1.8, .6, .94)); m.box('lgray', (0, 0, .96), (1.86, .66, .04)); m.box('paint_d', (0, -.305, .1), (1.8, .012, .2))
    m.box('dgray', (.5, .05, 1.04), (.36, .3, .12)); m.box('black', (.5, -.03, 1.18), (.24, .04, .16), rot=(.35, 0, 0)); m.box('screen', (.5, -.052, 1.18), (.2, .005, .12), rot=(.35, 0, 0))
    m.box('black', (-.3, 0, .99), (.9, .5, .02))

@model('pew', 'Церковная скамья', 'furniture')
def m_pew(m):
    m.box('wood', (0, 0, .45), (3.0, .44, .05)); m.box('wood', (0, .2, .77), (3.0, .05, .6), rot=(-.12, 0, 0)); m.box('wood_d', (0, -.1, .3), (2.9, .04, .2))
    for sx in (-1, 1): m.prism('wood_d', [(-.26, 0), (.26, 0), (.3, 1.0), (.1, 1.06), (-.2, .56), (-.26, .5)], .06, 'X', c=(sx*1.52, 0, 0))
    m.box('wood_d', (0, -.5, .14), (2.9, .16, .06))
    for sx in (-1, 1): m.box('wood_d', (sx*1.4, -.42, .08), (.04, .2, .16))

@model('carpet', 'Ковёр', 'furniture', paint=(.5, .12, .12))
def m_carpet(m):
    m.box('paint', (0, 0, .006), (2.0, 3.0, .012)); m.box('cream', (0, 0, .013), (1.7, 2.7, .004)); m.box('paint_d', (0, 0, .016), (1.5, 2.5, .004))
    m.box('blue', (0, 0, .019), (.7, 1.1, .004), rot=(0, 0, 0)); m.box('cream', (0, 0, .022), (.36, .6, .004), rot=(0, 0, .0))
    for sy in (-1, 1): m.box('yellow', (0, sy*.95, .019), (.5, .24, .004)); m.box('yellow', (sy*.5, 0, .019), (.14, .6, .004))

@model('floor_lamp', 'Торшер', 'furniture')
def m_floor_lamp(m):
    m.cyl('dgray', (0, 0, .02), .18, .04, 10); m.cyl('metal_d', (0, 0, .8), .015, 1.56, 6); m.cyl('cream', (0, 0, 1.62), .24, .3, 10, .15); m.cyl('light', (0, 0, 1.47), .2, .01, 10)

# =====================================================================================
# сцена, рендер, экспорт
# =====================================================================================
def get_mat(k, modelkey, paint):
    name = k if k not in PAINT_KEYS else f'{k}.{modelkey}'
    mat = bpy.data.materials.get(name)
    if mat: return mat
    col = PAL[k]
    if k in PAINT_KEYS and paint: col = paint if k == 'paint' else tuple(c*.78 for c in paint)
    mat = bpy.data.materials.new(name); lin = [srgb2lin(c) for c in col]+[1]
    b = mat.node_tree.nodes.get('Principled BSDF'); r, mt, em = SPEC.get(k, (.78, 0, 0))
    b.inputs['Base Color'].default_value = lin; b.inputs['Roughness'].default_value = r; b.inputs['Metallic'].default_value = mt
    if em: b.inputs['Emission Color'].default_value = lin; b.inputs['Emission Strength'].default_value = em
    mat.diffuse_color = lin; mat['srgb'] = list(col); mat['key'] = k
    return mat

def build(spec, coll):
    m = Mb(spec['key'], spec['paint']); spec['fn'](m)
    me = bpy.data.meshes.new(spec['key']); m.bm.normal_update(); m.bm.to_mesh(me); m.bm.free()
    for k in m.keys: me.materials.append(get_mat(k, spec['key'], spec['paint']))
    for p in me.polygons: p.use_smooth = False
    ob = bpy.data.objects.new(spec['key'], me); coll.objects.link(ob)
    ob['ru'] = spec['ru']; ob['cat'] = spec['cat']
    return ob

def setup_scene(samples=20):
    sc = bpy.context.scene
    for o in list(bpy.data.objects): bpy.data.objects.remove(o)
    sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'; sc.cycles.samples = samples; sc.cycles.use_denoising = True
    try: sc.cycles.denoiser = 'OPENIMAGEDENOISE'
    except Exception: pass
    sc.cycles.max_bounces = 4; sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = 'JPEG'; sc.render.image_settings.quality = 90
    try: sc.view_settings.look = 'AgX - Medium High Contrast'
    except Exception: pass
    w = bpy.data.worlds.new('World'); sc.world = w; bg = w.node_tree.nodes['Background']; bg.inputs[0].default_value = (.58, .66, .76, 1); bg.inputs[1].default_value = 1.0
    ld = bpy.data.lights.new('Sun', 'SUN'); ld.energy = 3.4; ld.angle = math.radians(5); so = bpy.data.objects.new('Sun', ld); sc.collection.objects.link(so)
    so.rotation_euler = (math.radians(42), 0, math.radians(215))
    gm = bpy.data.meshes.new('Ground'); bm = bmesh.new(); bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=300); bm.to_mesh(gm); bm.free()
    g = bpy.data.objects.new('Ground', gm); sc.collection.objects.link(g)
    gmat = bpy.data.materials.new('ground'); gb = gmat.node_tree.nodes['Principled BSDF']; gb.inputs['Base Color'].default_value = (.56, .56, .54, 1); gb.inputs['Roughness'].default_value = .95; gm.materials.append(gmat)
    cd = bpy.data.cameras.new('Cam'); cd.lens = 55; co = bpy.data.objects.new('Cam', cd); sc.collection.objects.link(co); sc.camera = co
    coll = bpy.data.collections.new('Models'); sc.collection.children.link(coll)
    return coll

def frame(obs, direction=(1.0, -1.35, .8), res=(960, 680), margin=1.1):
    sc = bpy.context.scene; sc.render.resolution_x, sc.render.resolution_y = res; cam = sc.camera
    pts = [ob.matrix_world @ Vector(c) for ob in obs for c in ob.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts))); hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    c = (lo+hi)/2; d = Vector(direction).normalized(); fw = -d; R = fw.cross(Vector((0, 0, 1))).normalized(); U = R.cross(fw)
    sw = 36.0; hf = math.atan(sw/2/cam.data.lens); vf = math.atan(math.tan(hf)*res[1]/res[0])
    cam.data.sensor_fit = 'HORIZONTAL'; cam.data.sensor_width = sw
    dist = 0
    for p in pts:
        q = p-c; x, y, off = q.dot(R), q.dot(U), q.dot(d)
        dist = max(dist, abs(x)*margin/math.tan(hf)+off, abs(y)*margin/math.tan(vf)+off)
    cam.location = c+d*dist; cam.rotation_euler = (-d).to_track_quat('-Z', 'Y').to_euler()
    cam.data.clip_end = dist*4+50

def render(path):
    bpy.context.scene.render.filepath = path; bpy.ops.render.render(write_still=True)

def export_game(obs, path):
    out = {'pal': {}, 'models': {}}
    for ob in obs:
        me = ob.data; me.calc_loop_triangles(); keys = [mt['key'] for mt in me.materials]
        vmap = {}; V = []; I = []; C = []
        for tri in me.loop_triangles:
            if tri.area < 1e-6: continue
            idx = []
            for vi in tri.vertices:
                co = me.vertices[vi].co; q = (round(co.x*1000), round(co.z*1000), round(-co.y*1000))
                if q not in vmap: vmap[q] = len(V); V.append(q)
                idx.append(vmap[q])
            if len(set(idx)) < 3: continue
            I += idx; C.append(tri.material_index)
        for k in keys: out['pal'][k] = [round(c, 3) for c in PAL[k]]
        xs = [v[0] for v in V]; ys = [v[1] for v in V]; zs = [v[2] for v in V]
        out['models'][ob.name] = {'ru': ob['ru'], 'cat': ob['cat'], 'keys': keys, 'v': [c for v in V for c in v], 'i': I, 'c': C,
                                  'bb': [min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)], 'tris': len(C)}
    with open(path, 'w') as f: json.dump(out, f, separators=(',', ':'))
    return out

def parse_args():
    argv = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
    opt = {}; i = 0
    while i < len(argv):
        if argv[i].startswith('--'):
            k = argv[i][2:]
            if i+1 < len(argv) and not argv[i+1].startswith('--'): opt[k] = argv[i+1]; i += 2
            else: opt[k] = True; i += 1
        else: i += 1
    return opt

VIEW = {'vehicle': (1.0, -1.35, .72), 'nature': (1.0, -1.3, .5), 'furniture': (1.0, -1.25, 1.05), 'prop': (1.0, -1.3, .7)}
RES = (820, 580)

def main():
    opt = parse_args(); specs = REG
    if 'only' in opt: want = opt['only'].split(','); specs = [s for s in REG if s['key'] in want]
    if 'cat' in opt: specs = [s for s in specs if s['cat'] in opt['cat'].split(',')]
    coll = setup_scene(int(opt.get('samples', 20)))
    obs = [build(s, coll) for s in specs]
    for ob in obs:
        me = ob.data; me.calc_loop_triangles()
        print(f'MODEL {ob.name:16s} tris={len(me.loop_triangles):5d} mats={len(me.materials):2d} dims={tuple(round(v, 2) for v in ob.dimensions)}')
    if 'render' in opt:
        os.makedirs(opt['render'], exist_ok=True)
        for ob in obs:
            for o in obs: o.hide_render = o is not ob
            frame([ob], direction=VIEW.get(ob['cat'], (1.0, -1.3, .8)), res=RES)
            render(os.path.join(opt['render'], ob.name+'.jpg')); print('RENDERED', ob.name)
        for o in obs: o.hide_render = False
    if 'lineup' in opt:
        x = 0
        for ob in obs: w = ob.dimensions.x; ob.location.x = x+w/2; x += w+1.2
        frame(obs, direction=(.55, -1.5, .62), res=(1600, 720), margin=1.04); render(os.path.join(opt['lineup'], opt.get('name', 'lineup')+'.jpg'))
        for ob in obs: ob.location.x = 0
    if 'export' in opt:
        os.makedirs(opt['export'], exist_ok=True); export_game(obs, os.path.join(opt['export'], 'fracture_models.json'))
        x = 0
        for ob in obs: ob.location = (x, 0, 0); x += ob.dimensions.x+1.5
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(os.path.join(opt['export'], 'fracture_models.blend')), compress=True)
        bpy.ops.export_scene.gltf(filepath=os.path.abspath(os.path.join(opt['export'], 'fracture_models.glb')), export_format='GLB')

main()
