#!/usr/bin/env python3
"""Unit tests for the MCP Tool Registry."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import unittest
from core.mcp_registry import MCPRegistry


class TestMCPRegistry(unittest.TestCase):

    def setUp(self):
        self.registry = MCPRegistry()

    def test_register_and_resolve(self):
        tools = [{"name": "run_sql", "description": "Run a SQL query",
                  "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}}}]
        registered = self.registry.register("db_agent", tools)
        self.assertEqual(registered, ["db_agent/run_sql"])
        self.assertEqual(self.registry.resolve("db_agent/run_sql"), "db_agent")
        self.assertEqual(len(self.registry), 1)

    def test_register_multiple_tools(self):
        tools = [
            {"name": "tool_a", "description": "A"},
            {"name": "tool_b", "description": "B"},
            {"name": "tool_c", "description": "C"},
        ]
        registered = self.registry.register("agent1", tools)
        self.assertEqual(len(registered), 3)
        self.assertEqual(len(self.registry), 3)
        for t in tools:
            ns_name = f"agent1/{t['name']}"
            self.assertEqual(self.registry.resolve(ns_name), "agent1")

    def test_unregister_role(self):
        self.registry.register("agent1", [{"name": "tool_a", "description": "A"}])
        self.registry.register("agent2", [{"name": "tool_b", "description": "B"}])
        removed = self.registry.unregister_role("agent1")
        self.assertTrue(removed)
        self.assertIsNone(self.registry.resolve("agent1/tool_a"))
        self.assertEqual(self.registry.resolve("agent2/tool_b"), "agent2")
        self.assertEqual(len(self.registry), 1)

    def test_unregister_empty_role(self):
        removed = self.registry.unregister_role("nonexistent")
        self.assertFalse(removed)

    def test_same_plain_name_different_owners_both_succeed(self):
        """Two roles can register tools with the same plain name (different namespaces)."""
        reg1 = self.registry.register("agent1", [{"name": "search", "description": "A"}])
        reg2 = self.registry.register("agent2", [{"name": "search", "description": "B"}])
        self.assertEqual(reg1, ["agent1/search"])
        self.assertEqual(reg2, ["agent2/search"])
        self.assertEqual(self.registry.resolve("agent1/search"), "agent1")
        self.assertEqual(self.registry.resolve("agent2/search"), "agent2")
        self.assertEqual(len(self.registry), 2)

    def test_same_owner_re_register_overwrites(self):
        self.registry.register("agent1", [{"name": "my_tool", "description": "v1"}])
        registered = self.registry.register("agent1", [{"name": "my_tool", "description": "v2"}])
        self.assertEqual(registered, ["agent1/my_tool"])
        tools = self.registry.get_tools()
        self.assertEqual(tools[0]["description"], "v2")

    def test_get_tools_returns_all(self):
        self.registry.register("a1", [{"name": "t1", "description": "D1"}])
        self.registry.register("a2", [{"name": "t2", "description": "D2"}])
        tools = self.registry.get_tools()
        self.assertEqual(len(tools), 2)
        names = {t["name"] for t in tools}
        self.assertEqual(names, {"a1/t1", "a2/t2"})
        for t in tools:
            self.assertIn("owner", t)
            self.assertIn("input_schema", t)

    def test_get_tools_exclude_role(self):
        self.registry.register("a1", [{"name": "t1", "description": "D1"}])
        self.registry.register("a2", [{"name": "t2", "description": "D2"}])
        tools = self.registry.get_tools(exclude_role="a1")
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]["name"], "a2/t2")

    def test_malformed_tool_skipped(self):
        tools = [
            {"description": "no name"},
            {"name": "valid_tool", "description": "has name"},
        ]
        registered = self.registry.register("agent1", tools)
        self.assertEqual(registered, ["agent1/valid_tool"])
        self.assertEqual(len(self.registry), 1)

    def test_default_input_schema(self):
        self.registry.register("a1", [{"name": "t1", "description": "D1"}])
        tools = self.registry.get_tools()
        self.assertEqual(tools[0]["input_schema"], {})

    def test_resolve_unknown_tool(self):
        self.assertIsNone(self.registry.resolve("nonexistent"))

    def test_resolve_plain_name_returns_none(self):
        """Resolving a non-namespaced name returns None (must use owner/tool format)."""
        self.registry.register("agent1", [{"name": "my_tool", "description": "D"}])
        self.assertIsNone(self.registry.resolve("my_tool"))

    def test_make_name(self):
        self.assertEqual(MCPRegistry.make_name("owner", "tool"), "owner/tool")

    def test_parse_name_valid(self):
        result = MCPRegistry.parse_name("owner/tool")
        self.assertEqual(result, ("owner", "tool"))

    def test_parse_name_no_separator(self):
        self.assertIsNone(MCPRegistry.parse_name("plain_name"))

    def test_parse_name_empty_parts(self):
        self.assertIsNone(MCPRegistry.parse_name("/tool"))
        self.assertIsNone(MCPRegistry.parse_name("owner/"))

    def test_non_string_name_skipped(self):
        tools = [{"name": 123, "description": "numeric"}, {"name": "ok", "description": "valid"}]
        registered = self.registry.register("agent1", tools)
        self.assertEqual(registered, ["agent1/ok"])


if __name__ == "__main__":
    unittest.main()
