"""
Optional: expose the same PIPESIM tools over MCP, so any MCP client can drive PIPESIM
(Claude Desktop, Claude Code, LM Studio, Open WebUI, etc.). Needs Python >= 3.10 and `pip install mcp`.
"""
from mcp.server.fastmcp import FastMCP
import pipesim_tools as pt

mcp = FastMCP("pipesim")
for f in pt.TOOLS:
    mcp.tool(name=f.__name__, description=f.__doc__)(f)

if __name__ == "__main__":
    mcp.run()  # stdio
