"""Format health check results for display."""

import json
from .checker import ServerReport, Status


COLORS = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "red": "\033[31m",
    "cyan": "\033[36m",
}

ICONS = {
    Status.PASS: f"{COLORS['green']}\u2713{COLORS['reset']}",
    Status.WARN: f"{COLORS['yellow']}!{COLORS['reset']}",
    Status.FAIL: f"{COLORS['red']}\u2717{COLORS['reset']}",
    Status.SKIP: f"{COLORS['dim']}-{COLORS['reset']}",
}


def format_text(reports: list[ServerReport], verbose: bool = False) -> str:
    """Format reports as colored text for terminal."""
    lines = []

    for report in reports:
        # Server header
        status_color = COLORS["green"] if report.healthy else COLORS["red"]
        status_label = "HEALTHY" if report.healthy else "UNHEALTHY"
        lines.append(
            f"\n{COLORS['bold']}{report.name}{COLORS['reset']} "
            f"{COLORS['dim']}({report.command} {' '.join(report.args)}){COLORS['reset']}"
        )

        if report.error:
            lines.append(f"  {COLORS['red']}Error: {report.error}{COLORS['reset']}")
            continue

        if report.server_name:
            info = report.server_name
            if report.server_version:
                info += f" v{report.server_version}"
            lines.append(f"  {COLORS['dim']}{info}{COLORS['reset']}")

        # Checks
        for check in report.checks:
            icon = ICONS[check.status]
            duration = f" {COLORS['dim']}{check.duration_ms}ms{COLORS['reset']}" if check.duration_ms else ""
            lines.append(f"  {icon} {check.name}: {check.message}{duration}")

            if verbose and check.details:
                if "issues" in check.details:
                    for issue in check.details["issues"]:
                        lines.append(f"    {COLORS['dim']}- {issue}{COLORS['reset']}")
                if "tools" in check.details:
                    for tool in check.details["tools"]:
                        desc = tool.get("description", "")[:60]
                        lines.append(
                            f"    {COLORS['dim']}- {tool['name']}: {desc}{COLORS['reset']}"
                        )

        # Summary line
        lines.append(
            f"  {status_color}{COLORS['bold']}{status_label}{COLORS['reset']} "
            f"— {report.passed} passed, {report.warned} warnings, {report.failed} failed"
        )

    # Overall summary
    total_healthy = sum(1 for r in reports if r.healthy)
    total = len(reports)
    lines.append(f"\n{COLORS['bold']}Summary{COLORS['reset']}")
    lines.append(f"  {total_healthy}/{total} servers healthy")

    return "\n".join(lines) + "\n"


def format_json(reports: list[ServerReport]) -> str:
    """Format reports as JSON for CI consumption."""
    data = {
        "summary": {
            "total": len(reports),
            "healthy": sum(1 for r in reports if r.healthy),
            "unhealthy": sum(1 for r in reports if not r.healthy),
        },
        "servers": [],
    }

    for report in reports:
        server = {
            "name": report.name,
            "command": report.command,
            "args": report.args,
            "server_name": report.server_name,
            "server_version": report.server_version,
            "protocol_version": report.protocol_version,
            "healthy": report.healthy,
            "error": report.error,
            "checks": [
                {
                    "name": c.name,
                    "status": c.status.value,
                    "message": c.message,
                    "duration_ms": c.duration_ms,
                }
                for c in report.checks
            ],
        }
        data["servers"].append(server)

    return json.dumps(data, indent=2)
