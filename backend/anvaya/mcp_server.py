"""MCP server exposing ANVAYA's own tools to external agents.

Run with:
    python -m anvaya.mcp_server

The server exposes selected incident/investigation tools so a client like
Claude Desktop can query ANVAYA without going through its own frontend.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import AsyncIterator

from mcp.server import MCPServer
from sqlmodel import Session, select

from anvaya.agent import default_tool_registry
from anvaya.agent.executor import LocalToolExecutor
from anvaya.config import settings
from anvaya.db import engine
from anvaya.logging import get_logger
from anvaya.models.incident import Incident

logger = get_logger("anvaya.mcp_server")


@asynccontextmanager
async def app_lifespan(server: MCPServer) -> AsyncIterator[dict]:
    """Initialize the MCP server lifespan."""
    logger.info("mcp_server.started")
    yield {}
    logger.info("mcp_server.stopped")


server = MCPServer(
    "anvaya",
    version="0.1.0",
    title="ANVAYA Autonomous SOC",
    description="MCP interface to ANVAYA incident detection and investigation tools.",
    lifespan=app_lifespan,
)


@server.tool()
def list_incidents(limit: int = 10) -> str:
    """List the most recent incidents from ANVAYA."""
    with Session(engine) as session:
        incidents = session.exec(
            select(Incident).order_by(Incident.created_at.desc()).limit(limit)
        ).all()
        items = [
            {
                "incident_id": i.incident_id,
                "title": i.title,
                "status": i.status.value,
                "severity": i.severity,
                "attack_family": i.attack_family,
            }
            for i in incidents
        ]
        return json.dumps({"items": items, "total": len(items)}, indent=2)


@server.tool()
def get_incident(incident_id: str) -> str:
    """Get detailed information about a single ANVAYA incident."""
    with Session(engine) as session:
        incident = session.exec(
            select(Incident).where(Incident.incident_id == incident_id)
        ).first()
        if not incident:
            return json.dumps({"error": "Incident not found"})
        return json.dumps(incident.model_dump(), indent=2, default=str)


@server.tool()
def threat_intelligence_lookup(indicator: str, indicator_type: str = "technique") -> str:
    """Look up threat intelligence for an indicator using Tavily or local fixture."""
    with Session(engine) as session:
        executor = LocalToolExecutor(session)
        result = executor.handle_threat_intelligence_lookup(
            {"indicator": indicator, "indicator_type": indicator_type}
        )
        return json.dumps(result.model_dump(), indent=2, default=str)


@server.tool()
def trigger_automation(workflow: str, incident_id: str) -> str:
    """Trigger an n8n workflow for an incident."""
    with Session(engine) as session:
        executor = LocalToolExecutor(session)
        result = executor.handle_trigger_automation(
            {"workflow": workflow, "incident_id": incident_id, "payload": {}}
        )
        return json.dumps(result.model_dump(), indent=2, default=str)


@server.tool()
def list_anvaya_tools() -> str:
    """List all tools registered in the ANVAYA tool registry."""
    registry = default_tool_registry()
    tools = [
        {
            "name": t.name,
            "description": t.description,
            "category": t.category,
            "provider": t.provider,
        }
        for t in registry.list_tools()
    ]
    return json.dumps({"items": tools, "total": len(tools)}, indent=2)


def main() -> None:
    """Run the ANVAYA MCP server over SSE."""
    host = settings.api_host
    port = 8001
    server.run("sse", host=host, port=port)


if __name__ == "__main__":
    main()
