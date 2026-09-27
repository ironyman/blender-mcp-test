"""
Pokémon-style 3D scene for Blender (route with Pikachu, a starter, tall grass, Poké Ball).

How to run:
    python send_to_blender.py pokemon_scene.py

Notes:
  - Re-running removes the previous "PokemonScene" collection first.
  - Change random.seed(11) for a different layout.
"""
import bpy, math, random
from mathutils import Vector, Matrix, noise

random.seed(11)

# ---------- Cleanup ----------
if "Cube" in bpy.data.objects:
    bpy.data.objects.remove(bpy.data.objects["Cube"], do_unlink=True)

old = bpy.data.collections.get("PokemonScene")
if old:
    for o in list(old.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.data.collections.remove(old)

col = bpy.data.collections.new("PokemonScene")
bpy.context.scene.collection.children.link(col)


# ---------- Helpers ----------
def mat(name, color, rough=0.7, emit=0.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    if emit:
        b.inputs["Emission Color"].default_value = (*color, 1)
        b.inputs["Emission Strength"].default_value = emit
    return m


def link(obj):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    col.objects.link(obj)
    return obj


def shade_smooth(obj):
    for p in obj.data.polygons:
        p.use_smooth = True


def sph(r, loc, m, scale=(1, 1, 1), seg=32):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=seg, ring_count=seg // 2, radius=r, location=loc)
    o = bpy.context.active_object
    o.scale = scale
    o.data.materials.append(m)
    shade_smooth(o)
    return link(o)


def ico(r, loc, m, sub=2, scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=sub, radius=r, location=loc)
    o = bpy.context.active_object
    o.scale = scale
    o.data.materials.append(m)
    shade_smooth(o)
    return link(o)


def cube(loc, scale, m, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.active_object
    o.scale = scale
    o.rotation_euler = rot
    o.data.materials.append(m)
    return link(o)


def cone(r1, depth, loc, m, rot=(0, 0, 0), verts=16, r2=0.0):
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r1, radius2=r2, depth=depth, location=loc)
    o = bpy.context.active_object
    o.rotation_euler = rot
    o.data.materials.append(m)
    return link(o)


def cyl(r, depth, loc, m, rot=(0, 0, 0), verts=16):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=depth, location=loc)
    o = bpy.context.active_object
    o.rotation_euler = rot
    o.data.materials.append(m)
    return link(o)


# ---------- Materials ----------
grass_m = mat("PokeGrass", (0.30, 0.62, 0.22))
grass2_m = mat("PokeGrassDark", (0.18, 0.48, 0.15))
dirt_m = mat("PokeDirt", (0.72, 0.55, 0.32))
trunk_m = mat("PokeTrunk", (0.35, 0.20, 0.10))
leaf_m = mat("PokeLeaves", (0.15, 0.50, 0.16))
leaf2_m = mat("PokeLeaves2", (0.35, 0.65, 0.18))
yellow_m = mat("PokeYellow", (0.98, 0.80, 0.05), 0.55)
black_m = mat("PokeBlack", (0.02, 0.02, 0.02), 0.4)
white_m = mat("PokeWhite", (0.95, 0.95, 0.95), 0.4)
red_m = mat("PokeRed", (0.85, 0.08, 0.06), 0.45)
brown_m = mat("PokeBrown", (0.45, 0.26, 0.10))
green_m = mat("PokeTeal", (0.35, 0.72, 0.50), 0.6)
bulb_m = mat("PokeBulb", (0.25, 0.60, 0.30), 0.6)
eye_r_m = mat("PokeEyeRed", (0.75, 0.10, 0.10), 0.3)
wall_m = mat("PokeWalls", (0.95, 0.92, 0.85))
roof_m = mat("PokeRoof", (0.85, 0.15, 0.12))
cloud_m = mat("PokeCloud", (1, 1, 1), 1.0)
sign_m = mat("PokeSign", (0.60, 0.40, 0.18))


# ---------- Ground ----------
bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, 0))
ground = bpy.context.active_object
ground.name = "Ground"
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.subdivide(number_cuts=40)
bpy.ops.object.mode_set(mode='OBJECT')
for v in ground.data.vertices:
    d = math.hypot(v.co.x, v.co.y)
    if d > 6:
        v.co.z += 0.25 * noise.noise(Vector((v.co.x * 0.3, v.co.y * 0.3, 4))) * min(1, (d - 6) / 8)
ground.data.materials.append(grass_m)
shade_smooth(ground)
link(ground)

# ---------- Dirt path (winding) ----------
for i in range(26):
    t = i / 25.0
    x = -9 + 18 * t
    y = 3.0 * math.sin(t * math.pi * 1.5) - 1.5
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=1.15 + 0.25 * math.sin(t * 9), depth=0.06,
                                        location=(x, y, 0.03))
    p = bpy.context.active_object
    p.scale = (1, 0.8, 1)
    p.data.materials.append(dirt_m)
    link(p)

# ---------- Tall grass patches ----------
def grass_patch(cx, cy, n):
    for _ in range(n):
        a = random.uniform(0, 2 * math.pi)
        r = random.uniform(0, 1.4)
        x, y = cx + r * math.cos(a), cy + r * math.sin(a)
        h = random.uniform(0.5, 0.95)
        cone(0.09, h, (x, y, h / 2), grass2_m,
             rot=(random.uniform(-.25, .25), random.uniform(-.25, .25), random.uniform(0, 3)), verts=6)


for gx, gy in [(-5.5, 3.2), (-3.0, -4.0), (1.0, 3.8), (4.5, -3.5), (6.0, 2.5), (-7.0, -2.0), (3.0, 1.5)]:
    grass_patch(gx, gy, random.randint(25, 45))

# ---------- Trees ----------
def tree(x, y, h=1.6, pine=False):
    cyl(0.13, h * 0.6, (x, y, h * 0.3), trunk_m, verts=10)
    if pine:
        for k in range(3):
            cone(0.75 - k * 0.18, 0.9, (x, y, h * 0.45 + k * 0.45), leaf_m, verts=12)
    else:
        for k in range(3):
            ico(random.uniform(0.55, 0.75),
                (x + random.uniform(-.3, .3), y + random.uniform(-.3, .3), h * 0.65 + random.uniform(0, .5)),
                random.choice([leaf_m, leaf2_m]))


for x, y, p in [(-8, 5, True), (-6, 6.5, False), (-4, 7, True), (-1, 7.5, False), (2, 7, True),
                (5, 6.5, False), (8, 5, True), (8.5, 1, False), (8, -4, True), (5, -7, False),
                (1, -7.5, True), (-3, -7, False), (-6.5, -6, True), (-8.5, -2.5, False), (-9, 2, True)]:
    tree(x, y, random.uniform(1.5, 2.3), p)

# ---------- Pikachu ----------
def build_pikachu(ox, oy, rot_z=0.0):
    objs = []

    def add(o):
        objs.append(o)
        return o

    # body + head
    add(sph(0.52, (ox, oy, 0.62), yellow_m, scale=(1.0, 0.85, 1.05)))
    add(sph(0.44, (ox, oy - 0.05, 1.30), yellow_m, scale=(1.05, 0.95, 0.95)))

    # ears (yellow base + black tip)
    for sx in (-1, 1):
        ex = ox + sx * 0.26
        base = cone(0.13, 0.72, (ex, oy, 1.85), yellow_m, rot=(math.radians(-14 * sx), math.radians(18 * sx), 0), verts=12)
        add(base)
        tip = cone(0.085, 0.26, (ex + sx * 0.11, oy, 2.18), black_m,
                   rot=(math.radians(-14 * sx), math.radians(18 * sx), 0), verts=12)
        add(tip)

    # face (front = -Y)
    for sx in (-1, 1):
        add(sph(0.075, (ox + sx * 0.17, oy - 0.38, 1.38), black_m))
        add(sph(0.028, (ox + sx * 0.15, oy - 0.44, 1.41), white_m))
        add(sph(0.10, (ox + sx * 0.30, oy - 0.33, 1.20), red_m, scale=(1, 0.5, 1)))
    add(sph(0.035, (ox, oy - 0.44, 1.27), black_m))
    add(cube((ox, oy - 0.42, 1.17), (0.14, 0.02, 0.03), black_m))

    # arms, feet
    for sx in (-1, 1):
        add(sph(0.14, (ox + sx * 0.42, oy - 0.18, 0.72), yellow_m, scale=(1, 1.3, 1)))
        add(sph(0.17, (ox + sx * 0.24, oy - 0.30, 0.13), yellow_m, scale=(1, 1.5, 0.75)))

    # lightning-bolt tail (brown base)
    add(cube((ox + 0.45, oy + 0.30, 0.55), (0.16, 0.09, 0.30), brown_m, rot=(0, math.radians(25), 0)))
    add(cube((ox + 0.62, oy + 0.32, 0.85), (0.42, 0.09, 0.20), yellow_m, rot=(0, math.radians(-35), 0)))
    add(cube((ox + 0.78, oy + 0.32, 1.15), (0.20, 0.09, 0.45), yellow_m, rot=(0, math.radians(15), 0)))
    add(cube((ox + 1.00, oy + 0.32, 1.45), (0.34, 0.09, 0.22), yellow_m, rot=(0, math.radians(-40), 0)))

    # rotate whole pikachu around its origin
    if rot_z:
        piv = Vector((ox, oy, 0))
        for o in objs:
            o.rotation_euler.rotate_axis('Z', rot_z)
            rel = Vector((o.location.x - piv.x, o.location.y - piv.y, 0))
            rel.rotate(Matrix.Rotation(rot_z, 3, 'Z'))
            o.location = piv + rel
    return objs


build_pikachu(-2.2, -0.6, rot_z=math.radians(35))

# ---------- Grass starter (quadruped with bulb) ----------
sx0, sy0 = 3.4, 1.6
sph(0.55, (sx0, sy0, 0.52), green_m, scale=(1.3, 1.0, 0.85))
sph(0.42, (sx0, sy0 - 0.62, 0.72), green_m, scale=(1.1, 1.0, 0.9))
ico(0.38, (sx0, sy0 + 0.25, 0.95), bulb_m, sub=2, scale=(1, 1, 1.15))
cone(0.28, 0.35, (sx0, sy0 + 0.25, 1.30), bulb_m, verts=8)
for dx, dy in [(-0.35, -0.35), (0.35, -0.35), (-0.35, 0.35), (0.35, 0.35)]:
    sph(0.17, (sx0 + dx, sy0 + dy, 0.18), green_m, scale=(1, 1, 1.2))
for ex in (-1, 1):
    sph(0.07, (sx0 + ex * 0.28, sy0 - 0.92, 0.80), eye_r_m)
    sph(0.05, (sx0 + ex * 0.20, sy0 - 1.0, 0.55), black_m, scale=(1.6, 0.6, 0.6))
for dx in (-0.3, 0.1, 0.45):
    sph(0.09, (sx0 + dx, sy0 - 0.5 + random.uniform(-.2, .2), 0.85), bulb_m, scale=(1.3, 1.0, 0.35))

# ---------- Poké Ball ----------
bx, by, br = 1.0, -3.2, 0.34
ball = sph(br, (bx, by, br), white_m, seg=40)
ball.data.materials.append(red_m)
ball.data.materials.append(black_m)
for p in ball.data.polygons:
    z = p.center.z
    if z > br * 0.12:
        p.material_index = 1
    elif z > -br * 0.12:
        p.material_index = 2
cyl(br * 1.02, 0.045, (bx, by, br), black_m, rot=(math.pi / 2, 0, 0), verts=32)
cyl(0.075, 0.05, (bx, by - br * 1.0, br), white_m, rot=(math.pi / 2, 0, 0), verts=24)
cyl(0.05, 0.06, (bx, by - br * 1.03, br), black_m, rot=(math.pi / 2, 0, 0), verts=24)

# ---------- Signpost ----------
px, py = -4.6, 1.9
cyl(0.07, 1.3, (px, py, 0.65), sign_m, verts=8)
cube((px, py - 0.05, 1.25), (0.9, 0.08, 0.45), sign_m)
cube((px, py - 0.10, 1.25), (0.7, 0.02, 0.06), black_m)
cube((px, py - 0.10, 1.10), (0.5, 0.02, 0.06), black_m)

# ---------- Small Pokémon Center ----------
hx, hy = 6.2, -5.0
hz = 0.0
cube((hx, hy, hz + 1.0), (3.4, 2.6, 2.0), wall_m)
bpy.ops.mesh.primitive_cone_add(vertices=4, radius1=2.6, depth=1.5, location=(hx, hy, hz + 2.7))
rf = bpy.context.active_object
rf.rotation_euler = (0, 0, math.pi / 4)
rf.scale = (1.15, 0.9, 1)
rf.data.materials.append(roof_m)
link(rf)
cube((hx, hy - 1.32, hz + 0.65), (0.9, 0.1, 1.3), red_m)
cube((hx, hy - 1.34, hz + 1.6), (2.6, 0.08, 0.35), red_m)
cyl(0.28, 0.1, (hx, hy - 1.42, hz + 1.6), white_m, rot=(math.pi / 2, 0, 0), verts=24)
cyl(0.18, 0.12, (hx, hy - 1.44, hz + 1.6), red_m, rot=(math.pi / 2, 0, 0), verts=24)

# ---------- Fence bits ----------
for i in range(5):
    fx = -7.5 + i * 1.1
    cyl(0.06, 0.9, (fx, -5.2, 0.45), sign_m, verts=8)
cube((-5.3, -5.2, 0.65), (5.2, 0.07, 0.12), sign_m)
cube((-5.3, -5.2, 0.35), (5.2, 0.07, 0.12), sign_m)

# ---------- Clouds ----------
for i in range(7):
    a = random.uniform(0, 2 * math.pi)
    r = random.uniform(12, 20)
    base = Vector((r * math.cos(a), r * math.sin(a), random.uniform(4, 11)))
    for k in range(random.randint(4, 6)):
        c = sph(random.uniform(1.0, 2.0),
                base + Vector((random.uniform(-2.5, 2.5), random.uniform(-1, 1), random.uniform(-.3, .5))),
                cloud_m, seg=24)
        c.scale.z = 0.55

# ---------- Sky gradient ----------
sc = bpy.context.scene
world = sc.world or bpy.data.worlds.new("World")
sc.world = world
world.use_nodes = True
nt = world.node_tree
nt.nodes.clear()
out = nt.nodes.new("ShaderNodeOutputWorld")
bg = nt.nodes.new("ShaderNodeBackground")
tc = nt.nodes.new("ShaderNodeTexCoord")
sep = nt.nodes.new("ShaderNodeSeparateXYZ")
mr = nt.nodes.new("ShaderNodeMapRange")
mr.inputs["From Min"].default_value = -1
mr.inputs["From Max"].default_value = 1
ramp = nt.nodes.new("ShaderNodeValToRGB")
e = ramp.color_ramp.elements
e[0].position = 0.45
e[0].color = (0.95, 0.98, 0.85, 1)
e[1].position = 0.85
e[1].color = (0.30, 0.62, 0.98, 1)
nt.links.new(tc.outputs["Generated"], sep.inputs[0])
nt.links.new(sep.outputs["Z"], mr.inputs["Value"])
nt.links.new(mr.outputs["Result"], ramp.inputs["Fac"])
nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
nt.links.new(bg.outputs[0], out.inputs[0])

# ---------- Sun ----------
L = bpy.data.objects.get("Light")
if L is None:
    L = bpy.data.objects.new("Light", bpy.data.lights.new("Light", 'SUN'))
    sc.collection.objects.link(L)
L.data.type = 'SUN'
L.data.energy = 4.5
L.data.color = (1, 0.97, 0.9)
L.rotation_euler = (math.radians(45), math.radians(-12), math.radians(-40))

# ---------- Camera ----------
cam = bpy.data.objects.get("Camera")
if cam is None:
    cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
    sc.collection.objects.link(cam)
sc.camera = cam
cam.location = (6.5, -9.5, 3.6)
cam.rotation_euler = (Vector((-0.5, 0.5, 1.0)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
cam.data.lens = 42

# ---------- Render settings ----------
for eng in ('BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE'):
    try:
        sc.render.engine = eng
        break
    except Exception:
        pass
sc.render.resolution_x = 1600
sc.render.resolution_y = 1000

# ---------- Viewport: camera view, scene sky + lights ----------
for o in bpy.context.selected_objects:
    o.select_set(False)
for area in bpy.context.screen.areas:
    if area.type == 'VIEW_3D':
        for sp in area.spaces:
            if sp.type == 'VIEW_3D':
                sp.shading.type = 'MATERIAL'
                sp.shading.use_scene_world = True
                sp.shading.use_scene_lights = True
                sp.region_3d.view_perspective = 'CAMERA'
        area.tag_redraw()

print("Pokemon scene built:", len(col.objects), "objects")
