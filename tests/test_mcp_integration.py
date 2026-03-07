#!/usr/bin/env python3
"""Integration tests for the MCP Tool Broker in ZeroRelay."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import asyncio
import json
import unittest
import websockets


# Import relay handler and reset state for each test
def reset_relay_state():
    """Reset global relay state between tests."""
    from core import zerorelay
    zerorelay.clients.clear()
    zerorelay.history.clear()
    zerorelay.mcp_registry = type(zerorelay.mcp_registry)()
    zerorelay.mcp_pending.clear()
    zerorelay.rate_limits.clear()
    zerorelay.mcp_rate_limits.clear()


async def connect_client(port, role):
    """Connect a WebSocket client with a given role."""
    ws = await websockets.connect(f"ws://localhost:{port}?role={role}")
    # Read the initial 'connected' message
    raw = await asyncio.wait_for(ws.recv(), timeout=5)
    data = json.loads(raw)
    assert data["type"] == "connected", f"Expected 'connected', got {data['type']}"
    return ws, data


async def recv_msg(ws, timeout=5):
    """Receive and parse a JSON message."""
    raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
    return json.loads(raw)


async def drain_system_msgs(ws, timeout=0.5):
    """Drain any pending system messages (join/leave notifications)."""
    while True:
        try:
            raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            data = json.loads(raw)
            if data.get("type") != "system":
                return data  # Return non-system message
        except asyncio.TimeoutError:
            return None


class TestMCPIntegration(unittest.IsolatedAsyncioTestCase):
    """Integration tests for MCP Tool Broker."""

    async def asyncSetUp(self):
        reset_relay_state()
        from core.zerorelay import handler
        self.server = await websockets.serve(handler, "localhost", 0, max_size=65536)
        self.port = self.server.sockets[0].getsockname()[1]
        self.clients = []

    async def asyncTearDown(self):
        for ws in self.clients:
            try: await ws.close()
            except Exception: pass
        self.server.close()
        await self.server.wait_closed()
        await asyncio.sleep(0.1)

    async def _connect(self, role):
        ws, connected_data = await connect_client(self.port, role)
        self.clients.append(ws)
        return ws, connected_data

    async def _register_tool(self, ws_provider, ws_others, name="greet", desc="Greet someone"):
        """Helper to register a tool and drain updates from all clients."""
        await ws_provider.send(json.dumps({
            "type": "mcp_register",
            "tools": [{"name": name, "description": desc}]
        }))
        await recv_msg(ws_provider)  # provider gets update
        for ws in ws_others:
            await recv_msg(ws)  # others get update

    # --- Original tests (updated for namespacing) ---

    async def test_tool_registration_broadcasts_update(self):
        """When a provider registers tools, all clients get mcp_tools_updated."""
        ws_provider, _ = await self._connect("provider")
        ws_user, _ = await self._connect("user")
        await drain_system_msgs(ws_provider)

        await ws_provider.send(json.dumps({
            "type": "mcp_register",
            "tools": [{"name": "echo", "description": "Echo back input",
                        "input_schema": {"type": "object",
                            "properties": {"text": {"type": "string"}}}}]
        }))

        # Provider should NOT see its own tools (per-role exclusion)
        provider_msg = await recv_msg(ws_provider)
        self.assertEqual(provider_msg["type"], "mcp_tools_updated")
        self.assertEqual(len(provider_msg["available_tools"]), 0)

        # Other clients should see the registered tools
        user_msg = await recv_msg(ws_user)
        self.assertEqual(user_msg["type"], "mcp_tools_updated")
        self.assertEqual(len(user_msg["available_tools"]), 1)
        self.assertEqual(user_msg["available_tools"][0]["name"], "provider/echo")
        self.assertEqual(user_msg["available_tools"][0]["owner"], "provider")

    async def test_connected_includes_available_tools(self):
        """New clients receive existing tools in the connected message."""
        ws_provider, _ = await self._connect("provider")
        await ws_provider.send(json.dumps({
            "type": "mcp_register",
            "tools": [{"name": "my_tool", "description": "A tool"}]
        }))
        await recv_msg(ws_provider)

        ws_user, connected_data = await self._connect("user")
        self.assertIn("available_tools", connected_data)
        self.assertEqual(len(connected_data["available_tools"]), 1)
        self.assertEqual(connected_data["available_tools"][0]["name"], "provider/my_tool")

    async def test_tool_call_routes_to_owner(self):
        """A tool call from user is forwarded to the tool owner with plain name."""
        ws_provider, _ = await self._connect("provider")
        ws_user, _ = await self._connect("user")
        await drain_system_msgs(ws_provider)
        await self._register_tool(ws_provider, [ws_user])

        # User calls with namespaced name
        await ws_user.send(json.dumps({
            "type": "mcp_tool_call",
            "call_id": "test-call-1",
            "tool_name": "provider/greet",
            "arguments": {"name": "World"}
        }))

        # Provider receives call with PLAIN name (namespace stripped)
        msg = await recv_msg(ws_provider)
        self.assertEqual(msg["type"], "mcp_tool_call")
        self.assertEqual(msg["call_id"], "test-call-1")
        self.assertEqual(msg["caller"], "user")
        self.assertEqual(msg["tool_name"], "greet")  # plain name
        self.assertEqual(msg["arguments"], {"name": "World"})

    async def test_tool_result_routes_back_to_caller(self):
        """Tool result from owner is forwarded back to the caller with namespaced name."""
        ws_provider, _ = await self._connect("provider")
        ws_user, _ = await self._connect("user")
        await drain_system_msgs(ws_provider)
        await self._register_tool(ws_provider, [ws_user])

        await ws_user.send(json.dumps({
            "type": "mcp_tool_call",
            "call_id": "test-call-2",
            "tool_name": "provider/greet",
            "arguments": {"name": "World"}
        }))

        call_msg = await recv_msg(ws_provider)
        await ws_provider.send(json.dumps({
            "type": "mcp_tool_result",
            "call_id": call_msg["call_id"],
            "result": {"greeting": "Hello, World!"}
        }))

        result = await recv_msg(ws_user)
        self.assertEqual(result["type"], "mcp_tool_result")
        self.assertEqual(result["call_id"], "test-call-2")
        self.assertEqual(result["tool_name"], "provider/greet")  # namespaced
        self.assertEqual(result["owner"], "provider")
        self.assertEqual(result["result"], {"greeting": "Hello, World!"})

    async def test_error_on_unknown_tool(self):
        """Calling a nonexistent tool returns an immediate error."""
        ws_user, _ = await self._connect("user")

        await ws_user.send(json.dumps({
            "type": "mcp_tool_call",
            "call_id": "test-call-3",
            "tool_name": "nonexistent/tool",
            "arguments": {}
        }))

        result = await recv_msg(ws_user)
        self.assertEqual(result["type"], "mcp_tool_result")
        self.assertEqual(result["call_id"], "test-call-3")
        self.assertIn("error", result)
        self.assertIn("not available", result["error"])

    async def test_disconnect_removes_tools_and_notifies(self):
        """When a provider disconnects, its tools are removed and others are notified."""
        ws_provider, _ = await self._connect("provider")
        ws_user, _ = await self._connect("user")
        await drain_system_msgs(ws_provider)
        await self._register_tool(ws_provider, [ws_user])

        await ws_provider.close()
        self.clients.remove(ws_provider)

        msgs = []
        for _ in range(3):
            try:
                msg = await recv_msg(ws_user, timeout=2)
                msgs.append(msg)
            except asyncio.TimeoutError:
                break

        types = [m["type"] for m in msgs]
        self.assertIn("mcp_tools_updated", types)
        tools_msg = next(m for m in msgs if m["type"] == "mcp_tools_updated")
        self.assertEqual(tools_msg["available_tools"], [])

    async def test_disconnect_errors_pending_calls(self):
        """When a tool owner disconnects mid-call, the caller gets an error."""
        ws_provider, _ = await self._connect("provider")
        ws_user, _ = await self._connect("user")
        await drain_system_msgs(ws_provider)
        await self._register_tool(ws_provider, [ws_user], name="slow_tool", desc="Slow")

        await ws_user.send(json.dumps({
            "type": "mcp_tool_call",
            "call_id": "pending-call-1",
            "tool_name": "provider/slow_tool",
            "arguments": {}
        }))
        await recv_msg(ws_provider)  # Consume the forwarded call

        await ws_provider.close()
        self.clients.remove(ws_provider)

        msgs = []
        for _ in range(4):
            try:
                msg = await recv_msg(ws_user, timeout=2)
                msgs.append(msg)
            except asyncio.TimeoutError:
                break

        error_msgs = [m for m in msgs if m["type"] == "mcp_tool_result"]
        self.assertTrue(len(error_msgs) > 0)
        err = error_msgs[0]
        self.assertEqual(err["call_id"], "pending-call-1")
        self.assertIn("error", err)
        self.assertIn("disconnected", err["error"])

    async def test_regular_messages_still_work(self):
        """Regular chat messages still broadcast normally alongside MCP."""
        ws_a, _ = await self._connect("alice")
        ws_b, _ = await self._connect("bob")
        await drain_system_msgs(ws_a)

        await ws_a.send(json.dumps({"content": "Hello Bob!"}))
        msg = await recv_msg(ws_b)
        self.assertEqual(msg["type"], "message")
        self.assertEqual(msg["from"], "alice")
        self.assertEqual(msg["content"], "Hello Bob!")

    async def test_tool_error_result_forwarded(self):
        """Tool owner can return an error result which is forwarded to caller."""
        ws_provider, _ = await self._connect("provider")
        ws_user, _ = await self._connect("user")
        await drain_system_msgs(ws_provider)
        await self._register_tool(ws_provider, [ws_user], name="fail_tool", desc="Fails")

        await ws_user.send(json.dumps({
            "type": "mcp_tool_call",
            "call_id": "err-call-1",
            "tool_name": "provider/fail_tool",
            "arguments": {}
        }))

        call_msg = await recv_msg(ws_provider)
        await ws_provider.send(json.dumps({
            "type": "mcp_tool_result",
            "call_id": call_msg["call_id"],
            "error": "Permission denied"
        }))

        result = await recv_msg(ws_user)
        self.assertEqual(result["type"], "mcp_tool_result")
        self.assertIn("error", result)
        self.assertEqual(result["error"], "Permission denied")

    # --- New security and edge-case tests ---

    async def test_self_call_prevented(self):
        """An agent cannot call its own tool."""
        ws_provider, _ = await self._connect("provider")
        await self._register_tool(ws_provider, [])

        await ws_provider.send(json.dumps({
            "type": "mcp_tool_call",
            "call_id": "self-call-1",
            "tool_name": "provider/greet",
            "arguments": {}
        }))

        result = await recv_msg(ws_provider)
        self.assertEqual(result["type"], "mcp_tool_result")
        self.assertIn("error", result)
        self.assertIn("Cannot call your own tool", result["error"])

    async def test_missing_call_id_rejected(self):
        """mcp_tool_call without call_id returns error."""
        ws_user, _ = await self._connect("user")

        await ws_user.send(json.dumps({
            "type": "mcp_tool_call",
            "tool_name": "some/tool",
            "arguments": {}
        }))

        result = await recv_msg(ws_user)
        self.assertEqual(result["type"], "mcp_tool_result")
        self.assertIn("error", result)
        self.assertIn("call_id", result["error"])

    async def test_missing_tool_name_rejected(self):
        """mcp_tool_call without tool_name returns error."""
        ws_user, _ = await self._connect("user")

        await ws_user.send(json.dumps({
            "type": "mcp_tool_call",
            "call_id": "test-123",
            "arguments": {}
        }))

        result = await recv_msg(ws_user)
        self.assertEqual(result["type"], "mcp_tool_result")
        self.assertIn("error", result)
        self.assertIn("tool_name", result["error"])

    async def test_spoofed_result_dropped(self):
        """Wrong sender's mcp_tool_result is dropped, pending entry preserved."""
        ws_provider, _ = await self._connect("provider")
        ws_user, _ = await self._connect("user")
        ws_spoofer, _ = await self._connect("spoofer")
        await drain_system_msgs(ws_provider)
        await drain_system_msgs(ws_spoofer)
        await self._register_tool(ws_provider, [ws_user, ws_spoofer])

        # User calls provider's tool
        await ws_user.send(json.dumps({
            "type": "mcp_tool_call",
            "call_id": "spoof-test-1",
            "tool_name": "provider/greet",
            "arguments": {}
        }))
        await recv_msg(ws_provider)  # provider gets call

        # Spoofer tries to send result (should be dropped)
        await ws_spoofer.send(json.dumps({
            "type": "mcp_tool_result",
            "call_id": "spoof-test-1",
            "result": {"spoofed": True}
        }))

        # Small delay to let relay process the spoofed message
        await asyncio.sleep(0.2)

        # Real provider sends the correct result
        await ws_provider.send(json.dumps({
            "type": "mcp_tool_result",
            "call_id": "spoof-test-1",
            "result": {"greeting": "Real result"}
        }))

        # User should get the real result, not the spoofed one
        # Drain any non-tool-result messages first (e.g., mcp_tools_updated)
        msgs = []
        for _ in range(5):
            try:
                msg = await recv_msg(ws_user, timeout=2)
                msgs.append(msg)
            except asyncio.TimeoutError:
                break

        results = [m for m in msgs if m["type"] == "mcp_tool_result"]
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["result"], {"greeting": "Real result"})

    async def test_concurrent_tool_calls(self):
        """Multiple tool calls in-flight at once all resolve correctly."""
        ws_provider, _ = await self._connect("provider")
        ws_user, _ = await self._connect("user")
        await drain_system_msgs(ws_provider)
        await self._register_tool(ws_provider, [ws_user])

        # Send two calls
        for i in range(2):
            await ws_user.send(json.dumps({
                "type": "mcp_tool_call",
                "call_id": f"concurrent-{i}",
                "tool_name": "provider/greet",
                "arguments": {"n": i}
            }))

        # Provider responds to both (in order received)
        for i in range(2):
            call = await recv_msg(ws_provider)
            await ws_provider.send(json.dumps({
                "type": "mcp_tool_result",
                "call_id": call["call_id"],
                "result": {"n": i}
            }))

        # User gets both results
        results = {}
        for _ in range(2):
            r = await recv_msg(ws_user)
            results[r["call_id"]] = r

        self.assertIn("concurrent-0", results)
        self.assertIn("concurrent-1", results)
        self.assertEqual(results["concurrent-0"]["result"], {"n": 0})
        self.assertEqual(results["concurrent-1"]["result"], {"n": 1})

    async def test_malformed_register_ignored(self):
        """mcp_register with tools as a non-list is silently ignored."""
        ws_provider, _ = await self._connect("provider")

        await ws_provider.send(json.dumps({
            "type": "mcp_register",
            "tools": "not a list"
        }))

        # Should not crash; no tools_updated should arrive (or empty)
        msg = await drain_system_msgs(ws_provider, timeout=1)
        # If we got a message, it should not be a tools_updated with tools
        if msg and msg.get("type") == "mcp_tools_updated":
            self.assertEqual(msg["available_tools"], [])

    async def test_namespaced_names_in_discovery(self):
        """Both connected and mcp_tools_updated messages use namespaced names."""
        ws_provider, _ = await self._connect("provider")
        ws_observer, _ = await self._connect("observer")
        await drain_system_msgs(ws_provider)

        await ws_provider.send(json.dumps({
            "type": "mcp_register",
            "tools": [{"name": "search", "description": "Search"}]
        }))
        # Provider won't see its own tools; check from observer's perspective
        await recv_msg(ws_provider)  # drain provider's empty update
        update = await recv_msg(ws_observer)
        self.assertEqual(update["available_tools"][0]["name"], "provider/search")

        # New client sees namespaced tools in connected message
        ws_user, connected = await self._connect("user")
        tools = connected["available_tools"]
        self.assertEqual(len(tools), 1)
        self.assertEqual(tools[0]["name"], "provider/search")

    async def test_two_providers_same_tool_name(self):
        """Two providers can register the same plain tool name without collision."""
        ws_a, _ = await self._connect("alpha")
        ws_b, _ = await self._connect("beta")
        ws_user, _ = await self._connect("user")
        await drain_system_msgs(ws_a)
        await drain_system_msgs(ws_b)

        # Both register "search"
        await self._register_tool(ws_a, [ws_b, ws_user], name="search", desc="Alpha search")
        await self._register_tool(ws_b, [ws_a, ws_user], name="search", desc="Beta search")

        # User calls alpha's search
        await ws_user.send(json.dumps({
            "type": "mcp_tool_call",
            "call_id": "ns-test-1",
            "tool_name": "alpha/search",
            "arguments": {"q": "hello"}
        }))

        call = await recv_msg(ws_a)
        self.assertEqual(call["tool_name"], "search")  # plain name
        self.assertEqual(call["caller"], "user")

        # User calls beta's search
        await ws_user.send(json.dumps({
            "type": "mcp_tool_call",
            "call_id": "ns-test-2",
            "tool_name": "beta/search",
            "arguments": {"q": "world"}
        }))

        call = await recv_msg(ws_b)
        self.assertEqual(call["tool_name"], "search")  # plain name
        self.assertEqual(call["caller"], "user")


if __name__ == "__main__":
    unittest.main()
