# Blender MCP as Python scripts

Plain-Python implementations of every tool and interface in the **official Blender Lab MCP server**
([`lab/blender_mcp`](https://projects.blender.org/lab/blender_mcp), add-on v1.0.3, Blender 5.1+),
so you can drive Blender from scripts without an LLM or MCP client in the loop.

Tested against Blender 5.2.2 LTS on Windows with the official add-on running. Standard library only.

```
blender_mcp_cli.py      single entry point: every tool, official names
selftest.py             smoke tests (safe by default)
bmcp/
  client.py             socket protocol client (+ deferred-reply handling)
  blender_cli.py        run code in `blender --background` (the *_for_cli half)
  cli.py                tiny argparse framework
  tools_code.py         execute_blender_code[_for_cli]
  tools_scene.py        blend-file summaries (x5, live + cli), objects summary, object detail
  tools_ui.py           screenshots (3) and jump_to_* navigation (4)
  tools_render.py       render_viewport_to_path, render_thumbnail_to_path
  tools_docs.py         get_python_api_docs, search_api_docs, search_manual_docs
  tools_server.py       extras: ping, raw, start/stop_background_server
send_to_blender.py      (pre-existing) minimal one-file sender
floating_island.py      (pre-existing) example scene script
```

## Quick start

1. Blender open, **MCP add-on enabled and server started** (it autostarts by default on `localhost:9876`).
2. From this folder:

```powershell
.venv\Scripts\python.exe blender_mcp_cli.py --help              # list all tools
.venv\Scripts\python.exe blender_mcp_cli.py ping
.venv\Scripts\python.exe blender_mcp_cli.py get_objects_summary
.venv\Scripts\python.exe blender_mcp_cli.py execute_blender_code "import bpy`nresult = {'n': len(bpy.data.objects)}"
.venv\Scripts\python.exe blender_mcp_cli.py render_thumbnail_to_path C:\temp\thumb.png
.venv\Scripts\python.exe blender_mcp_cli.py get_blendfile_summary_usage_guess_for_cli Untitled.blend
.venv\Scripts\python.exe -m bmcp.tools_docs get_python_api_docs bpy.types.Camera.angle
.venv\Scripts\python.exe selftest.py
```

Output is JSON on stdout; errors go to stderr; exit code is `0` ok, `1` tool/Blender error, `2` cannot reach Blender.
As a library: `from bmcp.client import run_tool, run_code`.

Config (same env vars as the official server): `BLENDER_MCP_HOST`, `BLENDER_MCP_PORT`, `BLENDER_PATH`
(for `*_for_cli`; auto-detected under `Program Files\Blender Foundation`), plus `BLMCP_DATA_DIR` (docs).

---

## Scope: what the official MCP exposes

### Interfaces

| # | Interface | Detail |
|---|---|---|
| 1 | **Socket bridge** | TCP `localhost:9876`; one request per connection; null-byte-delimited JSON. Request `{"type":"execute","code":…,"strict_json":bool}`. Response `{"status":"ok","result":{…},"stdout":…,"stderr":…}` or `{"status":"error","message":<traceback>}`. Code returns data by assigning a **dict** to `result`. |
| 2 | **Deferred replies** | If the code defines a callable `check_is_finished`, the add-on holds the connection open and polls it on a timer until it returns a dict (`None` = still running). Used for renders; 1 hour cap. |
| 3 | **Background mode** | `blender --background FILE --online-mode --command blender_mcp --port N` runs a *blocking* bridge (no deferred replies, no GUI). `blender --background FILE --python …` powers the `*_for_cli` tools. |
| 4 | **MCP transports** | The separate `blender-mcp` process speaks MCP over **stdio** (default) or **streamable HTTP** (`--transport http`, port 8000) and relays to the bridge. *Not reimplemented here — the point of this project is to skip it.* |
| 5 | **Configuration** | Env `BLENDER_MCP_HOST/PORT`, `BLENDER_PATH`; add-on prefs (host, port, autostart, timers, log); operators `blmcp.server_start/stop`. The add-on refuses to start unless Blender's *online access* is enabled. |
| 6 | **Guardrails** | "Weak sandbox": blocks `sys.exit` and `wm.quit_blender`, `wm.read_factory_settings`, `wm.read_factory_userpref`, `wm.read_userpref`. 10 MiB request cap; stalled clients evicted. **Not a security boundary** — code has full `bpy`/OS access. |
| 7 | **Bundled docs** | 1,857 Python-API + 2,217 manual RST files, exposed via 3 tools, plus LLM instructions (`prompts.yml`). |

### The 26 tools (all implemented)

> Correction: an earlier summary said 24 — the real count is **26**.

| Family | Tools (`X` = also `X_for_cli BLEND_FILE`) | Where it runs |
|---|---|---|
| Code | `execute_blender_code` (+cli) | live / background |
| Blend-file summaries | `get_blendfile_summary_` `datablocks`, `missing_files`, `of_linked_libraries`, `path_info`, `usage_guess` — each with `_for_cli` (10) | live / background |
| Scene | `get_objects_summary`, `get_object_detail_summary NAME` | live |
| Screenshots | `get_screenshot_of_area_as_image AREA -o F.png`, `get_screenshot_of_window_as_image -o F.png`, `get_screenshot_of_window_as_json` | live GUI only |
| Navigation | `jump_to_tab_by_name`, `jump_to_tab_by_space_type [--allow-edits]`, `jump_to_view3d_object_by_name`, `jump_to_view3d_object_data_by_name` (`[--allow-edits]`) | live GUI only |
| Render | `render_viewport_to_path`, `render_thumbnail_to_path` (deferred) | live (deferred) / background (sync) |
| Docs | `get_python_api_docs ID`, `search_api_docs Q`, `search_manual_docs Q` | local files, no Blender |

Extras (not official tools): `ping`, `raw JSON`, `start_background_server [FILE] [--port 9877]`, `stop_background_server --pid N`.

---

## Behaviour notes and deliberate differences from the official server

* **`execute_blender_code` runs in a bare namespace**, exactly like the official add-on: write `import bpy` yourself
  and assign a dict to `result`. Non-JSON values are `repr`-ed (`strict_json=false`); all other tools use strict JSON.
* **Screenshots** are written to a PNG (`-o`) instead of returned as an inline MCP image. `--size-limit BYTES`
  downscales; the default is *no* limit (the official default is the 1 MB MCP message cap).
* **Render output path**: a bare filename goes to `<Blender tempdir>/blender_mcp/` (official behaviour); an absolute
  path is used as given. Temporary overrides for thumbnails are restored **after the render job ends** (the official
  code restores some immediately, which can race a running render).
* **`get_object_detail_summary` errors** list at most 50 object names (official lists all).
* **Docs search is a reimplementation.** Same semantics (tokenised, stop-words dropped, all tokens must match, `--context`,
  `--index` to widen to the section) but different ranking, so scores/order will differ from the official tool.
  Corpus text is cached in `bmcp/.cache/` (delete or `--rebuild-cache` to refresh).
* **Docs corpus location**: `--data-dir` / `BLMCP_DATA_DIR`, an installed `blmcp` package, or the Claude Desktop
  extension folder (auto-detected, including the MSIX-virtualised `AppData\Local\Packages\Claude_*`).
  Otherwise clone the repo and point at `mcp/blmcp/data`.
* **Blender 5.x compatibility**: usage-guess reads `compositing_node_group` / `strips` with fallbacks for older builds.
* **Headless bridge limits**: screenshots and `jump_to_*` refuse; deferred replies are rejected. A background thumbnail of
  the 91-object `Untitled.blend` took ~54 s.

## Safety

Everything here executes code inside your Blender session with **no sandbox** — `execute_blender_code` can delete data or
touch the filesystem. `jump_to_*` change selection, active object, workspace and viewport; `--allow-edits` can un-hide
objects, enable collections, or create a workspace. Save first.

## What was tested (Blender 5.2.2, Windows)

Verified against the live add-on: every read-only tool, `execute_blender_code` (result, stdout, `repr` fallback, error,
non-dict result, sandbox block), all five `_for_cli` summaries + `execute_blender_code_for_cli`, window/area
screenshots (incl. size limit), `jump_to_tab_by_name`, `jump_to_tab_by_space_type` (no-create), both `jump_to_view3d_*`
tools with viewport framing, deferred `render_thumbnail_to_path` and `render_viewport_to_path` (settings verified
restored), the headless bridge (start, ping, sync render, deferred rejection, raw errors, stop), and all six result kinds
of `get_python_api_docs` plus search/context/index. `python selftest.py --screenshots --render` passes 24/24.

**Not tested:** `jump_to_tab_by_space_type --allow-edits` (creates a workspace), `jump_to_*_by_name --allow-edits`
un-hiding a hidden object, the dirty-file sync in `synced_blend_for_cli` (live session had no saved file), non-EEVEE render
engines (Cycles thumbnail sample override), and the MCP stdio/HTTP transports.

## Licence

The tool logic is derived from Blender Lab's `blender_mcp` (GPL-3.0-or-later), so these scripts are GPL-3.0-or-later too.
