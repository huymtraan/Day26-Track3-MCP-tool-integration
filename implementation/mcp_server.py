from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from fastmcp import FastMCP

try:
    from .db import SQLiteAdapter, ValidationError
    from .init_db import DEFAULT_DB_PATH, create_database
except ImportError:
    from db import SQLiteAdapter, ValidationError
    from init_db import DEFAULT_DB_PATH, create_database


def build_server(db_path: str | Path | None = None) -> FastMCP:
    path = Path(db_path or os.environ.get("SQLITE_LAB_DB", DEFAULT_DB_PATH))
    if not path.exists():
        create_database(path)

    adapter = SQLiteAdapter(path)
    mcp = FastMCP("SQLite Lab MCP Server")

    @mcp.tool(name="search")
    def search(
        table: str,
        filters: dict[str, Any] | list[dict[str, Any]] | None = None,
        columns: list[str] | None = None,
        limit: int = 20,
        offset: int = 0,
        order_by: str | None = None,
        descending: bool = False,
    ) -> dict[str, Any]:
        """Search rows from a validated table with optional filters, ordering, and pagination."""
        return _call_safely(
            adapter.search,
            table=table,
            filters=filters,
            columns=columns,
            limit=limit,
            offset=offset,
            order_by=order_by,
            descending=descending,
        )

    @mcp.tool(name="insert")
    def insert(table: str, values: dict[str, Any]) -> dict[str, Any]:
        """Insert one row into a validated table and return the inserted payload."""
        return _call_safely(adapter.insert, table=table, values=values)

    @mcp.tool(name="aggregate")
    def aggregate(
        table: str,
        metric: str,
        column: str | None = None,
        filters: dict[str, Any] | list[dict[str, Any]] | None = None,
        group_by: str | list[str] | None = None,
    ) -> dict[str, Any]:
        """Run count, avg, sum, min, or max over a validated table and optional filters."""
        return _call_safely(
            adapter.aggregate,
            table=table,
            metric=metric,
            column=column,
            filters=filters,
            group_by=group_by,
        )

    @mcp.resource("schema://database")
    def database_schema() -> str:
        """Return the full SQLite schema as JSON text."""
        return json.dumps(adapter.database_schema(), indent=2)

    @mcp.resource("schema://table/{table_name}")
    def table_schema(table_name: str) -> str:
        """Return one table schema as JSON text."""
        try:
            return json.dumps(adapter.get_table_schema(table_name), indent=2)
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc

    return mcp


def _call_safely(func: Any, **kwargs: Any) -> dict[str, Any]:
    try:
        return func(**kwargs)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the SQLite Lab MCP server.")
    parser.add_argument("--db", default=os.environ.get("SQLITE_LAB_DB", str(DEFAULT_DB_PATH)))
    parser.add_argument("--transport", default="stdio", choices=["stdio", "http", "sse"])
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    server = build_server(args.db)
    if args.transport == "stdio":
        server.run()
    else:
        server.run(transport=args.transport, host=args.host, port=args.port)
