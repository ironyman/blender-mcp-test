"""
Run tool code in a *background* Blender process (``blender --background``).

This is the "_for_cli" half of the official MCP tools: they open a .blend file
headlessly, run the same code the live tools send over the socket, and read the
JSON ``result`` back from stdout.

Environment: BLENDER_PATH overrides the executable location.

Derived from Blender Lab's blender_mcp (GPL-3.0-or-later).
"""
import contextlib
import glob
import json
import os
import shutil
import subprocess
import tempfile

from .client import BlenderConnectionError, build_toolcode, send_code

_RESULT = "__BLMCP_RESULT__"
_ERROR = "__BLMCP_ERROR__"
CLI_TIMEOUT = 120.0


def blender_path():
    env = os.environ.get("BLENDER_PATH")
    if env:
        return env
    found = shutil.which("blender")
    if found:
        return found
    for pattern in (r"C:\Program Files\Blender Foundation\Blender *\blender.exe",
                    "/Applications/Blender.app/Contents/MacOS/Blender",
                    "/usr/bin/blender", "/snap/bin/blender"):
        hits = sorted(glob.glob(pattern), reverse=True)  # newest version first
        if hits:
            return hits[0]
    return "blender"


# Runs inside Blender. Executes the tool code and prints a marker line with the JSON result.
_RUNNER = '''\
import json, sys
try:
    _ns = {{"result": {{}}}}
    exec(compile({code!r}, "<blmcp>", "exec"), _ns)
    _r = _ns["result"]
    if not isinstance(_r, dict):
        raise TypeError("`result` must be a dict, not " + type(_r).__name__)
    print("{ok}" + json.dumps(_r, default=repr))
except BaseException as _ex:
    import traceback
    print("{err}" + json.dumps(traceback.format_exc()))
'''


def run_blender_cli(blend_file, code, timeout=CLI_TIMEOUT):
    """Execute *code* against *blend_file* in ``blender --background``; return the result dict."""
    exe = blender_path()
    runner = _RUNNER.format(code=code, ok=_RESULT, err=_ERROR)
    fd, script = tempfile.mkstemp(suffix=".py", prefix="bmcp_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(runner)
        try:
            proc = subprocess.run([exe, "--background", blend_file, "--python", script],
                                  capture_output=True, text=True, timeout=timeout, check=False,
                                  encoding="utf-8", errors="replace")
        except subprocess.TimeoutExpired as ex:
            raise RuntimeError("Blender CLI timed out after {:.0f}s".format(timeout)) from ex
        except FileNotFoundError as ex:
            raise RuntimeError("Blender executable not found ({!r}). Set BLENDER_PATH.".format(exe)) from ex
    finally:
        with contextlib.suppress(OSError):
            os.remove(script)

    for line in proc.stdout.splitlines():
        if line.startswith(_RESULT):
            return json.loads(line[len(_RESULT):])
        if line.startswith(_ERROR):
            raise RuntimeError("Blender error:\n" + json.loads(line[len(_ERROR):]))
    raise RuntimeError("No result marker in Blender output.\nstdout: {}\nstderr: {}".format(proc.stdout, proc.stderr))


def run_tool_cli(blend_file, body, params=None, timeout=CLI_TIMEOUT):
    """Like :func:`bmcp.client.run_tool` but in a background Blender opening *blend_file*."""
    if not os.path.isfile(blend_file):
        raise RuntimeError("Blend file not found: {}".format(blend_file))
    with synced_blend_for_cli(blend_file) as path:
        return run_blender_cli(path, build_toolcode(body, params), timeout)


def _numbered_path(filepath):
    base, ext = os.path.splitext(filepath)
    for i in range(1, 10000):
        cand = "{}_mcp_{:04d}{}".format(base, i, ext)
        if not os.path.exists(cand):
            return cand
    raise RuntimeError("No unused numbered path for " + filepath)


@contextlib.contextmanager
def synced_blend_for_cli(blend_file):
    """
    Yield a path reflecting the live session's unsaved edits.

    If a running Blender has *blend_file* open and dirty, a numbered temporary copy is
    saved (``copy=True``) and yielded, then deleted. Otherwise *blend_file* is yielded as-is.
    """
    temp = None
    try:
        try:
            resp = send_code("import bpy\nresult = {'is_dirty': bpy.data.is_dirty, 'filepath': bpy.data.filepath}",
                             True, timeout=15)
        except BlenderConnectionError:
            yield blend_file
            return
        if resp.get("status") != "ok":
            raise RuntimeError(str(resp.get("message", "Unknown error")))
        info = resp["result"]
        live = info.get("filepath") or ""
        if not live or os.path.realpath(live) != os.path.realpath(blend_file) or not info.get("is_dirty"):
            yield blend_file
            return
        temp = _numbered_path(blend_file)
        saved = send_code("import bpy\nbpy.ops.wm.save_as_mainfile(filepath={!r}, copy=True)".format(temp),
                          True, timeout=60)
        if saved.get("status") != "ok":
            raise RuntimeError(str(saved.get("message", "Unknown error")))
        yield temp
    finally:
        if temp:
            with contextlib.suppress(OSError):
                os.remove(temp)
