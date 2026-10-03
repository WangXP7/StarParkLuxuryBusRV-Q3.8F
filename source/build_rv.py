# -*- coding: utf-8 -*-
"""
StarPark Luxury Bus RV - fully procedural Blender 5.2 LTS build.
All geometry from bpy/bmesh, all materials procedural nodes, Eevee render.
Axis: +X = vehicle front, +Y = vehicle LEFT, +Z up. Ground at Z=0.
"""
import bpy, bmesh, math, os, time
from mathutils import Vector, Matrix

OUT = r"PRIVACY-REDACTED\Blender\StarParkLuxuryBusRV-Qoder-Qwen3.8Flash"
R = math.radians
TAG = 'v1'
T0 = time.time()
LOG = []

def tick(label):
    t = time.time() - T0
    LOG.append((label, t))
    print('T %7.1fs  %s' % (t, label), flush=True)

# ============================================================ utils
def clear_all():
    for ob in list(bpy.data.objects):
        bpy.data.objects.remove(ob, do_unlink=True)
    for coll in (bpy.data.meshes, bpy.data.materials, bpy.data.lights,
                 bpy.data.cameras, bpy.data.curves, bpy.data.images, bpy.data.node_groups):
        for x in list(coll):
            if x.users == 0:
                coll.remove(x)

def collection(name):
    sc = bpy.context.scene
    if name not in bpy.data.collections:
        c = bpy.data.collections.new(name)
        sc.collection.children.link(c)
    return bpy.data.collections[name]

def link_to(obj, cname):
    c = collection(cname)
    for uc in obj.users_collection:
        uc.objects.unlink(obj)
    if obj.name not in c.objects:
        c.objects.link(obj)
    return obj

_BOXV = [(-1, -1, -1), (1, -1, -1), (1, 1, -1), (-1, 1, -1),
         (-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1)]
_BOXF = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6), (1, 2, 6, 5), (0, 4, 7, 3)]

def solid_from(name, verts, faces, mat=None, coll='RV'):
    """build a mesh and force consistent outward normals (needed by the boolean solver)"""
    bm = bmesh.new()
    bv = [bm.verts.new(tuple(v)) for v in verts]
    nf = []
    for f in faces:
        idx = list(dict.fromkeys(f))
        if len(idx) < 3:
            continue
        try:
            nf.append(bm.faces.new([bv[i] for i in idx]))
        except ValueError:
            pass
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    if mat:
        me.materials.append(mat)
    o = bpy.data.objects.new(name, me)
    return link_to(o, coll)

def from_pydata(name, verts, faces, mat=None, coll='RV'):
    me = bpy.data.meshes.new(name)
    me.from_pydata([tuple(v) for v in verts], [], faces)
    me.validate()
    if mat:
        me.materials.append(mat)
    o = bpy.data.objects.new(name, me)
    return link_to(o, coll)

def box(name, cx, cy, cz, sx, sy, sz, mat=None, coll='RV', rot=None):
    v = [(x * sx / 2.0, y * sy / 2.0, z * sz / 2.0) for (x, y, z) in _BOXV]
    o = from_pydata(name, v, _BOXF, mat, coll)
    o.location = (cx, cy, cz)
    if rot:
        o.rotation_euler = rot
    return o

def prim(name, kind, coll='RV', mat=None, **kw):
    if kind == 'cyl':
        bpy.ops.mesh.primitive_cylinder_add(vertices=kw.get('seg', 32), radius=kw['r'],
                                            depth=kw['d'], location=kw['loc'], rotation=kw.get('rot', (0, 0, 0)))
    elif kind == 'sph':
        s = kw.get('seg', 24)
        bpy.ops.mesh.primitive_uv_sphere_add(segments=s, ring_count=max(6, s // 2), radius=kw['r'],
                                             location=kw['loc'], rotation=kw.get('rot', (0, 0, 0)))
    elif kind == 'ico':
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=kw.get('seg', 2), radius=kw['r'], location=kw['loc'])
    elif kind == 'tor':
        bpy.ops.mesh.primitive_torus_add(major_radius=kw['R'], minor_radius=kw['r'],
                                         major_segments=kw.get('seg', 36), minor_segments=kw.get('mseg', 10),
                                         location=kw['loc'], rotation=kw.get('rot', (0, 0, 0)))
    elif kind == 'cone':
        bpy.ops.mesh.primitive_cone_add(vertices=kw.get('seg', 24), radius1=kw['r1'], radius2=kw['r2'],
                                        depth=kw['d'], location=kw['loc'], rotation=kw.get('rot', (0, 0, 0)))
    o = bpy.context.active_object
    o.name = name
    if mat:
        o.data.materials.append(mat)
    return link_to(o, coll)

def bevel(o, w=0.02, seg=2, ang=42.0):
    m = o.modifiers.new('bev', 'BEVEL')
    m.width = w
    m.segments = seg
    m.limit_method = 'ANGLE'
    m.angle_limit = R(ang)
    m.miter_outer = 'MITER_ARC'
    m.harden_normals = False
    return m

def shade(o, ang=40.0):
    if o.type != 'MESH':
        return o
    deselect()
    o.hide_set(False)
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    try:
        bpy.ops.object.shade_auto_smooth(angle=R(ang))
    except Exception:
        bpy.ops.object.shade_smooth()
    o.select_set(False)
    return o

def deselect():
    for ob in bpy.context.selected_objects:
        ob.select_set(False)

def apply_all(o):
    deselect()
    o.select_set(True)
    bpy.context.view_layer.objects.active = o
    bpy.ops.object.convert(target='MESH')
    return bpy.context.view_layer.objects.active

def boolean(target, cutter, op='DIFFERENCE', keep=False):
    m = target.modifiers.new('bool_' + op, 'BOOLEAN')
    m.operation = op
    m.solver = 'EXACT'
    m.object = cutter
    m.use_self = False
    if not keep:
        cutter.hide_render = True
        if cutter.name in bpy.context.view_layer.objects:
            cutter.hide_set(True)
    return m

def join(objs, name, coll='RV'):
    objs = [o for o in objs if o is not None]
    # the active object's modifiers survive a join and would then act on the whole
    # merged mesh, so bake every input first
    objs = [apply_all(o) if o.modifiers else o for o in objs]
    deselect()
    for o in objs:
        o.hide_set(False)
        o.select_set(True)
    bpy.context.view_layer.objects.active = objs[0]
    bpy.ops.object.join()
    res = bpy.context.view_layer.objects.active
    res.name = name
    link_to(res, coll)
    return res

def bake(o):
    bpy.context.view_layer.update()
    mw = o.matrix_world.copy()
    o.data.transform(mw)
    o.matrix_world = Matrix.Identity(4)
    return o

def empty(name, loc, size=0.3, coll='ENV'):
    o = bpy.data.objects.new(name, None)
    o.empty_display_size = size
    o.location = loc
    return link_to(o, coll)

# ============================================================ materials
M = {}

def new_mat(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        if n.type != 'OUTPUT_MATERIAL':
            nt.nodes.remove(n)
    b = nt.nodes.new('ShaderNodeBsdfPrincipled')
    b.location = (-260, 0)
    nt.links.new(b.outputs['BSDF'], nt.nodes['Material Output'].inputs['Surface'])
    return m, nt, b

def setin(b, name, val):
    if name in b.inputs:
        b.inputs[name].default_value = val
        return True
    return False

def mat_simple(name, col, metal=0.0, rough=0.5, **kw):
    m, nt, b = new_mat(name)
    setin(b, 'Base Color', (*col, 1))
    setin(b, 'Metallic', metal)
    setin(b, 'Roughness', rough)
    for k, v in kw.items():
        setin(b, k, v)
    M[name] = m
    return m

def mat_emit(name, col, strength):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        if n.type != 'OUTPUT_MATERIAL':
            nt.nodes.remove(n)
    e = nt.nodes.new('ShaderNodeEmission')
    e.inputs['Color'].default_value = (*col, 1)
    e.inputs['Strength'].default_value = strength
    nt.links.new(e.outputs['Emission'], nt.nodes['Material Output'].inputs['Surface'])
    M[name] = m
    return m

def build_mats():
    # --- pearl white
    m, nt, b = new_mat('PearlWhite')
    tc = nt.nodes.new('ShaderNodeTexCoord'); mp = nt.nodes.new('ShaderNodeMapping')
    nt.links.new(tc.outputs['Object'], mp.inputs['Vector'])
    n1 = nt.nodes.new('ShaderNodeTexNoise'); n1.inputs['Scale'].default_value = 5.0
    n1.inputs['Detail'].default_value = 4.0
    nt.links.new(mp.outputs['Vector'], n1.inputs['Vector'])
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.32
    ramp.color_ramp.elements[0].color = (0.915, 0.905, 0.880, 1)
    ramp.color_ramp.elements[1].position = 0.70
    ramp.color_ramp.elements[1].color = (0.855, 0.828, 0.762, 1)
    nt.links.new(n1.outputs['Fac'], ramp.inputs['Fac'])
    nt.links.new(ramp.outputs['Color'], b.inputs['Base Color'])
    n2 = nt.nodes.new('ShaderNodeTexNoise'); n2.inputs['Scale'].default_value = 700.0
    n2.inputs['Detail'].default_value = 2.0
    nt.links.new(mp.outputs['Vector'], n2.inputs['Vector'])
    bp = nt.nodes.new('ShaderNodeBump'); bp.inputs['Strength'].default_value = 0.03
    bp.inputs['Distance'].default_value = 0.0006
    nt.links.new(n2.outputs['Fac'], bp.inputs['Height'])
    nt.links.new(bp.outputs['Normal'], b.inputs['Normal'])
    setin(b, 'Metallic', 0.12); setin(b, 'Roughness', 0.17)
    setin(b, 'Coat Weight', 1.0); setin(b, 'Coat Roughness', 0.03)
    setin(b, 'Specular IOR Level', 0.6)
    M['pearl'] = m
    # --- graphite
    m, nt, b = new_mat('Graphite')
    tc = nt.nodes.new('ShaderNodeTexCoord')
    nz = nt.nodes.new('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = 180.0
    nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
    bp = nt.nodes.new('ShaderNodeBump'); bp.inputs['Strength'].default_value = 0.04
    bp.inputs['Distance'].default_value = 0.0006
    nt.links.new(nz.outputs['Fac'], bp.inputs['Height'])
    nt.links.new(bp.outputs['Normal'], b.inputs['Normal'])
    setin(b, 'Base Color', (0.034, 0.034, 0.038, 1))
    setin(b, 'Metallic', 0.20); setin(b, 'Roughness', 0.40)
    setin(b, 'Coat Weight', 0.30)
    M['graphite'] = m
    # --- champagne gold
    m, nt, b = new_mat('ChampagneGold')
    setin(b, 'Base Color', (0.760, 0.610, 0.370, 1))
    setin(b, 'Metallic', 1.0); setin(b, 'Roughness', 0.17)
    setin(b, 'Anisotropic', 0.55)
    M['gold'] = m
    # --- glass: alpha-blended so the lit cabin reads through the windows
    def glass(name, tint, rough, alpha):
        m, nt, b = new_mat(name)
        setin(b, 'Base Color', (*tint, 1))
        setin(b, 'Roughness', rough)
        setin(b, 'Transmission Weight', 0.0)
        setin(b, 'Alpha', alpha)
        setin(b, 'Specular IOR Level', 0.85)
        if hasattr(m, 'blend_method'):
            m.blend_method = 'BLEND'
        if hasattr(m, 'show_transparent_back'):
            m.show_transparent_back = False
        if hasattr(m, 'use_backface_culling'):
            m.use_backface_culling = False
        M[name] = m
        return m
    glass('TintGlass', (0.040, 0.038, 0.037), 0.05, 0.55)
    glass('WindGlass', (0.016, 0.016, 0.019), 0.04, 0.80)
    glass('BlackGlass', (0.018, 0.018, 0.021), 0.09, 0.86)
    # --- walnut
    m, nt, b = new_mat('Walnut')
    tc = nt.nodes.new('ShaderNodeTexCoord')
    mp = nt.nodes.new('ShaderNodeMapping'); mp.inputs['Scale'].default_value = (3.0, 3.0, 22.0)
    nt.links.new(tc.outputs['Object'], mp.inputs['Vector'])
    w = nt.nodes.new('ShaderNodeTexWave')
    w.bands_direction = 'Z'
    w.inputs['Scale'].default_value = 4.0
    w.inputs['Distortion'].default_value = 3.2
    w.inputs['Detail'].default_value = 3.0
    w.inputs['Detail Scale'].default_value = 1.4
    nt.links.new(mp.outputs['Vector'], w.inputs['Vector'])
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.18
    ramp.color_ramp.elements[0].color = (0.072, 0.040, 0.027, 1)
    ramp.color_ramp.elements[1].position = 0.86
    ramp.color_ramp.elements[1].color = (0.162, 0.098, 0.060, 1)
    ramp.color_ramp.elements.new(0.52).color = (0.114, 0.066, 0.040, 1)
    nt.links.new(w.outputs['Fac'], ramp.inputs['Fac'])
    nt.links.new(ramp.outputs['Color'], b.inputs['Base Color'])
    bp = nt.nodes.new('ShaderNodeBump'); bp.inputs['Strength'].default_value = 0.03
    nt.links.new(w.outputs['Fac'], bp.inputs['Height'])
    nt.links.new(bp.outputs['Normal'], b.inputs['Normal'])
    setin(b, 'Roughness', 0.32); setin(b, 'Coat Weight', 0.35)
    M['wood'] = m
    # --- marble
    m, nt, b = new_mat('Marble')
    tc = nt.nodes.new('ShaderNodeTexCoord')
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = 2.6; nz.inputs['Detail'].default_value = 8.0
    nz.inputs['Distortion'].default_value = 1.6
    nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
    w = nt.nodes.new('ShaderNodeTexWave')
    w.inputs['Scale'].default_value = 1.1; w.inputs['Distortion'].default_value = 4.5
    nt.links.new(nz.outputs['Fac'], w.inputs['Vector'])
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.20
    ramp.color_ramp.elements[0].color = (0.680, 0.672, 0.655, 1)
    ramp.color_ramp.elements[1].position = 0.72
    ramp.color_ramp.elements[1].color = (0.930, 0.925, 0.910, 1)
    nt.links.new(w.outputs['Fac'], ramp.inputs['Fac'])
    nt.links.new(ramp.outputs['Color'], b.inputs['Base Color'])
    setin(b, 'Roughness', 0.09); setin(b, 'Coat Weight', 1.0); setin(b, 'Coat Roughness', 0.02)
    M['marble'] = m
    # --- cream leather
    m, nt, b = new_mat('CreamLeather')
    tc = nt.nodes.new('ShaderNodeTexCoord')
    w1 = nt.nodes.new('ShaderNodeTexWave'); w1.inputs['Scale'].default_value = 9.0
    w1.inputs['Distortion'].default_value = 1.5; w1.bands_direction = 'X'
    w2 = nt.nodes.new('ShaderNodeTexWave'); w2.inputs['Scale'].default_value = 9.0
    w2.inputs['Distortion'].default_value = 1.5; w2.bands_direction = 'Y'
    nt.links.new(tc.outputs['Object'], w1.inputs['Vector'])
    nt.links.new(tc.outputs['Object'], w2.inputs['Vector'])
    mx = nt.nodes.new('ShaderNodeMath'); mx.operation = 'MAXIMUM'
    nt.links.new(w1.outputs['Fac'], mx.inputs[0]); nt.links.new(w2.outputs['Fac'], mx.inputs[1])
    nz = nt.nodes.new('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = 90.0
    nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
    ad = nt.nodes.new('ShaderNodeMath'); ad.operation = 'MULTIPLY'; ad.inputs[1].default_value = 0.35
    nt.links.new(mx.outputs[0], ad.inputs[0])
    bp = nt.nodes.new('ShaderNodeBump'); bp.inputs['Strength'].default_value = 0.14
    nt.links.new(ad.outputs[0], bp.inputs['Height'])
    nt.links.new(bp.outputs['Normal'], b.inputs['Normal'])
    setin(b, 'Base Color', (0.795, 0.735, 0.640, 1))
    setin(b, 'Roughness', 0.48); setin(b, 'Sheen Weight', 0.30)
    M['leather'] = m
    # --- fabric
    m, nt, b = new_mat('Fabric')
    tc = nt.nodes.new('ShaderNodeTexCoord')
    nz = nt.nodes.new('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = 220.0
    nz.inputs['Detail'].default_value = 4.0
    nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
    bp = nt.nodes.new('ShaderNodeBump'); bp.inputs['Strength'].default_value = 0.22
    nt.links.new(nz.outputs['Fac'], bp.inputs['Height'])
    nt.links.new(bp.outputs['Normal'], b.inputs['Normal'])
    setin(b, 'Base Color', (0.40, 0.33, 0.27, 1))
    setin(b, 'Roughness', 0.92); setin(b, 'Sheen Weight', 0.7)
    M['fabric'] = m
    # --- rubber / tyre
    m, nt, b = new_mat('Rubber')
    tc = nt.nodes.new('ShaderNodeTexCoord')
    w = nt.nodes.new('ShaderNodeTexWave'); w.inputs['Scale'].default_value = 45.0
    nt.links.new(tc.outputs['Object'], w.inputs['Vector'])
    bp = nt.nodes.new('ShaderNodeBump'); bp.inputs['Strength'].default_value = 0.55
    bp.inputs['Distance'].default_value = 0.005
    nt.links.new(w.outputs['Fac'], bp.inputs['Height'])
    nt.links.new(bp.outputs['Normal'], b.inputs['Normal'])
    setin(b, 'Base Color', (0.016, 0.016, 0.017, 1)); setin(b, 'Roughness', 0.85)
    M['rubber'] = m
    # --- bronze rim
    m, nt, b = new_mat('BronzeRim')
    setin(b, 'Base Color', (0.640, 0.450, 0.270, 1))
    setin(b, 'Metallic', 1.0); setin(b, 'Roughness', 0.22)
    setin(b, 'Anisotropic', 0.35)
    M['rim'] = m
    # --- metals
    def metal(name, col, rough):
        m, nt, b = new_mat(name)
        tc = nt.nodes.new('ShaderNodeTexCoord')
        nz = nt.nodes.new('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = 40.0
        nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
        bp = nt.nodes.new('ShaderNodeBump'); bp.inputs['Strength'].default_value = 0.07
        nt.links.new(nz.outputs['Fac'], bp.inputs['Height'])
        nt.links.new(bp.outputs['Normal'], b.inputs['Normal'])
        setin(b, 'Base Color', (*col, 1)); setin(b, 'Metallic', 1.0); setin(b, 'Roughness', rough)
        M[name] = m
        return m
    metal('ChassisSteel', (0.20, 0.21, 0.22), 0.52)
    metal('EngineMetal', (0.30, 0.31, 0.33), 0.36)
    metal('Chrome', (0.62, 0.63, 0.65), 0.10)
    metal('Exhaust', (0.16, 0.15, 0.14), 0.60)
    metal('Alu', (0.52, 0.53, 0.55), 0.28)
    mat_simple('BlackTrim', (0.016, 0.016, 0.018), 0.10, 0.32, **{'Coat Weight': 0.45})
    mat_simple('CreamPanel', (0.760, 0.705, 0.620), 0.0, 0.55)
    mat_simple('Ceiling', (0.850, 0.815, 0.755), 0.0, 0.70)
    mat_simple('DarkInterior', (0.050, 0.045, 0.040), 0.0, 0.60)
    mat_simple('RedPaint', (0.380, 0.015, 0.022), 0.25, 0.24, **{'Coat Weight': 1.0})
    mat_simple('SolarCell', (0.016, 0.022, 0.050), 0.55, 0.12)
    mat_simple('DroneBody', (0.400, 0.400, 0.420), 0.35, 0.30)
    mat_simple('RubberDark', (0.010, 0.010, 0.010), 0.0, 0.80)
    mat_simple('FloorTile', (0.480, 0.455, 0.420), 0.0, 0.20, **{'Coat Weight': 0.7})
    mat_simple('Backdrop', (0.330, 0.315, 0.300), 0.0, 0.95)
    # studio sweep: the floor falls off radially so the coach sits in a lit pool
    m, nt, b = new_mat('Sweep')
    tc = nt.nodes.new('ShaderNodeTexCoord')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(tc.outputs['Generated'], sep.inputs['Vector'])
    comb = nt.nodes.new('ShaderNodeCombineXYZ')
    nt.links.new(sep.outputs['X'], comb.inputs['X'])
    nt.links.new(sep.outputs['Y'], comb.inputs['Y'])
    dst = nt.nodes.new('ShaderNodeVectorMath'); dst.operation = 'DISTANCE'
    dst.inputs[1].default_value = (0.5, 0.5, 0.0)
    nt.links.new(comb.outputs['Vector'], dst.inputs[0])
    mr = nt.nodes.new('ShaderNodeMapRange')
    mr.inputs['From Min'].default_value = 0.0
    mr.inputs['From Max'].default_value = 0.30
    mr.inputs['To Min'].default_value = 0.0
    mr.inputs['To Max'].default_value = 1.0
    nt.links.new(dst.outputs['Value'], mr.inputs['Value'])
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (0.345, 0.330, 0.314, 1)
    ramp.color_ramp.elements[1].position = 1.0
    ramp.color_ramp.elements[1].color = (0.040, 0.039, 0.041, 1)
    ramp.color_ramp.elements.new(0.45).color = (0.150, 0.145, 0.142, 1)
    nt.links.new(mr.outputs['Result'], ramp.inputs['Fac'])
    nt.links.new(ramp.outputs['Color'], b.inputs['Base Color'])
    setin(b, 'Roughness', 0.92)
    M['Sweep'] = m
    mat_simple('PlantGreen', (0.055, 0.220, 0.062), 0.0, 0.55)
    mat_emit('LEDWarm', (1.0, 0.60, 0.26), 12.0)
    mat_emit('Cove', (1.0, 0.70, 0.40), 7.0)
    mat_emit('LEDWhite', (0.90, 0.95, 1.0), 16.0)
    mat_emit('LEDRed', (1.0, 0.035, 0.025), 12.0)
    mat_emit('LEDAmber', (1.0, 0.40, 0.05), 10.0)
    mat_emit('LEDGreen', (0.10, 1.0, 0.35), 6.0)
    for k in list(M):
        M[k.lower()] = M[k]
    M['aluwheel'] = M['Alu']

# ============================================================ body profile
ST = [
    (-5.92, 0.90, 3.10, 1.000, 0.20, 0.24),
    (-5.86, 0.86, 3.22, 1.140, 0.22, 0.30),
    (-5.72, 0.80, 3.36, 1.228, 0.26, 0.38),
    (-5.50, 0.74, 3.46, 1.264, 0.32, 0.42),
    (-5.10, 0.69, 3.51, 1.276, 0.36, 0.44),
    (-3.50, 0.65, 3.54, 1.278, 0.38, 0.45),
    (-1.00, 0.63, 3.56, 1.278, 0.40, 0.46),
    (1.50, 0.63, 3.56, 1.278, 0.40, 0.46),
    (3.60, 0.64, 3.54, 1.276, 0.40, 0.46),
    (4.80, 0.67, 3.48, 1.262, 0.40, 0.50),
    (5.45, 0.71, 3.34, 1.224, 0.42, 0.58),
    (5.85, 0.75, 3.16, 1.152, 0.44, 0.66),
    (6.05, 0.79, 3.00, 1.058, 0.46, 0.70),
    (6.12, 0.83, 2.90, 0.980, 0.48, 0.66),
]
X_REAR, X_FRONT = ST[0][0], ST[-1][0]
SHEAR = 0.23
# three near-continuous side window groups; slim pillars keep the greenhouse reading
# as one band rather than a row of punched-out boxes
WIN_SIDE = [(-5.35, -3.60), (-3.30, -1.00), (-0.70, 2.55)]
# side marker lamps, clear of the wheel arch cut-outs
MK_X = (5.50, 4.05, 1.55, -0.60, -2.05)

def prof(x, off=0.0):
    if x <= ST[0][0]:
        _, zb, zt, hw, rb, rt = ST[0]
    elif x >= ST[-1][0]:
        _, zb, zt, hw, rb, rt = ST[-1]
    else:
        for i in range(len(ST) - 1):
            if ST[i][0] <= x <= ST[i + 1][0]:
                t = (x - ST[i][0]) / (ST[i + 1][0] - ST[i][0])
                t = t * t * (3.0 - 2.0 * t)
                a, b = ST[i], ST[i + 1]
                zb = a[1] + (b[1] - a[1]) * t
                zt = a[2] + (b[2] - a[2]) * t
                hw = a[3] + (b[3] - a[3]) * t
                rb = a[4] + (b[4] - a[4]) * t
                rt = a[5] + (b[5] - a[5]) * t
                break
    return zb - off, zt + off, hw + off, rb + off * 0.5, rt + off * 0.5

def shp(x, y, z):
    if x > 5.10:
        t = min(1.0, (x - 5.10) / 1.02)
        x -= t * t * SHEAR * max(0.0, z - 1.00)
    return (x, y, z)

def xf(z, off=0.0):
    """world x of the sheared front-cap plane at height z"""
    return X_FRONT - SHEAR * max(0.0, z - 1.00) + off

def ring_pts(zb, zt, hw, rb, rt, n=10):
    h = zt - zb
    rb = max(0.002, min(rb, hw * 0.95, h * 0.48))
    # gentle tumblehome: the greenhouse leans inboard so the flank is not a flat wall
    ht = hw * 0.945
    rt = max(0.002, min(rt, ht * 0.95, h * 0.48))
    pts = []
    for (cy, cz), a0, a1, rr in (((hw - rb, zb + rb), -90, 0, rb),
                                 ((ht - rt, zt - rt), 0, 90, rt),
                                 ((-ht + rt, zt - rt), 90, 180, rt),
                                 ((-hw + rb, zb + rb), 180, 270, rb)):
        for i in range(n):
            a = R(a0 + (a1 - a0) * i / (n - 1.0))
            pts.append((cy + rr * math.cos(a), cz + rr * math.sin(a)))
    return pts

def sample_xs(step=0.115):
    xs = []
    for i in range(len(ST) - 1):
        x0, x1 = ST[i][0], ST[i + 1][0]
        k = max(2, int(round((x1 - x0) / step)))
        for j in range(k):
            xs.append(x0 + (x1 - x0) * j / k)
    xs.append(ST[-1][0])
    return xs

XS = sample_xs()

def loft(name, off=0.0, n=8, xs=None, mat=None, coll='RV', caps=(True, True)):
    xs = xs or XS
    verts, faces = [], []
    for x in xs:
        zb, zt, hw, rb, rt = prof(x, off)
        for (y, z) in ring_pts(zb, zt, hw, rb, rt, n):
            verts.append(shp(x, y, z))
    per = 4 * n
    for i in range(len(xs) - 1):
        for j in range(per):
            faces.append((i * per + j, i * per + (j + 1) % per,
                          (i + 1) * per + (j + 1) % per, (i + 1) * per + j))
    for idx, do in enumerate(caps):
        if not do:
            continue
        i = 0 if idx == 0 else len(xs) - 1
        base = i * per
        ring = [base + j for j in range(per)]
        zb, zt, hw, rb, rt = prof(xs[i], off)
        cen = len(verts)
        verts.append((xs[i], 0.0, 0.5 * (zb + zt)))
        for j in range(per):
            faces.append((cen, ring[j], ring[(j + 1) % per]))
    return solid_from(name, verts, faces, mat, coll)

def panel(name, off, bounds, thick=0.02, mat=None, n=8, xs=None, bev=0.0, coll='EXT'):
    """thin skin hugging the body surface at `off`, trimmed by a world box.

    Built as (outer solid - inner solid) so the result follows the compound
    curvature of the shell instead of reading as a flat box-cut plug.
    """
    (x0, x1), (y0, y1), (z0, z1) = bounds
    outer = loft(name + '_o', off=off + thick, n=n, xs=xs, coll='TMP2')
    inner = loft(name + '_i', off=off, n=n, xs=xs, coll='TMP2')
    boolean(outer, inner, 'DIFFERENCE')
    o = apply_all(outer)
    c = box(name + '_c', (x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2,
            x1 - x0, y1 - y0, z1 - z0, coll='TMP2')
    boolean(o, c, 'INTERSECT')
    o = apply_all(o)
    if bev > 0:
        bevel(o, bev, 2)
    o.name = name
    o.data.materials.clear()
    if mat:
        o.data.materials.append(mat)
    return link_to(o, coll)

# ============================================================ cutters
CUTTERS = []
CUTTER_OBJ = [None]

def arch_cutter(name):
    # the tandem arches overlap, so union them into one manifold shell: a joined
    # self-intersecting cutter makes the EXACT solver drop the whole boolean
    a = [prim('ar', 'cyl', r=0.755, d=3.6, loc=(ax, 0, 0.55), rot=(R(90), 0, 0), seg=56, coll='TMP2')
         for ax in AXLES]
    o = a[0]
    for n in a[1:]:
        n.hide_set(False)
        n.hide_render = False
        boolean(o, n, 'UNION')
        o = apply_all(o)
        n.hide_set(True)
        n.hide_render = True
    o.name = name
    return link_to(o, 'TMP2')

def build_body():
    body = loft('Body', 0.0, mat=M['pearl'], coll='BODY')
    # hollow the shell so window openings reveal a real cabin instead of solid white
    cav = loft('Cavity', off=-0.055, mat=M['pearl'], coll='TMP2')
    boolean(body, cav, 'DIFFERENCE')
    body = apply_all(body)
    win_side = WIN_SIDE
    for (x0, x1) in win_side:
        for s in (-1, 1):
            c = box('wc', (x0 + x1) / 2, s * 1.30, 2.34, x1 - x0, 0.70, 0.96, coll='TMP2')
            bevel(c, 0.085, 4, 60)
            CUTTERS.append(c)
    # entrance door (right side, ahead of front axle)
    d = box('dc', 4.72, -1.30, 1.60, 1.40, 0.80, 2.28, coll='TMP2')
    bevel(d, 0.09, 4, 60)
    CUTTERS.append(d)
    # rear lower garage opening (bottom half of rear face)
    g = box('gc', -5.95, 0, 1.32, 0.60, 1.86, 0.94, coll='TMP2')
    bevel(g, 0.07, 3, 60)
    CUTTERS.append(g)
    # front greenhouse opening (leaves pillars: |y|<1.13)
    fo = box('fc', 6.40, 0, 2.58, 1.60, 2.26, 1.72, coll='TMP2')
    bevel(fo, 0.10, 3, 60)
    CUTTERS.append(fo)
    # roof hatches
    for (cx, cy, sx, sy) in [(4.95, 0.0, 1.50, 1.40), (3.05, 0.0, 1.24, 1.00),
                             (-0.35, 0.0, 1.14, 0.90), (-3.60, 0.0, 1.04, 0.84)]:
        c = box('rc', cx, cy, 3.56, sx, sy, 0.60, coll='TMP2')
        bevel(c, 0.10, 3, 60)
        CUTTERS.append(c)
    # wheel arches
    CUTTERS.append(arch_cutter('ArchCutBody'))
    # skirt shadow-line groove
    gr = panel('groove', 0.014, ((X_REAR, X_FRONT), (-2, 2), (1.050, 1.072)),
               thick=0.034, coll='TMP2')
    CUTTERS.append(gr)
    # marker-lamp pockets
    for x in MK_X:
        for s in (-1, 1):
            c = box('mp', x, s * 1.29, 0.84, 0.15, 0.14, 0.075, coll='TMP2')
            bevel(c, 0.022, 2, 60)
            CUTTERS.append(c)
    keep = [c for i, c in enumerate(CUTTERS)
            if str(i) not in os.environ.get('RV_SKIP', '').split(',')]
    print('CUT n=%d polys=%d' % (len(keep), sum(len(c.data.polygons) for c in keep)))
    import bmesh
    bm = bmesh.new(); bm.from_mesh(body.data)
    nm = sum(1 for e in bm.edges if not e.is_manifold)
    print('BODY after cavity=%d nonmanifold_edges=%d' % (len(bm.faces), nm))
    bm.free()
    # cut one element at a time and apply: a joined union of overlapping shells is
    # self-intersecting, and the EXACT solver answers such a boolean with a stub mesh
    prev = len(body.data.polygons)
    for i, c in enumerate(keep):
        c.hide_set(False)
        c.hide_render = False
        boolean(body, c, 'DIFFERENCE')
        body = apply_all(body)
        c.hide_set(True)
        c.hide_render = True
        if len(body.data.polygons) < prev * 0.5:
            print('  !! collapse at cutter %d (%s) %d -> %d' % (i, c.name, prev, len(body.data.polygons)))
        prev = len(body.data.polygons)
    print('BODY cut=%d polys=%d' % (len(keep), len(body.data.polygons)))
    CUTTER_OBJ[0] = keep
    shade(body, 44)
    body.data.materials.clear()
    for nm in ('pearl', 'graphite', 'gold'):
        body.data.materials.append(M[nm])
    for p in body.data.polygons:
        p.material_index = 1 if p.center.z < 1.048 else 0
    return body

def build_cladding():
    objs = []
    arch = arch_cutter('ArchCutSkirt')
    sk = [panel('Skirt', 0.018, ((X_REAR - 0.02, X_FRONT + 0.02), (-2, 2), (-1, 1.048)),
                thick=0.040, mat=M['graphite'], coll='TMP2'),
          panel('BumperF', 0.036, ((5.20, X_FRONT + 0.30), (-2, 2), (-1, 0.95)),
                thick=0.055, mat=M['graphite'], coll='TMP2'),
          panel('BumperR', 0.036, ((X_REAR - 0.30, -5.20), (-2, 2), (-1, 0.95)),
                thick=0.055, mat=M['graphite'], coll='TMP2')]
    # cut each panel before merging: the bumper and skirt shells overlap, and a
    # self-intersecting target makes the EXACT solver leave the arch un-cut
    arch.hide_set(False)
    arch.hide_render = False
    for o in sk:
        boolean(o, arch, 'DIFFERENCE', keep=True)
    clad = join(sk, 'Cladding', coll='EXT')
    # valance blocks that hang below the body line
    low = []
    vb = box('fval', 5.72, 0, 0.62, 1.05, 2.30, 0.60, M['graphite'])
    bevel(vb, 0.14, 4, 50)
    low.append(vb)
    vb2 = box('rval', -5.68, 0, 0.62, 0.90, 2.34, 0.60, M['graphite'])
    bevel(vb2, 0.12, 4, 50)
    low.append(vb2)
    for s in (-1, 1):
        low.append(box('sill', 1.0, s * 1.20, 0.66, 7.60, 0.16, 0.14, M['graphite']))
    lw = join(low, 'Valance', coll='EXT')
    boolean(lw, arch, 'DIFFERENCE')
    objs += [clad, lw]
    gd = panel('GoldLine', 0.016, ((X_REAR + 0.10, X_FRONT + 0.02), (-2, 2), (1.552, 1.606)),
               thick=0.022, mat=M['gold'], coll='EXT')
    objs.append(gd)
    fr = []
    for (x0, x1) in WIN_SIDE:
        for s in (-1, 1):
            o = box('fo', (x0 + x1) / 2, s * 1.252, 2.34, x1 - x0 + 0.14, 0.060, 1.10,
                    M['BlackTrim'], coll='TMP2')
            bevel(o, 0.045, 3, 60)
            i = box('fi', (x0 + x1) / 2, s * 1.32, 2.34, x1 - x0 + 0.02, 0.22, 1.00, coll='TMP2')
            bevel(i, 0.075, 3, 60)
            boolean(o, i, 'DIFFERENCE')
            fr.append(apply_all(o))
    objs.append(join(fr, 'WinFrames', coll='EXT'))
    comp = []
    for (x0, x1) in [(2.05, 2.75), (0.45, 1.90), (-1.30, 0.25), (-2.80, -1.50)]:
        for s in (-1, 1):
            lo, hi = sorted((s * 0.55, s * 1.45))
            comp.append(panel('cp', 0.034, ((x0, x1), (lo, hi), (0.70, 1.02)),
                              thick=0.012, mat=M['graphite'],
                              xs=[x0 - 0.25, x0, x1, x1 + 0.25], coll='TMP2'))
    cmp_o = join(comp, 'Compartments', coll='EXT')
    boolean(cmp_o, arch, 'DIFFERENCE')
    objs.append(cmp_o)
    # wheel-well closures so the arches read as fenders, not holes into the cabin
    wells = []
    for ax in AXLES:
        for s in (-1, 1):
            wells.append(prim('fw', 'cyl', r=0.80, d=0.05, loc=(ax, s * 0.74, 0.55),
                              rot=(R(90), 0, 0), seg=48, mat=M['DarkInterior'], coll='TMP2'))
        wells.append(box('fwf', ax, 0, 0.62, 1.60, 1.44, 0.05, M['DarkInterior'], coll='TMP2'))
    objs.append(join(wells, 'FenderWells', coll='EXT'))
    for o in objs:
        shade(o, 44)
    return objs

def build_glass():
    objs = []
    xs = [5.00, 5.20, 5.40, 5.58, 5.75, 5.88, 6.00, 6.07, 6.12]
    g = panel('Windshield', -0.048, ((5.00, X_FRONT + 0.30), (-1.45, 1.45), (1.72, 3.52)),
              thick=0.034, mat=M["WindGlass"], n=8, xs=xs, coll='GLASS2')
    # clear the door out of the wrap-around band
    dcut = box('dcut', 4.72, -1.30, 1.60, 1.44, 0.90, 2.30, coll='TMP2')
    bevel(dcut, 0.09, 4, 60)
    boolean(g, dcut, 'DIFFERENCE')
    objs.append(g)
    # ceramic frit bands hide the raw cut edge of the shell behind the glass
    objs.append(panel('Frit', -0.016, ((5.00, X_FRONT + 0.30), (-1.45, 1.45), (3.14, 3.62)),
                      thick=0.026, mat=M['BlackTrim'], n=8, xs=xs, coll='GLASS2'))
    objs.append(panel('RoofBand', 0.012, ((5.20, X_FRONT + 0.30), (-1.45, 1.45), (3.16, 3.66)),
                      thick=0.026, mat=M['BlackGlass'], n=8,
                      xs=[5.20, 5.45, 5.70, 5.90, 6.05, 6.12], coll='GLASS2'))
    panes = []
    for (x0, x1) in WIN_SIDE:
        for s in (-1, 1):
            p = box('p', (x0 + x1) / 2, s * 1.228, 2.34, x1 - x0 - 0.02, 0.026, 0.93, coll='TMP2')
            bevel(p, 0.075, 4, 60)
            panes.append(p)
    dg = box('dg', 4.72, -1.235, 2.06, 1.26, 0.028, 0.84, coll='TMP2')
    bevel(dg, 0.055, 3, 60)
    panes.append(dg)
    for i, p in enumerate(panes):
        p.data.materials.append(M['TintGlass' if i < 6 else 'TintGlass'])
    sg = join(panes, 'SideGlass', coll='GLASS2')
    shade(sg, 50)
    objs.append(sg)
    # smoked rear panel glass
    rw = box('rearglass', -5.945, 0, 2.42, 0.035, 1.50, 0.34, M['BlackGlass'], coll='GLASS2')
    bevel(rw, 0.06, 3, 60)
    objs.append(rw)
    for o in objs:
        shade(o, 46)
    return objs

# ============================================================ running gear
AXLES = (2.90, -2.90, -4.30)

def build_wheel(i, ax, side):
    y = side * 1.10
    z = 0.55
    P = []
    t = prim('tire', 'cyl', r=0.555, d=0.290, loc=(ax, y, z), rot=(R(90), 0, 0), seg=56, mat=M['rubber'])
    bevel(t, 0.105, 5, 45)
    P.append(t)
    P.append(prim('inner', 'cyl', r=0.408, d=0.34, loc=(ax, y, z), rot=(R(90), 0, 0), seg=40, mat=M['graphite']))
    P.append(prim('dish', 'cyl', r=0.400, d=0.055, loc=(ax, y + side * 0.125, z), rot=(R(90), 0, 0), seg=40, mat=M['rim']))
    P.append(prim('lip', 'tor', R=0.392, r=0.030, loc=(ax, y + side * 0.150, z), rot=(R(90), 0, 0), seg=44, mseg=8, mat=M['rim']))
    for k in range(7):
        a = math.tau * k / 7.0 + 0.25
        rr = 0.235
        sp = box('spoke', ax + rr * math.cos(a), y + side * 0.140, z + rr * math.sin(a),
                 0.40, 0.062, 0.125, M['rim'])
        sp.rotation_euler = (0, -a, 0)
        P.append(sp)
    P.append(prim('hub', 'cyl', r=0.100, d=0.075, loc=(ax, y + side * 0.165, z), rot=(R(90), 0, 0), seg=24, mat=M['rim']))
    for k in range(5):
        a = math.tau * k / 5.0
        P.append(prim('lug', 'cyl', r=0.017, d=0.05, loc=(ax + 0.058 * math.cos(a), y + side * 0.200, z + 0.058 * math.sin(a)),
                      rot=(R(90), 0, 0), seg=10, mat=M['chrome']))
    w = join(P, 'Wheel_%d_%d' % (i, side), coll='WHEEL')
    shade(w, 38)
    return w

def build_wheels():
    return [build_wheel(i, ax, s) for i, ax in enumerate(AXLES) for s in (-1, 1)]

def build_chassis():
    P = []
    for s in (-1, 1):
        r = box('rail', -0.6, s * 0.62, 0.50, 9.6, 0.11, 0.22, M['ChassisSteel'])
        bevel(r, 0.018, 2, 60)
        P.append(r)
    for x in (-5.2, -3.7, -2.2, -0.7, 0.8, 2.3, 3.9):
        P.append(box('cross', x, 0, 0.50, 0.13, 1.32, 0.16, M['ChassisSteel']))
    for ax in AXLES:
        P.append(prim('axle', 'cyl', r=0.068, d=2.05, loc=(ax, 0, 0.55), rot=(R(90), 0, 0), seg=20, mat=M['ChassisSteel']))
        if ax < 0:
            d = prim('diff', 'sph', r=0.205, loc=(ax, 0, 0.55), seg=20, mat=M['ChassisSteel'])
            d.scale = (0.80, 1.0, 0.92)
            P.append(d)
            for s in (-1, 1):
                P.append(prim('halfshaft', 'cyl', r=0.055, d=0.62, loc=(ax, s * 0.42, 0.55),
                              rot=(R(90), 0, 0), seg=14, mat=M['Chrome']))
        else:
            P.append(box('steer', ax, 0, 0.55, 0.36, 1.55, 0.14, M['ChassisSteel']))
            for s in (-1, 1):
                P.append(box('knuckle', ax, s * 0.80, 0.55, 0.20, 0.16, 0.26, M['ChassisSteel']))
                P.append(box('track', ax - 0.30, s * 0.62, 0.52, 0.06, 0.42, 0.10, M['ChassisSteel']))
        for s in (-1, 1):
            P.append(prim('airbag', 'cyl', r=0.105, d=0.20, loc=(ax, s * 0.74, 0.66), seg=16, mat=M['RubberDark']))
            P.append(prim('shock', 'cyl', r=0.042, d=0.36, loc=(ax + 0.30, s * 0.80, 0.72), rot=(R(6 * s), 0, 0), seg=12, mat=M['Chrome']))
    P.append(prim('prop', 'cyl', r=0.078, d=6.8, loc=(-1.3, 0, 0.62), rot=(0, R(90), 0), seg=18, mat=M['Chrome']))
    P.append(prim('ujoin', 'sph', r=0.095, loc=(2.1, 0, 0.62), seg=14, mat=M['ChassisSteel']))
    P.append(box('fuel', 1.55, 0.78, 0.60, 1.45, 0.50, 0.42, M['ChassisSteel']))
    P.append(box('water', 1.55, -0.78, 0.60, 1.45, 0.50, 0.42, M['Alu']))
    for x in (0.10, -0.55):
        P.append(prim('airtank', 'cyl', r=0.135, d=1.00, loc=(x, 0.60, 0.72), rot=(0, R(90), 0), seg=18, mat=M['ChassisSteel']))
    P.append(prim('muff', 'cyl', r=0.115, d=2.30, loc=(-1.0, 0.95, 0.40), rot=(0, R(90), 0), seg=18, mat=M['Exhaust']))
    P.append(prim('tail', 'cyl', r=0.048, d=1.00, loc=(0.45, 0.95, 0.40), rot=(0, R(90), 0), seg=14, mat=M['Chrome']))
    P.append(box('gen', 3.30, 0.70, 0.64, 0.92, 0.46, 0.42, M['EngineMetal']))
    P.append(box('batt', 3.30, -0.70, 0.64, 0.82, 0.46, 0.42, M['ChassisSteel']))
    P.append(box('sump', -4.55, 0.30, 0.86, 1.30, 0.70, 0.22, M['ChassisSteel']))
    for ax in AXLES:
        P.append(box('apron', ax, 0, 0.40, 0.55, 1.95, 0.05, M['graphite']))
    o = join(P, 'Chassis', coll='CHASSIS')
    shade(o, 42)
    return o

def build_engine():
    P = []
    # transverse-inline six, mounted under the front floor (pusher space at the
    # rear is fully allocated to the garage bay and raised bed by the brief)
    ex, ey, ez = 4.28, 0.06, 0.64
    blk = box('block', ex, ey, ez, 1.44, 1.24, 0.50, M['EngineMetal'])
    bevel(blk, 0.045, 2, 60); P.append(blk)
    P.append(box('head', ex, ey, ez + 0.33, 1.32, 1.06, 0.17, M['ChassisSteel']))
    for i in range(6):
        P.append(prim('cover', 'cyl', r=0.070, d=0.30, loc=(ex - 0.52 + i * 0.21, ey, ez + 0.45),
                      rot=(0, R(90), 0), seg=14, mat=M['Alu']))
    for i in range(5):
        P.append(box('rib', ex - 0.52 + i * 0.26, ey, ez + 0.05, 0.045, 1.28, 0.055, M['ChassisSteel']))
    P.append(prim('turbo', 'cyl', r=0.140, d=0.24, loc=(ex + 0.80, ey + 0.34, ez + 0.06),
                  rot=(0, R(90), 0), seg=22, mat=M['Exhaust']))
    P.append(prim('tscroll', 'sph', r=0.130, loc=(ex + 0.94, ey + 0.34, ez + 0.06), seg=16, mat=M['Exhaust']))
    P.append(prim('intake', 'cyl', r=0.082, d=1.30, loc=(ex - 0.10, ey + 0.52, ez + 0.40),
                  rot=(0, R(90), 0), seg=18, mat=M['RubberDark']))
    P.append(prim('afilter', 'cyl', r=0.155, d=0.34, loc=(ex - 0.78, ey + 0.52, ez + 0.40),
                  rot=(0, R(90), 0), seg=22, mat=M['graphite']))
    tr = prim('trans', 'cyl', r=0.285, d=0.72, loc=(ex - 1.02, ey, ez - 0.06),
              rot=(0, R(90), 0), seg=26, mat=M['EngineMetal'])
    bevel(tr, 0.03, 2, 60); P.append(tr)
    P.append(prim('conv', 'cyl', r=0.220, d=0.26, loc=(ex - 1.46, ey, ez - 0.06),
                  rot=(0, R(90), 0), seg=22, mat=M['ChassisSteel']))
    P.append(prim('alt', 'cyl', r=0.105, d=0.26, loc=(ex - 0.30, ey - 0.62, ez + 0.02),
                  rot=(0, R(90), 0), seg=16, mat=M['Chrome']))
    P.append(prim('acomp', 'cyl', r=0.115, d=0.24, loc=(ex + 0.34, ey - 0.62, ez + 0.02),
                  rot=(0, R(90), 0), seg=16, mat=M['Alu']))
    P.append(prim('starter', 'cyl', r=0.082, d=0.34, loc=(ex + 0.52, ey + 0.58, ez - 0.22),
                  rot=(0, R(90), 0), seg=14, mat=M['EngineMetal']))
    P.append(prim('dpipe', 'cyl', r=0.058, d=1.05, loc=(ex + 0.62, ey + 0.44, ez - 0.20),
                  rot=(R(70), 0, 0), seg=14, mat=M['Exhaust']))
    P.append(prim('dpf', 'cyl', r=0.150, d=0.72, loc=(ex + 0.62, ey + 0.44, ez - 0.66),
                  rot=(0, R(90), 0), seg=20, mat=M['Exhaust']))
    # cooling pack behind the front grille
    P.append(box('rad', 5.42, ey, 0.72, 0.20, 1.46, 0.62, M['ChassisSteel']))
    for i in range(7):
        P.append(box('fin', 5.32, ey, 0.46 + i * 0.09, 0.05, 1.40, 0.026, M['Alu']))
    P.append(prim('fan', 'cyl', r=0.300, d=0.08, loc=(5.20, ey, 0.72), rot=(0, R(90), 0),
                  seg=28, mat=M['graphite']))
    for k in range(7):
        a = math.tau * k / 7.0
        P.append(box('blade', 5.20, ey + 0.16 * math.cos(a), 0.72 + 0.16 * math.sin(a),
                     0.045, 0.28, 0.075, M['Alu'], rot=(a, 0, 0)))
    for (loc, rot) in [((5.10, ey - 0.46, 0.98), (0, R(28), 0)), ((5.10, ey + 0.46, 0.98), (0, R(-26), 0))]:
        P.append(prim('hose', 'cyl', r=0.052, d=0.62, loc=loc, rot=rot, seg=12, mat=M['RubberDark']))
    P.append(box('pan', ex, ey, 0.33, 1.36, 1.14, 0.12, M['ChassisSteel']))
    P.append(box('shield', ex, ey, 0.99, 1.90, 1.60, 0.022, M['Alu']))
    P.append(box('cradle', ex - 0.30, ey, 0.40, 2.30, 1.70, 0.075, M['ChassisSteel']))
    P.append(box('cradle2', ex + 0.60, ey, 0.40, 0.90, 1.70, 0.075, M['ChassisSteel']))
    o = join(P, 'Engine', coll='ENGINE')
    shade(o, 44)
    return o

# ============================================================ exterior trim
def build_front():
    P = []
    P.append(box('rec', xf(1.40, -0.005), 0, 1.40, 0.10, 2.02, 0.17, M['BlackTrim']))
    P.append(box('bar', xf(1.40, 0.030), 0, 1.40, 0.05, 1.80, 0.070, M['LEDWhite']))
    for s in (-1, 1):
        P.append(box('drl', xf(1.60, 0.016), s * 0.70, 1.60, 0.05, 0.34, 0.040, M['LEDWhite']))
        P.append(box('fog', xf(0.55, 0.012), s * 0.55, 0.55, 0.05, 0.28, 0.10, M['LEDAmber']))
    P.append(box('grille', xf(0.80, 0.010), 0, 0.80, 0.05, 1.24, 0.20, M['graphite']))
    for i in range(5):
        P.append(box('slat', xf(0.80, 0.022), 0, 0.71 + i * 0.045, 0.03, 1.18, 0.014, M['BlackTrim']))
    P.append(box('plate', xf(1.05, 0.012), 0, 1.05, 0.03, 0.44, 0.13, M['CreamPanel']))
    P.append(box('nose_gold', xf(1.22, 0.014), 0, 1.22, 0.02, 1.00, 0.022, M['gold']))
    P.append(prim('badge', 'cyl', r=0.095, d=0.035, loc=(xf(2.10, 0.020), 0, 2.10), rot=(0, R(90), 0), seg=26, mat=M['gold']))
    for s in (-1, 1):
        w = box('wiper', xf(2.05, -0.010), s * 0.40, 2.05, 0.022, 0.86, 0.030, M['RubberDark'])
        w.rotation_euler = (R(-10 * s), R(4), R(s * 16))
        P.append(w)
        arm = box('marm', xf(2.30, 0.010), s * 1.40, 2.30, 0.11, 0.62, 0.065, M['graphite'])
        arm.rotation_euler = (R(10 * s), 0, 0)
        P.append(arm)
        pod = box('mpod', xf(2.18, -0.02), s * 1.66, 2.18, 0.14, 0.20, 0.42, M['graphite'])
        pod.rotation_euler = (0, R(6), R(s * 4))
        bevel(pod, 0.045, 3, 55)
        P.append(pod)
        P.append(box('lens', xf(2.02, -0.06), s * 1.66, 2.02, 0.025, 0.13, 0.055, M['BlackGlass']))
    P.append(box('step', 4.72, -1.31, 0.40, 1.28, 0.44, 0.10, M['graphite']))
    P.append(box('step2', 4.72, -1.16, 0.60, 1.28, 0.16, 0.06, M['Alu']))
    # the leaf is a skin that hugs the shell, so it closes the aperture flush instead
    # of reading as a flat slab parked against a curved body
    dl = panel('doorleaf', 0.006, ((3.96, 5.48), (-2.0, -1.0), (0.40, 2.80)),
               thick=0.030, mat=M['pearl'], coll='TMP2')
    ap = box('dap', 4.72, -1.30, 2.06, 1.18, 0.18, 0.84, coll='TMP2')
    bevel(ap, 0.065, 3, 60)
    boolean(dl, ap, 'DIFFERENCE')
    P.append(apply_all(dl))
    P.append(box('dglass', 4.72, -1.185, 2.06, 1.06, 0.024, 0.72, M['TintGlass']))
    se = panel('dseal', 0.014, ((3.86, 5.58), (-2.0, -1.0), (0.30, 2.90)),
               thick=0.026, mat=M['BlackTrim'], coll='TMP2')
    si = box('dsi', 4.72, -1.45, 1.60, 1.40, 1.10, 2.28, coll='TMP2')
    boolean(se, si, 'DIFFERENCE')
    P.append(apply_all(se))
    P.append(box('handle', 4.30, -1.275, 1.72, 0.055, 0.05, 0.28, M['Chrome']))
    # headlight washers / sensors
    for s in (-1, 1):
        P.append(prim('sensor', 'cyl', r=0.028, d=0.03, loc=(xf(1.02, 0.045), s * 0.42, 1.02), rot=(0, R(90), 0), seg=12, mat=M['BlackGlass']))
    o = join(P, 'FrontDetails', coll='EXT')
    shade(o, 46)
    return o

def build_rear():
    P = []
    P.append(box('rbarg', -5.935, 0, 2.96, 0.05, 2.10, 0.18, M['graphite']))
    P.append(box('rbar', -5.955, 0, 2.96, 0.04, 1.98, 0.085, M['LEDRed']))
    for s in (-1, 1):
        P.append(box('tl', -5.945, s * 0.90, 2.10, 0.04, 0.15, 1.20, M['LEDRed']))
        P.append(box('tl2', -5.945, s * 0.90, 1.30, 0.04, 0.15, 0.20, M['LEDAmber']))
    gd = box('gdoor', -5.945, 0, 1.32, 0.05, 1.80, 0.90, M['pearl'])
    bevel(gd, 0.028, 2, 60); P.append(gd)
    P.append(box('ghandle', -5.985, 0, 1.72, 0.05, 0.48, 0.05, M['Chrome']))
    P.append(box('lvrec', -5.935, 0.55, 2.42, 0.04, 0.66, 0.62, M['graphite']))
    for i in range(9):
        P.append(box('lv', -5.955, 0.55, 2.15 + i * 0.065, 0.03, 0.58, 0.028, M['BlackTrim']))
    P.append(box('hitch', -6.06, 0, 0.58, 0.32, 0.30, 0.15, M['ChassisSteel']))
    for s in (-1, 1):
        P.append(box('rmk', -5.955, s * 0.72, 0.60, 0.04, 0.22, 0.08, M['LEDAmber']))
    P.append(box('plate_r', -5.965, -0.55, 1.95, 0.03, 0.40, 0.13, M['CreamPanel']))
    o = join(P, 'RearDetails', coll='EXT')
    shade(o, 46)
    return o

def build_side_details():
    P = []
    aw = box('awning', -0.60, -1.288, 1.70, 6.20, 0.115, 0.17, M['graphite'])
    bevel(aw, 0.045, 3, 55); P.append(aw)
    for x in MK_X:
        for s in (-1, 1):
            P.append(box('amk', x, s * 1.288, 0.84, 0.14, 0.03, 0.055, M['LEDAmber']))
    for (x0, x1) in [(2.05, 2.75), (0.45, 1.90), (-1.30, 0.25), (-2.80, -1.50)]:
        for s in (-1, 1):
            P.append(box('ch', (x0 + x1) / 2, s * 1.305, 0.90, 0.22, 0.03, 0.05, M['Chrome']))
    P.append(prim('cap', 'cyl', r=0.100, d=0.05, loc=(1.00, -1.292, 1.92), rot=(R(90), 0, 0), seg=26, mat=M['Alu']))
    P.append(box('power', -1.90, -1.290, 1.92, 0.34, 0.04, 0.24, M['graphite']))
    P.append(prim('fuelcap', 'cyl', r=0.110, d=0.05, loc=(3.55, 1.292, 1.05), rot=(R(90), 0, 0), seg=26, mat=M['Chrome']))
    for i in range(4):
        P.append(box('rung', -5.30, 1.30, 0.98 + i * 0.27, 0.30, 0.035, 0.045, M['Alu']))
    # slide-out / bay window bulge on the left side (living area)
    P.append(box('bay', 0.60, 1.30, 2.34, 2.60, 0.055, 1.05, M['pearl']))
    o = join(P, 'SideDetails', coll='EXT')
    shade(o, 46)
    return o

# ============================================================ roof
def build_roof():
    P = []
    px, pz = 4.95, 3.552
    P.append(box('padbase', px, 0, pz + 0.050, 1.62, 1.50, 0.10, M['graphite']))
    P.append(box('paddeck', px, 0, pz + 0.125, 1.44, 1.36, 0.05, M['ChassisSteel']))
    for sx in (-1, 1):
        for sy in (-1, 1):
            P.append(prim('post', 'cyl', r=0.034, d=0.30, loc=(px + sx * 0.60, sy * 0.56, pz + 0.29), seg=12, mat=M['Chrome']))
            P.append(prim('pcap', 'sph', r=0.024, loc=(px + sx * 0.60, sy * 0.56, pz + 0.445), seg=10, mat=M['LEDGreen']))
    lf = box('lift', px, 0, pz + 0.335, 1.06, 0.96, 0.055, M['Alu'])
    bevel(lf, 0.018, 2, 60); P.append(lf)
    for sx in (-1, 1):
        for sy in (-1, 1):
            P.append(prim('leg', 'cyl', r=0.030, d=0.20, loc=(px + sx * 0.44, sy * 0.40, pz + 0.22), seg=10, mat=M['Chrome']))
    for (sx, sy) in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
        p = box('sp', px + sx * 0.72, sy * 0.50, pz + 0.20, 0.40, 0.44, 0.020, M['SolarCell'])
        p.rotation_euler = (R(-sy * 9), R(sx * 3), 0)
        P.append(p)
        f = box('spfr', px + sx * 0.72, sy * 0.50, pz + 0.180, 0.43, 0.47, 0.016, M['Alu'])
        f.rotation_euler = p.rotation_euler
        P.append(f)
    # ---------- drone
    dx, dz = px, pz + 0.50
    bd = box('drone', dx, 0, dz, 0.30, 0.34, 0.13, M['DroneBody'])
    bevel(bd, 0.05, 3, 55); P.append(bd)
    P.append(box('drone_top', dx, 0, dz + 0.10, 0.22, 0.24, 0.08, M['graphite']))
    P.append(prim('gimbal', 'sph', r=0.075, loc=(dx + 0.14, 0, dz - 0.05), seg=16, mat=M['graphite']))
    P.append(prim('dlens', 'cyl', r=0.035, d=0.05, loc=(dx + 0.21, 0, dz - 0.06), rot=(0, R(90), 0), seg=16, mat=M['BlackGlass']))
    for k in range(4):
        a = R(45 + 90 * k)
        ax_, ay_ = dx + 0.34 * math.cos(a), 0.34 * math.sin(a)
        arm = box('darm', (dx + ax_) / 2, ay_ / 2, dz - 0.01, 0.42, 0.070, 0.050, M['graphite'])
        arm.rotation_euler = (0, 0, -a)
        P.append(arm)
        P.append(prim('motor', 'cyl', r=0.055, d=0.12, loc=(ax_, ay_, dz + 0.045), seg=18, mat=M['DroneBody']))
        P.append(prim('mcap', 'cyl', r=0.030, d=0.05, loc=(ax_, ay_, dz + 0.12), seg=12, mat=M['Chrome']))
        for s in (0, 1):
            bl = box('blade', ax_, ay_, dz + 0.140, 0.30, 0.042, 0.007, M['RubberDark'])
            bl.rotation_euler = (0, 0, -a + R(90) * s + R(18))
            P.append(bl)
        P.append(prim('led', 'cyl', r=0.013, d=0.025, loc=(ax_, ay_, dz - 0.055), seg=8,
                      mat=M['LEDRed'] if k % 2 else M['LEDGreen']))
    # ---------- defense turret (rear, offset to vehicle left)
    tx, ty, tz = -3.35, 0.32, 3.552
    P.append(box('tring', tx, ty, tz + 0.06, 1.34, 1.24, 0.12, M['graphite']))
    tb = box('tbase', tx, ty, tz + 0.26, 1.06, 0.96, 0.30, M['graphite'])
    bevel(tb, 0.08, 3, 45); P.append(tb)
    th = box('thead', tx, ty, tz + 0.60, 0.88, 0.72, 0.42, M['graphite'])
    bevel(th, 0.12, 4, 40); P.append(th)
    t2 = box('ttop', tx - 0.06, ty, tz + 0.84, 0.62, 0.52, 0.16, M['BlackTrim'])
    bevel(t2, 0.05, 3, 45); P.append(t2)
    ang = R(-26)
    bar = prim('barrel', 'cyl', r=0.055, d=1.60, loc=(tx + 0.95 * math.cos(ang) + 0.25, ty + 0.95 * math.sin(ang), tz + 0.62),
               rot=(R(90), R(90 + 26), 0), seg=22, mat=M['Exhaust'])
    P.append(bar)
    P.append(prim('muzzle', 'cyl', r=0.078, d=0.24, loc=(tx + 1.72 * math.cos(ang) + 0.25, ty + 1.72 * math.sin(ang), tz + 0.62),
                  rot=(R(90), R(90 + 26), 0), seg=18, mat=M['graphite']))
    P.append(box('mantlet', tx + 0.44, ty + 0.22, tz + 0.62, 0.32, 0.44, 0.38, M['graphite']))
    P.append(box('optic', tx + 0.10, ty - 0.44, tz + 0.80, 0.28, 0.16, 0.17, M['BlackTrim']))
    P.append(prim('olens', 'cyl', r=0.050, d=0.05, loc=(tx + 0.25, ty - 0.44, tz + 0.80), rot=(0, R(90), 0), seg=14, mat=M['BlackGlass']))
    P.append(box('ammo', tx - 0.58, ty + 0.36, tz + 0.42, 0.46, 0.36, 0.32, M['graphite']))
    # ---------- AC / vents / solar / skylights
    for (cx, sx, sy, hz) in [(2.35, 1.36, 1.06, 0.22), (-0.55, 1.26, 1.00, 0.19), (-4.95, 0.86, 1.10, 0.15)]:
        a = box('ac', cx, 0, 3.552 + hz / 2, sx, sy, hz, M['graphite'])
        bevel(a, 0.13, 5, 45); P.append(a)
        P.append(box('acg', cx, 0, 3.552 + hz + 0.012, sx * 0.66, sy * 0.55, 0.028, M['BlackTrim']))
    for x in (1.40, -1.50, -4.20):
        v = box('vent', x, -0.58, 3.595, 0.55, 0.30, 0.09, M['graphite'])
        bevel(v, 0.03, 2, 55); P.append(v)
    P.append(box('rsolar', 0.90, 0.0, 3.566, 3.00, 1.86, 0.026, M['SolarCell']))
    P.append(box('sky1', 3.05, 0.0, 3.566, 1.20, 0.96, 0.040, M['BlackGlass']))
    P.append(box('sky2', -0.35, 0.0, 3.566, 1.10, 0.86, 0.040, M['BlackGlass']))
    P.append(prim('ant', 'cyl', r=0.018, d=0.34, loc=(-5.45, 0.78, 3.70), seg=10, mat=M['graphite']))
    P.append(prim('dish', 'cyl', r=0.15, d=0.05, loc=(-5.45, 0.78, 3.94),
                  rot=(R(52), 0, R(20)), seg=18, mat=M['CreamPanel']))
    P.append(prim('whip', 'cyl', r=0.014, d=0.60, loc=(5.55, -0.88, 3.85), rot=(0, R(12), 0), seg=8, mat=M['graphite']))
    P.append(box('spot', 5.72, 0, 3.30, 0.20, 0.44, 0.17, M['graphite']))
    o = join(P, 'RoofGear', coll='ROOF')
    shade(o, 44)
    return o

# ============================================================ interior
def seat(name, x, y, rotz, recline=8.0):
    P = []
    P.append(box('base', 0, 0, 0.06, 0.46, 0.46, 0.12, M['graphite']))
    P.append(prim('ped', 'cyl', r=0.23, d=0.05, loc=(0, 0, 0.02), seg=22, mat=M['Chrome']))
    P.append(box('cush', 0, 0, 0.44, 0.62, 0.60, 0.17, M['leather']))
    P.append(box('seatmid', 0, 0, 0.24, 0.56, 0.53, 0.28, M['leather']))
    bk = box('back', -0.28, 0, 0.44, 0.20, 0.60, 0.86, M['leather'])
    bk.location = (bk.location.x + 0, bk.location.y, bk.location.z)
    bk.rotation_euler = (0, R(recline), 0)
    P.append(bk)
    hr = box('headrest', -0.36, 0, 0.92, 0.16, 0.40, 0.24, M['leather'])
    hr.rotation_euler = (0, R(recline), 0)
    P.append(hr)
    for s in (-1, 1):
        P.append(box('arm', 0.02, s * 0.34, 0.60, 0.54, 0.09, 0.11, M['leather']))
        P.append(box('armst', 0.02, s * 0.34, 0.50, 0.07, 0.07, 0.22, M['DarkInterior']))
    for p in P:
        p.location = p.location + Vector((0, 0, 0.97))
    o = join(P, name)
    bevel(o, 0.028, 2, 60)
    bake(o)
    o.location = (x, y, 0)
    o.rotation_euler = (0, 0, rotz)
    shade(o, 52)
    return o

def build_interior():
    objs = []
    # inner liner: a skin riding just inside the cavity, opened by the same cutters
    lin = panel('Liner', -0.145, ((X_REAR - 0.5, X_FRONT + 0.5), (-2, 2), (-1, 4.5)),
                thick=0.080, mat=M['CreamPanel'], coll='INT')
    for c in (CUTTER_OBJ[0] or []):
        c.hide_set(False)
        c.hide_render = False
        boolean(lin, c, 'DIFFERENCE')
        lin = apply_all(lin)
        c.hide_set(True)
        c.hide_render = True
    shade(lin, 46)
    objs.append(lin)
    P = []
    P.append(box('floor', -0.20, 0, 0.955, 11.40, 2.32, 0.06, M['FloorTile']))
    P.append(box('ceil', -0.20, 0, 3.40, 11.10, 2.24, 0.05, M['Ceiling']))
    o = join(P, 'InteriorPanels', coll='INT')
    shade(o, 46)
    objs.append(o)
    # cove lighting
    cv = []
    for s in (-1, 1):
        cv.append(box('cove', -0.20, s * 0.92, 3.355, 10.60, 0.06, 0.028, M['Cove']))
    cv.append(box('cove3', -4.60, 0, 3.355, 1.90, 1.70, 0.024, M['Cove']))
    objs.append(join(cv, 'InteriorLED', coll='INT'))
    dl = []
    for x in (-4.6, -3.2, -1.6, 0.0, 1.6, 3.2, 4.6):
        for y in (-0.55, 0.55):
            dl.append(prim('dl', 'cyl', r=0.055, d=0.022, loc=(x, y, 3.375), seg=12, mat=M['LEDWarm']))
    objs.append(join(dl, 'Downlights', coll='INT'))
    # ---------- cab
    dp = []
    dsh = box('dash', 5.38, 0.10, 1.52, 0.60, 2.10, 0.44, M['DarkInterior'])
    bevel(dsh, 0.09, 3, 55); dp.append(dsh)
    dp.append(box('dash_top', 5.26, 0.10, 1.755, 0.80, 2.06, 0.06, M['leather']))
    dp.append(box('dash_wood', 5.14, 0.10, 1.40, 0.10, 2.00, 0.24, M['wood']))
    dp.append(box('screen', 5.52, 0.55, 1.70, 0.05, 0.56, 0.22, M['BlackGlass']))
    dp.append(box('screen2', 5.52, -0.32, 1.70, 0.05, 0.46, 0.18, M['BlackGlass']))
    dp.append(prim('swrim', 'tor', R=0.215, r=0.024, loc=(5.10, 0.62, 1.70), rot=(R(70), 0, R(16)), seg=30, mseg=8, mat=M['RubberDark']))
    dp.append(prim('swcol', 'cyl', r=0.050, d=0.32, loc=(5.24, 0.62, 1.66), rot=(0, R(90), 0), seg=14, mat=M['Chrome']))
    for k in range(3):
        a = R(90 * k + 30)
        dp.append(box('swsp', 5.12, 0.62 + 0.105 * math.cos(a), 1.68 + 0.105 * math.sin(a), 0.04, 0.20, 0.04, M['Chrome']))
    dp.append(box('console', 4.72, 0.03, 1.20, 0.80, 0.44, 0.28, M['DarkInterior']))
    objs.append(join(dp, 'Dashboard', coll='INT'))
    objs.append(seat('seat_L', 4.62, 0.62, 0.0, 8.0))
    objs.append(seat('seat_R', 4.62, -0.55, 0.0, 8.0))
    # ---------- lounge
    lp = []
    lp.append(box('sofa1', 3.45, -0.82, 1.30, 2.10, 0.64, 0.44, M['leather']))
    lp.append(box('sofa1b', 3.45, -1.08, 1.66, 2.10, 0.18, 0.66, M['leather']))
    lp.append(box('sofa2', 4.30, 0.10, 1.30, 0.64, 1.60, 0.44, M['leather']))
    lp.append(box('sofa2b', 4.58, 0.10, 1.66, 0.18, 1.60, 0.66, M['leather']))
    lp.append(box('sofa3', 3.45, 0.80, 1.30, 2.10, 0.56, 0.44, M['leather']))
    lp.append(box('sofa3b', 3.45, 1.05, 1.66, 2.10, 0.14, 0.66, M['leather']))
    for x in (2.80, 3.45, 4.10):
        c = box('cush', x, -0.80, 1.56, 0.60, 0.58, 0.15, M['leather'])
        bevel(c, 0.06, 3, 60); lp.append(c)
    for (px, py, rz) in [(3.05, -1.00, 8), (3.85, -1.00, -7), (4.42, 0.50, 0)]:
        p = box('pil', px, py, 1.82, 0.15, 0.42, 0.42, M['fabric'])
        p.rotation_euler = (R(rz), 0, 0)
        bevel(p, 0.07, 3, 60); lp.append(p)
    lp.append(prim('tbaser', 'cyl', r=0.30, d=0.05, loc=(3.35, 0.00, 1.01), seg=26, mat=M['gold']))
    lp.append(prim('tstem', 'cyl', r=0.115, d=0.58, loc=(3.35, 0.00, 1.28), seg=22, mat=M['gold']))
    top = prim('ttop', 'cyl', r=0.56, d=0.055, loc=(3.35, 0.00, 1.56), seg=44, mat=M['marble'])
    bevel(top, 0.02, 3, 60); lp.append(top)
    lp.append(prim('vase', 'cyl', r=0.065, d=0.18, loc=(3.35, 0.00, 1.67), seg=18, mat=M['marble']))
    for k in range(7):
        a = R(k * 51)
        lp.append(prim('stem', 'cyl', r=0.008, d=0.24, loc=(3.35 + 0.05 * math.cos(a), 0.05 * math.sin(a), 1.85),
                      rot=(R(14 * math.cos(a)), R(14 * math.sin(a)), 0), seg=6, mat=M['PlantGreen']))
        lp.append(prim('leaf', 'ico', r=0.055, loc=(3.35 + 0.12 * math.cos(a), 0.12 * math.sin(a), 1.96), seg=1, mat=M['PlantGreen']))
    objs.append(join(lp, 'Lounge', coll='INT'))
    objs.append(seat('chair_lounge', 2.28, 0.42, R(155), 12.0))
    # ---------- kitchen
    kp = []
    kp.append(box('kcab', 1.00, -0.92, 1.30, 2.60, 0.62, 0.70, M['wood']))
    ct = box('ccount', 1.00, -0.90, 1.665, 2.66, 0.70, 0.05, M['marble'])
    bevel(ct, 0.018, 2, 60); kp.append(ct)
    kp.append(box('kupcab', 1.00, -0.96, 2.66, 2.60, 0.40, 0.72, M['wood']))
    kp.append(box('sink', 1.80, -0.88, 1.66, 0.52, 0.36, 0.05, M['Chrome']))
    kp.append(box('sinkin', 1.80, -0.88, 1.60, 0.44, 0.28, 0.11, M['Alu']))
    kp.append(prim('faucet', 'cyl', r=0.022, d=0.36, loc=(2.02, -1.06, 1.84), seg=12, mat=M['gold']))
    kp.append(prim('fauc2', 'cyl', r=0.020, d=0.30, loc=(2.02, -0.94, 2.00), rot=(R(90), 0, 0), seg=12, mat=M['gold']))
    kp.append(box('hob', 0.40, -0.86, 1.695, 0.62, 0.44, 0.02, M['BlackGlass']))
    for (dx, dy) in [(-0.14, -0.10), (0.14, -0.10), (-0.14, 0.10), (0.14, 0.10)]:
        kp.append(prim('ring', 'tor', R=0.070, r=0.006, loc=(0.40 + dx, -0.86 + dy, 1.708), seg=20, mseg=6, mat=M['LEDRed']))
    for x in (-0.10, 0.80, 1.70):
        kp.append(box('khandle', x, -0.585, 1.44, 0.24, 0.025, 0.03, M['gold']))
    kp.append(box('splash', 1.00, -0.98, 2.12, 2.50, 0.03, 0.62, M['marble']))
    kp.append(box('fridge', -0.60, 0.86, 1.74, 0.74, 0.62, 1.56, M['Alu']))
    kp.append(box('frhandle', -0.24, 0.555, 1.95, 0.04, 0.04, 0.58, M['gold']))
    objs.append(join(kp, 'Kitchen', coll='INT'))
    oc = []
    for s in (-1, 1):
        # keep clear of the shell: the greenhouse tumbles inboard above the belt line
        c = box('oc', 0.60, s * 0.84, 2.86, 6.40, 0.36, 0.56, M['wood'])
        bevel(c, 0.03, 2, 60); oc.append(c)
    objs.append(join(oc, 'Overheads', coll='INT'))
    # ---------- bath
    bp = []
    bp.append(box('bwall', -2.05, 0.72, 1.92, 1.50, 0.05, 1.92, M['marble']))
    bp.append(box('bwall2', -2.80, 0.78, 1.92, 0.05, 0.66, 1.92, M['marble']))
    bp.append(box('vanity', -1.72, 0.90, 1.30, 0.80, 0.44, 0.68, M['wood']))
    bp.append(box('vcount', -1.72, 0.90, 1.655, 0.84, 0.48, 0.05, M['marble']))
    bp.append(box('vbasin', -1.72, 0.90, 1.71, 0.38, 0.28, 0.13, M['marble']))
    bp.append(prim('vtap', 'cyl', r=0.020, d=0.26, loc=(-1.72, 0.74, 1.80), seg=10, mat=M['gold']))
    bp.append(box('mirror', -1.72, 1.08, 2.20, 0.64, 0.03, 0.52, M['Chrome']))
    bp.append(box('toilet', -2.45, 0.90, 1.20, 0.38, 0.50, 0.46, M['CreamPanel']))
    bp.append(box('toilet2', -2.45, 1.06, 1.45, 0.34, 0.46, 0.06, M['CreamPanel']))
    bp.append(box('shower', -2.32, 0.70, 1.95, 0.02, 0.52, 1.90, M['TintGlass']))
    bp.append(prim('shhead', 'cyl', r=0.075, d=0.03, loc=(-2.60, 0.90, 2.55), rot=(R(20), 0, 0), seg=14, mat=M['gold']))
    objs.append(join(bp, 'Bath', coll='INT'))
    # ---------- rear raised bedroom
    rp = []
    rp.append(box('bedplat', -4.78, 0, 1.31, 1.94, 2.22, 0.14, M['wood']))
    for x in (-5.58, -4.78, -3.98):
        rp.append(box('bedcab', x, 0, 1.04, 0.70, 2.12, 0.56, M['wood']))
    mt = box('mattress', -4.78, 0, 1.51, 1.88, 2.12, 0.24, M['CreamPanel'])
    bevel(mt, 0.09, 3, 60); rp.append(mt)
    dv = box('duvet', -4.36, 0, 1.61, 1.20, 2.14, 0.10, M['leather'])
    bevel(dv, 0.06, 3, 60); rp.append(dv)
    for py in (-0.52, 0.52):
        p = box('pillow', -5.50, py, 1.72, 0.30, 0.62, 0.17, M['CreamPanel'])
        p.rotation_euler = (0, R(-12), 0)
        bevel(p, 0.075, 3, 60); rp.append(p)
    for (py, c) in [(-0.20, 'fabric'), (0.24, 'leather')]:
        p = box('pillow2', -5.30, py, 1.76, 0.18, 0.40, 0.34, M[c])
        bevel(p, 0.07, 3, 60); rp.append(p)
    rp.append(box('headb', -5.74, 0, 1.98, 0.12, 2.12, 0.82, M['leather']))
    for s in (-1, 1):
        rp.append(box('rdl', -5.64, s * 0.76, 2.44, 0.06, 0.10, 0.26, M['LEDWarm']))
    for i in range(3):
        rp.append(box('bst', -3.72, -0.30, 1.02 + i * 0.16, 0.46, 0.62, 0.14, M['wood']))
    rp.append(box('ward', -3.18, 0.86, 1.88, 0.56, 0.62, 1.62, M['wood']))
    objs.append(join(rp, 'Bedroom', coll='INT'))
    # ---------- rear low garage (under bedroom)
    gp = []
    gp.append(box('gfloor', -4.85, 0, 0.995, 2.00, 2.14, 0.04, M['graphite']))
    cb = box('car_body', -4.85, 0, 1.18, 1.78, 0.96, 0.22, M['RedPaint'])
    bevel(cb, 0.07, 3, 55); gp.append(cb)
    cc = box('car_cab', -4.95, 0, 1.40, 0.86, 0.80, 0.26, M['RedPaint'])
    bevel(cc, 0.11, 3, 50); gp.append(cc)
    gp.append(box('car_glass', -4.95, 0, 1.44, 0.72, 0.72, 0.10, M['BlackGlass']))
    nz = box('car_nose', -3.82, 0, 1.16, 0.40, 0.92, 0.16, M['RedPaint'])
    bevel(nz, 0.06, 3, 55); gp.append(nz)
    for sx in (-1, 1):
        for dx in (-0.62, 0.62):
            gp.append(prim('cw', 'cyl', r=0.135, d=0.10, loc=(-4.85 + dx, sx * 0.48, 1.06), rot=(R(90), 0, 0), seg=20, mat=M['RubberDark']))
    for s in (-1, 1):
        gp.append(box('chd', -3.62, s * 0.30, 1.20, 0.05, 0.20, 0.09, M['LEDWhite']))
    objs.append(join(gp, 'GarageCar', coll='INT'))
    # lights
    for i, x in enumerate((-4.6, -2.0, 0.8, 3.4, 4.9)):
        ld = bpy.data.lights.new('int_%d' % i, 'POINT')
        ld.energy = 95.0
        ld.color = (1.0, 0.70, 0.44)
        ld.shadow_soft_size = 0.30
        lo = bpy.data.objects.new('int_%d' % i, ld)
        lo.location = (x, 0, 3.05)
        link_to(lo, 'INT')
        objs.append(lo)
    for i, x in enumerate((-4.9, 1.0, 3.4)):
        ld = bpy.data.lights.new('intw_%d' % i, 'POINT')
        ld.energy = 45.0
        ld.color = (1.0, 0.78, 0.52)
        ld.shadow_soft_size = 0.20
        lo = bpy.data.objects.new('intw_%d' % i, ld)
        lo.location = (x, -0.5, 1.9)
        link_to(lo, 'INT')
        objs.append(lo)
    # the cabin lamps only lift the interior; letting them cast cube shadows blows
    # past Eevee's shadow buffer and the ground shadow disappears
    for ld in bpy.data.lights:
        if ld.name.startswith('int'):
            try:
                ld.use_shadow = False
            except Exception:
                pass
    for o in objs:
        if o.type == 'MESH':
            shade(o, 52)
    return objs

# ============================================================ env / render
def build_env():
    bpy.ops.mesh.primitive_plane_add(size=1.0, location=(0, 0, 0))
    g = bpy.context.active_object
    g.name = 'Ground'
    g.scale = (120, 120, 1)
    g.data.materials.append(M['Sweep'])
    link_to(g, 'ENV')
    w = bpy.data.worlds.get('World') or bpy.data.worlds.new('World')
    bpy.context.scene.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes.get('Background')
    bg.inputs['Color'].default_value = (0.245, 0.250, 0.262, 1)
    bg.inputs['Strength'].default_value = 0.30

    def area(name, loc, rot, size, energy, col, sy=None):
        ld = bpy.data.lights.new(name, 'AREA')
        ld.energy = energy
        ld.color = col
        ld.size = size
        if sy:
            ld.shape = 'RECTANGLE'
            ld.size_y = sy
        o = bpy.data.objects.new(name, ld)
        o.location = loc
        o.rotation_euler = rot
        link_to(o, 'ENV')
        return o
    area('key', (14, -15, 17), (R(36), R(30), R(30)), 16, 1500, (1.0, 0.97, 0.92), 16)
    area('fill', (-4, -20, 8), (R(74), R(-16), R(-14)), 20, 620, (0.90, 0.93, 1.0), 12)
    area('rim', (-16, 14, 11), (R(58), R(38), R(205)), 18, 1100, (1.0, 0.96, 0.90), 14)
    area('top', (0, 0, 20), (0, 0, 0), 26, 520, (1.0, 1.0, 1.0), 26)
    sd = bpy.data.lights.new('sun', 'SUN')
    sd.energy = 1.6
    sd.color = (1.0, 0.96, 0.90)
    sd.angle = R(2.5)
    so = bpy.data.objects.new('sun', sd)
    so.rotation_euler = (R(46), R(12), R(36))
    link_to(so, 'ENV')
    cd = bpy.data.cameras.new('Cam')
    cd.lens = 50
    cd.sensor_width = 36
    cd.clip_end = 500
    co = bpy.data.objects.new('Camera', cd)
    link_to(co, 'ENV')
    tgt = empty('cam_target', (0.75, -0.35, 1.80))
    co.location = (19.0, -15.6, 16.7)
    c = co.constraints.new('TRACK_TO')
    c.target = tgt
    c.track_axis = 'TRACK_NEGATIVE_Z'
    c.up_axis = 'UP_Y'
    bpy.context.scene.camera = co
    return co

def setup_render():
    sc = bpy.context.scene
    sc.render.engine = 'BLENDER_EEVEE'
    ee = sc.eevee
    ee.taa_render_samples = int(os.environ.get('RV_SAMPLES', '64'))
    ee.use_raytracing = True
    ee.use_shadows = True
    ee.use_volumetric_shadows = True
    ee.shadow_resolution_scale = 1.5
    ee.gi_diffuse_bounces = 2
    try:
        ee.use_fast_gi = True
    except Exception:
        pass
    sc.render.resolution_x = 1920
    sc.render.resolution_y = 1080
    sc.render.resolution_percentage = int(os.environ.get('RV_RES', '100'))
    for vt in ('AgX', 'Filmic', 'Standard'):
        try:
            sc.view_settings.view_transform = vt
            break
        except Exception:
            continue
    try:
        sc.view_settings.look = 'AgX - Medium High Contrast'
    except Exception:
        try:
            sc.view_settings.look = 'None'
        except Exception:
            pass
    sc.view_settings.exposure = float(os.environ.get('RV_EXP', '0.0'))
    print('view_transform =', sc.view_settings.view_transform, 'look =', sc.view_settings.look)
    sc.use_nodes = True
    nt = getattr(sc, 'compositing_node_group', None)
    if nt is None:
        nt = bpy.data.node_groups.new('Compositing', 'CompositorNodeTree')
        sc.compositing_node_group = nt
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    rl = nt.nodes.new('CompositorNodeRLayers'); rl.location = (-700, 0)

    def safe(idname, loc):
        try:
            n = nt.nodes.new(idname)
            n.location = loc
            return n
        except Exception as e:
            print('node unavailable', idname, e)
            return None

    def nset(node, key, val):
        if node is None:
            return
        try:
            setattr(node, key, val)
            return
        except Exception:
            pass
        if key in getattr(node, 'inputs', ()):
            try:
                node.inputs[key].default_value = val
            except Exception:
                pass

    chain = []
    gl = safe('CompositorNodeGlare', (-450, 0))
    nset(gl, 'type', 'FOG_GLOW')
    nset(gl, 'glare_type', 'FOG_GLOW')
    nset(gl, 'quality', 'HIGH')
    nset(gl, 'threshold', 0.95)
    nset(gl, 'size', 7)
    nset(gl, 'mix', -0.72)
    chain.append(gl)
    hs = safe('CompositorNodeHueSat', (100, 0))
    if hs is not None:
        for nm, v in (('Saturation', 1.05), ('Value', 1.02)):
            if nm in hs.inputs:
                hs.inputs[nm].default_value = v
    chain.append(hs)
    cp = nt.nodes.new('NodeGroupOutput'); cp.location = (520, 0)
    nodes = [rl] + [n for n in chain if n is not None] + [cp]

    def sock(node, want_in):
        """compositor socket names differ across 4.x/5.x; resolve by type instead"""
        coll = node.inputs if want_in else node.outputs
        for s in coll:
            if s.type in ('RGBA', 'COLOR', 'NodeSocketColor'):
                return s
        return coll[0] if len(coll) else None

    for a, b in zip(nodes, nodes[1:]):
        try:
            sa, sb = sock(a, False), sock(b, True)
            if sa is None or sb is None:
                print('socket missing on', a.name, b.name)
                continue
            nt.links.new(sa, sb)
        except Exception as e:
            print('link fail', a.name, b.name, e)
    print('compositor chain:', [n.name for n in nodes])

def hide_scratch():
    """TMP holds every boolean cutter; hide the objects so nothing leaks into the frame"""
    c = bpy.data.collections.get('TMP2')
    if not c:
        return
    c.hide_render = True
    for o in c.objects:
        o.hide_render = True
        if o.name in bpy.context.view_layer.objects:
            o.hide_set(True)

# ============================================================ main
def main():
    clear_all()
    build_mats()
    tick('materials')
    build_body()
    tick('body')
    if os.environ.get('RV_ONLY') == 'body':
        return
    build_cladding()
    tick('cladding')
    build_glass()
    tick('glass')
    hide_scratch()
    tick('scratch hidden')
    build_wheels()
    tick('wheels')
    build_chassis()
    build_engine()
    tick('chassis+engine')
    build_front()
    build_rear()
    build_side_details()
    tick('exterior trim')
    build_roof()
    tick('roof')
    build_interior()
    tick('interior')
    build_env()
    setup_render()
    tick('env+render setup')
    os.makedirs(OUT, exist_ok=True)
    tag = os.environ.get('RV_TAG', 'v1')
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, 'starpark_bus_rv_%s.blend' % tag))
    tick('save blend')
    sc = bpy.context.scene
    sc.render.filepath = os.path.join(OUT, 'render_%s.png' % tag)
    bpy.ops.render.render(write_still=True)
    tick('RENDER DONE ' + tag)

main()
