"""The ruflo preset must wire a pinned, filtered Ruflo MCP server."""

from __future__ import annotations

import json
from pathlib import Path

from openjarvis.core.config import load_config

PRESET = (
    Path(__file__).resolve().parents[2]
    / "configs"
    / "openjarvis"
    / "examples"
    / "ruflo.toml"
)


def _ruflo_server() -> tuple[dict, list[str]]:
    cfg = load_config(path=PRESET)
    servers = json.loads(cfg.tools.mcp.servers)
    assert cfg.tools.mcp.enabled
    assert len(servers) == 1
    enabled = cfg.tools.enabled
    if isinstance(enabled, str):
        enabled = [name.strip() for name in enabled.split(",") if name.strip()]
    return servers[0], list(enabled)


def test_ruflo_server_is_pinned_stdio() -> None:
    server, _ = _ruflo_server()
    assert server["name"] == "ruflo"
    assert server["command"] == "npx"
    package = server["args"][1]
    assert package.startswith("ruflo@")
    version = package.split("@", 1)[1]
    assert version and version != "latest"
    assert server["args"][2:] == ["mcp", "start"]


def test_ruflo_tools_are_filtered_and_enabled() -> None:
    server, enabled = _ruflo_server()
    include = server["include_tools"]
    assert 0 < len(include) <= 20
    # The outer [tools] enabled filter would drop any MCP tool not listed.
    missing = set(include) - set(enabled)
    assert not missing, f"ruflo tools missing from [tools] enabled: {missing}"
    # Tools that call cloud LLM providers stay out of the default preset.
    assert "agent_execute" not in include
