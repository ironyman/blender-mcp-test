"""
Animal Crossing style village for Blender.

How to run:
  1. In Blender: Scripting workspace -> Open this file -> Run Script (Alt+P).
  2. Or push it into a live Blender from this folder through the MCP bridge:

       .venv\\Scripts\\python.exe -c "from bmcp.client import run_code; import pathlib; \\
           r = run_code(pathlib.Path('test/animal_crossing_village.py').read_text(encoding='utf-8')); \\
           print(r['status'], r.get('result'))"

Notes:
  - Re-running rebuilds the "ACTown" collection from scratch (camera/sun are reused).
  - Change SEED for a different scatter of trees / flowers / bushes.
  - Roughly 400 objects: grass island, sandy beach, winding river with a wooden
    bridge, stone plaza, five villager houses, a shop with a striped awning,
    fenced flower garden, trees, lamps, benches, bushes and rocks.
"""
import bpy
import math
import os
import random
import sys
from mathutils import Matrix, Vector

SEED = 21
random.seed(SEED)

ISLAND_R = 13.5      # grass radius
BEACH_R = 15.3       # sand radius
RIVER_X0, RIVER_AMP, RIVER_K = 10.5, 1.8, 0.28

# ---------------------------------------------------------------- helpers

def link(o):
    for c in list(o.users_collection):
        c.objects.unlink(o)
    COL.objects.link(o)
    return o


def mat(name, color, rough=0.85, emis=None, emis_strength=4.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    if emis:
        if "Emission Color" in b.inputs:
            b.inputs["Emission Color"].default_value = (*emis, 1)
        if "Emission Strength" in b.inputs:
            b.inputs["Emission Strength"].default_value = emis_strength
    return m


def grass_mat(name, c1, c2, scale=7.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes.get("Principled BSDF")
    b.inputs["Roughness"].default_value = 0.95
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = 6.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*c1, 1)
    ramp.color_ramp.elements[1].color = (*c2, 1)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Base Color"])
    return m


def _finish(o, material, name, smooth=False):
    if material:
        o.data.materials.append(material)
    if smooth:
        for p in o.data.polygons:
            p.use_smooth = True
    if name:
        o.name = name
    return link(o)


def box(loc, scale, material, rot=(0, 0, 0), name=None):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
    o = bpy.context.active_object
    o.scale = scale
    return _finish(o, material, name)


def cyl(loc, r, depth, material, rot=(0, 0, 0), verts=16, name=None, smooth=True):
    bpy.ops.mesh.primitive_cylinder_add(vertices=verts, radius=r, depth=depth,
                                        location=loc, rotation=rot)
    return _finish(bpy.context.active_object, material, name, smooth)


def cone(loc, r1, depth, material, rot=(0, 0, 0), verts=4, name=None, smooth=False):
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r1, radius2=0, depth=depth,
                                    location=loc, rotation=rot)
    return _finish(bpy.context.active_object, material, name, smooth)


def ball(loc, r, material, name=None, scale=None, smooth=True):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=20, ring_count=12, radius=r, location=loc)
    o = bpy.context.active_object
    if scale:
        o.scale = scale
    return _finish(o, material, name, smooth)


def ico(loc, r, material, name=None, scale=None):
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=r, location=loc)
    o = bpy.context.active_object
    if scale:
        o.scale = scale
    return _finish(o, material, name, True)


def ribbon(name, pts, widths, z_offsets, material, zfun):
    """Flat strip following a centerline (used for river bed + water)."""
    verts, faces = [], []
    n = len(pts)
    for i, (px, py) in enumerate(pts):
        if i == 0:
            tx, ty = pts[1][0] - px, pts[1][1] - py
        elif i == n - 1:
            tx, ty = px - pts[-2][0], py - pts[-2][1]
        else:
            tx, ty = pts[i + 1][0] - pts[i - 1][0], pts[i + 1][1] - pts[i - 1][1]
        L = math.hypot(tx, ty) or 1.0
        nx, ny = -ty / L, tx / L
        z = zfun(px, py) + z_offsets
        w = widths / 2
        verts.append((px + nx * w, py + ny * w, z))
        verts.append((px - nx * w, py - ny * w, z))
    for i in range(n - 1):
        a = 2 * i
        faces.append((a, a + 1, a + 3, a + 2))
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.update()
    o = bpy.data.objects.new(name, me)
    COL.objects.link(o)
    me.materials.append(material)
    return o


def face_center_angle(x, y):
    """Yaw so a part whose front is local -Y looks at the origin."""
    return math.atan2(-x, y)


# ---------------------------------------------------------------- cleanup

OLD = bpy.data.collections.get("ACTown")
if OLD:
    for o in list(OLD.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    bpy.data.collections.remove(OLD)
if "Cube" in bpy.data.objects:
    bpy.data.objects.remove(bpy.data.objects["Cube"], do_unlink=True)

SCN = bpy.context.scene
COL = bpy.data.collections.new("ACTown")
SCN.collection.children.link(COL)

# ---------------------------------------------------------------- materials

grass_m = grass_mat("AC_Grass", (0.30, 0.55, 0.16), (0.40, 0.66, 0.22))
sand_m = mat("AC_Sand", (0.90, 0.80, 0.54), 0.95)
water_m = mat("AC_Water", (0.22, 0.60, 0.92), 0.12)
riverbed_m = mat("AC_Riverbed", (0.82, 0.72, 0.50), 0.95)
path_m = mat("AC_Path", (0.76, 0.63, 0.41), 0.95)
plaza_m = mat("AC_Plaza", (0.87, 0.84, 0.77), 0.9)
stone_m = mat("AC_Stone", (0.70, 0.68, 0.64), 0.9)
trunk_m = mat("AC_Trunk", (0.48, 0.31, 0.16), 0.9)
leaf_m = mat("AC_Leaves", (0.22, 0.52, 0.18))
leaf2_m = mat("AC_Leaves2", (0.32, 0.62, 0.22))
cedar_m = mat("AC_Cedar", (0.14, 0.42, 0.22))
white_m = mat("AC_White", (0.96, 0.96, 0.94), 0.7)
door_m = mat("AC_Door", (0.44, 0.27, 0.14), 0.75)
glass_m = mat("AC_Glass", (0.62, 0.83, 0.96), 0.1)
chimney_m = mat("AC_Chimney", (0.63, 0.60, 0.57), 0.9)
chimney_cap_m = mat("AC_ChimneyCap", (0.48, 0.45, 0.43), 0.9)
gold_m = mat("AC_Gold", (0.95, 0.78, 0.25), 0.35)
black_m = mat("AC_Black", (0.10, 0.10, 0.12), 0.7)
lamp_m = mat("AC_LampGlow", (1.0, 0.88, 0.5), 0.4, emis=(1.0, 0.82, 0.40), emis_strength=2.0)
wood_m = mat("AC_Wood", (0.62, 0.42, 0.22), 0.9)
wood_dark_m = mat("AC_WoodDark", (0.45, 0.29, 0.14), 0.9)
rock_m = mat("AC_Rock", (0.52, 0.52, 0.50), 0.95)
mail_m = mat("AC_Mailbox", (0.24, 0.36, 0.62), 0.6)
flag_m = mat("AC_Flag", (0.86, 0.24, 0.22), 0.6)
sign_m = mat("AC_SignText", (0.20, 0.13, 0.08), 0.8)

FLOWER_MS = [
    mat("AC_FlowerRed", (0.90, 0.20, 0.22)),
    mat("AC_FlowerYellow", (0.98, 0.82, 0.18)),
    mat("AC_FlowerPink", (0.98, 0.55, 0.70)),
    mat("AC_FlowerWhite", (0.97, 0.97, 0.95)),
    mat("AC_FlowerPurple", (0.72, 0.45, 0.90)),
]
flower_center_m = mat("AC_FlowerCenter", (0.99, 0.90, 0.35))

# ---------------------------------------------------------------- terrain

# Ocean
bpy.ops.mesh.primitive_plane_add(size=140, location=(0, 0, -0.18))
sea = bpy.context.active_object
sea.name = "AC_Ocean"
sea.data.materials.append(water_m)
link(sea)

# Sand disc (beach) and grass disc
cyl((0, 0, -0.30), BEACH_R, 0.5, sand_m, verts=72, name="AC_Beach", smooth=False)
cyl((0, 0, -0.25), ISLAND_R, 0.5, grass_m, verts=72, name="AC_Grass", smooth=False)

# River: centerline, then a sandy bank ribbon + a water ribbon on top.
river_pts = []
y = -17.5
while y <= 17.5001:
    river_pts.append((RIVER_X0 + RIVER_AMP * math.sin(y * RIVER_K), y))
    y += 0.5


def river_z(x, yy):
    d = math.hypot(x, yy)
    if d <= 13.3:
        return 0.02
    if d <= 15.35:
        f = (d - 13.3) / 2.05
        return 0.02 - 0.055 * f
    if d >= 15.9:
        return -0.17
    f = (d - 15.35) / 0.55
    return -0.035 - 0.135 * f


ribbon("AC_RiverBank", river_pts, 4.4, -0.012, riverbed_m, river_z)
ribbon("AC_River", river_pts, 3.0, 0.0, water_m, river_z)

# ---------------------------------------------------------------- plaza + paths

cyl((0, 0, 0.025), 3.5, 0.05, plaza_m, verts=48, name="AC_Plaza", smooth=False)

HOUSES = [
    (-7.5, 5.5, (0.95, 0.90, 0.78), (0.80, 0.22, 0.18)),   # cream / red roof
    (6.5, 6.5, (0.74, 0.86, 0.93), (0.28, 0.32, 0.62)),    # blue / navy roof
    (-8.0, -5.5, (0.96, 0.82, 0.70), (0.92, 0.52, 0.16)),  # peach / orange roof
    (4.5, -7.0, (0.82, 0.93, 0.84), (0.25, 0.58, 0.32)),   # mint / green roof
    (0.5, -10.5, (0.88, 0.83, 0.96), (0.55, 0.30, 0.65)),  # lavender / purple roof
]
SHOP_POS = (-3.5, 10.0)
GARDEN_C = (-4.5, -9.5)
GARDEN_W, GARDEN_D = 4.0, 2.6

# Paths: plaza centre -> each front door, the shop, the bridge, the beaches.
path_targets = []
for hx, hy, _, _ in HOUSES:
    d = math.hypot(hx, hy)
    path_targets.append((hx - hx / d * 2.4, hy - hy / d * 2.4))
sd = math.hypot(*SHOP_POS)
path_targets.append((SHOP_POS[0] - SHOP_POS[0] / sd * 3.4, SHOP_POS[1] - SHOP_POS[1] / sd * 3.4))
path_targets += [(8.6, 0.0), (-13.0, 0.0), (GARDEN_C[0], GARDEN_C[1] + 1.9)]

for i, (tx, ty) in enumerate(path_targets):
    L = math.hypot(tx, ty)
    ang = math.atan2(ty, tx)
    top = 0.046 + i * 0.0007
    box((tx / 2, ty / 2, top - 0.018), (L + 0.6, 1.2, 0.036), path_m,
        rot=(0, 0, ang), name="AC_Path_%02d" % i)

# ---------------------------------------------------------------- buildings

def hip_roof(loc, rz, r, sx, sy, depth, material, name):
    """Rectangular pyramid roof; the 45 deg corner alignment is baked into the mesh."""
    bpy.ops.mesh.primitive_cone_add(vertices=4, radius1=r, radius2=0, depth=depth, location=(0, 0, 0))
    o = bpy.context.active_object
    o.data.transform(Matrix.Rotation(math.pi / 4, 4, "Z"))
    o.rotation_euler = (0, 0, rz)
    o.scale = (sx, sy, 1)
    o.location = loc
    return _finish(o, material, name)


def house(x, y, wall_m, roof_m, tag):
    rz = face_center_angle(x, y)
    c, s = math.cos(rz), math.sin(rz)

    def W(lx, ly, lz=0.0):
        return (x + lx * c - ly * s, y + lx * s + ly * c, lz)

    def R(extra=0.0):
        return (0, 0, rz + extra)

    box(W(0, 0, 1.0), (3.2, 2.6, 2.0), wall_m, R(), tag + "_Body")
    hip_roof(W(0, 0, 2.65), rz, 2.4, 1.06, 0.913, 1.3, roof_m, tag + "_Roof")

    # chimney
    box(W(1.0, 0.6, 2.9), (0.4, 0.4, 1.0), chimney_m, R(), tag + "_Chimney")
    box(W(1.0, 0.6, 3.45), (0.52, 0.52, 0.14), chimney_cap_m, R(), tag + "_ChimneyCap")

    # door + arch + knob
    box(W(0, -1.32, 0.65), (0.7, 0.1, 1.3), door_m, R(), tag + "_Door")
    cyl(W(0, -1.30, 1.3), 0.35, 0.1, door_m, rot=(math.pi / 2, 0, rz),
        verts=20, name=tag + "_DoorArch")
    ball(W(0.25, -1.39, 0.62), 0.06, gold_m, tag + "_Knob")

    # porch slab
    box(W(0, -1.75, 0.06), (1.3, 0.9, 0.12), stone_m, R(), tag + "_Porch")

    # windows (front pair + one per side)
    for lx in (-1.0, 1.0):
        box(W(lx, -1.31, 1.25), (0.55, 0.06, 0.65), glass_m, R(), tag + "_WinF")
        box(W(lx, -1.31, 1.25), (0.07, 0.09, 0.65), white_m, R(), tag + "_WinBarV")
        box(W(lx, -1.31, 1.25), (0.55, 0.09, 0.07), white_m, R(), tag + "_WinBarH")
        box(W(lx, -1.33, 0.90), (0.7, 0.12, 0.08), white_m, R(), tag + "_WinSill")
    for lx in (-1.61, 1.61):
        box(W(lx, 0.3, 1.25), (0.06, 0.55, 0.65), glass_m, R(), tag + "_WinS")
        box(W(lx, 0.3, 1.25), (0.09, 0.07, 0.65), white_m, R(), tag + "_WinBarSV")
        box(W(lx, 0.3, 1.25), (0.09, 0.55, 0.07), white_m, R(), tag + "_WinBarSH")
        box(W(lx, 0.3, 0.90), (0.12, 0.7, 0.08), white_m, R(), tag + "_WinSillS")

    # mailbox by the path
    cyl(W(-1.5, -2.5, 0.375), 0.05, 0.75, wood_dark_m, verts=10, name=tag + "_MailPost")
    box(W(-1.5, -2.5, 0.85), (0.3, 0.42, 0.28), mail_m, R(), tag + "_MailBox")
    box(W(-1.33, -2.5, 1.02), (0.05, 0.08, 0.2), flag_m, R(), tag + "_MailFlag")


for i, (hx, hy, wc, rc) in enumerate(HOUSES):
    house(hx, hy, mat("AC_Wall_%d" % i, wc), mat("AC_Roof_%d" % i, rc), "House%d" % (i + 1))


def shop(x, y, wall_m, roof_m):
    rz = face_center_angle(x, y)
    c, s = math.cos(rz), math.sin(rz)

    def W(lx, ly, lz=0.0):
        return (x + lx * c - ly * s, y + lx * s + ly * c, lz)

    def R(extra=0.0):
        return (0, 0, rz + extra)

    box(W(0, 0, 1.2), (5.0, 3.4, 2.4), wall_m, R(), "Shop_Body")
    hip_roof(W(0, 0, 2.95), rz, 3.4, 1.165, 0.832, 1.1, roof_m, "Shop_Roof")

    # striped awning over the front
    for k in range(5):
        lx = -2.0 + k * 1.0
        m = flag_m if k % 2 == 0 else white_m
        o = box(W(lx, -2.0, 2.0), (1.0, 1.1, 0.07), m,
                rot=(math.radians(18), 0, rz), name="Shop_Awning%d" % k)

    box(W(0, -1.72, 0.7), (1.0, 0.1, 1.4), door_m, R(), "Shop_Door")
    ball(W(0.35, -1.79, 0.7), 0.07, gold_m, "Shop_Knob")
    for lx in (-1.7, 1.7):
        box(W(lx, -1.71, 1.4), (0.8, 0.06, 0.7), glass_m, R(), "Shop_Win")
        box(W(lx, -1.71, 1.4), (0.08, 0.09, 0.7), white_m, R(), "Shop_WinBarV")
        box(W(lx, -1.71, 1.4), (0.8, 0.09, 0.08), white_m, R(), "Shop_WinBarH")

    # sign board + text
    box(W(0, -1.76, 2.55), (2.6, 0.1, 0.7), white_m, R(), "Shop_SignBoard")
    cu = bpy.data.curves.new("ShopSignText", type="FONT")
    cu.body = "SHOP"
    cu.size = 0.5
    cu.extrude = 0.03
    cu.align_x = "CENTER"
    cu.align_y = "CENTER"
    to = bpy.data.objects.new("Shop_Sign", cu)
    COL.objects.link(to)
    to.location = W(0, -1.83, 2.55)
    to.rotation_euler = (math.pi / 2, 0, rz)
    cu.materials.append(sign_m)


shop(SHOP_POS[0], SHOP_POS[1],
     mat("AC_ShopWall", (0.96, 0.94, 0.88)), mat("AC_ShopRoof", (0.28, 0.55, 0.34)))

# ---------------------------------------------------------------- bridge

BR_X0, BR_X1 = 8.6, 12.4
box(((BR_X0 + BR_X1) / 2, 0, 0.25), (BR_X1 - BR_X0, 2.4, 0.18), wood_m, name="AC_BridgeDeck")
for sx in (BR_X0 + 0.15, BR_X1 - 0.15):
    box((sx, 0, 0.08), (0.6, 2.4, 0.16), wood_m, name="AC_BridgeStep")
for sy in (-1.15, 1.15):
    box((10.5, sy, 0.82), (4.0, 0.08, 0.08), wood_dark_m, name="AC_BridgeRail")
    for px in (8.75, 9.6, 10.5, 11.4, 12.25):
        box((px, sy, 0.5), (0.1, 0.1, 0.66), wood_dark_m, name="AC_BridgePost")

# ---------------------------------------------------------------- props

def lamp(x, y):
    cyl((x, y, 1.0), 0.07, 2.0, black_m, verts=12, name="AC_LampPost")
    ball((x, y, 2.16), 0.26, lamp_m, "AC_LampGlow")
    cone((x, y, 2.45), 0.34, 0.26, black_m, rot=(0, 0, math.pi / 4), verts=4, name="AC_LampCap")


for deg in (20, 70, 200, 340):
    a = math.radians(deg)
    lamp(3.3 * math.cos(a), 3.3 * math.sin(a))


def bench(x, y):
    rz = face_center_angle(x, y)
    c, s = math.cos(rz), math.sin(rz)

    def W(lx, ly, lz=0.0):
        return (x + lx * c - ly * s, y + lx * s + ly * c, lz)

    box(W(0, 0, 0.5), (1.7, 0.55, 0.12), wood_m, (0, 0, rz), "Bench_Seat")
    box(W(0, 0.26, 0.85), (1.7, 0.1, 0.6), wood_m,
        (math.radians(-12), 0, rz), "Bench_Back")
    for lx in (-0.65, 0.65):
        box(W(lx, 0, 0.24), (0.12, 0.45, 0.48), wood_dark_m, (0, 0, rz), "Bench_Leg")


bench(4.6 * math.cos(math.radians(125)), 4.6 * math.sin(math.radians(125)))
bench(4.6 * math.cos(math.radians(300)), 4.6 * math.sin(math.radians(300)))

# fenced flower garden
gx, gy = GARDEN_C
posts = []
for i in range(5):
    lx = -GARDEN_W / 2 + i * (GARDEN_W / 4)
    posts += [(gx + lx, gy - GARDEN_D / 2), (gx + lx, gy + GARDEN_D / 2)]
for i in (1, 2, 3):
    ly = -GARDEN_D / 2 + i * (GARDEN_D / 3)
    posts += [(gx - GARDEN_W / 2, gy + ly), (gx + GARDEN_W / 2, gy + ly)]
for px, py in posts:
    box((px, py, 0.32), (0.09, 0.09, 0.64), white_m, name="AC_FencePost")
for z in (0.24, 0.48):
    for py in (gy - GARDEN_D / 2, gy + GARDEN_D / 2):
        box((gx, py, z), (GARDEN_W + 0.1, 0.05, 0.05), white_m, name="AC_FenceRail")
    for px in (gx - GARDEN_W / 2, gx + GARDEN_W / 2):
        box((px, gy, z), (0.05, GARDEN_D + 0.1, 0.05), white_m, name="AC_FenceRail")


def flower(x, y, m):
    cyl((x, y, 0.1), 0.02, 0.2, leaf_m, verts=6, name="AC_Stem", smooth=False)
    ball((x, y, 0.24), 0.09, m, "AC_FlowerHead", scale=(1, 1, 0.6))
    ball((x, y, 0.27), 0.04, flower_center_m, "AC_FlowerCenter")


for row, ly in enumerate((-0.65, 0.65)):
    for k in range(5):
        lx = -1.4 + k * 0.7
        flower(gx + lx, gy + ly, FLOWER_MS[(row * 5 + k) % len(FLOWER_MS)])

# ---------------------------------------------------------------- scatter

def river_x_at(y):
    return RIVER_X0 + RIVER_AMP * math.sin(y * RIVER_K)


path_angles = [math.atan2(ty, tx) for tx, ty in path_targets]
path_lens = [math.hypot(tx, ty) for tx, ty in path_targets]


def near_path(x, y, margin=1.4):
    r = math.hypot(x, y)
    th = math.atan2(y, x)
    for a, L in zip(path_angles, path_lens):
        if r > L + 2.0:
            continue
        proj = r * math.cos(th - a)
        perp = abs(r * math.sin(th - a))
        if -1.5 < proj < L + 2.0 and perp < margin:
            return True
    return False


def blocked(x, y, wall=1.5, house_r=4.0, shop_r=4.5, path_margin=None):
    if math.hypot(x, y) < 5.0:
        return True
    if abs(x - river_x_at(y)) < wall + 1.6:
        return True
    for hx, hy, _, _ in HOUSES:
        if math.hypot(x - hx, y - hy) < house_r:
            return True
    if math.hypot(x - SHOP_POS[0], y - SHOP_POS[1]) < shop_r:
        return True
    if abs(x - gx) < GARDEN_W / 2 + wall and abs(y - gy) < GARDEN_D / 2 + wall:
        return True
    if near_path(x, y, path_margin if path_margin is not None else wall):
        return True
    return False


def oak(x, y, s=1.0):
    h = 1.3 * s
    cyl((x, y, h / 2), 0.13 * s, h, trunk_m, verts=10, name="AC_OakTrunk")
    ball((x, y, h + 0.55 * s), 0.85 * s, leaf_m, "AC_OakLeaves")
    ball((x + 0.45 * s, y + 0.2 * s, h + 0.35 * s), 0.55 * s, leaf2_m, "AC_OakLeaves")
    ball((x - 0.4 * s, y - 0.3 * s, h + 0.4 * s), 0.5 * s, leaf_m, "AC_OakLeaves")
    ball((x, y, h + 1.05 * s), 0.55 * s, leaf2_m, "AC_OakLeaves")


def cedar(x, y, s=1.0):
    h = 0.85 * s
    cyl((x, y, h / 2), 0.11 * s, h, trunk_m, verts=10, name="AC_CedarTrunk")
    for k, (r, dz) in enumerate(((0.78, 0.45), (0.62, 0.9), (0.46, 1.32))):
        cone((x, y, h * 0.6 + dz * s), r * s, 0.95 * s, cedar_m,
             verts=12, name="AC_CedarLeaves")


oak(0, 0, 1.25)  # big plaza tree

placed = 0
flower_n = 0
bush_n = 0
for ring, base_r in enumerate((10.6, 11.8, 12.9)):
    for i in range(30):
        a = math.radians(i * 12 + ring * 4 + random.uniform(-3.5, 3.5))
        r = base_r + random.uniform(-0.45, 0.45)
        x, y = r * math.cos(a), r * math.sin(a)
        if blocked(x, y, wall=1.3, house_r=3.7, shop_r=4.2, path_margin=1.2):
            continue
        if random.random() < 0.45:
            cedar(x, y, random.uniform(0.9, 1.2))
        else:
            oak(x, y, random.uniform(0.85, 1.15))
        placed += 1

for _ in range(120):  # scattered flowers
    a = random.uniform(0, 2 * math.pi)
    r = random.uniform(4.5, 11.0)
    x, y = r * math.cos(a), r * math.sin(a)
    if blocked(x, y, wall=1.0, house_r=3.2, shop_r=3.5, path_margin=0.9):
        continue
    flower(x, y, random.choice(FLOWER_MS))
    flower_n += 1

for _ in range(80):  # bushes
    a = random.uniform(0, 2 * math.pi)
    r = random.uniform(5.0, 11.5)
    x, y = r * math.cos(a), r * math.sin(a)
    if blocked(x, y, wall=1.2, house_r=3.4, shop_r=3.8, path_margin=1.1):
        continue
    s = random.uniform(0.7, 1.1)
    ball((x, y, 0.24 * s), 0.36 * s, leaf_m, "AC_Bush", scale=(1, 1, 0.8))
    ball((x + 0.3 * s, y + 0.15 * s, 0.18 * s), 0.26 * s, leaf2_m, "AC_Bush")
    bush_n += 1

for x, y, s in ((3.6, -13.6, 1.0), (-11.0, -8.4, 0.8), (1.0, 13.6, 0.7)):
    ico((x, y, -0.05 + 0.2 * s), 0.5 * s, rock_m, "AC_Rock",
        scale=(1.2, 1.0, 0.75))

# ---------------------------------------------------------------- world / camera

world = SCN.world or bpy.data.worlds.new("World")
SCN.world = world
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
e[0].position = 0.42
e[0].color = (0.86, 0.94, 1.0, 1)
e[1].position = 0.95
e[1].color = (0.30, 0.58, 0.97, 1)
nt.links.new(tc.outputs["Generated"], sep.inputs[0])
nt.links.new(sep.outputs["Z"], mr.inputs["Value"])
nt.links.new(mr.outputs["Result"], ramp.inputs["Fac"])
nt.links.new(ramp.outputs["Color"], bg.inputs["Color"])
nt.links.new(bg.outputs[0], out.inputs[0])

sun = bpy.data.objects.get("Light")
if sun is None or sun.type != 'LIGHT':
    sun = bpy.data.objects.new("Light", bpy.data.lights.new("Light", 'SUN'))
    SCN.collection.objects.link(sun)
sun.data.type = 'SUN'
sun.data.energy = 3.2
sun.data.color = (1.0, 0.96, 0.86)
sun.rotation_euler = (math.radians(48), math.radians(8), math.radians(35))

cam = bpy.data.objects.get("Camera")
if cam is None:
    cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
    SCN.collection.objects.link(cam)
SCN.camera = cam
cam.location = (20, -22, 16)
cam.rotation_euler = (Vector((0, 0, 0.5)) - cam.location).to_track_quat('-Z', 'Y').to_euler()
cam.data.lens = 32

for eng in ('BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE'):
    try:
        SCN.render.engine = eng
        break
    except Exception:
        pass
SCN.render.resolution_x = 1600
SCN.render.resolution_y = 1000

# Punchy, saturated toy-town colours instead of AgX's washed-out look.
for vt in ('Khronos PBR Neutral', 'Standard'):
    try:
        SCN.view_settings.view_transform = vt
        break
    except Exception:
        pass

try:
    for area in bpy.context.screen.areas:
        if area.type == 'VIEW_3D':
            for sp in area.spaces:
                if sp.type == 'VIEW_3D':
                    sp.shading.type = 'MATERIAL'
                    sp.shading.use_scene_world = True
                    sp.shading.use_scene_lights = True
                    sp.region_3d.view_perspective = 'CAMERA'
            area.tag_redraw()
except Exception:
    pass

result = {
    "village_objects": len(COL.objects),
    "total_objects": len(bpy.data.objects),
    "trees": placed + 1,
    "flowers": flower_n + 15,
    "bushes": bush_n,
    "seed": SEED,
}

# Optional: blender --background --python this_file.py -- --save path.blend
if "--" in sys.argv:
    argv = sys.argv[sys.argv.index("--") + 1:]
    if argv and argv[0] == "--save" and len(argv) > 1:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(argv[1]))
        result["saved"] = os.path.abspath(argv[1])

print("Animal Crossing village built:", result)
