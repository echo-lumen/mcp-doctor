"""CLI entry point for mcp-doctor."""

import argparse
import asyncio
import sys
from pathlib import Path

from .checker import check_server, load_config
from .report import format_text, format_json


def find_configs() -> list[Path]:
    """Auto-discover MCP config files in common locations."""
    home = Path.home()
    candidates = [
        home / ".claude" / "mcp.json",
        home / ".cursor" / "mcp.json",
        home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json",
        Path.cwd() / ".claude" / "mcp.json",
        Path.cwd() / ".mcp.json",
    ]
    return [p for p in candidates if p.exists()]


async def run_check(args: argparse.Namespace) -> int:
    """Run health checks."""
    reports = []

    if args.command:
        # Check a single server by command (shell-style string)
        import shlex
        parts = shlex.split(args.command)
        command = parts[0]
        cmd_args = parts[1:] if len(parts) > 1 else []
        report = await check_server(
            name=command,
            command=command,
            args=cmd_args,
            timeout=args.timeout,
            smoke_test=not args.no_smoke,
        )
        reports.append(report)

    elif args.config:
        # Check all servers in a config file
        config_path = Path(args.config)
        if not config_path.exists():
            print(f"Error: Config file not found: {args.config}", file=sys.stderr)
            return 1

        servers = load_config(str(config_path))
        if not servers:
            print(f"No servers found in {args.config}", file=sys.stderr)
            return 1

        print(f"Found {len(servers)} servers in {config_path.name}", file=sys.stderr)

        for name, server_config in servers.items():
            command = server_config.get("command", "")
            cmd_args = server_config.get("args", [])
            env = server_config.get("env")

            if not command:
                print(f"  Skipping {name}: no command specified", file=sys.stderr)
                continue

            print(f"  Checking {name}...", file=sys.stderr)
            report = await check_server(
                name=name,
                command=command,
                args=cmd_args,
                env=env,
                timeout=args.timeout,
                smoke_test=not args.no_smoke,
            )
            reports.append(report)

    else:
        # Auto-discover configs
        configs = find_configs()
        if not configs:
            print("No MCP config files found.", file=sys.stderr)
            print("Use --config <path> or --command <cmd> [args...]", file=sys.stderr)
            return 1

        for config_path in configs:
            print(f"Found: {config_path}", file=sys.stderr)
            servers = load_config(str(config_path))

            for name, server_config in servers.items():
                command = server_config.get("command", "")
                cmd_args = server_config.get("args", [])
                env = server_config.get("env")

                if not command:
                    continue

                print(f"  Checking {name}...", file=sys.stderr)
                report = await check_server(
                    name=name,
                    command=command,
                    args=cmd_args,
                    env=env,
                    timeout=args.timeout,
                    smoke_test=not args.no_smoke,
                )
                reports.append(report)

    # Output
    if not reports:
        print("No servers to check.", file=sys.stderr)
        return 1

    if args.format == "json":
        print(format_json(reports))
    else:
        print(format_text(reports, verbose=args.verbose))

    # Exit code
    unhealthy = sum(1 for r in reports if not r.healthy)
    return 1 if unhealthy > 0 else 0


def main():
    parser = argparse.ArgumentParser(
        prog="mcp-doctor",
        description="Health check CLI for MCP servers",
    )

    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--config", "-c",
        help="Path to MCP config file (mcp.json or claude_desktop_config.json)",
    )
    group.add_argument(
        "--command",
        help='MCP server command to check (e.g., "npx -y @modelcontextprotocol/server-filesystem /tmp")',
    )

    parser.add_argument(
        "--format", "-f",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument(
        "--timeout", "-t",
        type=float,
        default=30.0,
        help="Connection timeout in seconds (default: 30)",
    )
    parser.add_argument(
        "--no-smoke",
        action="store_true",
        help="Skip smoke testing individual tools",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed output (tool lists, schema issues)",
    )

    args = parser.parse_args()
    exit_code = asyncio.run(run_check(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
