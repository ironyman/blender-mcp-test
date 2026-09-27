"""
Tools: execute_blender_code, execute_blender_code_for_cli.

Runs arbitrary Python (with full ``bpy`` access) in the live Blender, or in a background
Blender opened on a .blend file. Assign a dict to ``result`` to return data.

Non-strict JSON: values that are not serialisable (e.g. Blender objects) come back as ``repr``.
Derived from Blender Lab's blender_mcp (GPL-3.0-or-later).
"""
import sys

from .blender_cli import CLI_TIMEOUT, run_blender_cli, synced_blend_for_cli
from .cli import Tool, main
from .client import run_code


def _read_code(args):
    if args.code == "-":
        return sys.stdin.read()
    if args.file:
        with open(args.file, encoding="utf-8") as fh:
            return fh.read()
    if args.code:
        return args.code
    raise ValueError("Provide code as an argument, --file PATH, or '-' to read stdin")


def _add_live(p):
    p.add_argument("code", nargs="?", help="Python source, or '-' for stdin")
    p.add_argument("-f", "--file", help="read the code from this file")


def _run_live(args):
    """Returns the full response envelope (status/result/stdout/stderr) like the official tool."""
    return run_code(_read_code(args), args.host, args.port, args.timeout)


def _add_cli(p):
    p.add_argument("blend_file")
    _add_live(p)
    p.add_argument("--timeout", type=float, default=CLI_TIMEOUT, help="seconds to allow Blender (default %(default)s)")


def _run_cli(args):
    code = _read_code(args)
    with synced_blend_for_cli(args.blend_file) as path:
        return run_blender_cli(path, code, args.timeout)


TOOLS = [
    Tool("execute_blender_code", "Execute Python code in the connected Blender instance.", _add_live, _run_live),
    Tool("execute_blender_code_for_cli", "Execute Python code in a background Blender opened on BLEND_FILE.",
         _add_cli, _run_cli, needs_blender=False),
]

if __name__ == "__main__":  # python -m bmcp.tools_code <tool> ...
    sys.exit(main(TOOLS, prog="python -m bmcp.tools_code"))
