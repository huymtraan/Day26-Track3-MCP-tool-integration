from __future__ import annotations

import json
import asyncio

from fastmcp import Client

from init_db import create_database
from mcp_server import build_server


def test_mcp_discovery_and_resource_template(tmp_path):
    asyncio.run(_assert_mcp_discovery_and_resource_template(tmp_path))


async def _assert_mcp_discovery_and_resource_template(tmp_path):
    db_path = tmp_path / "school.db"
    create_database(db_path)

    async with Client(build_server(db_path)) as client:
        tools = await client.list_tools()
        assert sorted(tool.name for tool in tools) == ["aggregate", "insert", "search"]

        resources = await client.list_resources()
        assert "schema://database" in {str(resource.uri) for resource in resources}

        templates = await client.list_resource_templates()
        assert "schema://table/{table_name}" in {str(template.uriTemplate) for template in templates}

        table_schema = await client.read_resource("schema://table/students")
        payload = json.loads(table_schema[0].text)
        assert payload["table"] == "students"
