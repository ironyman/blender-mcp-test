"""
Client for the Blender Lab MCP add-on's TCP bridge.

Protocol (from the official add-on, ``mcp_to_blender_server.py``):

  * One request per connection: a JSON object followed by a NUL byte (``b"\\0"``).
  * Request:  ``{"type": "execute", "code": <str>, "strict_json": <bool>}``
  * Response: JSON followed by a NUL byte:
        ``{"status": "ok", "result": {...}, "stdout": "...", "stderr": "..."}`` or
        ``{"status": "error", "message": "<traceback>", ...}``
  * The executed code communicates by assigning a ``dict`` to ``result``.
  * Deferred responses: if the code defines a callable ``check_is_finished`` the
    add-on keeps the connection open, polls it on its timer, and replies once it
    returns a dict (``None`` means "still running"). Used for renders.
  * Limits: 10 MiB per request, and a request must arrive complete promptly.

Environment variables (same names as the official MCP server):
  BLENDER_MCP_HOST (default localhost), BLENDER_MCP_PORT (default 9876).

Derived from Blender Lab's blender_mcp (GPL-3.0-or-later).
"""
import json
import os
import socket

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 9876
DEFAULT_TIMEOUT = 300.0
_RECV_SIZE = 65536


class BlenderConnectionError(ConnectionError):
    """Blender is unreachable or sent something that is not a valid response."""


class BlenderError(RuntimeError):
    """Blender executed the request and reported an error."""

    def __init__(self, message, response=None):
        super().__init__(message)
        self.response = response or {}


def connection_params(host=None, port=None):
    host = host or os.environ.get("BLENDER_MCP_HOST", DEFAULT_HOST)
    port = int(port or os.environ.get("BLENDER_MCP_PORT", DEFAULT_PORT))
    return host, port


def send_request(request, host=None, port=None, timeout=DEFAULT_TIMEOUT):
    """Send an arbitrary request dict and return the decoded response dict."""
    host, port = connection_params(host, port)
    data = json.dumps(request).encode("utf-8") + b"\0"
    buf = bytearray()
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(data)
            while b"\0" not in buf:
                chunk = sock.recv(_RECV_SIZE)
                if not chunk:
                    break
                buf.extend(chunk)
    except ConnectionRefusedError as ex:
        raise BlenderConnectionError(
            "Cannot connect to Blender at {}:{}. Open Blender with the MCP add-on enabled "
            "and its server started (Preferences > Add-ons > MCP).".format(host, port)) from ex
    except socket.timeout as ex:
        raise BlenderConnectionError(
            "Timed out after {:.0f}s waiting for Blender at {}:{}".format(timeout, host, port)) from ex
    except OSError as ex:
        raise BlenderConnectionError("Socket error talking to Blender at {}:{}: {}".format(host, port, ex)) from ex

    if not buf:
        raise BlenderConnectionError("Blender closed the connection without a response")
    line = bytes(buf).partition(b"\0")[0]
    try:
        return json.loads(line.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as ex:
        raise BlenderConnectionError("Invalid response from Blender: {}".format(ex)) from ex


def send_code(code, strict_json=True, host=None, port=None, timeout=DEFAULT_TIMEOUT):
    """Execute *code* in Blender. Returns the full response envelope."""
    return send_request({"type": "execute", "code": code, "strict_json": strict_json}, host, port, timeout)


# Appended to every tool's code. ``main`` may return a dict (immediate result) or a
# callable (deferred: becomes ``check_is_finished`` for the add-on's poller).
_FOOTER = (
    "\n_rv = main(PARAMS)\n"
    "if callable(_rv):\n"
    "    check_is_finished = _rv\n"
    "    result = {}\n"
    "else:\n"
    "    result = _rv\n"
)


def build_toolcode(body, params=None):
    """Bind *params* to ``PARAMS`` and call ``main(PARAMS)`` after the tool *body*."""
    return "PARAMS = {!r}\n{}\n{}".format(params, body, _FOOTER)


def unwrap(response):
    """Return ``response['result']`` or raise :class:`BlenderError`."""
    if response.get("status") != "ok":
        msg = str(response.get("message", "Unknown error"))
        if response.get("stderr"):
            msg += "\n" + str(response["stderr"])
        raise BlenderError(msg, response)
    return response.get("result", {})


def run_tool(body, params=None, host=None, port=None, timeout=DEFAULT_TIMEOUT):
    """Run a tool body in the live Blender; returns its ``result`` dict (strict JSON)."""
    response = send_code(build_toolcode(body, params), True, host, port, timeout)
    return unwrap(response)


def run_code(code, host=None, port=None, timeout=DEFAULT_TIMEOUT):
    """Run arbitrary code (non-strict JSON: unserialisable values are ``repr``-ed). Returns the envelope."""
    return send_code(code, False, host, port, timeout)
