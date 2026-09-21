import os

import httpx
from fastmcp import FastMCP

mcp = FastMCP("AI Trading Analysis")

BACKEND_URL = "http://127.0.0.1:8000"


@mcp.tool
async def analyze_market(
    symbol: str,
    count: int = 300,
) -> dict:
    """
    Run the live market analysis engine for a symbol.

    Returns multi-timeframe technical analysis, market bias,
    key levels, scenarios, confirmation, stop plan, trade plan,
    and AI reasoning.
    """
    if count < 200 or count > 1000:
        raise ValueError("count must be between 200 and 1000")

    token = os.getenv("JWT_TOKEN")
    if not token:
        raise RuntimeError("JWT_TOKEN is not configured")

    async with httpx.AsyncClient(timeout=90.0) as client:
        response = await client.get(
            f"{BACKEND_URL}/analysis/{symbol}",
            params={"count": count},
            headers={"Authorization": f"Bearer {token}"},
        )

    if response.status_code != 200:
        raise RuntimeError(
            f"Backend analysis failed: "
            f"{response.status_code} {response.text}"
        )

    return response.json()


@mcp.tool
def ping() -> str:
    """Check whether the AI Trading MCP server is alive."""
    return "AI Trading MCP is alive."


if __name__ == "__main__":
    mcp.run()
