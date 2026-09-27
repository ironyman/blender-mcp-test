"""
Single entry point for every Blender MCP tool, using the official tool names.

    python blender_mcp_cli.py --help                       # list all tools
    python blender_mcp_cli.py get_objects_summary
    python blender_mcp_cli.py execute_blender_code "result = {'n': len(bpy.data.objects)}"
    python blender_mcp_cli.py render_thumbnail_to_path thumb.png
    python blender_mcp_cli.py get_blendfile_summary_datablocks_for_cli Untitled.blend

Connection: --host/--port (or env BLENDER_MCP_HOST / BLENDER_MCP_PORT); BLENDER_PATH for *_for_cli.
Each tool module can also be run alone:  python -m bmcp.tools_scene --help
"""
import sys

from bmcp import tools_code, tools_docs, tools_render, tools_scene, tools_server, tools_ui
from bmcp.cli import main

ALL_TOOLS = (tools_code.TOOLS + tools_scene.TOOLS + tools_ui.TOOLS + tools_render.TOOLS
             + tools_docs.TOOLS + tools_server.TOOLS)

if __name__ == "__main__":
    sys.exit(main(ALL_TOOLS, prog="blender_mcp_cli.py"))
