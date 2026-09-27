"""
Send a Python script to an already-running Blender via its MCP add-on socket.

Usage:
    python send_to_blender.py floating_island.py
    python send_to_blender.py floating_island.py --port 9876

Requirements:
  - Blender is open with the "blender-mcp" extension enabled and its server started.
  - Plain Python 3 on your machine (no extra packages).

Protocol (see mcp_to_blender_server.py in the extension):
  - Request:  {"type": "execute", "code": <str>, "strict_json": <bool>}
  - Messages are null-byte (b"\\0") delimited JSON, both ways.
  - The executed code may set a `result` dict variable to return data.
"""
import argparse
import json
import socket
import sys


def send(port, code, timeout=120):
    payload = {"type": "execute", "code": code, "strict_json": True}
    data = json.dumps(payload).encode("utf-8") + b"\0"
    with socket.create_connection(("localhost", port), timeout=timeout) as s:
        s.sendall(data)
        buf = bytearray()
        while b"\0" not in buf:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf.extend(chunk)
    buf = buf.split(b"\0")[0]
    return json.loads(buf) if buf else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("--port", type=int, default=9876)
    args = ap.parse_args()

    with open(args.script, encoding="utf-8") as f:
        code = f.read()

    try:
        resp = send(args.port, code)
    except ConnectionRefusedError:
        sys.exit(f"Nothing is listening on localhost:{args.port}. "
                 "Open Blender and start the blender-mcp extension's server first.")
    except (socket.timeout, OSError, ValueError) as e:
        sys.exit(f"Failed to talk to Blender: {e}")

    if resp is None:
        sys.exit("Blender closed the connection without sending a response.")

    if resp.get("status") == "ok":
        print("Done.")
        if resp.get("stdout"):
            print(resp["stdout"])
        if resp.get("result"):
            print(resp["result"])
    else:
        if resp.get("stderr"):
            print(resp["stderr"], file=sys.stderr)
        sys.exit(f"Blender reported an error:\n{resp.get('message', resp)}")


if __name__ == "__main__":
    main()
