"""
Render tools.

  render_viewport_to_path  OUTPUT_PATH   render the scene with current settings
  render_thumbnail_to_path OUTPUT_PATH   small, fast preview (settings temporarily overridden)

In an interactive Blender the render runs with ``INVOKE_DEFAULT`` (a render window opens) and the
reply is *deferred*: ``main`` returns a ``check_is_finished`` callable that the add-on polls until
the render job ends (the official add-on allows up to 1 hour). In background mode it renders
synchronously.

OUTPUT_PATH: a bare filename is placed in ``<blender tempdir>/blender_mcp/`` (the official behaviour);
an absolute path is used as given. Temporary render-setting overrides are restored once the job ends
(the official code restores some of them immediately, which can race the running render).
Derived from Blender Lab's blender_mcp (GPL-3.0-or-later).
"""
import sys

from .cli import Tool, main
from .client import run_tool

RENDER = '''
def main(params):
    import os, bpy
    use_deferred = not bpy.app.background
    out = params["output_path"]
    if not os.path.isabs(out):
        out = os.path.join(bpy.app.tempdir, "blender_mcp", os.path.basename(out))
    try:
        os.makedirs(os.path.dirname(out), exist_ok=True)
    except OSError as ex:
        return {"status": "error", "message": "Cannot create output directory: %s" % ex}

    scene = bpy.context.scene
    rd = scene.render
    saved = []                      # (owner, attr, original value)
    def override(owner, **attrs):
        for k, v in attrs.items():
            saved.append((owner, k, getattr(owner, k)))
            setattr(owner, k, v)
    def restore():
        for owner, k, v in reversed(saved):
            try:
                setattr(owner, k, v)
            except Exception:
                pass

    if params["thumbnail"]:
        longest = 320
        rx, ry = rd.resolution_x, rd.resolution_y
        tx, ty = (longest, max(int(ry * longest / rx), 1)) if rx >= ry else (max(int(rx * longest / ry), 1), longest)
        override(rd, resolution_x=tx, resolution_y=ty, resolution_percentage=100,
                 use_simplify=True, simplify_subdivision_render=1)
        if rd.engine == "CYCLES":
            override(scene.cycles, samples=16)
        elif rd.engine.startswith("BLENDER_EEVEE"):
            override(scene.eevee, taa_render_samples=16)
    override(rd, filepath=out)

    ext = rd.file_extension if rd.use_file_extension else ""
    expected = out if (not ext or out.lower().endswith(ext.lower())) else out + ext

    try:
        if use_deferred:
            bpy.ops.render.render("INVOKE_DEFAULT", write_still=True)
        else:
            bpy.ops.render.render(write_still=True)
    except RuntimeError as ex:
        restore()
        return {"status": "error", "message": str(ex)}

    def finish():
        restore()
        if os.path.exists(expected):
            return {"status": "ok", "filepath": expected}
        return {"status": "error", "message": "Job completed but output file was not created"}

    if not use_deferred:
        return finish()

    def check_is_finished():
        if bpy.app.is_job_running("RENDER"):
            return None
        return finish()
    return check_is_finished
'''

_TIMEOUT = 3600.0  # renders can be long; matches the add-on's 1 hour deferred cap


def _out_args(p):
    p.add_argument("output_path", help="filename (placed in Blender's scratch dir) or absolute path")


def _tool(name, help_text, thumbnail):
    def run(a):
        return run_tool(RENDER, {"output_path": a.output_path, "thumbnail": thumbnail}, a.host, a.port, a.timeout)
    return Tool(name, help_text, _out_args, run, default_timeout=_TIMEOUT)


TOOLS = [
    _tool("render_viewport_to_path", "Render the current scene to OUTPUT_PATH using current render settings.", False),
    _tool("render_thumbnail_to_path", "Render a small low-quality thumbnail (<=320px) to OUTPUT_PATH.", True),
]

if __name__ == "__main__":
    sys.exit(main(TOOLS, prog="python -m bmcp.tools_render"))
