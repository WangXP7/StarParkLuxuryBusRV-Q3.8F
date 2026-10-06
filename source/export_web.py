import bpy
import os

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'output')
dst = os.path.join(OUT, 'web', 'assets', 'starpark_rv.glb')
os.makedirs(os.path.dirname(dst), exist_ok=True)

SCRATCH = {'TMP2'}

# The glTF exporter cannot read a base colour that is driven by nodes, so it writes
# white. Flatten each procedural material onto its colour-ramp's brightest stop,
# which is the dominant tone of that surface.
FALLBACK = {
    'PearlWhite': (0.86, 0.86, 0.88),
    'Walnut': (0.13, 0.08, 0.05),
    'Marble': (0.86, 0.85, 0.84),
    'BronzeRim': (0.64, 0.45, 0.27),
    'TintGlass': (0.05, 0.05, 0.06),
    'WindGlass': (0.35, 0.42, 0.48),
    'BlackGlass': (0.02, 0.02, 0.02),
}
EMISSIVE = {
    'LEDWarm': ((1.0, 0.62, 0.30), 6.0),
    'LEDWhite': ((0.95, 0.97, 1.0), 5.0),
    'LEDAmber': ((1.0, 0.52, 0.12), 5.0),
    'LEDRed': ((1.0, 0.06, 0.06), 4.0),
    'LEDGreen': ((0.25, 1.0, 0.45), 4.0),
    'Cove': ((1.0, 0.68, 0.36), 5.0),
}

for m in bpy.data.materials:
    if not m.use_nodes:
        continue
    nt = m.node_tree
    b = nt.nodes.get('Principled BSDF')
    if b is None:
        continue
    col = FALLBACK.get(m.name)
    base = b.inputs.get('Base Color')
    if base is not None and base.is_linked:
        src = base.links[0].from_node
        ramp = src if src.type == 'VALTORGB' else None
        if ramp is None:
            for l in src.inputs:
                if l.is_linked and l.links[0].from_node.type == 'VALTORGB':
                    ramp = l.links[0].from_node
                    break
        if ramp is not None:
            col = tuple(ramp.color_ramp.elements[-1].color[:3])
        if col is not None:
            nt.links.remove(base.links[0])
            base.default_value = (*col, 1.0)
    em = b.inputs.get('Emission Color')
    if em is not None and m.name in EMISSIVE:
        c, s = EMISSIVE[m.name]
        em.default_value = (*c, 1.0)
        b.inputs['Emission Strength'].default_value = s

sc = bpy.context.scene
bpy.ops.object.select_all(action='DESELECT')
kept = []
tris = 0
for o in sc.objects:
    if o.type != 'MESH' or o.hide_render:
        continue
    if any(c.name in SCRATCH for c in o.users_collection):
        continue
    if o.name == 'Ground':
        continue
    ev = o.evaluated_get(bpy.context.evaluated_depsgraph_get())
    tris += sum(len(p.vertices) - 2 for p in ev.data.polygons)
    o.select_set(True)
    kept.append(o.name)
print('EXPORT selected=%d triangles=%d' % (len(kept), tris))
print('NODES ' + ' '.join(sorted(kept)))

bpy.ops.export_scene.gltf(
    filepath=dst,
    export_format='GLB',
    use_selection=True,
    export_apply=True,
    export_yup=True,
    export_materials='EXPORT',
    export_extras=False,
    export_cameras=False,
    export_lights=False,
)
print('WROTE %s  %.2f MB' % (dst, os.path.getsize(dst) / 1048576.0))
