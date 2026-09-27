"""
Smoke-test the tools. Safe by default: only read-only calls against the live Blender, docs tools,
and background-Blender (`*_for_cli`) tools. Nothing changes the open scene, selection, workspace
or viewport.

    python selftest.py                     # read-only + docs + cli
    python selftest.py --blend Untitled.blend
    python selftest.py --screenshots       # also capture window/3D-area PNGs (read-only, writes files)
    python selftest.py --render            # also render a thumbnail (briefly opens a render window)

NOT covered (they mutate the live session; try them by hand): jump_to_* tools, and
jump_to_tab_by_space_type --allow-edits (creates a workspace).
"""
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CLI = os.path.join(HERE, "blender_mcp_cli.py")


def run(args, timeout=300):
    t = time.time()
    p = subprocess.run([sys.executable, CLI, *args], capture_output=True, text=True, timeout=timeout)
    try:
        payload = json.loads(p.stdout) if p.stdout.strip() else None
    except ValueError:
        payload = None
    return p.returncode, payload, p.stderr.strip(), time.time() - t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--blend", default=os.path.join(HERE, "Untitled.blend"), help="file for *_for_cli tools")
    ap.add_argument("--screenshots", action="store_true")
    ap.add_argument("--render", action="store_true")
    a = ap.parse_args()

    # (label, args, predicate on payload, needs live blender)
    ok = lambda p: isinstance(p, dict) and p.get("status") == "ok"
    checks = [
        ("ping", ["ping"], ok, True),
        ("execute_blender_code", ["execute_blender_code", "import bpy\nresult={'v': bpy.app.version_string}"],
         ok, True),
        ("get_objects_summary", ["get_objects_summary"], ok, True),
        ("get_object_detail_summary", ["get_object_detail_summary", "Camera"], ok, True),
        ("get_screenshot_of_window_as_json", ["get_screenshot_of_window_as_json"], ok, True),
    ]
    for s in ("datablocks", "missing_files", "of_linked_libraries", "path_info", "usage_guess"):
        checks.append(("get_blendfile_summary_" + s, ["get_blendfile_summary_" + s], ok, True))
        checks.append(("get_blendfile_summary_%s_for_cli" % s, ["get_blendfile_summary_%s_for_cli" % s, a.blend],
                       ok, False))
    checks += [
        ("execute_blender_code_for_cli",
         ["execute_blender_code_for_cli", a.blend, "import bpy\nresult={'bg': bpy.app.background}"],
         lambda p: p == {"bg": True}, False),
        ("get_python_api_docs (definition)", ["get_python_api_docs", "bpy.types.Camera.angle"],
         lambda p: p and p["kind"] == "definition", False),
        ("get_python_api_docs (namespace)", ["get_python_api_docs", "bpy.*"],
         lambda p: p and p["kind"] == "namespace", False),
        ("search_api_docs", ["search_api_docs", "camera lens angle", "-n", "3"],
         lambda p: p and p["total_hits"] > 0, False),
        ("search_manual_docs", ["search_manual_docs", "bake", "-n", "3"],
         lambda p: p and p["total_hits"] > 0, False),
        ("expected error: missing object", ["get_object_detail_summary", "__nope__"],
         lambda p: isinstance(p, dict) and p.get("status") == "error", True),
    ]
    tmp = tempfile.gettempdir()
    if a.screenshots:
        checks.append(("get_screenshot_of_window_as_image",
                       ["get_screenshot_of_window_as_image", "-o", os.path.join(tmp, "bmcp_window.png")], ok, True))
        checks.append(("get_screenshot_of_area_as_image",
                       ["get_screenshot_of_area_as_image", "VIEW_3D", "-o", os.path.join(tmp, "bmcp_view3d.png")],
                       ok, True))
    if a.render:
        checks.append(("render_thumbnail_to_path (deferred)",
                       ["render_thumbnail_to_path", os.path.join(tmp, "bmcp_thumb.png")], ok, True))

    live = run(["ping"])[0] == 0
    if not live:
        print("NOTE: no Blender bridge reachable; live checks will be skipped.\n")
    failed = 0
    for label, args, pred, needs_live in checks:
        if needs_live and not live:
            print("SKIP  %-46s (no live Blender)" % label)
            continue
        rc, payload, err, dt = run(args)
        try:
            passed = bool(pred(payload))
        except Exception:
            passed = False
        failed += not passed
        print("%s  %-46s %5.1fs%s" % ("PASS" if passed else "FAIL", label, dt,
                                      "" if passed else "   rc=%s %s" % (rc, err[:120])))
    print("\n%d check(s) failed" % failed if failed else "\nall checks passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
