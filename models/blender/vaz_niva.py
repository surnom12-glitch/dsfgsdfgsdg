# ВАЗ-21214 «LADA 4x4» (Нива), 3 двери — детальная модель по реальным размерам и чертежу.
# Запуск: blender -b --factory-startup --python models/blender/vaz_niva.py -- [--stage body|full]
#         [--render DIR] [--match PHOTO] [--export DIR] [--samples N]
# Оси: X — левый борт машины, -Y — вперёд, Z — вверх; начало координат на земле посередине базы.
import bpy, bmesh, math, os, sys, json
from mathutils import Vector, Matrix, Euler

# ---------------- размеры, м (3740 × 1680 × 1640, база 2200, колея 1430/1400) ----------------
FRONT_AXLE, REAR_AXLE = -1.165, 1.035          # свесы 705 / 835
TRACK_F, TRACK_R = .715, .700
TIRE_R, TIRE_W, RIM_R = .342, .185, .203       # 185/75 R16
AXLE_Z = .33
HW = .84
Y_FRONT, Y_REAR = -1.73, 1.80                  # плоскости кузова; бамперы выходят до ±1.87
ARCH_R, ARCH_ZC = .405, .35
BELT = 1.093

def lerp(a, b, t): return a+(b-a)*t
def interp(pts, x):
    if x <= pts[0][0]: return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if x <= x1: return y0+(y1-y0)*(x-x0)/(x1-x0) if x1 > x0 else y1
    return pts[-1][1]

# Профиль сбоку по центру (из чертежа): капот → лобовое → крыша → скругление → стекло двери багажника.
TOP = [(-1.73, .930), (-1.724, .946), (-1.715, .958), (-1.703, .968), (-1.688, .977), (-1.665, .986), (-1.64, .992), (-1.60, .998),
       (-1.50, 1.012), (-1.40, 1.027), (-1.30, 1.037), (-1.20, 1.046), (-1.10, 1.054), (-1.00, 1.061), (-.90, 1.067), (-.80, 1.072), (-.74, 1.076), (-.70, 1.080),
       (-.675, 1.093), (-.64, 1.110), (-.60, 1.138), (-.56, 1.180), (-.52, 1.228), (-.48, 1.279), (-.44, 1.327), (-.40, 1.372), (-.36, 1.415), (-.32, 1.451),
       (-.28, 1.487), (-.24, 1.524), (-.20, 1.564), (-.17, 1.587), (-.14, 1.601), (-.10, 1.614), (-.05, 1.625), (.02, 1.634), (.12, 1.641), (.22, 1.647),
       (.60, 1.647), (.90, 1.638), (1.15, 1.626), (1.35, 1.617), (1.44, 1.598), (1.54, 1.572), (1.62, 1.542), (1.68, 1.515), (1.72, 1.490),
       (1.745, 1.458), (1.76, 1.40), (1.772, 1.30), (1.783, 1.20), (1.792, 1.11), (1.80, 1.09)]
BOT = [(-1.73, .44), (-1.62, .44), (-1.50, .40), (-1.30, .37), (1.30, .37), (1.50, .40), (1.62, .44), (1.80, .44)]
# Правая половина сечения (x, z, от_низа): днище, порог, борт, ребро, плечо, подоконная линия, боковина салона, водосток, крыша.
PROF = [(0., 0, 1), (.40, 0, 1), (.76, 0, 1), (.805, .012, 1), (.832, .045, 1), (.840, .11, 1),
        (.8415, .60, 0), (.842, .75, 0), (.843, .876, 0), (.8465, .894, 0), (.8485, .906, 0), (.8455, .922, 0),
        (.839, .96, 0), (.830, 1.015, 0), (.821, 1.055, 0), (.810, 1.079, 0), (.795, 1.092, 0),
        (.788, 1.100, 0), (.772, 1.22, 0), (.758, 1.34, 0), (.746, 1.45, 0),
        (.738, 1.515, 0), (.733, 1.545, 0), (.722, 1.570, 0), (.700, 1.590, 0),
        (.62, 1.607, 0), (.48, 1.625, 0), (.32, 1.638, 0), (.16, 1.645, 0), (0., 1.647, 0)]
SIDE_Z = [(z, x) for x, z, rel in PROF[6:25]]      # x боковины по высоте (без масштаба крыши)

def roof_c(y): return 1.647 if y < .22 else interp(TOP, y)
def zscale(y, z):
    if z <= BELT: return z
    return BELT+(z-BELT)*(roof_c(y)-BELT)/(1.647-BELT)
def plan_scale(y):
    RCf, RCr = .09, .10
    if y < Y_FRONT+RCf: d = Y_FRONT+RCf-y; return (HW-RCf+math.sqrt(max(0, RCf*RCf-d*d)))/HW
    taper = 1-.045*max(0., (y-1.0)/.8)                      # корма чуть уже середины кузова
    if y > Y_REAR-RCr: d = y-(Y_REAR-RCr); return taper*(HW-RCr+math.sqrt(max(0, RCr*RCr-d*d)))/HW
    return taper
def xscale(y, z):
    """Масштаб по x: скругление углов в плане; у задних стоек салона радиус больше, чем у низа кузова."""
    s = plan_scale(y); RG = .24
    if z > BELT and y > Y_REAR-RG:
        d = y-(Y_REAR-RG); sg = (1-.045*max(0., (y-1.0)/.8))*(HW-RG+math.sqrt(max(0, RG*RG-d*d)))/HW
        s = lerp(s, min(s, sg), min(1., (z-BELT)/.15))
    return s
WS_BOW, REAR_BOW = .045, .03
def top_z(y, x):
    u = min(1., (x/.74)**2)
    if y < -.70: return interp(TOP, y)
    if y < .22: return interp(TOP, y-WS_BOW*u)
    if y < 1.30: return 9.
    return interp(TOP, y+REAR_BOW*u)
def ws_y(z, x=0.):
    """Y лобового стекла на высоте z (обратная функция профиля) с учётом изгиба по x."""
    seg = [p for p in TOP if -.70 <= p[0] <= .22]
    return interp([(b, a) for a, b in seg], z)+WS_BOW*min(1., (x/.74)**2)

STATIONS = ([-1.73, -1.725, -1.718, -1.708, -1.695, -1.68, -1.662, -1.64, -1.61, -1.58, -1.50, -1.40, -1.30, -1.20, -1.10, -1.00, -.90, -.80, -.74, -.71,
             -.69, -.67, -.65, -.625, -.60, -.57, -.54, -.51, -.48, -.45, -.42, -.39, -.36, -.33, -.30, -.27, -.24, -.21, -.185, -.16, -.135, -.10, -.05,
             .03, .15, .30, .50, .70, .90, 1.10, 1.25, 1.35, 1.42, 1.48, 1.54, 1.59, 1.635, 1.67, 1.70, 1.72, 1.735, 1.748, 1.76, 1.77, 1.78, 1.788, 1.795, 1.80])

def station(y):
    zb = interp(BOT, y); pts = []
    for x, z, rel in PROF:
        zz = zb+z if rel else zscale(y, z)
        zz = min(zz, top_z(y, x))
        pts.append((x*xscale(y, zz), zz))
    return pts

def side_x(y, z):
    """x правого борта на станции y и высоте z (для деталей, стёкол и швов)."""
    zu = z if z <= BELT else BELT+(z-BELT)*(1.647-BELT)/(roof_c(y)-BELT)
    return interp(SIDE_Z, zu)*xscale(y, z)

# ---------------- материалы ----------------
def srgb2lin(c): return c/12.92 if c <= .04045 else ((c+.055)/1.055)**2.4
MATS = {}
def glass_mat(name, tint, refl=1.):
    """Автомобильное стекло для Cycles: прозрачность + отражение по Френелю (свет проходит в салон)."""
    if name in MATS: return MATS[name]
    m = bpy.data.materials.new(name); nt = m.node_tree; nt.nodes.remove(nt.nodes['Principled BSDF']); out = nt.nodes['Material Output']
    tr = nt.nodes.new('ShaderNodeBsdfTransparent'); tr.inputs[0].default_value = [srgb2lin(c) for c in tint]+[1]
    gl = nt.nodes.new('ShaderNodeBsdfGlossy'); gl.inputs['Roughness'].default_value = .015
    fr = nt.nodes.new('ShaderNodeLayerWeight'); fr.inputs['Blend'].default_value = .12
    mul = nt.nodes.new('ShaderNodeMath'); mul.operation = 'MULTIPLY'; mul.inputs[1].default_value = refl
    mix = nt.nodes.new('ShaderNodeMixShader')
    nt.links.new(fr.outputs['Fresnel'], mul.inputs[0]); nt.links.new(mul.outputs[0], mix.inputs[0]); nt.links.new(tr.outputs[0], mix.inputs[1]); nt.links.new(gl.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs['Surface'])
    for attr, val in (('surface_render_method', 'BLENDED'), ('blend_method', 'BLEND')):
        try: setattr(m, attr, val); break
        except Exception: pass
    m.diffuse_color = [srgb2lin(c) for c in tint]+[.3]; m['srgb'] = list(tint); MATS[name] = m
    return m
def mat(name, col, rough=.5, metal=0., coat=0., trans=0., emit=0., ior=1.45, alpha=1., backface=None):
    if name in MATS: return MATS[name]
    m = bpy.data.materials.new(name); nt = m.node_tree; b = nt.nodes['Principled BSDF']
    lin = [srgb2lin(c) for c in col]+[1]
    b.inputs['Base Color'].default_value = lin; b.inputs['Roughness'].default_value = rough; b.inputs['Metallic'].default_value = metal
    b.inputs['IOR'].default_value = ior
    if coat: b.inputs['Coat Weight'].default_value = coat; b.inputs['Coat Roughness'].default_value = .03
    if trans:
        b.inputs['Transmission Weight'].default_value = trans
        if 'Thin Wall' in b.inputs: b.inputs['Thin Wall'].default_value = True
    if emit: b.inputs['Emission Color'].default_value = lin; b.inputs['Emission Strength'].default_value = emit
    if alpha < 1: b.inputs['Alpha'].default_value = alpha
    if backface:  # изнанка оболочки кузова — обивка салона
        geo = nt.nodes.new('ShaderNodeNewGeometry'); mix = nt.nodes.new('ShaderNodeMixShader'); b2 = nt.nodes.new('ShaderNodeBsdfPrincipled')
        b2.inputs['Base Color'].default_value = [srgb2lin(c) for c in backface]+[1]; b2.inputs['Roughness'].default_value = .9
        out = nt.nodes['Material Output']; nt.links.new(geo.outputs['Backfacing'], mix.inputs[0]); nt.links.new(b.outputs[0], mix.inputs[1]); nt.links.new(b2.outputs[0], mix.inputs[2])
        nt.links.new(mix.outputs[0], out.inputs['Surface'])
    m.diffuse_color = lin; m['srgb'] = list(col); MATS[name] = m
    return m

def init_mats():
    mat('paint', (.64, .655, .67), rough=.3, metal=.6, coat=1.)
    mat('interior', (.60, .60, .58), rough=.9)
    mat('rubber', (.035, .035, .037), rough=.75)
    mat('black', (.028, .028, .03), rough=.62)
    mat('black_gloss', (.04, .04, .045), rough=.22)
    mat('chrome', (.72, .73, .74), rough=.1, metal=1.)
    glass_mat('glass', (.86, .9, .89), .85)
    glass_mat('lens', (.95, .95, .95), .8)
    mat('amber', (.93, .52, .16), rough=.15)
    mat('red_lamp', (.66, .06, .05), rough=.15)
    mat('white_lamp', (.80, .80, .78), rough=.08, metal=.4)
    mat('tire', (.045, .045, .048), rough=.88)
    mat('alloy', (.78, .79, .8), rough=.26, metal=1.)
    mat('alloy_dark', (.35, .36, .37), rough=.4, metal=1.)
    mat('brake', (.3, .3, .3), rough=.5, metal=.8)
    mat('seat', (.30, .30, .31), rough=.95)
    mat('dash', (.13, .13, .135), rough=.7)
    mat('headliner', (.55, .55, .53), rough=.95)
    mat('under', (.035, .035, .035), rough=.8)
    mat('plate', (.93, .93, .9), rough=.35)
    mat('plate_text', (.03, .03, .03), rough=.5)
    mat('seam', (.05, .05, .05), rough=.8)
    mat('spring', (.15, .15, .16), rough=.5, metal=.6)

# ---------------- утилиты сетки ----------------
def new_obj(name, bm, mats, coll, smooth=False):
    me = bpy.data.meshes.new(name); bm.normal_update(); bm.to_mesh(me); bm.free()
    for m in mats: me.materials.append(MATS[m] if isinstance(m, str) else m)
    for p in me.polygons: p.use_smooth = smooth
    ob = bpy.data.objects.new(name, me); coll.objects.link(ob); return ob

def apply_mods(ob):
    dg = bpy.context.evaluated_depsgraph_get(); ev = ob.evaluated_get(dg)
    me = bpy.data.meshes.new_from_object(ev, preserve_all_data_layers=True, depsgraph=dg)
    old = ob.data; ob.modifiers.clear(); ob.data = me; bpy.data.meshes.remove(old)

def loft_body():
    bm = bmesh.new(); rings = []
    for y in STATIONS:
        half = station(y); loop = half+[(-x, z) for x, z in reversed(half[1:-1])]
        rings.append([bm.verts.new((x, y, z)) for x, z in loop])
    n = len(rings[0])
    for a, b in zip(rings, rings[1:]):
        for i in range(n):
            j = (i+1) % n; bm.faces.new([a[i], a[j], b[j], b[i]])
    bm.faces.new(rings[0]); bm.faces.new(rings[-1][::-1])
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    return bm

def prism(bm, outline, normal, d0, d1):
    """Замкнутая призма: контур (список Vector) выдавлен вдоль normal от d0 до d1."""
    n = Vector(normal).normalized(); a = [bm.verts.new(p+n*d0) for p in outline]; b = [bm.verts.new(p+n*d1) for p in outline]
    k = len(outline); bm.faces.new(a[::-1]); bm.faces.new(b)
    for i in range(k): j = (i+1) % k; bm.faces.new([a[i], a[j], b[j], b[i]])

def rounded_poly(corners, radii, seg=5):
    """Многоугольник (2D) со скруглёнными углами; corners по порядку, radii — радиус каждого угла."""
    out = []; n = len(corners)
    for i in range(n):
        p0, p1, p2 = Vector(corners[i-1]), Vector(corners[i]), Vector(corners[(i+1) % n]); r = radii[i]
        if r <= 0: out.append(p1); continue
        d1 = (p0-p1).normalized(); d2 = (p2-p1).normalized(); ang = math.acos(max(-1, min(1, d1.dot(d2))))
        t = r/math.tan(ang/2); a = p1+d1*t; b = p1+d2*t
        bis = (d1+d2).normalized(); c = p1+bis*(r/math.sin(ang/2))
        a0 = math.atan2(a.y-c.y, a.x-c.x); a1 = math.atan2(b.y-c.y, b.x-c.x)
        da = a1-a0
        while da > math.pi: da -= 2*math.pi
        while da < -math.pi: da += 2*math.pi
        for k in range(seg+1): th = a0+da*k/seg; out.append(Vector((c.x+r*math.cos(th), c.y+r*math.sin(th))))
    return out

# Окна в координатах (y, z) борта: дверь, форма которой повторяет наклон стойки, и заднее боковое.
def door_window():
    z0, z1 = 1.148, 1.502; off = .14
    yf0 = ws_y(z0, .76)+off; yf1 = ws_y(z1, .74)+off
    return rounded_poly([(yf0, z0), (.36, z0), (.36, z1), (yf1, z1)], [.025, .03, .035, .06])
def quarter_window():
    z0, z1 = 1.148, 1.502
    return rounded_poly([(.445, z0), (1.30, z0), (1.16, z1), (.445, z1)], [.03, .06, .13, .035], seg=7)

def side_outline3d(poly, sx=1, lift=0.):
    return [Vector((sx*(side_x(p.x, p.y)+lift), p.x, p.y)) for p in poly]
def side_normal(z=1.3):
    dxdz = (interp(SIDE_Z, z+.05)-interp(SIDE_Z, z-.05))/.1
    return Vector((1, 0, -dxdz)).normalized()

WS_N = Vector((0, -math.sin(math.radians(47)), math.cos(math.radians(47))))
def windshield_outline():
    """Контур проёма лобового стекла: точки на поверхности стекла (с изгибом)."""
    pts2 = rounded_poly([(-.655, 1.168), (.655, 1.168), (.615, 1.552), (-.615, 1.552)], [.05, .05, .07, .07], seg=6)
    return [Vector((p.x, ws_y(p.y, p.x), p.y)) for p in pts2]
REAR_N = Vector((0, math.cos(math.radians(10)), math.sin(math.radians(10))))
def rear_y(z, x=0.):
    seg = [p for p in TOP if p[0] >= 1.62]
    return interp(sorted((b, a) for a, b in seg), z)-REAR_BOW*min(1., (x/.74)**2)   # interp ждёт возрастания z
def rear_outline():
    pts2 = rounded_poly([(-.60, 1.14), (.60, 1.14), (.585, 1.45), (-.585, 1.45)], [.06, .06, .08, .08], seg=6)
    return [Vector((p.x, rear_y(p.y, p.x), p.y)) for p in pts2]

def arch_cutter(bm, yc, sx):
    seg = 40; r = ARCH_R+.01
    ring0 = [Vector((sx*.56, yc+r*math.cos(2*math.pi*i/seg), ARCH_ZC+r*math.sin(2*math.pi*i/seg))) for i in range(seg)]
    prism(bm, ring0, (sx, 0, 0), 0, .5)

def build_body(coll):
    bm = loft_body(); ob = new_obj('Body', bm, ['paint', 'interior', 'rubber'], coll)
    sol = ob.modifiers.new('Shell', 'SOLIDIFY'); sol.thickness = .016; sol.offset = -1; sol.use_even_offset = True; sol.material_offset = 1; sol.material_offset_rim = 2
    apply_mods(ob)
    cb = bmesh.new()
    for sx in (1, -1):
        n = side_normal(); n.x *= sx
        prism(cb, side_outline3d(door_window(), sx), n, -.09, .09)
        prism(cb, side_outline3d(quarter_window(), sx), n, -.09, .09)
        for yc in (FRONT_AXLE, REAR_AXLE): arch_cutter(cb, yc, sx)
    prism(cb, windshield_outline(), WS_N, -.12, .12)
    prism(cb, rear_outline(), REAR_N, -.12, .12)
    bmesh.ops.recalc_face_normals(cb, faces=cb.faces[:])   # зеркальные призмы иначе вывернуты и не режут правый борт
    cut = new_obj('Cutters', cb, ['rubber'], coll)
    bo = ob.modifiers.new('Openings', 'BOOLEAN'); bo.operation = 'DIFFERENCE'; bo.solver = 'EXACT'; bo.object = cut
    bo.use_self = True; bo.use_hole_tolerant = True; bo.material_mode = 'TRANSFER'
    apply_mods(ob); bpy.data.objects.remove(cut)
    me = ob.data
    if 'under' not in [m.name for m in me.materials]: me.materials.append(MATS['under'])
    ui = [m.name for m in me.materials].index('under'); pi = [m.name for m in me.materials].index('paint')
    for p in me.polygons:   # днище — тёмное, а не цвета кузова
        if p.material_index == pi and p.normal.z < -.5 and p.center.z < .47: p.material_index = ui
    return ob

# ---------------- сборщик деталей ----------------
def TR(loc=(0, 0, 0), rot=(0, 0, 0)): return Matrix.Translation(Vector(loc)) @ Euler(rot, 'XYZ').to_matrix().to_4x4()
class B:
    def __init__(s): s.bm = bmesh.new(); s.keys = []
    def mi(s, k):
        if k not in s.keys: s.keys.append(k)
        return s.keys.index(k)
    def add(s, part, mat, T=None):
        T = T if T is not None else Matrix.Identity(4); vm = {v: s.bm.verts.new(T @ v.co) for v in part.verts}
        flip = T.to_3x3().determinant() < 0
        for f in part.faces:
            vs = [vm[v] for v in f.verts]
            if flip: vs.reverse()
            try: nf = s.bm.faces.new(vs)
            except ValueError: continue
            nf.material_index = s.mi(mat(f) if callable(mat) else (mat[f.material_index] if isinstance(mat, (list, tuple)) else mat))
        part.free(); return s
    def box(s, mat, c, sz, rot=(0, 0, 0), bevel=0.):
        bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1)
        for v in bm.verts: v.co = Vector((v.co.x*sz[0], v.co.y*sz[1], v.co.z*sz[2]))
        if bevel: bmesh.ops.bevel(bm, geom=list(bm.edges), offset=bevel, segments=2, affect='EDGES', profile=.5)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:]); return s.add(bm, mat, TR(c, rot))
    def cyl(s, mat, c, r, h, seg=16, r2=None, rot=(0, 0, 0), axis='Z'):
        bm = bmesh.new(); bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg, radius1=r, radius2=r if r2 is None else r2, depth=h)
        base = {'Z': (0, 0, 0), 'X': (0, math.pi/2, 0), 'Y': (math.pi/2, 0, 0)}[axis]
        return s.add(bm, mat, TR(c, rot) @ TR((0, 0, 0), base))
    def beam(s, mat, a, b, r, seg=8, r2=None):
        a, b = Vector(a), Vector(b); v = b-a; q = Vector((0, 0, 1)).rotation_difference(v.normalized())
        bm = bmesh.new(); bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=seg, radius1=r, radius2=r if r2 is None else r2, depth=v.length)
        return s.add(bm, mat, Matrix.Translation((a+b)/2) @ q.to_matrix().to_4x4())
    def poly(s, mat, pts, flip=False):
        bm = bmesh.new(); vs = [bm.verts.new(p) for p in pts]; bm.faces.new(vs[::-1] if flip else vs); return s.add(bm, mat)
    def loft(s, mat, rings, closed=True, caps=True):
        bm = bmesh.new(); R = [[bm.verts.new(p) for p in r] for r in rings]; n = len(rings[0])
        for a, b in zip(R, R[1:]):
            for i in range(n if closed else n-1):
                j = (i+1) % n
                try: bm.faces.new([a[i], a[j], b[j], b[i]])
                except ValueError: pass
        if caps and closed: bm.faces.new(R[0][::-1]); bm.faces.new(R[-1])
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:]); return s.add(bm, mat)
    def sweep(s, mat, profile, path, up=Vector((0, 0, 1))):
        """Профиль (u — наружу по горизонтали, v — вверх) вдоль ломаной path в плоскости XY."""
        rings = []; P = [Vector((p[0], p[1], p[2] if len(p) > 2 else 0.)) for p in path]
        for i, p in enumerate(P):
            t0 = (P[i]-P[i-1]).normalized() if i > 0 else (P[1]-P[0]).normalized()
            t1 = (P[i+1]-P[i]).normalized() if i < len(P)-1 else t0
            t = (t0+t1).normalized(); n = Vector((t.y, -t.x, 0)); k = 1/max(.3, n.dot(Vector((t0.y, -t0.x, 0))))
            rings.append([p+n*u*k+up*v for u, v in profile])
        return s.loft(mat, rings)
    def obj(s, name, coll, smooth=False): return new_obj(name, s.bm, s.keys, coll, smooth)

def ring_strip(b, mat, outer, inner):
    n = len(outer); bm = bmesh.new(); O = [bm.verts.new(p) for p in outer]; I = [bm.verts.new(p) for p in inner]
    for i in range(n): j = (i+1) % n; bm.faces.new([O[i], O[j], I[j], I[i]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:]); b.add(bm, mat)

def offset2d(poly, d):
    """Смещение замкнутого 2D-контура (против часовой) наружу на d."""
    n = len(poly); out = []
    for i in range(n):
        a, p, c = poly[i-1], poly[i], poly[(i+1) % n]
        t = ((p-a).normalized()+(c-p).normalized()).normalized(); nn = Vector((t.y, -t.x))
        e = (c-p).normalized(); ne = Vector((e.y, -e.x)); out.append(p+nn*(d/max(.35, nn.dot(ne))))
    return out
def ccw(poly):
    a = sum(p.x*q.y-q.x*p.y for p, q in zip(poly, poly[1:]+poly[:1])); return poly if a > 0 else poly[::-1]

def text_bm(txt, size, extrude=.0012):
    cu = bpy.data.curves.new('txt', 'FONT'); cu.body = txt; cu.size = size; cu.extrude = extrude; cu.align_x = 'CENTER'; cu.align_y = 'CENTER'
    ob = bpy.data.objects.new('txt', cu); bpy.context.scene.collection.objects.link(ob)
    dg = bpy.context.evaluated_depsgraph_get(); me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    bpy.data.objects.remove(ob); bpy.data.curves.remove(cu); bm = bmesh.new(); bm.from_mesh(me); bpy.data.meshes.remove(me); return bm

def side_pt(y, z, lift=.0012, sx=1):
    return Vector((sx*(side_x(y, z)+lift), y, z))

def seam(b, pts2, sx=1, w=.0016, mat='seam', surf=None):
    """Шов кузова: тонкая тёмная полоса по поверхности вдоль ломаной (y, z) борта или (x, y) крыши."""
    P = [surf(*p) if surf else side_pt(p[0], p[1], sx=sx) for p in pts2]
    for a, c in zip(P, P[1:]):
        t = (c-a); L = t.length
        if L < 1e-5: continue
        n = Vector((sx, 0, 0)) if not surf else Vector((0, 0, 1)); wv = t.cross(n).normalized()*w
        b.poly(mat, [a-wv, c-wv, c+wv, a+wv], flip=(sx < 0) != bool(surf))

def door_seam_path():
    pts = [(-.569, 1.085), (-.569, .50), (-.555, .462), (-.52, .455), (.39, .455), (.425, .462), (.432, .50), (.432, 1.30), (.405, 1.535)]
    top = [(y, 1.535) for y in (.30, .10, -.05)]; ap = [(ws_y(z, .76)+.05, z) for z in (1.535, 1.45, 1.33, 1.20, 1.10)]
    return pts+top+ap+[(-.569, 1.085)]

def build_glass(coll):
    g = B(); gk = B()
    for sx in (1, -1):
        n = side_normal(); n.x *= sx
        for poly in (door_window(), quarter_window()):
            P = ccw(poly)
            g.poly('glass', [p-n*.007 for p in side_outline3d(P, sx)], flip=sx < 0)
            ring_strip(gk, 'rubber', side_outline3d(offset2d(P, .011), sx, .0015), side_outline3d(offset2d(P, -.004), sx, .0015))
    def curved(outline_fn, surf_fn, normal, name):
        pts2 = outline_fn(); c = Vector((0, 0)); [c.__iadd__(p) for p in pts2]; c /= len(pts2)
        rings = [[c+(p-c)*k for p in pts2] for k in (.34, .67, 1.)]; bm = bmesh.new()
        R = [[bm.verts.new(surf_fn(p)-normal*.007) for p in r] for r in rings]; cv = bm.verts.new(surf_fn(c)-normal*.007); n = len(pts2)
        for i in range(n): bm.faces.new([cv, R[0][i], R[0][(i+1) % n]])
        for a, b2 in zip(R, R[1:]):
            for i in range(n): j = (i+1) % n; bm.faces.new([a[i], b2[i], b2[j], a[j]])
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:]); g.add(bm, 'glass')
        ring_strip(gk, 'rubber', [surf_fn(p)+normal*.0015 for p in offset2d(ccw(pts2), .012)], [surf_fn(p)+normal*.0015 for p in offset2d(ccw(pts2), -.004)])
    ws2 = lambda: [Vector((p.x, p.z)) for p in windshield_outline()]
    curved(ws2, lambda p: Vector((p.x, ws_y(p.y, p.x), p.y)), WS_N, 'ws')
    rr2 = lambda: [Vector((p.x, p.z)) for p in rear_outline()]
    curved(rr2, lambda p: Vector((p.x, rear_y(p.y, p.x), p.y)), REAR_N, 'rear')
    ob = g.obj('Glass', coll, smooth=True); gk.obj('Window seals', coll)
    for p in ob.data.polygons:   # все стёкла — нормалью наружу
        c = p.center; out = Vector((math.copysign(1, c.x), 0, 0)) if abs(c.x) > .6 else (WS_N if c.y < 0 else REAR_N)
        if p.normal.dot(out) < 0: p.flip()

def build_trim(coll):
    b = B()
    # водостоки по краям крыши
    for sx in (1, -1):
        rings = []
        for y in [i*.05-.15 for i in range(35)]:
            if top_z(y, .73) < 1.56 or y > 1.58: continue
            x = side_x(y, 1.548); rings.append([Vector((sx*(x+dx), y, zscale(y, 1.548)+dz)) for dx, dz in ((-.004, -.004), (.012, -.006), (.014, .006), (-.004, .008))])
        if len(rings) > 2: b.loft('paint', rings)
    # расширители арок, пороги, брызговики
    def flare(yc, a0, a1, sx):
        prof = [(-.004, .792), (0, .848), (.012, .872), (.045, .878), (.066, .852), (.07, .838)]; rings = []
        for k in range(33):
            ph = math.radians(a0+(a1-a0)*k/32); rings.append([Vector((sx*x, yc+(ARCH_R+dr)*math.cos(ph), ARCH_ZC+(ARCH_R+dr)*math.sin(ph))) for dr, x in prof])
        b.loft('black', rings)
    for sx in (1, -1):
        flare(FRONT_AXLE, 2, 162, sx); flare(REAR_AXLE, 18, 178, sx)
        prof = [(.80, .352), (.846, .357), (.866, .382), (.864, .455), (.846, .468)]
        b.loft('black', [[Vector((sx*x, y, z)) for x, z in prof] for y in (-.725, .585)])
        for y0 in (-.735, 1.49): b.box('rubber', (sx*.74, y0, .30), (.20, .012, .24))
    # зеркала
    for sx in (1, -1):
        z0 = 1.17; y0 = ws_y(1.14, .78)+.16; x0 = side_x(y0, 1.14)
        b.box('black', (sx*(x0+.012), y0, 1.135), (.03, .09, .07), bevel=.008)
        b.box('black', (sx*(x0+.055), y0+.01, z0-.02), (.07, .035, .03), bevel=.006)
        b.box('black', (sx*(x0+.115), y0+.015, z0+.02), (.115, .075, .165), bevel=.018)
        b.box('chrome', (sx*(x0+.115), y0+.053, z0+.02), (.095, .004, .135))
    # ручки дверей и замки
    for sx in (1, -1):
        x = side_x(.37, 1.025); b.box('black', (sx*(x+.012), .37, 1.022), (.024, .115, .034), bevel=.008); b.cyl('chrome', (sx*(x+.004), .285, 1.022), .009, .01, 10, axis='X')
    # жабры вентиляции на задней стойке
    for sx in (1, -1):
        for k in range(4):
            y = 1.215+k*.028; z = 1.40
            p = [side_pt(y-.035, z-.055, .0015, sx), side_pt(y-.02, z-.055, .0015, sx), side_pt(y+.035, z+.055, .0015, sx), side_pt(y+.02, z+.055, .0015, sx)]
            b.poly('black', p, flip=sx < 0)
    # швы: двери, капот, дверь багажника, лючок бензобака
    for sx in (1, -1): seam(b, door_seam_path(), sx)
    hood = lambda x, y: Vector((x, y, top_z(y, abs(x))+.0012))
    for sx in (1, -1): seam(b, [(sx*.705, y) for y in (-1.66, -1.4, -1.1, -.8, -.715)], surf=hood)
    seam(b, [(x, -.715) for x in (-.705, -.35, 0, .35, .705)], surf=hood)
    nose = lambda x, z: Vector((x*plan_scale(-1.71), -1.7125-.0012, z))
    seam(b, [(x, .985) for x in (-.70, -.35, 0, .35, .70)], surf=lambda x, z: Vector((x, [yy for yy, zz in TOP if zz >= z][0]-.003, z)))
    rear = lambda x, z: Vector((x, (rear_y(z, abs(x)) if z > 1.1 else Y_REAR)+.0012, z))
    for sx in (1, -1): seam(b, [(sx*.675, z) for z in (.575, .8, 1.05, 1.09, 1.2, 1.3, 1.4, 1.47)], surf=lambda x, z: rear(x, z) + Vector((0, .0, 0)))
    seam(b, [(x, 1.48) for x in (-.675, -.4, 0, .4, .675)], surf=rear)
    seam(b, [(x, .578) for x in (-.675, -.4, 0, .4, .675)], surf=rear)
    fc = [(1.30+.065*math.cos(a*math.pi/8), .87+.065*math.sin(a*math.pi/8)) for a in range(17)]; seam(b, fc, -1)
    b.obj('Trim', coll)

def build_front(coll):
    b = B(); yf = Y_FRONT
    # решётка радиатора с корпусами фар — одна чёрная панель
    b.box('black', (0, yf-.016, .718), (1.47, .036, .288), bevel=.012)
    # жабо под лобовым стеклом (чёрный пластик с щелями воздухозаборника)
    rings = [[Vector((x, ws_y(z, abs(x))-.004, z)) for x in (-.70, -.35, 0, .35, .70)] for z in (1.086, 1.12, 1.172)]
    bm = bmesh.new(); R = [[bm.verts.new(p) for p in r] for r in rings]
    for a, c in zip(R, R[1:]):
        for i in range(4): bm.faces.new([a[i], a[i+1], c[i+1], c[i]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:]); b.add(bm, 'black')
    for k in range(9):
        x = -.48+k*.12; z = 1.14; b.box('rubber', (x, ws_y(z, abs(x))-.006, z), (.08, .004, .012), rot=(math.radians(-43), 0, 0))
    b.box('rubber', (0, yf-.031, .718), (.93, .012, .24))
    for k in range(4): b.box('black_gloss', (0, yf-.042, .636+k*.055), (.92, .026, .034), bevel=.006)
    for sx in (1, -1):
        cx = sx*.6075; b.box('black', (cx, yf-.036, .718), (.25, .016, .262), bevel=.02)
        b.cyl('rubber', (cx, yf-.046, .716), .097, .012, 32, axis='Y')
        b.cyl('chrome', (cx, yf-.052, .716), .09, .016, 32, r2=.078, axis='Y')
        b.cyl('alloy', (cx, yf-.05, .716), .074, .01, 32, r2=.03, axis='Y')
        lens = bmesh.new(); bmesh.ops.create_uvsphere(lens, u_segments=32, v_segments=8, radius=.2)
        for v in list(lens.verts):
            if v.co.z < .18: pass
        bmesh.ops.delete(lens, geom=[v for v in lens.verts if v.co.z < .176], context='VERTS')
        b.add(lens, 'lens', TR((cx, yf-.06+.176, .716), (math.pi/2, 0, 0)))
    # эмблема LADA: хромовый овал с ладьёй
    ov = [Vector((.062*math.cos(a*math.pi/16), .036*math.sin(a*math.pi/16))) for a in range(32)]
    oi = [Vector((.052*math.cos(a*math.pi/16), .027*math.sin(a*math.pi/16))) for a in range(32)]
    em = lambda p, dy: Vector((p.x, yf-.058-dy, .728+p.y))
    ring_strip(b, 'chrome', [em(p, .002) for p in ov], [em(p, .002) for p in oi]); b.poly('black_gloss', [em(p, 0) for p in oi], flip=True)
    sail = [(-.034, -.014), (.036, -.014), (.022, .0), (.03, .02), (.008, .02), (-.002, .006), (-.022, .006)]
    b.poly('chrome', [em(Vector(p), .003) for p in sail], flip=True)
    # указатели поворота над фарами: 2/3 оранжевые снаружи, 1/3 белые
    for sx in (1, -1):
        x0, x1 = .50, .72; zc = .905; b.box('chrome', (sx*(x0+x1)/2, yf-.004, zc), (x1-x0+.012, .014, .10), bevel=.004)
        xm = x0+(x1-x0)/3
        b.box('white_lamp', (sx*(x0+xm)/2, yf-.011, zc), (xm-x0-.004, .006, .084)); b.box('amber', (sx*(xm+x1)/2, yf-.011, zc), (x1-xm-.004, .006, .084))
        b.box('amber', (sx*.8455, -1.605, .905), (.008, .048, .022), bevel=.003)
    # бампер и номер «4x4»
    prof = [(-.12, .458), (-.02, .448), (0, .458), (0, .538), (-.012, .551), (-.12, .556)]
    b.sweep('black', prof, [(-.846, -1.625), (-.846, -1.785), (-.805, -1.863), (.805, -1.863), (.846, -1.785), (.846, -1.625)])
    b.box('plate', (0, -1.867, .48), (.52, .006, .112), bevel=.002)
    t = text_bm('4x4', .085); b.add(t, 'plate_text', TR((0, -1.8705, .478), (math.pi/2, 0, 0)))
    b.box('under', (0, -1.70, .38), (1.3, .06, .14))
    b.obj('Front', coll)

def build_rear(coll):
    b = B(); yr = Y_REAR
    prof = [(-.12, .432), (-.022, .417), (0, .43), (0, .532), (-.012, .546), (-.12, .552)]
    b.sweep('black', prof, [(.846, 1.605), (.846, 1.79), (.805, 1.866), (-.805, 1.866), (-.846, 1.79), (-.846, 1.605)])
    for sx in (1, -1):
        cx = sx*.585; b.box('black', (cx, yr+.008, .70), (.25, .02, .225), bevel=.01)
        for (dx, dz, m) in ((-.06, .05, 'red_lamp'), (.06, .05, 'amber'), (-.06, -.05, 'red_lamp'), (.06, -.05, 'white_lamp')):
            b.box(m, (cx+sx*dx, yr+.019, .70+dz), (.108, .006, .09), bevel=.004)
        b.box('red_lamp', (sx*.72, 1.867, .49), (.07, .004, .03))
    b.box('black', (0, yr+.006, .69), (.56, .012, .15))
    b.box('plate', (0, yr+.014, .69), (.52, .006, .112), bevel=.002)
    t = text_bm('4x4', .085); b.add(t, 'plate_text', TR((0, yr+.0175, .688), (math.pi/2, 0, math.pi)))
    t = text_bm('LADA 4x4', .045, .003); b.add(t, 'chrome', TR((0, rear_y(1.12)+.003, .83), (math.pi/2, 0, math.pi)))
    # рычаг и щётка стеклоочистителя двери багажника
    b.beam('black', (.0, rear_y(1.16)+.02, 1.16), (-.38, rear_y(1.33)+.02, 1.33), .008)
    b.beam('rubber', (-.05, rear_y(1.20)+.028, 1.20), (-.52, rear_y(1.40)+.028, 1.40), .006)
    b.beam('under', (-.42, 1.72, .30), (-.46, 1.90, .30), .026); b.cyl('rubber', (-.46, 1.905, .30), .02, .012, 12, axis='Y')
    b.obj('Rear', coll)

def build_wipers(coll):
    b = B()
    for px in (.44, -.06):
        z = 1.152; a = Vector((px, ws_y(z, px)-.01, z)); e = Vector((px-.47, ws_y(z+.012, px-.47)-.01, z+.012))
        b.beam('black', a, e, .007); b.cyl('black', a, .018, .03, 10, rot=(math.radians(-43), 0, 0))
        bl = [Vector((px-.02-t*.5, ws_y(z+.02, px-.02-t*.5)-.012, z+.02)) for t in (0, 1)]; b.beam('rubber', bl[0], bl[1], .006)
    b.obj('Wipers', coll)

def wheel(coll, name, c, sx, front):
    b = B(); seg = 48
    prof = [(.203, -.083), (.25, -.094), (.31, -.093), (.332, -.083), (.336, -.07), (.336, .07), (.332, .083), (.31, .093), (.25, .094), (.203, .083)]
    rings = [[Vector((sx*x, r*math.cos(2*math.pi*i/seg), r*math.sin(2*math.pi*i/seg))) for r, x in prof] for i in range(seg)]
    bm = bmesh.new(); R = [[bm.verts.new(p) for p in r] for r in rings]; n = len(prof)
    for i in range(seg):
        a, c2 = R[i], R[(i+1) % seg]
        for k in range(n-1): bm.faces.new([a[k], a[k+1], c2[k+1], c2[k]])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:]); b.add(bm, 'tire')
    for row, (x0, x1, off) in enumerate(((.006, .072, 0), (-.072, -.006, .5))):   # грунтозацепы
        for i in range(40):
            a0 = 2*math.pi*(i+off)/40; a1 = a0+2*math.pi*.62/40; blk = []
            for r in (.334, .343):
                for a in (a0, a1):
                    for x in (x0, x1): blk.append(Vector((sx*x, r*math.cos(a), r*math.sin(a))))
            bb = bmesh.new(); v = [bb.verts.new(p) for p in blk]
            for f in ((0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)): bb.faces.new([v[j] for j in f])
            bmesh.ops.recalc_face_normals(bb, faces=bb.faces[:]); b.add(bb, 'tire')
    # литой диск: обод, 5 сдвоенных спиц, ступица, колпачок, гайки
    barrel = bmesh.new(); bmesh.ops.create_cone(barrel, cap_ends=False, segments=32, radius1=.19, radius2=.19, depth=.15)
    b.add(barrel, 'alloy_dark', TR((sx*-.005, 0, 0), (0, math.pi/2, 0)))
    b.cyl('alloy_dark', (sx*-.078, 0, 0), .19, .004, 32, axis='X')
    lip = bmesh.new(); ring_o = [Vector((sx*.078, .207*math.cos(2*math.pi*i/48), .207*math.sin(2*math.pi*i/48))) for i in range(48)]
    ring_i = [Vector((sx*.078, .188*math.cos(2*math.pi*i/48), .188*math.sin(2*math.pi*i/48))) for i in range(48)]; ring_strip(b, 'alloy', ring_o, ring_i)
    b.loft('alloy', [[Vector((sx*x, r*math.cos(2*math.pi*i/48), r*math.sin(2*math.pi*i/48))) for i in range(48)] for r, x in ((.207, .078), (.2, .07), (.19, .05))], caps=False)
    for k in range(5):
        th = 2*math.pi*k/5+math.pi/2
        for s in (-1, 1):
            rings = []
            for r, dang, w, x in ((.062, 6.5, .026, .058), (.12, 8.0, .032, .062), (.188, 9.8, .04, .068)):
                a = th+s*math.radians(dang); c0 = Vector((0, r*math.cos(a), r*math.sin(a))); tg = Vector((0, -math.sin(a), math.cos(a)))
                rings.append([Vector((sx*(x+dx), 0, 0))+c0+tg*dw for dx, dw in ((0, -w/2), (0, w/2), (-.022, w/2), (-.022, -w/2))])
            b.loft('alloy', rings)
    b.cyl('alloy', (sx*.05, 0, 0), .07, .025, 24, axis='X'); b.cyl('chrome', (sx*.066, 0, 0), .036, .012, 20, r2=.03, axis='X')
    for k in range(5):
        a = 2*math.pi*(k+.5)/5+math.pi/2; b.cyl('chrome', (sx*.064, .05*math.cos(a), .05*math.sin(a)), .009, .012, 6, axis='X')
    b.cyl('brake', (sx*-.03, 0, 0), .135 if front else .115, .02 if front else .07, 32, axis='X')
    if front: b.box('dash', (sx*-.02, -.02, .125), (.05, .09, .06))
    ob = b.obj(name, coll); ob.location = c
    return ob

def spring(b, base, top, r=.06, turns=6, wire=.011, seg=10):
    pts = []; base = Vector(base); top = Vector(top); n = turns*seg
    for i in range(n+1):
        t = i/n; a = 2*math.pi*turns*t; pts.append(base+(top-base)*t+Vector((r*math.cos(a), r*math.sin(a), 0)))
    for a, c in zip(pts, pts[1:]): b.beam('spring', a, c, wire, seg=6)

def build_under(coll):
    b = B()
    b.box('under', (0, -.95, .40), (.55, 1.25, .14)); b.box('under', (0, .05, .36), (.25, .6, .1))
    b.box('under', (0, -1.14, .30), (.26, .22, .20), bevel=.03)
    for sx in (1, -1):
        b.beam('under', (sx*.12, -1.14, .30), (sx*.62, FRONT_AXLE, AXLE_Z), .028)
        b.beam('under', (sx*.20, -1.28, .30), (sx*.60, -1.19, .26), .02); b.beam('under', (sx*.20, -1.02, .30), (sx*.60, -1.14, .26), .02)
        b.beam('under', (sx*.28, -1.22, .52), (sx*.58, -1.17, .48), .018)
        spring(b, (sx*.47, -1.16, .30), (sx*.47, -1.16, .56), .055, 6)
        b.beam('spring', (sx*.47, -1.16, .30), (sx*.47, -1.16, .60), .018)
    b.beam('under', (-.64, REAR_AXLE, AXLE_Z), (.64, REAR_AXLE, AXLE_Z), .038); b.cyl('under', (.06, REAR_AXLE, AXLE_Z), .13, .2, 20, axis='Y')
    for sx in (1, -1):
        b.beam('under', (sx*.52, REAR_AXLE, AXLE_Z), (sx*.55, .35, .40), .02); spring(b, (sx*.52, REAR_AXLE-.05, .36), (sx*.52, REAR_AXLE-.05, .60), .06, 6)
    b.beam('under', (0, -.25, .33), (.06, REAR_AXLE, AXLE_Z), .03); b.beam('under', (0, -.35, .33), (0, -1.10, .30), .028)
    b.beam('under', (-.22, -1.0, .33), (-.25, .4, .33), .025); b.cyl('under', (-.30, .75, .34), .085, .55, 16, axis='Y'); b.beam('under', (-.35, 1.05, .33), (-.42, 1.72, .30), .025)
    b.box('under', (.12, 1.47, .44), (.95, .34, .16), bevel=.02)
    b.obj('Underbody', coll)

def build_interior(coll):
    b = B()
    b.box('seat', (0, .30, .455), (1.60, 2.0, .02)); b.box('seat', (0, 1.52, .62), (1.50, .56, .02))
    b.box('dash', (0, -.60, .96), (1.56, .26, .26), bevel=.03); b.box('dash', (0, -.53, 1.10), (1.50, .20, .06), rot=(.35, 0, 0))
    b.box('dash', (.37, -.52, 1.13), (.30, .12, .10), bevel=.02); b.box('dash', (0, -.40, .70), (.26, .45, .30), bevel=.03)
    col_a = Vector((.37, -.58, .98)); col_b = Vector((.37, -.40, 1.03)); b.beam('dash', col_a, col_b, .03)
    sw = bmesh.new(); bmesh.ops.create_circle(sw, cap_ends=False, segments=32, radius=.19)
    rot = Euler((math.radians(-62), 0, 0)); tor = B()
    for i in range(32):
        a0, a1 = 2*math.pi*i/32, 2*math.pi*(i+1)/32
        p0 = Vector((.19*math.cos(a0), .19*math.sin(a0), 0)); p1 = Vector((.19*math.cos(a1), .19*math.sin(a1), 0))
        b.beam('dash', col_b+(rot.to_matrix() @ p0), col_b+(rot.to_matrix() @ p1), .016, seg=6)
    sw.free()
    for a in (math.pi*.15, math.pi*.85, math.pi*1.5): b.beam('dash', col_b, col_b+rot.to_matrix() @ Vector((.19*math.cos(a), .19*math.sin(a), 0)), .012, seg=6)
    b.cyl('dash', col_b, .055, .04, 16, rot=(math.radians(28), 0, 0))
    for sx in (1, -1):
        x = sx*.37
        b.box('seat', (x, .08, .68), (.50, .50, .12), bevel=.03)
        b.box('seat', (x, .33, 1.02), (.50, .11, .60), rot=(math.radians(-14), 0, 0), bevel=.035)
        b.box('seat', (x, .38, 1.42), (.26, .09, .17), bevel=.03)
        for dx in (-.07, .07): b.beam('chrome', (x+dx, .37, 1.30), (x+dx, .38, 1.34), .006)
        b.box('headliner', (sx*.35, .0, 1.588), (.34, .15, .018), rot=(.1, 0, 0))
    b.box('seat', (0, .95, .70), (1.30, .48, .13), bevel=.035); b.box('seat', (0, 1.19, 1.00), (1.30, .11, .52), rot=(math.radians(-10), 0, 0), bevel=.035)
    b.box('dash', (0, -.21, 1.52), (.20, .03, .06), bevel=.008); b.beam('dash', (0, -.21, 1.52), (0, -.19, 1.585), .008)
    b.beam('dash', (0, -.32, .84), (.02, -.30, 1.0), .01); b.cyl('dash', (.02, -.30, 1.0), .022, .04, 10)
    b.obj('Interior', coll)

def build_car(coll, stage='full'):
    parts = [build_body(coll)]
    if stage == 'body': return parts
    for fn in (build_glass, build_trim, build_front, build_rear, build_wipers, build_under, build_interior): fn(coll)
    for name, sx, y, front in (('Wheel FL', 1, FRONT_AXLE, True), ('Wheel FR', -1, FRONT_AXLE, True), ('Wheel RL', 1, REAR_AXLE, False), ('Wheel RR', -1, REAR_AXLE, False)):
        wheel(coll, name, (sx*(TRACK_F if front else TRACK_R), y, AXLE_Z), sx, front)
    for ob in coll.objects:   # гладкое затенение, острые кромки по углу — без «ступенек» в отражениях
        if ob.type == 'MESH' and ob.name not in ('Glass',):
            ob.data.shade_smooth(); ob.data.set_sharp_from_angle(angle=math.radians(32))
    return list(coll.objects)

# ---------------- сцена ----------------
def setup_scene(samples=64):
    sc = bpy.context.scene
    for o in list(bpy.data.objects): bpy.data.objects.remove(o)
    sc.render.engine = 'CYCLES'; sc.cycles.device = 'CPU'; sc.cycles.samples = samples; sc.cycles.use_denoising = True
    sc.cycles.max_bounces = 8; sc.cycles.transmission_bounces = 8; sc.cycles.glossy_bounces = 4; sc.cycles.caustics_reflective = False; sc.cycles.caustics_refractive = False
    sc.render.film_transparent = True; sc.view_settings.view_transform = 'Standard'; sc.view_settings.look = 'None'
    sc.render.image_settings.file_format = 'PNG'; sc.render.image_settings.color_mode = 'RGBA'
    w = bpy.data.worlds.new('Studio'); sc.world = w; bg = w.node_tree.nodes['Background']; bg.inputs[0].default_value = (1, 1, 1, 1); bg.inputs[1].default_value = .78
    ld = bpy.data.lights.new('Key', 'AREA'); ld.energy = 750; ld.size = 5; key = bpy.data.objects.new('Key', ld); sc.collection.objects.link(key)
    key.location = (2.5, -3.5, 6.5); key.rotation_euler = (Vector((0, 0, .6))-key.location).to_track_quat('-Z', 'Y').to_euler()
    gm = bpy.data.meshes.new('Ground'); bm = bmesh.new(); bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=40); bm.to_mesh(gm); bm.free()
    g = bpy.data.objects.new('Ground', gm); sc.collection.objects.link(g); g.is_shadow_catcher = True
    gmat = bpy.data.materials.new('ground'); gmat.node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (.8, .8, .8, 1); gm.materials.append(gmat)
    cd = bpy.data.cameras.new('Cam'); co = bpy.data.objects.new('Cam', cd); sc.collection.objects.link(co); sc.camera = co
    coll = bpy.data.collections.new('VAZ-21214 LADA 4x4'); sc.collection.children.link(coll)
    return coll

def look(cam, loc, target, lens=50, res=(1200, 900)):
    sc = bpy.context.scene; sc.render.resolution_x, sc.render.resolution_y = res; sc.render.resolution_percentage = 100
    cam.location = Vector(loc); cam.rotation_euler = (Vector(target)-Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    cam.data.lens = lens; cam.data.sensor_width = 36; cam.data.sensor_fit = 'HORIZONTAL'; cam.data.clip_end = 200

def render(path):
    sc = bpy.context.scene; sc.render.filepath = path; bpy.ops.render.render(write_still=True)

# ---------------- подбор камеры по фото (Левенберг–Марквардт) ----------------
def photo_picks():
    """Пары: точка модели (м) ↔ пиксель на фото 300×225 (image.png из чата)."""
    ym = ws_y(1.14, .78)+.16; xm = side_x(ym, 1.14)+.115
    wt = ws_y(1.552, .615); wb = ws_y(1.128, .655)
    return [((.78, FRONT_AXLE, AXLE_Z), (176, 158)), ((.766, REAR_AXLE, AXLE_Z), (270, 144)),
            ((.80, FRONT_AXLE-.035, 0), (176, 193)), ((.79, REAR_AXLE-.035, 0), (264, 172.4)), ((-.63, FRONT_AXLE-.055, 0), (48, 184)),
            ((.6075, -1.79, .716), (129, 121)), ((-.6075, -1.79, .716), (29, 119.6)), ((0, -1.79, .728), (72.4, 120)),
            ((.61, -1.738, .905), (129.6, 102)), ((-.61, -1.738, .905), (29.6, 99.2)),
            ((.615, wt, 1.552), (201, 38)), ((-.615, wt, 1.552), (102, 41)), ((-.655, wb, 1.168), (86, 70)),
            ((.853, .37, 1.022), (242.4, 84.4)), ((xm, ym+.015, 1.19), (219, 73)), ((-xm, ym+.015, 1.19), (77, 71)),
            ((-.26, -1.87, .536), (47.6, 137)), ((.26, -1.87, .536), (92.4, 138)), ((-.26, -1.87, .424), (48, 148)), ((.26, -1.87, .424), (92.4, 149)),
            ((side_x(1.30, 1.148), 1.30, 1.148), (272.5, 71.2)), ((side_x(.445, 1.148), .445, 1.148), (239.5, 72)), ((side_x(.445, 1.50), .445, 1.50), (239, 40.5))]

def cam_basis(p):
    import numpy as np
    yaw, pitch, roll = p[3], p[4], p[5]
    d = np.array([math.sin(yaw)*math.cos(pitch), math.cos(yaw)*math.cos(pitch), math.sin(pitch)])
    r0 = np.array([d[1], -d[0], 0.]); r0 /= np.linalg.norm(r0); u0 = np.cross(r0, d)
    r = r0*math.cos(roll)+u0*math.sin(roll); u = u0*math.cos(roll)-r0*math.sin(roll)
    return d, r, u

def project(p, P):
    import numpy as np
    d, r, u = cam_basis(p); C = np.array(p[:3]); f = math.exp(p[6]); a = math.exp(p[7]) if len(p) > 7 else 1.
    cx, cy = (150.+p[8], 112.5+p[9]) if len(p) > 9 else (150., 112.5); out = []
    for X in P:
        v = np.array(X)-C; z = v.dot(d); out.append((cx+a*f*v.dot(r)/z, cy-f*v.dot(u)/z))
    return np.array(out)

def solve_camera(picks, full=False):
    import numpy as np
    P = [a for a, b in picks]; Q = np.array([b for a, b in picks], float)
    C0 = np.array([3.2, -7.0, 1.6]); d0 = np.array([0, 0, .7])-C0; d0 /= np.linalg.norm(d0)
    p = np.array([*C0, math.atan2(d0[0], d0[1]), math.asin(d0[2]), 0., math.log(900.)]); lam = 1e-2
    if full: p = np.array([*p, 0., 0., 0.])
    res = lambda q: (project(q, P)-Q).ravel()
    for it in range(400):
        r0 = res(p); J = np.zeros((len(r0), len(p)))
        for k in range(len(p)):
            dp = np.zeros(len(p)); dp[k] = 1e-5; J[:, k] = (res(p+dp)-res(p-dp))/2e-5
        A = J.T @ J; g = J.T @ r0
        step = np.linalg.solve(A+lam*np.diag(np.diag(A)+1e-9), -g); pn = p+step
        if (res(pn)**2).sum() < (r0**2).sum(): p = pn; lam = max(1e-7, lam*.4)
        else: lam *= 5
        if np.linalg.norm(step) < 1e-10: break
    err = project(p, P)-Q
    return p, err

def set_camera_from(p, res=(900, 675)):
    import numpy as np
    sc = bpy.context.scene; cam = sc.camera; d, r, u = cam_basis(p)
    M = Matrix(((r[0], u[0], -d[0]), (r[1], u[1], -d[1]), (r[2], u[2], -d[2])))
    cam.location = Vector(p[:3]); cam.rotation_euler = M.to_euler()
    cam.data.sensor_fit = 'HORIZONTAL'; cam.data.sensor_width = 36; cam.data.lens = math.exp(p[6])/300*36; cam.data.clip_end = 200
    sc.render.resolution_x, sc.render.resolution_y = res; sc.render.resolution_percentage = 100

def parse_args():
    argv = sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []; opt = {}; i = 0
    while i < len(argv):
        if argv[i].startswith('--'):
            k = argv[i][2:]
            if i+1 < len(argv) and not argv[i+1].startswith('--'): opt[k] = argv[i+1]; i += 2
            else: opt[k] = True; i += 1
        else: i += 1
    return opt

VIEWS = {'front34': ((4.3, -6.9, 1.55), (0, -.1, .75), 50), 'side': ((12.5, .03, .95), (0, .03, .8), 85),
         'rear34': ((-6.4, 9.6, 2.1), (0, .15, .78), 85), 'front': ((0, -13, 1.0), (0, 0, .82), 120),
         'high34': ((-7.0, -8.2, 5.6), (0, 0, .55), 85), 'nose': ((2.6, -5.6, 1.25), (.05, -1.62, .74), 85),
         'top': ((0, 0, 14), (0, 0, 0), 30)}

def main():
    opt = parse_args(); init_mats()
    coll = setup_scene(int(opt.get('samples', 64)))
    obs = build_car(coll, opt.get('stage', 'full'))
    tot = 0
    for ob in obs:
        me = ob.data; me.calc_loop_triangles(); tot += len(me.loop_triangles); print(f'PART {ob.name:16s} tris={len(me.loop_triangles)}')
    print('TOTAL tris', tot)
    if 'match' in opt:
        for full in (False, True):
            p, err = solve_camera(photo_picks(), full)
            extra = f' aspect {math.exp(p[7]):.4f} pp_shift {p[8]:.1f},{p[9]:.1f}' if full else ''
            print('SOLVE', 'full' if full else 'basic', 'RMS px', round(float((err**2).sum(axis=1).mean()**.5), 2), extra)
        p, err = solve_camera(photo_picks(), opt.get('fullcam', False) is not False)
        print('CAMERA pos', [round(v, 3) for v in p[:3]], 'yaw/pitch/roll', [round(math.degrees(v), 2) for v in p[3:6]], 'f_px', round(math.exp(p[6]), 1), 'lens_mm', round(math.exp(p[6])/300*36, 1))
        for (P3, Q2), e in zip(photo_picks(), err): print('  pick', tuple(round(v, 3) for v in P3), '->', Q2, 'err px', round(float(e[0]), 1), round(float(e[1]), 1))
        print('RMS px', round(float((err**2).sum(axis=1).mean()**.5), 2))
        set_camera_from(p); os.makedirs(os.path.dirname(os.path.abspath(opt['match'])), exist_ok=True); render(opt['match']); print('RENDERED match')
    if 'render' in opt:
        os.makedirs(opt['render'], exist_ok=True)
        for name in opt.get('views', 'front34,side').split(','):
            if name == 'photo':
                p, err = solve_camera(photo_picks()); set_camera_from(p, res=(1440, 1080))
            else:
                loc, tgt, lens = VIEWS[name]; look(bpy.context.scene.camera, loc, tgt, lens, res=(1280, 960))
            render(os.path.join(opt['render'], name+'.png')); print('RENDERED', name)
    if 'save' in opt: bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(opt['save']))
    if 'export' in opt:
        out = os.path.abspath(opt['export']); os.makedirs(out, exist_ok=True)
        p, err = solve_camera(photo_picks()); set_camera_from(p, res=(1440, 1080))   # в файле камера стоит как на фото
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, 'vaz_niva.blend'), compress=True)
        for o in bpy.context.scene.objects: o.select_set(o.name in coll.objects)
        bpy.ops.export_scene.gltf(filepath=os.path.join(out, 'vaz_niva.glb'), export_format='GLB', use_selection=True)
        print('EXPORTED', out)

main()
