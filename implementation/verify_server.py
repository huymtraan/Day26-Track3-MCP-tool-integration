from __future__ import annotations

import asyncio
import contextlib
import io
import json
import tempfile
from pathlib import Path

from fastmcp import Client

from init_db import create_database
from mcp_server import build_server


async def main() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "verify.db"
        create_database(db_path)
        server = build_server(db_path)

        async with Client(server) as client:
            tools = await client.list_tools()
            tool_names = sorted(tool.name for tool in tools)
            assert tool_names == ["aggregate", "insert", "search"], tool_names

            resources = await client.list_resources()
            resource_uris = sorted(str(resource.uri) for resource in resources)
            assert "schema://database" in resource_uris, resource_uris

            templates = await client.list_resource_templates()
            template_uris = sorted(str(template.uriTemplate) for template in templates)
            assert "schema://table/{table_name}" in template_uris, template_uris

            search_result = await client.call_tool(
                "search",
                {
                    "table": "students",
                    "filters": {"cohort": "A1"},
                    "columns": ["id", "name", "cohort", "gpa"],
                    "order_by": "gpa",
                    "descending": True,
                },
            )
            search_payload = _tool_payload(search_result)
            assert search_payload["count"] == 2, search_payload

            insert_result = await client.call_tool(
                "insert",
                {
                    "table": "students",
                    "values": {
                        "name": "Minh Dao",
                        "email": "minh.dao@example.edu",
                        "cohort": "A1",
                        "age": 23,
                        "gpa": 3.61,
                    },
                },
            )
            insert_payload = _tool_payload(insert_result)
            assert insert_payload["inserted"]["id"] > 0, insert_payload

            aggregate_result = await client.call_tool(
                "aggregate",
                {"table": "students", "metric": "avg", "column": "gpa", "group_by": "cohort"},
            )
            aggregate_payload = _tool_payload(aggregate_result)
            assert aggregate_payload["rows"], aggregate_payload

            schema_result = await client.read_resource("schema://table/students")
            schema_payload = json.loads(schema_result[0].text)
            assert schema_payload["table"] == "students", schema_payload

            error_output = io.StringIO()
            with contextlib.redirect_stdout(error_output), contextlib.redirect_stderr(error_output):
                try:
                    await client.call_tool("search", {"table": "missing"})
                except Exception as exc:
                    assert "unknown table" in str(exc)
                else:
                    raise AssertionError("invalid table search should fail")

    print("Verification passed: tools, resources, valid calls, and invalid errors work.")


def _tool_payload(result: object) -> dict:
    data = getattr(result, "structured_content", None)
    if data is None:
        data = getattr(result, "data", None)
    if data is not None:
        return data

    content = getattr(result, "content", None)
    if content:
        text = getattr(content[0], "text", None)
        if text:
            return json.loads(text)

    raise AssertionError(f"Could not extract tool payload from {result!r}")


if __name__ == "__main__":
    asyncio.run(main())
