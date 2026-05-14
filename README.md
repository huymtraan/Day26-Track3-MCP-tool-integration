# SQLite FastMCP Database Server

This repo implements the lab server described in `Rubric.md`: a FastMCP server backed by SQLite with three tools, schema resources, validation, tests, and client setup notes.

## What Is Included

- `search`: query a validated table with filters, ordering, limit, and offset
- `insert`: insert one row and return the inserted payload
- `aggregate`: run `count`, `avg`, `sum`, `min`, or `max`, with optional filters and grouping
- `schema://database`: full database schema resource
- `schema://table/{table_name}`: dynamic per-table schema resource
- SQLite schema and seed data for `students`, `courses`, and `enrollments`
- Repeatable verification through pytest and `implementation/verify_server.py`

## Project Layout

```text
implementation/
  db.py                 # SQLite adapter, validation, and safe SQL building
  init_db.py            # reproducible schema and seed data
  mcp_server.py         # FastMCP server and tool/resource registration
  verify_server.py      # MCP client smoke test
  start_inspector.sh    # MCP Inspector helper
  tests/
    test_db.py
    test_mcp_server.py
requirements.txt
Rubric.md
Tips.md
```

## Setup

Use `python3`; this machine may not have a `python` command.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python implementation/init_db.py
```

The init command creates `implementation/school.db`. The MCP server will also create it automatically if it is missing.

## Run The Server

```bash
.venv/bin/python implementation/mcp_server.py
```

The default transport is stdio, which is the easiest option for local MCP clients.

Optional HTTP/SSE examples:

```bash
.venv/bin/python implementation/mcp_server.py --transport http --host 127.0.0.1 --port 8000
.venv/bin/python implementation/mcp_server.py --transport sse --host 127.0.0.1 --port 8000
```

Use a custom database path with either:

```bash
.venv/bin/python implementation/mcp_server.py --db /absolute/path/to/school.db
SQLITE_LAB_DB=/absolute/path/to/school.db .venv/bin/python implementation/mcp_server.py
```

## Tool Inputs

### `search`

```json
{
  "table": "students",
  "filters": {"cohort": "A1"},
  "columns": ["id", "name", "cohort", "gpa"],
  "limit": 20,
  "offset": 0,
  "order_by": "gpa",
  "descending": true
}
```

Filters can also use explicit operators:

```json
[
  {"column": "gpa", "op": "gte", "value": 3.5},
  {"column": "name", "op": "contains", "value": "Nguyen"}
]
```

Supported operators: `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `like`, `contains`, `in`, plus symbolic forms such as `>=`.

### `insert`

```json
{
  "table": "students",
  "values": {
    "name": "Minh Dao",
    "email": "minh.dao@example.edu",
    "cohort": "A1",
    "age": 23,
    "gpa": 3.61
  }
}
```

### `aggregate`

```json
{
  "table": "students",
  "metric": "avg",
  "column": "gpa",
  "group_by": "cohort"
}
```

```json
{
  "table": "enrollments",
  "metric": "count",
  "group_by": "course_id"
}
```

## Validation Behavior

The server rejects:

- unknown table names
- unknown column names
- unsupported filter operators
- invalid aggregate metrics
- `avg` or `sum` on non-numeric columns
- empty inserts
- invalid pagination values

SQL values are passed as bound parameters. Identifiers are accepted only after checking them against the live SQLite schema.

## Verify

Run the automated tests:

```bash
.venv/bin/python -m pytest implementation/tests -q
```

Run the MCP smoke test:

```bash
.venv/bin/python implementation/verify_server.py
```

Expected smoke test output:

```text
Verification passed: tools, resources, valid calls, and invalid errors work.
```

## MCP Inspector

```bash
chmod +x implementation/start_inspector.sh
implementation/start_inspector.sh
```

Manual equivalent:

```bash
mkdir -p .npm-cache
NPM_CONFIG_CACHE="$PWD/.npm-cache" npx -y @modelcontextprotocol/inspector "$PWD/.venv/bin/python" "$PWD/implementation/mcp_server.py"
```

Checklist in Inspector:

- `search`, `insert`, and `aggregate` appear under tools
- `schema://database` appears under resources
- `schema://table/{table_name}` appears under resource templates
- `search` with `{"table":"students","filters":{"cohort":"A1"}}` succeeds
- `search` with `{"table":"missing"}` returns a clear unknown table error

## Client Config Examples

### Claude Code

```json
{
  "mcpServers": {
    "sqlite-lab": {
      "type": "stdio",
      "command": "/absolute/path/to/repo/.venv/bin/python",
      "args": ["/absolute/path/to/repo/implementation/mcp_server.py"],
      "env": {}
    }
  }
}
```

### Codex

Add this to `~/.codex/config.toml`:

```toml
[mcp_servers.sqlite_lab]
command = "/absolute/path/to/repo/.venv/bin/python"
args = ["/absolute/path/to/repo/implementation/mcp_server.py"]
```

Or add it with the CLI:

```bash
codex mcp add sqlite_lab -- /absolute/path/to/repo/.venv/bin/python /absolute/path/to/repo/implementation/mcp_server.py
codex mcp list
codex mcp get sqlite_lab
```

Verified local Codex CLI run:

```bash
codex --dangerously-bypass-approvals-and-sandbox exec --cd /absolute/path/to/repo \
  "Use the sqlite_lab MCP server. Call the search tool on table students with filters {\"cohort\":\"A1\"} and columns [\"name\",\"cohort\",\"gpa\"]. Do not edit files. Return only the tool result rows in Vietnamese."
```

Observed result:

```json
[
  {
    "name": "An Nguyen",
    "cohort": "A1",
    "gpa": 3.75
  },
  {
    "name": "Binh Tran",
    "cohort": "A1",
    "gpa": 3.2
  }
]
```

Note: in non-interactive `codex exec`, MCP tool calls may require approval/bypass flags. Resource reads worked normally; the `search` tool call succeeded with approval bypass enabled.

### Gemini CLI

```bash
gemini mcp add sqlite-lab /absolute/path/to/repo/.venv/bin/python /absolute/path/to/repo/implementation/mcp_server.py --description "SQLite lab FastMCP server" --timeout 10000
gemini mcp list
gemini --allowed-mcp-server-names sqlite-lab --yolo -p "Use sqlite-lab to show the top 2 students by GPA."
```

## Demo Script

1. Run tests and `verify_server.py`.
2. Open MCP Inspector and show the three tools.
3. Read `schema://database`.
4. Read `schema://table/students`.
5. Call `search` for students in cohort `A1`.
6. Call `insert` to add a student.
7. Call `aggregate` to average GPA by cohort.
8. Call `search` on a missing table to show safe error handling.
