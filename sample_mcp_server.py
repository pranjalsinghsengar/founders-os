"""Real MCP transport, harmless local fixture tool; no external research."""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Company local tools")


@mcp.tool()
def inspect_workflow(topic: str) -> dict:
    """Return local fixture information for integration testing."""
    return {"topic": topic, "source": "Local test fixture",
            "workflow": ["research", "proposal", "approval", "build", "review"],
            "limitation": "Not real market research"}


if __name__ == "__main__":
    mcp.run(transport="stdio")
