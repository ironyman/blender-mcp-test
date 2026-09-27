"""
Floating island scene for Blender.

How to run:
  1. Open Blender and switch to the Scripting workspace (tab at the top).
  2. Click Open, choose this file, then click Run Script (or press Alt+P).

Notes:
  - Deletes the default "Cube" if present.
  - Re-running removes the previous "FloatingIsland" collection first,
    so you won't get duplicates.
  - Change random.seed(7) to another number for a different layout.
"""
import bpy, math, random
from mathutils import Vector, noise

random.seed(7)

# ---------- Cleanup ----------
if "Cube" in bpy.data.objects:
    bpy.data.objects.remove(bpy.data.objects["Cube"], do_unlink=True)

old = bpy.data.collections.get("FloatingIsland")
if old:
    for o in list(old.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.data.collections.remove(old)

col = bpy.data.collections.new("FloatingIsland")
bpy.context.scene.collection.children.link(col)


# ---------- Helpers ----------
def mat(name, color, rough=0.8):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    return m


def link(obj):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    col.objects.link(obj)
    return obj


def shade_smooth(obj):
    for p in obj.data.polygons:
        p.use_smooth = True


def top_z(x, y):
    """Height of the grassy surface at (x, y)."""
    return 0.35 + 0.5 * noise.noise(Vector((x * 0.4, y * 0.4, 9))) + max(0, 1.2 - math.hypot(x, y) * 0.35) * 0.6


# ---------- Materials ----------
grass_m = mat("Grass", (0.18, 0.45, 0.12))
rock_m = mat("Rock", (0.35, 0.27, 0.2), 0.95)
trunk_m = mat("Trunk", (0.22, 0.13, 0.07))
leaf_m = mat("Leaves", (0.12, 0.38, 0.1))
leaf2_m = mat("Leaves2", (0.3, 0.5, 0.12))
cloud_m = mat("Cloud", (1, 1, 1), 1.0)
water_m = mat("Water", (0.3, 0.6, 0.9), 0.1)
house_m = mat("Walls", (0.85, 0.78, 0.62))
roof_m = mat("Roof", (0.6, 0.15, 0.1))


# ---------- Island rock (upside-down cone, roughened) ----------
bpy.ops.mesh.primitive_cone_add(vertices=48, radius1=4.0, radius2=0.2, depth=5, location=(0, 0, -2.5))
rock = bpy.context.active_object
rock.name = "IslandRock"
rock.rotation_euler = (math.pi, 0, 0)
bpy.ops.object.transform_apply(rotation=True)
sub = rock.modifiers.new("sub", 'SUBSURF')
sub.levels = 3
bpy.ops.object.modifier_apply(modifier="sub")
for v in rock.data.vertices:
    co = v.co
    n = noise.noise(Vector((co.x * 0.6, co.y * 0.6, co.z * 0.6)))
    n2 = noise.noise(Vector((co.x * 2, co.y * 2, co.z * 2)))
    if co.z < 2.4:
        s = 1 + 0.35 * n + 0.12 * n2
        co.x *= s
        co.y *= s
        co.z += 0.3 * n2
rock.data.materials.append(rock_m)
shade_smooth(rock)
link(rock)

# ---------- Grass top ----------
bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=4.3, depth=0.4, location=(0, 0, 0.1))
top = bpy.context.active_object
top.name = "GrassTop"
sub = top.modifiers.new("sub", 'SUBSURF')
sub.levels = 2
bpy.ops.object.modifier_apply(modifier="sub")
for v in top.data.vertices:
    co = v.co
    s = 1 + 0.2 * noise.noise(Vector((co.x * 0.5, co.y * 0.5, 3)))
    co.x *= s
    co.y *= s
    if co.z > 0:
        co.z += top_z(co.x, co.y) - 0.35
top.data.materials.append(grass_m)
shade_smooth(top)
link(top)

# ---------- Hanging rock spikes ----------
for i in range(5):
    a = random.uniform(0, 2 * math.pi)
    r = random.uniform(1.5, 3.3)
    bpy.ops.mesh.primitive_cone_add(vertices=12, radius1=random.uniform(0.3, 0.7), radius2=0.02,
                                    depth=random.uniform(1.2, 2.5), location=(r * math.cos(a), r * math.sin(a), -1.3))
    s = bpy.context.active_object
    s.rotation_euler = (math.pi + random.uniform(-.2, .2), random.uniform(-.2, .2), 0)
    s.data.materials.append(rock_m)
    link(s)

# ---------- Small floating rocks ----------
for i in range(8):
    a = random.uniform(0, 2 * math.pi)
    r = random.uniform(5, 8)
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=random.uniform(0.2, 0.6),
                                          location=(r * math.cos(a), r * math.sin(a), random.uniform(-3, 1.5)))
    s = bpy.context.active_object
    s.scale = (1, 1, random.uniform(0.6, 1.4))
    for v in s.data.vertices:
        v.co *= 1 + 0.25 * random.uniform(-1, 1)
    s.data.materials.append(rock_m)
    link(s)


# ---------- Trees ----------
def tree(x, y, h, pine):
    z = top_z(x, y)
    bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=0.1, depth=h * 0.6, location=(x, y, z + h * 0.3))
    t = bpy.context.active_object
    t.data.materials.append(trunk_m)
    link(t)
    if pine:
        for k in range(3):
            bpy.ops.mesh.primitive_cone_add(vertices=10, radius1=0.6 - k * 0.15, depth=0.8,
                                            location=(x, y, z + h * 0.5 + k * 0.4))
            c = bpy.context.active_object
            c.data.materials.append(leaf_m)
            link(c)
    else:
        for k in range(3):
            bpy.ops.mesh.primitive_ico_sphere_add(
                subdivisions=2, radius=random.uniform(0.45, 0.65),
                location=(x + random.uniform(-.25, .25), y + random.uniform(-.25, .25), z + h * 0.7 + random.uniform(0, .4)))
            c = bpy.context.active_object
            c.data.materials.append(random.choice([leaf_m, leaf2_m]))
            shade_smooth(c)
            link(c)


for x, y, p in [(-2.2, 1.2, True), (-2.6, -0.5, False), (-1.4, -2.2, True), (1.8, 2.3, False), (2.6, 0.9, True),
                (0.4, 2.9, True), (-0.6, 2.5, False), (1.5, -2.6, False), (2.9, -1.2, True)]:
    tree(x, y, random.uniform(1.3, 2.0), p)

# ---------- Cottage ----------
cx, cy = 0.9, -0.4
cz = top_z(cx, cy)
bpy.ops.mesh.primitive_cube_add(size=1, location=(cx, cy, cz + 0.3))
h = bpy.context.active_object
h.scale = (0.9, 0.7, 0.6)
h.name = "Cottage"
h.data.materials.append(house_m)
link(h)
bpy.ops.mesh.primitive_cone_add(vertices=4, radius1=0.95, depth=0.7, location=(cx, cy, cz + 0.95))
rf = bpy.context.active_object
rf.name = "Roof"
rf.rotation_euler = (0, 0, math.pi / 4)
rf.scale = (1.1, 0.85, 1)
rf.data.materials.append(roof_m)
link(rf)

# ---------- Waterfall ----------
bpy.ops.mesh.primitive_plane_add(size=1, location=(-3.9, -1.6, -2.0))
wf = bpy.context.active_object
wf.name = "Waterfall"
wf.scale = (0.35, 4.5, 1)
wf.rotation_euler = (math.pi / 2, 0, math.radians(-68))
wf.data.materials.append(water_m)
link(wf)

# ---------- Clouds ----------
for i in range(7):
    a = random.uniform(0, 2 * math.pi)
    r = random.uniform(7, 13)
    base = Vector((r * math.cos(a), r * math.sin(a), random.uniform(-5, 3)))
    for k in range(random.randint(4, 6)):
        bpy.ops.mesh.primitive_uv_sphere_add(
            segments=24, ring_count=12, radius=random.uniform(0.6, 1.2),
            location=base + Vector((random.uniform(-1.5, 1.5), random.uniform(-.6, .6), random.uniform(-.2, .4))))
        c = bpy.context.active_object
        c.scale.z = 0.6
        c.data.materials.append(cloud_m)
        shade_smooth(c)
        link(c)

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
e[0].position = 0.35
e[0].color = (0.85, 0.92, 1.0, 1)
e[1].position = 0.8
e[1].color = (0.25, 0.5, 0.95, 1)
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
L.data.energy = 4
L.data.color = (1, 0.95, 0.85)
L.rotation_euler = (math.radians(50), math.radians(10), math.radians(35))

# ---------- Camera ----------
cam = bpy.data.objects.get("Camera")
if cam is None:
    cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
    sc.collection.objects.link(cam)
sc.camera = cam
cam.location = (14, -14, 5)
cam.rotation_euler = (Vector((0, 0, -0.5)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
cam.data.lens = 40

# ---------- Render settings ----------
for eng in ('BLENDER_EEVEE', 'BLENDER_EEVEE_NEXT'):
    try:
        sc.render.engine = eng
        break
    except Exception:
        pass
sc.render.resolution_x = 1600
sc.render.resolution_y = 1000

# ---------- Viewport: look through camera, show scene sky + lights ----------
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

print("Floating island built:", len(col.objects), "objects")
