"""
Extras around the add-on's socket bridge (not MCP tools in the official server).

  ping                     is the bridge reachable? Blender version, mode, open file
  raw JSON                 send a raw protocol request and print the raw reply (explore the protocol/errors)
  start_background_server  launch ``blender --background FILE --command blender_mcp`` (headless bridge)
  stop_background_server   terminate a process started above

The headless bridge is the official "background mode": blocking, one request at a time, and it
does NOT support deferred replies (renders via INVOKE_DEFAULT), screenshots, or workspace/viewport tools.
The add-on refuses to start unless Blender's online access is enabled, hence ``--online-mode``.
"""
import json
import os
import socket
import subprocess
import sys
import time

from .blender_cli import blender_path
from .cli import Tool, main
from .client import BlenderConnectionError, connection_params, run_tool, send_request

PING = '''
def main(params):
    import bpy
    return {"status": "ok", "blender": bpy.app.version_string, "background": bpy.app.background,
            "filepath": bpy.data.filepath, "is_dirty": bpy.data.is_dirty, "online_access": bpy.app.online_access}
'''


def _none(_p):
    pass


def _raw_args(p):
    p.add_argument("request", help='JSON request, e.g. \'{"type":"execute","code":"result={}","strict_json":true}\'')


def _run_raw(a):
    return send_request(json.loads(a.request), a.host, a.port, a.timeout)


def _bg_args(p):
    p.add_argument("blend_file", nargs="?", help="file to open (default: empty startup scene)")
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=9877, help="default 9877, to avoid clashing with a GUI on 9876")
    p.add_argument("--wait", type=float, default=30.0, help="seconds to wait for the port to open")


def _port_open(host, port):
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def _run_start(a):
    host, port = connection_params(a.host, a.port)
    if _port_open(host, port):
        raise RuntimeError("Something is already listening on {}:{}".format(host, port))
    cmd = [blender_path(), "--background"] + ([a.blend_file] if a.blend_file else []) + [
        "--online-mode", "--command", "blender_mcp", "--host", host, "--port", str(port)]
    flags = 0
    if os.name == "nt":
        flags = subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=flags)
    deadline = time.time() + a.wait
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError("Blender exited with code {} (is the MCP add-on installed and enabled?)"
                               .format(proc.returncode))
        if _port_open(host, port):
            return {"status": "ok", "pid": proc.pid, "host": host, "port": port,
                    "hint": "BLENDER_MCP_PORT={} to target it; stop with stop_background_server --pid {}".format(
                        port, proc.pid)}
        time.sleep(0.25)
    proc.terminate()
    raise RuntimeError("Timed out waiting for {}:{} to open".format(host, port))


def _stop_args(p):
    p.add_argument("--pid", type=int, required=True)


def _run_stop(a):
    if os.name == "nt":
        r = subprocess.run(["taskkill", "/PID", str(a.pid), "/T", "/F"], capture_output=True, text=True)
        ok = r.returncode == 0
        return {"status": "ok" if ok else "error", "message": (r.stdout + r.stderr).strip()}
    os.kill(a.pid, 15)
    return {"status": "ok"}


def _run_ping(a):
    try:
        info = run_tool(PING, None, a.host, a.port, a.timeout)
    except BlenderConnectionError as ex:
        return {"status": "error", "message": str(ex)}
    host, port = connection_params(a.host, a.port)
    return dict(info, host=host, port=port)


TOOLS = [
    Tool("ping", "Check the bridge is reachable; report Blender version, mode and open file.", _none, _run_ping,
         default_timeout=15.0),
    Tool("raw", "Send a raw JSON protocol request and print the raw response.", _raw_args, _run_raw),
    Tool("start_background_server", "Start a headless Blender bridge (--command blender_mcp).", _bg_args,
         _run_start, needs_blender=False),
    Tool("stop_background_server", "Terminate a headless bridge by PID.", _stop_args, _run_stop, needs_blender=False),
]

if __name__ == "__main__":
    sys.exit(main(TOOLS, prog="python -m bmcp.tools_server"))
