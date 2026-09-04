"""Tests for the ANVAYA MCP server surface."""

from __future__ import annotations

from anvaya.mcp_server import list_anvaya_tools


def test_mcp_server_lists_anvaya_tools() -> None:
    """The MCP server exposes the ANVAYA tool registry."""
    import json

    result = json.loads(list_anvaya_tools())
    names = {t["name"] for t in result["items"]}
    assert "threat_intelligence_lookup" in names
    assert "trigger_automation" in names
    assert "notify_via_email" in names
    assert "lyzr_propose_rule" in names
    assert result["total"] > 0
