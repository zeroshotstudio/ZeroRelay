#!/usr/bin/env python3
"""
MCP Tool Registry for ZeroRelay.

Maintains a mapping of tool names to their owning agents (roles).
Agents register tools on connect; the registry cleans up on disconnect.
"""

import logging

log = logging.getLogger("zerorelay.mcp")


class MCPRegistry:
    """In-memory registry mapping tool_name → owner role."""

    def __init__(self):
        # tool_name -> {"owner": str, "description": str, "input_schema": dict}
        self._tools: dict[str, dict] = {}
        # role -> set of tool_names (for fast cleanup on disconnect)
        self._role_tools: dict[str, set[str]] = {}

    def register(self, role: str, tools: list[dict]) -> list[str]:
        """Register tools for a role. Returns list of successfully registered tool names.

        Rejects tools missing a 'name' field and tools whose name is already
        owned by a different role. Same-owner re-registration overwrites
        (idempotent for reconnect).
        """
        registered = []
        for tool in tools:
            name = tool.get("name")
            if not name:
                log.warning(f"[MCP] {role}: skipping tool with missing 'name'")
                continue

            existing = self._tools.get(name)
            if existing and existing["owner"] != role:
                log.warning(f"[MCP] {role}: tool '{name}' already registered by {existing['owner']}, skipping")
                continue

            self._tools[name] = {
                "owner": role,
                "description": tool.get("description", ""),
                "input_schema": tool.get("input_schema", {}),
            }
            self._role_tools.setdefault(role, set()).add(name)
            registered.append(name)

        return registered

    def unregister_role(self, role: str) -> bool:
        """Remove all tools owned by a role. Returns True if any were removed."""
        tool_names = self._role_tools.pop(role, set())
        for name in tool_names:
            self._tools.pop(name, None)
        if tool_names:
            log.info(f"[MCP] Unregistered {len(tool_names)} tools from {role}")
        return bool(tool_names)

    def resolve(self, tool_name: str) -> str | None:
        """Return the owner role for a tool, or None if not registered."""
        entry = self._tools.get(tool_name)
        return entry["owner"] if entry else None

    def get_tools(self, exclude_role: str | None = None) -> list[dict]:
        """Return all registered tools with owner info.

        Optionally exclude tools owned by exclude_role (an agent doesn't
        need its own tools in the remote list).
        """
        result = []
        for name, entry in self._tools.items():
            if exclude_role and entry["owner"] == exclude_role:
                continue
            result.append({
                "name": name,
                "description": entry["description"],
                "input_schema": entry["input_schema"],
                "owner": entry["owner"],
            })
        return result

    def __len__(self) -> int:
        return len(self._tools)
