"""MCP client: launches the observability server for one incident and exposes
its tools (as LangChain tools) and the firing alert (an MCP resource)."""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools

ROOT = Path(__file__).resolve().parents[1]

# Tools that change system state; only the post-approval node may call them.
WRITE_TOOLS = {"apply_fix"}


@dataclass
class McpContext:
    alert: str
    tools: dict[str, BaseTool]

    @property
    def read_tools(self) -> list[BaseTool]:
        return [t for name, t in self.tools.items() if name not in WRITE_TOOLS]


@asynccontextmanager
async def connect(case_id: str, suite: str = "v1") -> AsyncIterator[McpContext]:
    client = MultiServerMCPClient({
        "observability": {
            "transport": "stdio",
            "command": sys.executable,
            "args": ["-m", "mcp_server.observability_server", "--scenario", case_id, "--suite", suite],
            "cwd": str(ROOT),
        }
    })
    async with client.session("observability") as session:
        tools = await load_mcp_tools(session)
        resource = await session.read_resource("alert://current")
        yield McpContext(alert=resource.contents[0].text, tools={t.name: t for t in tools})


def content_to_text(content) -> str:
    """MCP tool results arrive as a string or a list of content blocks."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(
            block.get("text", "") if isinstance(block, dict) else str(block) for block in content
        )
    return str(content)
