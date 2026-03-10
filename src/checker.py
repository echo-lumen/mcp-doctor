"""Core health check logic for MCP servers."""

import asyncio
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


class Status(Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    SKIP = "skip"


@dataclass
class Check:
    name: str
    status: Status
    message: str = ""
    duration_ms: int = 0
    details: dict = field(default_factory=dict)


@dataclass
class ServerReport:
    name: str
    command: str
    args: list[str]
    server_name: str | None = None
    server_version: str | None = None
    protocol_version: str | None = None
    checks: list[Check] = field(default_factory=list)
    error: str | None = None

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.status == Status.PASS)

    @property
    def warned(self) -> int:
        return sum(1 for c in self.checks if c.status == Status.WARN)

    @property
    def failed(self) -> int:
        return sum(1 for c in self.checks if c.status == Status.FAIL)

    @property
    def healthy(self) -> bool:
        return self.failed == 0 and self.error is None


async def check_server(
    name: str,
    command: str,
    args: list[str],
    env: dict | None = None,
    timeout: float = 30.0,
    smoke_test: bool = True,
) -> ServerReport:
    """Run all health checks against a single MCP server."""
    report = ServerReport(name=name, command=command, args=args or [])
    params = StdioServerParameters(command=command, args=args or [], env=env)

    try:
        async with stdio_client(params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                # Check 1: Initialize
                report.checks.append(await _check_initialize(session, timeout))
                init_check = report.checks[-1]
                if init_check.status == Status.FAIL:
                    return report

                report.server_name = init_check.details.get("server_name")
                report.server_version = init_check.details.get("server_version")
                report.protocol_version = init_check.details.get("protocol_version")

                # Check 2: Ping
                report.checks.append(await _check_ping(session))

                # Check 3: List tools
                tools_check = await _check_list_tools(session)
                report.checks.append(tools_check)
                tools = tools_check.details.get("tools", [])

                # Check 4: List resources
                report.checks.append(await _check_list_resources(session))

                # Check 5: List prompts
                report.checks.append(await _check_list_prompts(session))

                # Check 6: Tool schema validation
                report.checks.append(_check_tool_schemas(tools))

                # Check 7: Smoke test tools (optional)
                if smoke_test and tools:
                    for tool in tools[:5]:  # Limit to first 5 tools
                        report.checks.append(
                            await _check_tool_smoke(session, tool)
                        )

    except asyncio.TimeoutError:
        report.error = f"Connection timed out after {timeout}s"
        report.checks.append(Check(
            name="connect",
            status=Status.FAIL,
            message=f"Server did not respond within {timeout}s",
        ))
    except FileNotFoundError:
        report.error = f"Command not found: {command}"
        report.checks.append(Check(
            name="connect",
            status=Status.FAIL,
            message=f"Command not found: {command}",
        ))
    except Exception as e:
        report.error = str(e)
        report.checks.append(Check(
            name="connect",
            status=Status.FAIL,
            message=f"Connection failed: {e}",
        ))

    return report


async def _check_initialize(session: ClientSession, timeout: float) -> Check:
    """Check that the server initializes correctly."""
    start = time.monotonic()
    try:
        init = await asyncio.wait_for(session.initialize(), timeout=timeout)
        duration = int((time.monotonic() - start) * 1000)

        server_name = init.serverInfo.name if init.serverInfo else None
        server_version = init.serverInfo.version if init.serverInfo else None
        protocol_version = init.protocolVersion

        details = {
            "server_name": server_name,
            "server_version": server_version,
            "protocol_version": protocol_version,
        }

        # Check capabilities
        caps = init.capabilities
        if caps:
            details["capabilities"] = {
                "tools": bool(caps.tools),
                "resources": bool(caps.resources),
                "prompts": bool(caps.prompts),
                "logging": bool(caps.logging) if hasattr(caps, "logging") else False,
            }

        msg = f"{server_name or 'unknown'}"
        if server_version:
            msg += f" v{server_version}"
        msg += f" (protocol {protocol_version})"

        return Check(
            name="initialize",
            status=Status.PASS,
            message=msg,
            duration_ms=duration,
            details=details,
        )
    except asyncio.TimeoutError:
        return Check(
            name="initialize",
            status=Status.FAIL,
            message=f"Initialize timed out after {timeout}s",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
    except Exception as e:
        return Check(
            name="initialize",
            status=Status.FAIL,
            message=f"Initialize failed: {e}",
            duration_ms=int((time.monotonic() - start) * 1000),
        )


async def _check_ping(session: ClientSession) -> Check:
    """Check that the server responds to ping."""
    start = time.monotonic()
    try:
        await asyncio.wait_for(session.send_ping(), timeout=5.0)
        duration = int((time.monotonic() - start) * 1000)
        return Check(
            name="ping",
            status=Status.PASS,
            message=f"Response in {duration}ms",
            duration_ms=duration,
        )
    except Exception as e:
        duration = int((time.monotonic() - start) * 1000)
        return Check(
            name="ping",
            status=Status.WARN,
            message=f"Ping failed: {e}",
            duration_ms=duration,
        )


async def _check_list_tools(session: ClientSession) -> Check:
    """Check that tools can be listed."""
    start = time.monotonic()
    try:
        result = await asyncio.wait_for(session.list_tools(), timeout=10.0)
        duration = int((time.monotonic() - start) * 1000)
        tools = []
        for t in result.tools:
            tools.append({
                "name": t.name,
                "description": t.description or "",
                "inputSchema": t.inputSchema if hasattr(t, "inputSchema") else {},
            })

        return Check(
            name="list_tools",
            status=Status.PASS,
            message=f"{len(tools)} tools found",
            duration_ms=duration,
            details={"tools": tools, "count": len(tools)},
        )
    except Exception as e:
        return Check(
            name="list_tools",
            status=Status.FAIL,
            message=f"Failed to list tools: {e}",
            duration_ms=int((time.monotonic() - start) * 1000),
        )


async def _check_list_resources(session: ClientSession) -> Check:
    """Check that resources can be listed."""
    start = time.monotonic()
    try:
        result = await asyncio.wait_for(session.list_resources(), timeout=10.0)
        duration = int((time.monotonic() - start) * 1000)
        count = len(result.resources)
        return Check(
            name="list_resources",
            status=Status.PASS,
            message=f"{count} resources found",
            duration_ms=duration,
            details={"count": count},
        )
    except Exception as e:
        # Resources are optional — not all servers support them
        return Check(
            name="list_resources",
            status=Status.WARN,
            message=f"Could not list resources: {e}",
            duration_ms=int((time.monotonic() - start) * 1000),
        )


async def _check_list_prompts(session: ClientSession) -> Check:
    """Check that prompts can be listed."""
    start = time.monotonic()
    try:
        result = await asyncio.wait_for(session.list_prompts(), timeout=10.0)
        duration = int((time.monotonic() - start) * 1000)
        count = len(result.prompts)
        return Check(
            name="list_prompts",
            status=Status.PASS,
            message=f"{count} prompts found",
            duration_ms=duration,
            details={"count": count},
        )
    except Exception as e:
        return Check(
            name="list_prompts",
            status=Status.WARN,
            message=f"Could not list prompts: {e}",
            duration_ms=int((time.monotonic() - start) * 1000),
        )


def _check_tool_schemas(tools: list[dict]) -> Check:
    """Validate that tool schemas are well-formed."""
    issues = []
    for tool in tools:
        name = tool["name"]
        schema = tool.get("inputSchema", {})

        if not tool.get("description"):
            issues.append(f"{name}: missing description")

        if not schema:
            issues.append(f"{name}: missing inputSchema")
        elif schema.get("type") != "object":
            issues.append(f"{name}: inputSchema type is not 'object'")

    if not tools:
        return Check(
            name="tool_schemas",
            status=Status.SKIP,
            message="No tools to validate",
        )

    if issues:
        return Check(
            name="tool_schemas",
            status=Status.WARN,
            message=f"{len(issues)} schema issues",
            details={"issues": issues},
        )

    return Check(
        name="tool_schemas",
        status=Status.PASS,
        message=f"All {len(tools)} tool schemas valid",
    )


async def _check_tool_smoke(session: ClientSession, tool: dict) -> Check:
    """Smoke test: call a tool with empty/minimal arguments."""
    name = tool["name"]
    start = time.monotonic()

    # Build minimal arguments from schema
    schema = tool.get("inputSchema", {})
    required = schema.get("required", [])
    properties = schema.get("properties", {})

    args = {}
    for prop_name in required:
        prop = properties.get(prop_name, {})
        prop_type = prop.get("type", "string")
        if prop_type == "string":
            args[prop_name] = ""
        elif prop_type == "number" or prop_type == "integer":
            args[prop_name] = 0
        elif prop_type == "boolean":
            args[prop_name] = False
        elif prop_type == "array":
            args[prop_name] = []
        elif prop_type == "object":
            args[prop_name] = {}

    try:
        result = await asyncio.wait_for(
            session.call_tool(name=name, arguments=args),
            timeout=10.0,
        )
        duration = int((time.monotonic() - start) * 1000)

        if result.isError:
            # Error is expected with empty args — but the tool responded
            return Check(
                name=f"smoke:{name}",
                status=Status.PASS,
                message=f"Tool responded with error (expected with minimal args) in {duration}ms",
                duration_ms=duration,
            )

        return Check(
            name=f"smoke:{name}",
            status=Status.PASS,
            message=f"Tool responded successfully in {duration}ms",
            duration_ms=duration,
        )
    except asyncio.TimeoutError:
        return Check(
            name=f"smoke:{name}",
            status=Status.WARN,
            message="Tool call timed out (10s)",
            duration_ms=int((time.monotonic() - start) * 1000),
        )
    except Exception as e:
        duration = int((time.monotonic() - start) * 1000)
        err_str = str(e)
        # Some errors are expected (validation, missing required args)
        if "validation" in err_str.lower() or "required" in err_str.lower():
            return Check(
                name=f"smoke:{name}",
                status=Status.PASS,
                message=f"Tool rejected invalid args (expected) in {duration}ms",
                duration_ms=duration,
            )
        return Check(
            name=f"smoke:{name}",
            status=Status.WARN,
            message=f"Tool call failed: {err_str[:100]}",
            duration_ms=duration,
        )


def load_config(config_path: str) -> dict[str, dict]:
    """Load MCP server config from a JSON file."""
    path = Path(config_path)
    config = json.loads(path.read_text())
    return config.get("mcpServers", {})
