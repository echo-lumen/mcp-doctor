# mcp-doctor

Health check CLI for MCP servers. Connect, enumerate, smoke-test, report.

Think `npm doctor` but for MCP servers. Answers the question: "is my MCP server actually working?"

## Quick Start

```bash
pip install .
mcp-doctor --command "npx -y @modelcontextprotocol/server-everything"
```

Output:

```
npx (npx -y @modelcontextprotocol/server-everything)
  mcp-servers/everything v2.0.0
  ✓ initialize: mcp-servers/everything v2.0.0 (protocol 2025-11-25) 458ms
  ✓ ping: Response in 1ms
  ✓ list_tools: 13 tools found
  ✓ list_resources: 7 resources found
  ✓ list_prompts: 4 prompts found
  ✓ tool_schemas: All 13 tool schemas valid
  ✓ smoke:echo: Tool responded successfully in 1ms
  ✓ smoke:get-env: Tool responded successfully in 0ms
  HEALTHY — 11 passed, 0 warnings, 0 failed
```

## What It Checks

| Check | What it does | Status |
|-------|-------------|--------|
| **initialize** | Connect and complete MCP handshake | Pass/Fail |
| **ping** | Verify server responds to pings | Pass/Warn |
| **list_tools** | Enumerate all available tools | Pass/Fail |
| **list_resources** | Enumerate resources (optional capability) | Pass/Warn |
| **list_prompts** | Enumerate prompts (optional capability) | Pass/Warn |
| **tool_schemas** | Validate tool schemas are well-formed | Pass/Warn |
| **smoke:&lt;tool&gt;** | Call each tool with minimal args | Pass/Warn |

Checks that test optional capabilities (resources, prompts) produce warnings instead of failures when not supported.

## Usage

### Check a single server

```bash
mcp-doctor --command "npx -y @modelcontextprotocol/server-filesystem /tmp"
```

### Check all servers in a config file

```bash
mcp-doctor --config ~/.claude/mcp.json
mcp-doctor --config ~/Library/Application\ Support/Claude/claude_desktop_config.json
```

### Auto-discover and check all configs

```bash
mcp-doctor
```

Searches `~/.claude/mcp.json`, `~/.cursor/mcp.json`, Claude Desktop config, and the current project's `.claude/mcp.json`.

### Skip smoke tests

```bash
mcp-doctor --command "..." --no-smoke
```

### Verbose output (shows tool listings, schema issues)

```bash
mcp-doctor -v --command "..."
```

### JSON output for CI

```bash
mcp-doctor -f json --command "..."
```

```json
{
  "summary": { "total": 1, "healthy": 1, "unhealthy": 0 },
  "servers": [
    {
      "name": "npx",
      "server_name": "mcp-servers/everything",
      "healthy": true,
      "checks": [
        { "name": "initialize", "status": "pass", "duration_ms": 458 },
        { "name": "list_tools", "status": "pass", "message": "13 tools found" }
      ]
    }
  ]
}
```

Exit code 0 = all healthy. Exit code 1 = at least one unhealthy.

## What It Catches

- Servers that fail to start (bad command, missing dependencies)
- Servers that start but don't respond to initialize (broken stdio pipe)
- Servers that enumerate tools but crash when called (schema mismatches)
- Tools with missing descriptions or malformed schemas
- Servers that time out under load
- Missing capabilities (resources/prompts not implemented)

## Companion Tools

- [mcp-security-scan](https://github.com/echo-lumen/mcp-security-scan) — audit MCP servers against the OWASP MCP Top 10
- Together: health check + security audit = complete MCP server quality story

## Requirements

- Python >= 3.10
- `mcp` Python package (installed automatically)

## License

MIT
