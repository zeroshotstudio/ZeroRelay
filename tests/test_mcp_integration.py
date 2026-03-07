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

    async def test_tool_registration_broadcasts_update(self):
        """When a provider registers tools, all clients get mcp_tools_updated."""
        ws_provider, _ = await self._connect("provider")
        ws_user, _ = await self._connect("user")
        # Drain the "user joined" system message from provider
        await drain_system_msgs(ws_provider)

        # Provider registers a tool
        await ws_provider.send(json.dumps({
            "type": "mcp_register",
            "tools": [{"name": "echo", "description": "Echo back input",
                        "input_schema": {"type": "object",
                            "properties": {"text": {"type": "string"}}}}]
        }))

        # Both should receive mcp_tools_updated
        for ws in [ws_provider, ws_user]:
            msg = await recv_msg(ws)
            self.assertEqual(msg["type"], "mcp_tools_updated")
            self.assertEqual(len(msg["available_tools"]), 1)
            self.assertEqual(msg["available_tools"][0]["name"], "echo")
            self.assertEqual(msg["available_tools"][0]["owner"], "provider")

    async def test_connected_includes_available_tools(self):
        """New clients receive existing tools in the connected message."""
        ws_provider, _ = await self._connect("provider")
        await ws_provider.send(json.dumps({
            "type": "mcp_register",
            "tools": [{"name": "my_tool", "description": "A tool"}]
        }))
        # Drain the update for provider itself
        await recv_msg(ws_provider)

        # New client connects and should see available_tools
        ws_user, connected_data = await self._connect("user")
        self.assertIn("available_tools", connected_data)
        self.assertEqual(len(connected_data["available_tools"]), 1)
        self.assertEqual(connected_data["available_tools"][0]["name"], "my_tool")

    async def test_tool_call_routes_to_owner(self):
        """A tool call from user is forwarded to the tool owner."""
        ws_provider, _ = await self._connect("provider")
        ws_user, _ = await self._connect("user")
        await drain_system_msgs(ws_provider)

        # Register tool
        await ws_provider.send(json.dumps({
            "type": "mcp_register",
            "tools": [{"name": "greet", "description": "Greet someone"}]
        }))
        # Drain updates
        await recv_msg(ws_provider)
        await recv_msg(ws_user)

        # User calls the tool
        await ws_user.send(json.dumps({
            "type": "mcp_tool_call",
            "call_id": "test-call-1",
            "tool_name": "greet",
            "arguments": {"name": "World"}
        }))

        # Provider should receive the forwarded call
        msg = await recv_msg(ws_provider)
        self.assertEqual(msg["type"], "mcp_tool_call")
        self.assertEqual(msg["call_id"], "test-call-1")
        self.assertEqual(msg["caller"], "user")
        self.assertEqual(msg["tool_name"], "greet")
        self.assertEqual(msg["arguments"], {"name": "World"})

    async def test_tool_result_routes_back_to_caller(self):
        """Tool result from owner is forwarded back to the caller."""
        ws_provider, _ = await self._connect("provider")
        ws_user, _ = await self._connect("user")
        await drain_system_msgs(ws_provider)

        # Register and call
        await ws_provider.send(json.dumps({
            "type": "mcp_register",
            "tools": [{"name": "greet", "description": "Greet"}]
        }))
        await recv_msg(ws_provider)
        await recv_msg(ws_user)

        await ws_user.send(json.dumps({
            "type": "mcp_tool_call",
            "call_id": "test-call-2",
            "tool_name": "greet",
            "arguments": {"name": "World"}
        }))

        # Provider gets the call and responds
        call_msg = await recv_msg(ws_provider)
        await ws_provider.send(json.dumps({
            "type": "mcp_tool_result",
            "call_id": call_msg["call_id"],
            "result": {"greeting": "Hello, World!"}
        }))

        # User should receive the result
        result = await recv_msg(ws_user)
        self.assertEqual(result["type"], "mcp_tool_result")
        self.assertEqual(result["call_id"], "test-call-2")
        self.assertEqual(result["tool_name"], "greet")
        self.assertEqual(result["owner"], "provider")
        self.assertEqual(result["result"], {"greeting": "Hello, World!"})

    async def test_error_on_unknown_tool(self):
        """Calling a nonexistent tool returns an immediate error."""
        ws_user, _ = await self._connect("user")

        await ws_user.send(json.dumps({
            "type": "mcp_tool_call",
            "call_id": "test-call-3",
            "tool_name": "nonexistent_tool",
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

        # Register tool
        await ws_provider.send(json.dumps({
            "type": "mcp_register",
            "tools": [{"name": "my_tool", "description": "Tool"}]
        }))
        await recv_msg(ws_provider)
        await recv_msg(ws_user)

        # Disconnect provider
        await ws_provider.close()
        self.clients.remove(ws_provider)

        # User should receive mcp_tools_updated with empty list,
        # followed by a system "left" message
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

        # Register and call
        await ws_provider.send(json.dumps({
            "type": "mcp_register",
            "tools": [{"name": "slow_tool", "description": "Slow"}]
        }))
        await recv_msg(ws_provider)
        await recv_msg(ws_user)

        await ws_user.send(json.dumps({
            "type": "mcp_tool_call",
            "call_id": "pending-call-1",
            "tool_name": "slow_tool",
            "arguments": {}
        }))
        await recv_msg(ws_provider)  # Consume the forwarded call

        # Disconnect provider before responding
        await ws_provider.close()
        self.clients.remove(ws_provider)

        # User should get an error result for the pending call
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

        await ws_provider.send(json.dumps({
            "type": "mcp_register",
            "tools": [{"name": "fail_tool", "description": "Fails"}]
        }))
        await recv_msg(ws_provider)
        await recv_msg(ws_user)

        await ws_user.send(json.dumps({
            "type": "mcp_tool_call",
            "call_id": "err-call-1",
            "tool_name": "fail_tool",
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


if __name__ == "__main__":
    unittest.main()
