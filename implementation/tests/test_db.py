from __future__ import annotations

import pytest

from db import SQLiteAdapter, ValidationError
from init_db import create_database


@pytest.fixture()
def adapter(tmp_path):
    db_path = tmp_path / "school.db"
    create_database(db_path)
    return SQLiteAdapter(db_path)


def test_search_filters_order_and_pagination(adapter):
    result = adapter.search(
        "students",
        columns=["name", "cohort", "gpa"],
        filters={"cohort": "A1"},
        order_by="gpa",
        descending=True,
        limit=1,
    )

    assert result["count"] == 1
    assert result["rows"][0]["name"] == "An Nguyen"


def test_insert_returns_inserted_payload(adapter):
    result = adapter.insert(
        "students",
        {
            "name": "Minh Dao",
            "email": "minh.dao@example.edu",
            "cohort": "A1",
            "age": 23,
            "gpa": 3.61,
        },
    )

    assert result["inserted"]["id"] > 0
    assert result["inserted"]["email"] == "minh.dao@example.edu"


def test_aggregate_avg_by_group(adapter):
    result = adapter.aggregate("students", "avg", column="gpa", group_by="cohort")

    cohorts = {row["cohort"] for row in result["rows"]}
    assert {"A1", "B2", "C3"}.issubset(cohorts)


def test_rejects_unknown_table(adapter):
    with pytest.raises(ValidationError, match="unknown table"):
        adapter.search("missing")


def test_rejects_unknown_column(adapter):
    with pytest.raises(ValidationError, match="unknown column"):
        adapter.search("students", filters={"not_a_column": "x"})


def test_rejects_unsupported_operator(adapter):
    with pytest.raises(ValidationError, match="unsupported filter operator"):
        adapter.search("students", filters=[{"column": "gpa", "op": "regex", "value": ".*"}])


def test_rejects_empty_insert(adapter):
    with pytest.raises(ValidationError, match="non-empty"):
        adapter.insert("students", {})


def test_rejects_invalid_aggregate(adapter):
    with pytest.raises(ValidationError, match="unsupported aggregate"):
        adapter.aggregate("students", "median", column="gpa")
