"""
Interactive-UI tools (need a live, non-background Blender).

  get_screenshot_of_area_as_image AREA_UI_TYPE [-o out.png] [--size-limit BYTES]
  get_screenshot_of_window_as_image [-o out.png] [--size-limit BYTES]
  get_screenshot_of_window_as_json
  jump_to_tab_by_name NAME
  jump_to_tab_by_space_type SPACE_TYPE [--allow-edits]
  jump_to_view3d_object_by_name NAME [--allow-edits]
  jump_to_view3d_object_data_by_name NAME [--allow-edits]

Screenshots are written to a PNG file instead of being returned inline as an MCP image.
``--size-limit`` (bytes, default 0 = no limit) downscales the PNG until it fits.
Derived from Blender Lab's blender_mcp (GPL-3.0-or-later).
"""
import base64
import os
import sys

from .cli import Tool, main
from .client import run_tool

AREA_UI_TYPES = [
    "VIEW_3D", "IMAGE_EDITOR", "UV", "ShaderNodeTree", "CompositorNodeTree", "GeometryNodeTree",
    "TextureNodeTree", "SEQUENCE_EDITOR", "CLIP_EDITOR", "DOPESHEET_EDITOR", "GRAPH_EDITOR", "NLA_EDITOR",
    "TEXT_EDITOR", "CONSOLE", "INFO", "TOPBAR", "STATUSBAR", "OUTLINER", "PROPERTIES", "FILE_BROWSER",
    "SPREADSHEET", "PREFERENCES",
]

# ---------------------------------------------------------------------------
# Screenshots.

_SCREENSHOT_COMMON = '''
def _window():
    import bpy
    ctx = bpy.context
    if ctx.window is not None:
        return ctx.window
    wins = ctx.window_manager.windows  # timer callbacks may have no active window
    return wins[0] if wins else None

def _downscale(tmpdir, filepath, limit):
    """Return PNG bytes <= limit (best effort): HiDPI -> logical size, then step the size down."""
    import os
    if limit <= 0 or os.path.getsize(filepath) <= limit:
        with open(filepath, "rb") as fh:
            return fh.read()
    import imbuf
    import bpy
    out = os.path.join(tmpdir, "downscaled.png")
    im = imbuf.load(filepath)
    try:
        w0, h0 = im.size
        px = bpy.context.preferences.system.pixel_size
        if px > 1.0:
            im.resize((round(w0 / px), round(h0 / px)), method="BILINEAR")
            w0, h0 = im.size
        data = None
        for div in (1, 2, 3, 4, 6, 8, 12, 16, 24, 32):
            w, h = w0 // div, h0 // div
            if w <= 64 or h <= 64:
                break
            c = im.copy()
            if div > 1:
                c.resize((w, h), method="BILINEAR")
            imbuf.write(c, filepath=out)
            c.free()
            with open(out, "rb") as fh:
                data = fh.read()
            if len(data) <= limit:
                break
        return data
    finally:
        im.free()
'''

AREA_SHOT = _SCREENSHOT_COMMON + '''
def main(params):
    import base64, os, tempfile, bpy
    if bpy.app.background:
        return {"status": "error", "message": "Screenshots are not available in background mode"}
    window = _window()
    if window is None:
        return {"status": "error", "message": "No active window"}
    want = params["area_ui_type"]
    area = bpy.context.area
    if area is None or area.ui_type != want:
        cands = sorted((a for a in window.screen.areas if a.ui_type == want), key=lambda a: -(a.width * a.height))
        area = cands[0] if cands else None
    if area is None:
        return {"status": "error", "message": "No area with type %r found. Available: %s" % (
            want, ", ".join(sorted({a.ui_type for a in window.screen.areas})))}
    with tempfile.TemporaryDirectory(prefix="blmcp_screenshot_") as tmp:
        path = os.path.join(tmp, "screenshot.png")
        with bpy.context.temp_override(window=window, area=area):
            try:
                bpy.ops.screen.screenshot_area(filepath=path)
            except RuntimeError as ex:
                return {"status": "error", "message": str(ex)}
        data = _downscale(tmp, path, params["size_limit_in_bytes"])
    return {"status": "ok", "image_base64": base64.b64encode(data).decode("ascii")}
'''

WINDOW_SHOT = _SCREENSHOT_COMMON + '''
def main(params):
    import base64, os, tempfile, bpy
    if bpy.app.background:
        return {"status": "error", "message": "Screenshots are not available in background mode"}
    window = _window()
    if window is None:
        return {"status": "error", "message": "No active window"}
    with tempfile.TemporaryDirectory(prefix="blmcp_screenshot_") as tmp:
        path = os.path.join(tmp, "screenshot.png")
        with bpy.context.temp_override(window=window):
            try:
                bpy.ops.screen.screenshot(filepath=path)
            except RuntimeError as ex:
                return {"status": "error", "message": str(ex)}
        data = _downscale(tmp, path, params["size_limit_in_bytes"])
    return {"status": "ok", "image_base64": base64.b64encode(data).decode("ascii")}
'''

WINDOW_JSON = '''
def main(params):
    import bpy
    ctx = bpy.context
    window = ctx.window or (ctx.window_manager.windows[0] if ctx.window_manager.windows else None)
    if bpy.app.background or window is None:
        return {"status": "error", "message": "Window layout is not available (background mode or no window)"}
    areas = []
    for area in window.screen.areas:
        info = {"type": area.type, "x": area.x, "y": area.y, "width": area.width, "height": area.height}
        sp = area.spaces.active
        if sp:
            s = {"type": sp.type}
            if sp.type == "VIEW_3D":
                r3d = sp.region_3d
                if r3d:
                    s["view_perspective"] = r3d.view_perspective
                    s["view_location"] = list(r3d.view_location)
                s["shading_type"] = sp.shading.type
                s["show_overlays"] = sp.overlay.show_overlays
            elif sp.type == "PROPERTIES":
                s["context"] = sp.context
            elif sp.type == "OUTLINER":
                s["display_mode"] = sp.display_mode
            elif sp.type == "TEXT_EDITOR" and sp.text:
                s["text_name"] = sp.text.name
            elif sp.type == "NODE_EDITOR":
                s["tree_type"] = sp.tree_type
                if sp.node_tree:
                    s["node_tree_name"] = sp.node_tree.name
            info["space"] = s
        info["regions"] = [{"type": r.type, "x": r.x, "y": r.y, "width": r.width, "height": r.height}
                           for r in area.regions if r.width > 0 and r.height > 0]
        areas.append(info)
    act = ctx.active_object
    return {"status": "ok", "window_width": window.width, "window_height": window.height,
            "screen_name": window.screen.name, "workspace": window.workspace.name, "scene": ctx.scene.name,
            "areas": areas,
            "active_object": {"name": act.name, "type": act.type, "mode": ctx.mode,
                              "location": list(act.location)} if act else None,
            "selected_objects": [{"name": o.name, "type": o.type} for o in ctx.selected_objects]}
'''

# ---------------------------------------------------------------------------
# Navigation.

TAB_BY_NAME = '''
def main(params):
    import bpy
    if bpy.app.background:
        return {"status": "error", "message": "Not available in background mode"}
    if bpy.context.window is None:
        return {"status": "error", "message": "No active window"}
    ws = bpy.data.workspaces.get(params["name"])
    if ws is None:
        return {"status": "error", "message": "Workspace %r not found" % params["name"],
                "available_workspaces": [w.name for w in bpy.data.workspaces]}
    bpy.context.window.workspace = ws
    return {"status": "ok", "workspace": ws.name}
'''

TAB_BY_SPACE = '''
def main(params):
    import bpy
    if bpy.app.background:
        return {"status": "error", "message": "Not available in background mode"}
    if bpy.context.window is None:
        return {"status": "error", "message": "No active window"}
    want = params["space_type"]
    def largest(screen):
        return max(screen.areas, key=lambda a: a.width * a.height, default=None)
    for ws in bpy.data.workspaces:
        for screen in ws.screens:
            a = largest(screen)
            if a is not None and a.type == want:
                bpy.context.window.workspace = ws
                return {"status": "ok", "workspace": ws.name, "space_type": want}
    if params["allow_edits"]:
        try:
            bpy.ops.workspace.duplicate()
        except RuntimeError as ex:
            return {"status": "error", "message": str(ex)}
        ws = bpy.context.window.workspace
        ws.name = want.replace("_", " ").title()
        a = largest(bpy.context.screen)
        if a is not None:
            a.type = want
        return {"status": "ok", "workspace": ws.name, "space_type": want, "created": True}
    avail = sorted({largest(s).type for w in bpy.data.workspaces for s in w.screens if largest(s)})
    return {"status": "error", "message": "No workspace with space type %r found" % want,
            "available_space_types": avail}
'''

# ``params["by_data"]`` selects lookup by object name (False) or by the object's data-block name (True).
JUMP_TO_OBJECT = '''
def _enable_collections(layer_col, target):
    found = False
    for child in layer_col.children:
        if _enable_collections(child, target):
            found = True
    if target.name in layer_col.collection.objects:
        found = True
    if found:
        layer_col.exclude = False
        layer_col.hide_viewport = False
    return found

def main(params):
    import bpy
    if bpy.app.background:
        return {"status": "error", "message": "Not available in background mode"}
    if bpy.context.window is None:
        return {"status": "error", "message": "No active window"}
    name = params["name"]
    if params["by_data"]:
        obj = next((o for o in bpy.data.objects if o.data is not None and o.data.name == name), None)
        if obj is None:
            return {"status": "error", "message": "No object found with data named %r" % name}
    else:
        obj = bpy.data.objects.get(name)
        if obj is None:
            return {"status": "error", "message": "Object %r not found" % name}
    if params["allow_edits"]:
        if obj.hide_viewport:
            obj.hide_viewport = False
        if obj.hide_get():
            obj.hide_set(False)
        _enable_collections(bpy.context.view_layer.layer_collection, obj)
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    framed = False
    for area in bpy.context.screen.areas:
        if area.type != "VIEW_3D":
            continue
        r3d = area.spaces.active.region_3d
        if r3d and r3d.view_perspective == "CAMERA":
            r3d.view_perspective = "PERSP"  # leave camera view so the object is framed freely
        for region in area.regions:
            if region.type == "WINDOW":
                with bpy.context.temp_override(area=area, region=region):
                    bpy.ops.view3d.view_selected()
                framed = True
                break
        break
    out = {"status": "ok", "object": obj.name, "type": obj.type, "location": list(obj.location),
           "message": None if framed else "No 3D viewport found, object selected but not framed"}
    if params["by_data"]:
        out["data_name"] = name
    return out
'''

# ---------------------------------------------------------------------------
# Tool table.


def _screenshot_runner(body, default_name):
    def run(args):
        params = {"size_limit_in_bytes": args.size_limit}
        if hasattr(args, "area_ui_type"):
            params["area_ui_type"] = args.area_ui_type
        res = run_tool(body, params, args.host, args.port, args.timeout)
        if res.get("status") != "ok":
            return res
        data = base64.b64decode(res["image_base64"])
        out = os.path.abspath(args.output or default_name)
        with open(out, "wb") as fh:
            fh.write(data)
        return {"status": "ok", "path": out, "bytes": len(data)}
    return run


def _shot_args(p):
    p.add_argument("-o", "--output", help="PNG path to write")
    p.add_argument("--size-limit", type=int, default=0, help="max PNG bytes; 0 = no limit (default)")


def _area_args(p):
    p.add_argument("area_ui_type", choices=AREA_UI_TYPES, metavar="AREA_UI_TYPE",
                   help="one of: " + ", ".join(AREA_UI_TYPES))
    _shot_args(p)


def _none(_p):
    pass


def _name_args(p):
    p.add_argument("name")


def _name_edit_args(p):
    p.add_argument("name")
    p.add_argument("--allow-edits", action="store_true",
                   help="allow un-hiding the object and enabling its collections")


def _space_args(p):
    p.add_argument("space_type", help="e.g. VIEW_3D, NODE_EDITOR, TEXT_EDITOR")
    p.add_argument("--allow-edits", action="store_true", help="create a workspace if none matches")


def _jump(by_data):
    def run(a):
        return run_tool(JUMP_TO_OBJECT, {"name": a.name, "allow_edits": a.allow_edits, "by_data": by_data},
                        a.host, a.port, a.timeout)
    return run


TOOLS = [
    Tool("get_screenshot_of_area_as_image", "Screenshot of one Blender area (by ui_type) written to a PNG.",
         _area_args, _screenshot_runner(AREA_SHOT, "area_screenshot.png")),
    Tool("get_screenshot_of_window_as_image", "Screenshot of the whole Blender window written to a PNG.",
         _shot_args, _screenshot_runner(WINDOW_SHOT, "window_screenshot.png")),
    Tool("get_screenshot_of_window_as_json", "JSON description of window layout, areas, active object, selection.",
         _none, lambda a: run_tool(WINDOW_JSON, None, a.host, a.port, a.timeout)),
    Tool("jump_to_tab_by_name", "Switch the active workspace tab to NAME.", _name_args,
         lambda a: run_tool(TAB_BY_NAME, {"name": a.name}, a.host, a.port, a.timeout)),
    Tool("jump_to_tab_by_space_type", "Switch to a workspace whose main area matches SPACE_TYPE.", _space_args,
         lambda a: run_tool(TAB_BY_SPACE, {"space_type": a.space_type, "allow_edits": a.allow_edits},
                            a.host, a.port, a.timeout)),
    Tool("jump_to_view3d_object_by_name", "Select an object by name and frame it in the 3D viewport.",
         _name_edit_args, _jump(False)),
    Tool("jump_to_view3d_object_data_by_name", "Select the object whose data-block is NAME and frame it.",
         _name_edit_args, _jump(True)),
]

if __name__ == "__main__":
    sys.exit(main(TOOLS, prog="python -m bmcp.tools_ui"))
