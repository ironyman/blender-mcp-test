"""
Tiny command-line framework shared by every tool module.

Each module declares ``TOOLS = [Tool(...), ...]``. A tool's ``run(args)`` returns a
JSON-serialisable payload which is printed; a payload with ``status == "error"``
(or a raised BlenderError) makes the process exit non-zero.
"""
import argparse
import json
import sys
from typing import Any, Callable, NamedTuple

from .client import DEFAULT_TIMEOUT, BlenderConnectionError, BlenderError


class Tool(NamedTuple):
    name: str                                       # matches the official MCP tool name
    help: str
    add_args: Callable[[argparse.ArgumentParser], None]
    run: Callable[[argparse.Namespace], Any]
    needs_blender: bool = True                      # adds --host/--port/--timeout
    default_timeout: float = DEFAULT_TIMEOUT


def _add_connection_args(p, default_timeout):
    g = p.add_argument_group("connection")
    g.add_argument("--host", help="add-on host (env BLENDER_MCP_HOST, default localhost)")
    g.add_argument("--port", type=int, help="add-on port (env BLENDER_MCP_PORT, default 9876)")
    g.add_argument("--timeout", type=float, default=default_timeout,
                   help="seconds to wait for Blender (default %(default)s)")


def build_parser(tools, prog):
    parser = argparse.ArgumentParser(prog=prog, description="Blender MCP tools as plain Python scripts.")
    sub = parser.add_subparsers(dest="tool", metavar="TOOL", required=True)
    for t in tools:
        p = sub.add_parser(t.name, help=t.help, description=t.help)
        if t.needs_blender:
            _add_connection_args(p, t.default_timeout)
        t.add_args(p)
        p.set_defaults(_tool=t)
    return parser


def emit(payload):
    print(json.dumps(payload, indent=2, ensure_ascii=False, default=repr))


def main(tools, argv=None, prog=None):
    args = build_parser(tools, prog or sys.argv[0]).parse_args(argv)
    try:
        payload = args._tool.run(args)
    except BlenderConnectionError as ex:
        print("error: {}".format(ex), file=sys.stderr)
        return 2
    except (BlenderError, RuntimeError, ValueError, OSError) as ex:
        print("error: {}".format(ex), file=sys.stderr)
        return 1
    try:
        emit(payload)
        sys.stdout.flush()
    except BrokenPipeError:  # e.g. `... | head`; not an error
        return 0
    return 1 if isinstance(payload, dict) and payload.get("status") == "error" else 0
