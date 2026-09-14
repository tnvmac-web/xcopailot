"""MCP (Model Context Protocol) Gateway for X-Copilot."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server."""

    name: str
    transport: str  # stdio, sse
    command: str | None = None
    args: list[str] | None = None
    url: str | None = None
    env: dict[str, str] | None = None


@dataclass
class MCPTool:
    """MCP tool definition."""

    name: str
    description: str
    inputSchema: dict


class MCPGateway:
    """Gateway to connect to and manage MCP servers."""

    def __init__(self, config: dict) -> None:
        self.config = config
        self._servers: dict[str, MCPServerConfig] = {}
        self._processes: dict[str, subprocess.Popen] = {}
        self._clients: dict[str, httpx.AsyncClient] = {}
        self._tools_cache: dict[str, list[MCPTool]] = {}
        self._request_id_counter = 0

    def _next_request_id(self) -> int:
        """Generate the next unique JSON-RPC request ID."""
        self._request_id_counter += 1
        return self._request_id_counter

    def add_server(self, server_config: MCPServerConfig) -> None:
        """Add an MCP server configuration."""
        self._servers[server_config.name] = server_config

    def remove_server(self, name: str) -> bool:
        """Remove an MCP server configuration."""
        if name in self._servers:
            del self._servers[name]
            return True
        return False

    async def connect(self, name: str, server_config: dict | None = None) -> bool:
        """Connect to an MCP server."""
        if server_config:
            config = MCPServerConfig(
                name=name,
                transport=server_config.get("transport", "stdio"),
                command=server_config.get("command"),
                args=server_config.get("args", []),
                url=server_config.get("url"),
                env=server_config.get("env"),
            )
            self._servers[name] = config
        elif name not in self._servers:
            return False

        config = self._servers[name]

        if config.transport == "stdio":
            return await self._connect_stdio(name, config)
        elif config.transport == "sse":
            return await self._connect_sse(name, config)

        return False

    async def _connect_stdio(self, name: str, config: MCPServerConfig) -> bool:
        """Connect via stdio transport."""
        try:
            env = os.environ.copy()
            if config.env:
                env.update(config.env)

            args = config.args or []
            self._processes[name] = await asyncio.create_subprocess_exec(
                config.command,
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
            )

            # Initialize MCP connection
            await self._send_mcp_request(
                name,
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "xcopilot", "version": "0.1.0"},
                    },
                },
            )

            # Send initialized notification
            await self._send_mcp_request(
                name,
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                },
            )

            return True
        except (OSError, subprocess.SubprocessError, json.JSONDecodeError) as e:
            print(f"Failed to connect to MCP server {name}: {e}")
            return False

    async def _connect_sse(self, name: str, config: MCPServerConfig) -> bool:
        """Connect via SSE transport."""
        try:
            if not config.url:
                return False

            client = httpx.AsyncClient(base_url=config.url, timeout=30.0)
            self._clients[name] = client

            # Initialize via HTTP
            response = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "xcopilot", "version": "0.1.0"},
                    },
                },
            )
            response.raise_for_status()

            return True
        except (httpx.HTTPError, json.JSONDecodeError) as e:
            print(f"Failed to connect to MCP server {name} via SSE: {e}")
            return False

    async def _send_mcp_request(self, name: str, request: dict) -> dict | None:
        """Send a JSON-RPC request to an MCP server."""
        config = self._servers[name]

        if config.transport == "stdio":
            process = self._processes.get(name)
            if not process or not process.stdin:
                return None

            request_json = json.dumps(request) + "\n"
            process.stdin.write(request_json)
            process.stdin.flush()

            # Read response
            response_line = process.stdout.readline()
            if response_line:
                return json.loads(response_line.strip())
            return None

        elif config.transport == "sse":
            client = self._clients.get(name)
            if not client:
                return None

            response = await client.post("/mcp", json=request)
            response.raise_for_status()
            return response.json()

        return None

    async def list_tools(self, name: str) -> list[MCPTool]:
        """List available tools from an MCP server."""
        if name in self._tools_cache:
            return self._tools_cache[name]

        response = await self._send_mcp_request(
            name,
            {
                "jsonrpc": "2.0",
                "id": self._next_request_id(),
                "method": "tools/list",
            },
        )

        if response and "result" in response:
            tools = [
                MCPTool(
                    name=tool["name"],
                    description=tool.get("description", ""),
                    inputSchema=tool.get("inputSchema", {}),
                )
                for tool in response["result"].get("tools", [])
            ]
            self._tools_cache[name] = tools
            return tools

        return []

    async def call_tool(self, name: str, tool_name: str, arguments: dict) -> Any:
        """Call a tool on an MCP server."""
        response = await self._send_mcp_request(
            name,
            {
                "jsonrpc": "2.0",
                "id": self._next_request_id(),
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments,
                },
            },
        )

        if response and "result" in response:
            return response["result"]
        if response and "error" in response:
            raise RuntimeError(f"MCP tool error: {response['error']}")
        return None

    async def list_resources(self, name: str) -> list[dict]:
        """List available resources from an MCP server."""
        response = await self._send_mcp_request(
            name,
            {
                "jsonrpc": "2.0",
                "id": self._next_request_id(),
                "method": "resources/list",
            },
        )

        if response and "result" in response:
            return response["result"].get("resources", [])
        return []

    async def read_resource(self, name: str, uri: str) -> Any:
        """Read a resource from an MCP server."""
        response = await self._send_mcp_request(
            name,
            {
                "jsonrpc": "2.0",
                "id": self._next_request_id(),
                "method": "resources/read",
                "params": {"uri": uri},
            },
        )

        if response and "result" in response:
            return response["result"]
        return None

    async def disconnect(self, name: str) -> None:
        """Disconnect from an MCP server."""
        config = self._servers.get(name)

        if config and config.transport == "stdio":
            process = self._processes.pop(name, None)
            if process:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()

        elif config and config.transport == "sse":
            client = self._clients.pop(name, None)
            if client:
                await client.aclose()

        self._tools_cache.pop(name, None)

    async def disconnect_all(self) -> None:
        """Disconnect from all MCP servers."""
        for name in list(self._servers.keys()):
            await self.disconnect(name)

    def get_server_config(self, name: str) -> MCPServerConfig | None:
        """Get server configuration."""
        return self._servers.get(name)

    def list_servers(self) -> list[MCPServerConfig]:
        """List all configured servers."""
        return list(self._servers.values())
