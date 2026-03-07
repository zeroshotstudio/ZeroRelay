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
        self.assertEqual(registered, ["run_sql"])
        self.assertEqual(self.registry.resolve("run_sql"), "db_agent")
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
            self.assertEqual(self.registry.resolve(t["name"]), "agent1")

    def test_unregister_role(self):
        self.registry.register("agent1", [{"name": "tool_a", "description": "A"}])
        self.registry.register("agent2", [{"name": "tool_b", "description": "B"}])
        removed = self.registry.unregister_role("agent1")
        self.assertTrue(removed)
        self.assertIsNone(self.registry.resolve("tool_a"))
        self.assertEqual(self.registry.resolve("tool_b"), "agent2")
        self.assertEqual(len(self.registry), 1)

    def test_unregister_empty_role(self):
        removed = self.registry.unregister_role("nonexistent")
        self.assertFalse(removed)

    def test_duplicate_tool_different_owner_rejected(self):
        self.registry.register("agent1", [{"name": "shared_tool", "description": "A"}])
        registered = self.registry.register("agent2", [{"name": "shared_tool", "description": "B"}])
        self.assertEqual(registered, [])
        self.assertEqual(self.registry.resolve("shared_tool"), "agent1")

    def test_duplicate_tool_same_owner_overwrites(self):
        self.registry.register("agent1", [{"name": "my_tool", "description": "v1"}])
        registered = self.registry.register("agent1", [{"name": "my_tool", "description": "v2"}])
        self.assertEqual(registered, ["my_tool"])
        tools = self.registry.get_tools()
        self.assertEqual(tools[0]["description"], "v2")

    def test_get_tools_returns_all(self):
        self.registry.register("a1", [{"name": "t1", "description": "D1"}])
        self.registry.register("a2", [{"name": "t2", "description": "D2"}])
        tools = self.registry.get_tools()
        self.assertEqual(len(tools), 2)
        names = {t["name"] for t in tools}
        self.assertEqual(names, {"t1", "t2"})
        for t in tools:
            self.assertIn("owner", t)
            self.assertIn("input_schema", t)

    def test_get_tools_exclude_role(self):
        self.registry.register("a1", [{"name": "t1", "description": "D1"}])
        self.registry.register("a2", [{"name": "t2", "description": "D2"}])
        tools = self.registry.get_tools(exclude_role="a1")
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]["name"], "t2")

    def test_malformed_tool_skipped(self):
        tools = [
            {"description": "no name"},
            {"name": "valid_tool", "description": "has name"},
        ]
        registered = self.registry.register("agent1", tools)
        self.assertEqual(registered, ["valid_tool"])
        self.assertEqual(len(self.registry), 1)

    def test_default_input_schema(self):
        self.registry.register("a1", [{"name": "t1", "description": "D1"}])
        tools = self.registry.get_tools()
        self.assertEqual(tools[0]["input_schema"], {})

    def test_resolve_unknown_tool(self):
        self.assertIsNone(self.registry.resolve("nonexistent"))


if __name__ == "__main__":
    unittest.main()
