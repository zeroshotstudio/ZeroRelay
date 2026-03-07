#!/usr/bin/env python3
"""
MCP Tool Registry for ZeroRelay.

Maintains a mapping of tool names to their owning agents (roles).
Tools are stored with namespaced keys ({owner}/{tool_name}) to prevent
collisions. Agents register with plain names; the registry namespaces them.
"""

import logging

log = logging.getLogger("zerorelay.mcp")

SEPARATOR = "/"


class MCPRegistry:
    """In-memory registry mapping namespaced tool names to owner roles."""

    def __init__(self):
        # "owner/tool_name" -> {"owner": str, "description": str, "input_schema": dict}
        self._tools: dict[str, dict] = {}
        # role -> set of namespaced tool_names (for fast cleanup on disconnect)
        self._role_tools: dict[str, set[str]] = {}

    @staticmethod
    def make_name(owner: str, tool_name: str) -> str:
        """Build a namespaced tool name: owner/tool_name."""
        return f"{owner}{SEPARATOR}{tool_name}"

    @staticmethod
    def parse_name(namespaced: str) -> tuple[str, str] | None:
        """Split a namespaced name into (owner, tool_name), or None if invalid."""
        if SEPARATOR not in namespaced:
            return None
        owner, _, tool_name = namespaced.partition(SEPARATOR)
        if not owner or not tool_name:
            return None
        return (owner, tool_name)

    def register(self, role: str, tools: list[dict]) -> list[str]:
        """Register tools for a role. Returns list of namespaced tool names.

        Tools are stored under namespaced keys ({role}/{name}), so different
        roles can register tools with the same plain name without collision.
        Same-owner re-registration overwrites (idempotent for reconnect).
        """
        registered = []
        for tool in tools:
            name = tool.get("name")
            if not name or not isinstance(name, str):
                log.warning(f"[MCP] {role}: skipping tool with missing/invalid 'name'")
                continue

            ns_name = self.make_name(role, name)
            self._tools[ns_name] = {
                "owner": role,
                "description": tool.get("description", ""),
                "input_schema": tool.get("input_schema", {}),
            }
            self._role_tools.setdefault(role, set()).add(ns_name)
            registered.append(ns_name)

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
        """Return the owner role for a namespaced tool, or None if not registered."""
        entry = self._tools.get(tool_name)
        return entry["owner"] if entry else None

    def get_tools(self, exclude_role: str | None = None) -> list[dict]:
        """Return all registered tools with owner info and namespaced names.

        Optionally exclude tools owned by exclude_role (an agent doesn't
        need its own tools in the remote list).
        """
        result = []
        for ns_name, entry in self._tools.items():
            if exclude_role and entry["owner"] == exclude_role:
                continue
            result.append({
                "name": ns_name,
                "description": entry["description"],
                "input_schema": entry["input_schema"],
                "owner": entry["owner"],
            })
        return result

    def __len__(self) -> int:
        return len(self._tools)
