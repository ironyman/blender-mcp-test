"""
Read-only scene inspection tools.

  get_blendfile_summary_datablocks | _missing_files | _of_linked_libraries | _path_info | _usage_guess
      (each also as ``*_for_cli BLEND_FILE``, run in a background Blender)
  get_objects_summary
  get_object_detail_summary NAME

Each tool is a code *body* defining ``main(params) -> dict``; the same body runs in the live
Blender (over the socket) or in ``blender --background``.
Derived from Blender Lab's blender_mcp (GPL-3.0-or-later); reworked for Blender 5.x API changes.
"""
import sys

from .blender_cli import CLI_TIMEOUT, run_tool_cli
from .cli import Tool, main
from .client import run_tool

# ---------------------------------------------------------------------------
# Tool bodies (executed inside Blender).

DATABLOCKS = '''
def main(params):
    import bpy
    counts = {}
    for attr in sorted(dir(bpy.data)):
        val = getattr(bpy.data, attr, None)
        if hasattr(val, "__len__") and hasattr(val, "keys"):
            try:
                n = len(val)
                if n > 0:
                    counts[attr] = n
            except Exception:
                pass  # some attributes look like collections but raise (e.g. during undo)
    window = getattr(bpy.context, "window", None)
    return {
        "status": "ok",
        "datablock_counts": counts,
        "render_engine": bpy.context.scene.render.engine,
        "scene_name": bpy.context.scene.name,
        "workspaces": [w.name for w in bpy.data.workspaces],
        "active_workspace": window.workspace.name if window else None,
    }
'''

MISSING_FILES = '''
def main(params):
    import os, bpy
    missing, checked = [], [0]
    def visit(id_data, path, _placeholder):
        checked[0] += 1
        filepath = bpy.path.abspath(path)
        if not os.path.exists(filepath):
            missing.append({"id_type": type(id_data).__name__, "id_name": getattr(id_data, "name", ""),
                            "path": filepath})
    bpy.data.file_path_foreach(visit, flags={"SKIP_PACKED", "SKIP_WEAK_REFERENCES", "RESOLVE_TOKEN"})
    return {"status": "ok", "missing_files": missing, "total_checked": checked[0]}
'''

LINKED_LIBRARIES = '''
def main(params):
    import bpy
    direct, indirect = [], []
    for lib in bpy.data.libraries:
        count = 0
        for attr in dir(bpy.data):
            coll = getattr(bpy.data, attr, None)
            if not hasattr(coll, "__iter__") or isinstance(coll, (str, bytes)):
                continue
            try:
                for item in coll:
                    if getattr(item, "library", None) == lib:
                        count += 1
            except Exception:
                pass
        info = {"filepath": lib.filepath, "name": lib.name, "linked_datablocks_count": count}
        if lib.parent is None:
            direct.append(info)
        else:
            info["parent_library"] = lib.parent.name
            indirect.append(info)
    return {"status": "ok", "direct_libraries": direct, "indirect_libraries": indirect,
            "total_library_count": len(bpy.data.libraries)}
'''

PATH_INFO = '''
def main(params):
    import os, time, bpy
    filepath = bpy.data.filepath
    out = {"status": "ok", "filepath": filepath, "is_saved": bool(filepath), "is_dirty": bpy.data.is_dirty,
           "age_seconds": None, "file_size_bytes": None, "backups": None}
    if filepath and os.path.exists(filepath):
        st = os.stat(filepath)
        out["age_seconds"] = round(time.time() - st.st_mtime, 1)
        out["file_size_bytes"] = st.st_size
        out["backups"] = []
        for i in range(1, 33):  # Blender keeps up to 32 numbered backups
            bp = filepath + str(i)
            if not os.path.exists(bp):
                break
            bs = os.stat(bp)
            out["backups"].append({"path": bp, "age_seconds": round(time.time() - bs.st_mtime, 1),
                                   "size_bytes": bs.st_size})
    return out
'''

USAGE_GUESS = '''
def _summ(name, signals):
    """signals = [(contribution 0..1, certainty 0..1)] -> {score, certainty} as integer percentages."""
    if not signals:
        return name, {"score": 0, "certainty": 0}
    n = len(signals)
    return name, {"score": round(100 * sum(c for c, _ in signals) / n),
                  "certainty": round(100 * sum(k for _, k in signals) / n)}

def main(params):
    import bpy
    d, sc = bpy.data, bpy.context.scene
    tree = getattr(sc, "compositing_node_group", None) or getattr(sc, "node_tree", None)  # 5.x / <=4.x
    uses_nodes = getattr(sc, "use_nodes", True)
    def strips(s):
        se = s.sequence_editor
        return bool(se and (getattr(se, "strips", None) or getattr(se, "sequences", None)))
    non_default = [m for m in d.meshes if m.name != "Cube" or len(m.vertices) != 8]  # default cube
    g = []
    g.append(_summ("Animation", [(float(bool(d.actions)), 1.0), (float(bool(d.armatures)), 1.0),
                                 (float(any(bool(o.constraints) for o in d.objects)), 0.5)]))
    g.append(_summ("Rendering", [
        (float(sc.render.engine not in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE")), 0.5),
        (float(sc.render.filepath not in ("/tmp/", "/tmp\\\\", "")), 0.8),
        (float(bool(tree and any(n.type == "R_LAYERS" for n in tree.nodes))), 1.0)]))
    g.append(_summ("Scripting", [(float(bool(d.texts)), 1.0)]))
    g.append(_summ("Video Editing", [(float(any(strips(s) for s in d.scenes)), 1.0)]))
    g.append(_summ("Modeling", [
        (float(bool(non_default)), 0.8),
        (float(bool(non_default and any(len(m.uv_layers) > 1 or bool(m.color_attributes) for m in non_default))), 0.7),
        (float(bool(d.curves) or bool(d.metaballs)), 0.7),
        (float(any(bool(o.modifiers) for o in d.objects)), 0.5)]))
    g.append(_summ("Grease Pencil", [(float(bool(d.grease_pencils)), 1.0)]))
    g.append(_summ("Geometry Nodes", [(float(any(any(m.type == "NODES" and m.node_group for m in o.modifiers)
                                                 for o in d.objects)), 1.0)]))
    g.append(_summ("Compositing", [(float(bool(tree and uses_nodes and len(tree.nodes) > 2)), 1.0)]))
    g.append(_summ("UV Unwrapping", [
        (float(any(len(m.uv_layers) > 1 for m in d.meshes)), 1.0),
        (float(any(any(uv.name != "UVMap" for uv in m.uv_layers) for m in d.meshes)), 0.7),
        (float(any(mt.node_tree and any(n.type == "TEX_IMAGE" and n.image for n in mt.node_tree.nodes)
                   for mt in d.materials)), 0.7)]))
    g.append(_summ("Motion Tracking", [(float(bool(d.movieclips)), 1.0)]))
    g.append(_summ("Audio", [(float(bool(d.sounds)), 1.0), (float(bool(d.speakers)), 1.0)]))
    return {"status": "ok", "usage_guesses": dict(g)}
'''

OBJECTS_SUMMARY = '''
def _obj(o):
    info = {"name": o.name, "type": o.type, "parent": o.parent.name if o.parent else None,
            "data_name": o.data.name if o.data else None, "selected": o.select_get(),
            "visible": o.visible_get(), "hide_viewport": o.hide_get()}
    if o.type == "EMPTY" and o.instance_type == "COLLECTION" and o.instance_collection is not None:
        info["instance_collection"] = o.instance_collection.name
    return info

def _tree(lc):
    col = lc.collection
    return {"name": col.name, "exclude": lc.exclude, "hide_viewport": col.hide_viewport,
            "objects": sorted((_obj(o) for o in col.objects), key=lambda x: x["name"]),
            "children": sorted((_tree(c) for c in lc.children), key=lambda x: x["name"])}

def main(params):
    from bpy import context as ctx
    active = ctx.view_layer.objects.active
    window = getattr(ctx, "window", None)
    return {"status": "ok", "scene_name": ctx.scene.name,
            "active_workspace": window.workspace.name if window else None,
            "active_object": active.name if active else None,
            "object_mode": ctx.mode if active else None,
            "camera_object": ctx.scene.camera.name if ctx.scene.camera else None,
            "collections": [_tree(ctx.view_layer.layer_collection)]}
'''

OBJECT_DETAIL = '''
def main(params):
    import bpy
    o = bpy.data.objects.get(params["name"])
    if o is None:
        avail = sorted(bpy.data.objects.keys())
        shown = ", ".join(avail[:50]) + (" ... (%d more)" % (len(avail) - 50) if len(avail) > 50 else "")
        return {"status": "error", "message": "Object %r not found. Available objects: %s" % (
            params["name"], shown if avail else "(none)")}
    return {
        "status": "ok", "name": o.name, "type": o.type,
        "location": list(o.location), "rotation": list(o.rotation_euler), "scale": list(o.scale),
        "dimensions": list(o.dimensions),
        "parent": o.parent.name if o.parent else None,
        "children": [c.name for c in o.children],
        "modifiers": [{"name": m.name, "type": m.type, "show_viewport": m.show_viewport,
                       "show_render": m.show_render} for m in o.modifiers],
        "constraints": [{"name": c.name, "type": c.type, "enabled": c.enabled} for c in o.constraints],
        "materials": [s.material.name if s.material else None for s in o.material_slots],
        "visibility": {"hide_viewport": o.hide_viewport, "hide_render": o.hide_render, "hide_get": o.hide_get()},
        "data_name": o.data.name if o.data else None,
        "collections": [c.name for c in o.users_collection],
    }
'''

# ---------------------------------------------------------------------------
# Tool table.

_SUMMARIES = [
    ("datablocks", DATABLOCKS, "Data-block counts, active workspace, and render engine."),
    ("missing_files", MISSING_FILES,
     "External file references missing from disk (images, libraries, fonts, sounds, clips, caches, sequences)."),
    ("of_linked_libraries", LINKED_LIBRARIES, "Tree of directly and indirectly linked library files."),
    ("path_info", PATH_INFO, "The blend file's path, save status, age, and backups."),
    ("usage_guess", USAGE_GUESS, "Guess the file's primary use-cases (scored 0-100 with certainty)."),
]


def _no_args(_p):
    pass


def _summary_tools():
    tools = []
    for suffix, body, help_text in _SUMMARIES:
        name = "get_blendfile_summary_" + suffix

        def live(args, body=body):
            return run_tool(body, None, args.host, args.port, args.timeout)

        def cli(args, body=body):
            return run_tool_cli(args.blend_file, body, None, args.timeout)

        def cli_args(p):
            p.add_argument("blend_file")
            p.add_argument("--timeout", type=float, default=CLI_TIMEOUT)

        tools.append(Tool(name, help_text, _no_args, live))
        tools.append(Tool(name + "_for_cli", help_text + " Opens BLEND_FILE in background Blender.",
                          cli_args, cli, needs_blender=False))
    return tools


def _detail_args(p):
    p.add_argument("name", help="object name")


TOOLS = _summary_tools() + [
    Tool("get_objects_summary", "Scene collection hierarchy with each collection's objects.", _no_args,
         lambda a: run_tool(OBJECTS_SUMMARY, None, a.host, a.port, a.timeout)),
    Tool("get_object_detail_summary",
         "Type, transforms, parent, children, modifiers, constraints, materials, visibility, collections of NAME.",
         _detail_args,
         lambda a: run_tool(OBJECT_DETAIL, {"name": a.name}, a.host, a.port, a.timeout)),
]

if __name__ == "__main__":
    sys.exit(main(TOOLS, prog="python -m bmcp.tools_scene"))
