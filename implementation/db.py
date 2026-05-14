from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

try:
    from .init_db import DEFAULT_DB_PATH, create_database
except ImportError:
    from init_db import DEFAULT_DB_PATH, create_database


class ValidationError(Exception):
    """Raised when a database request cannot be safely executed."""


FilterInput = dict[str, Any] | list[dict[str, Any]] | None


class SQLiteAdapter:
    """Small SQLite data access layer with identifier validation."""

    ALLOWED_OPERATORS = {
        "eq": "=",
        "=": "=",
        "ne": "!=",
        "!=": "!=",
        "gt": ">",
        ">": ">",
        "gte": ">=",
        ">=": ">=",
        "lt": "<",
        "<": "<",
        "lte": "<=",
        "<=": "<=",
        "like": "LIKE",
        "contains": "LIKE",
        "in": "IN",
    }
    AGGREGATES = {"count", "avg", "sum", "min", "max"}
    NUMERIC_TYPES = {"INTEGER", "REAL", "NUMERIC", "DECIMAL", "FLOAT", "DOUBLE"}
    MAX_LIMIT = 100

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH, auto_init: bool = True):
        self.db_path = Path(db_path)
        if auto_init and not self.db_path.exists():
            create_database(self.db_path)

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def list_tables(self) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name NOT LIKE 'sqlite_%'
                ORDER BY name
                """
            ).fetchall()
        return [row["name"] for row in rows]

    def get_table_schema(self, table: str) -> dict[str, Any]:
        self._validate_table(table)
        quoted_table = self._quote_identifier(table)

        with self.connect() as conn:
            columns = conn.execute(f"PRAGMA table_info({quoted_table})").fetchall()
            foreign_keys = conn.execute(f"PRAGMA foreign_key_list({quoted_table})").fetchall()

        return {
            "table": table,
            "columns": [
                {
                    "name": row["name"],
                    "type": row["type"],
                    "not_null": bool(row["notnull"]),
                    "default": row["dflt_value"],
                    "primary_key": bool(row["pk"]),
                }
                for row in columns
            ],
            "foreign_keys": [
                {
                    "from": row["from"],
                    "to_table": row["table"],
                    "to_column": row["to"],
                    "on_update": row["on_update"],
                    "on_delete": row["on_delete"],
                }
                for row in foreign_keys
            ],
        }

    def database_schema(self) -> dict[str, Any]:
        return {
            "database": str(self.db_path),
            "tables": {table: self.get_table_schema(table) for table in self.list_tables()},
        }

    def search(
        self,
        table: str,
        columns: list[str] | None = None,
        filters: FilterInput = None,
        limit: int = 20,
        offset: int = 0,
        order_by: str | None = None,
        descending: bool = False,
    ) -> dict[str, Any]:
        self._validate_table(table)
        table_columns = self._column_names(table)
        selected_columns = self._validate_selected_columns(table, columns)
        limit = self._validate_limit(limit)
        offset = self._validate_offset(offset)

        where_sql, params = self._build_where(table, filters)
        order_sql = ""
        if order_by:
            self._validate_column(table, order_by)
            direction = "DESC" if descending else "ASC"
            order_sql = f" ORDER BY {self._quote_identifier(order_by)} {direction}"

        select_sql = ", ".join(self._quote_identifier(column) for column in selected_columns)
        sql = (
            f"SELECT {select_sql} FROM {self._quote_identifier(table)}"
            f"{where_sql}{order_sql} LIMIT ? OFFSET ?"
        )

        with self.connect() as conn:
            rows = conn.execute(sql, [*params, limit, offset]).fetchall()

        return {
            "table": table,
            "columns": selected_columns,
            "limit": limit,
            "offset": offset,
            "count": len(rows),
            "rows": [dict(row) for row in rows],
            "available_columns": table_columns,
        }

    def insert(self, table: str, values: dict[str, Any]) -> dict[str, Any]:
        self._validate_table(table)
        if not isinstance(values, dict) or not values:
            raise ValidationError("insert requires a non-empty values object")

        for column in values:
            self._validate_column(table, column)

        columns = list(values.keys())
        placeholders = ", ".join("?" for _ in columns)
        column_sql = ", ".join(self._quote_identifier(column) for column in columns)
        sql = f"INSERT INTO {self._quote_identifier(table)} ({column_sql}) VALUES ({placeholders})"

        try:
            with self.connect() as conn:
                cursor = conn.execute(sql, [values[column] for column in columns])
                row_id = cursor.lastrowid
                conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ValidationError(f"insert failed integrity checks: {exc}") from exc

        inserted = dict(values)
        if "id" not in inserted:
            inserted["id"] = row_id

        return {"table": table, "inserted": inserted}

    def aggregate(
        self,
        table: str,
        metric: str,
        column: str | None = None,
        filters: FilterInput = None,
        group_by: str | list[str] | None = None,
    ) -> dict[str, Any]:
        self._validate_table(table)
        normalized_metric = metric.lower()
        if normalized_metric not in self.AGGREGATES:
            allowed = ", ".join(sorted(self.AGGREGATES))
            raise ValidationError(f"unsupported aggregate metric {metric!r}; use one of: {allowed}")

        group_columns = self._normalize_group_by(table, group_by)
        aggregate_expression = self._aggregate_expression(table, normalized_metric, column)
        where_sql, params = self._build_where(table, filters)

        select_parts = [self._quote_identifier(column_name) for column_name in group_columns]
        select_parts.append(f"{aggregate_expression} AS value")
        group_sql = ""
        if group_columns:
            group_sql = " GROUP BY " + ", ".join(self._quote_identifier(name) for name in group_columns)

        sql = (
            f"SELECT {', '.join(select_parts)} FROM {self._quote_identifier(table)}"
            f"{where_sql}{group_sql}"
        )

        with self.connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        return {
            "table": table,
            "metric": normalized_metric,
            "column": column if column else ("*" if normalized_metric == "count" else None),
            "group_by": group_columns,
            "rows": [dict(row) for row in rows],
        }

    def _validate_table(self, table: str) -> None:
        if table not in self.list_tables():
            allowed = ", ".join(self.list_tables())
            raise ValidationError(f"unknown table {table!r}; allowed tables: {allowed}")

    def _column_names(self, table: str) -> list[str]:
        schema = self.get_table_schema(table)
        return [column["name"] for column in schema["columns"]]

    def _column_types(self, table: str) -> dict[str, str]:
        schema = self.get_table_schema(table)
        return {column["name"]: column["type"].upper() for column in schema["columns"]}

    def _validate_column(self, table: str, column: str) -> None:
        if column not in self._column_names(table):
            allowed = ", ".join(self._column_names(table))
            raise ValidationError(f"unknown column {column!r} for table {table!r}; allowed columns: {allowed}")

    def _validate_selected_columns(self, table: str, columns: list[str] | None) -> list[str]:
        if columns is None:
            return self._column_names(table)
        if not isinstance(columns, list) or not columns:
            raise ValidationError("columns must be a non-empty list when provided")
        for column in columns:
            self._validate_column(table, column)
        return columns

    def _validate_limit(self, limit: int) -> int:
        if not isinstance(limit, int) or isinstance(limit, bool):
            raise ValidationError("limit must be an integer")
        if limit < 1 or limit > self.MAX_LIMIT:
            raise ValidationError(f"limit must be between 1 and {self.MAX_LIMIT}")
        return limit

    def _validate_offset(self, offset: int) -> int:
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise ValidationError("offset must be a non-negative integer")
        return offset

    def _normalize_filters(self, filters: FilterInput) -> list[dict[str, Any]]:
        if filters is None:
            return []
        if isinstance(filters, list):
            normalized = filters
        elif isinstance(filters, dict):
            normalized = []
            for column, value in filters.items():
                if isinstance(value, dict):
                    normalized.append(
                        {
                            "column": column,
                            "op": value.get("op", "eq"),
                            "value": value.get("value"),
                        }
                    )
                else:
                    normalized.append({"column": column, "op": "eq", "value": value})
        else:
            raise ValidationError("filters must be an object, a list of filter objects, or null")

        for item in normalized:
            if not isinstance(item, dict):
                raise ValidationError("each filter must be an object")
            if "column" not in item:
                raise ValidationError("each filter requires a column")
        return normalized

    def _build_where(self, table: str, filters: FilterInput) -> tuple[str, list[Any]]:
        clauses: list[str] = []
        params: list[Any] = []

        for filter_item in self._normalize_filters(filters):
            column = filter_item["column"]
            op = filter_item.get("op", "eq")
            value = filter_item.get("value")
            self._validate_column(table, column)

            if op not in self.ALLOWED_OPERATORS:
                allowed = ", ".join(sorted(self.ALLOWED_OPERATORS))
                raise ValidationError(f"unsupported filter operator {op!r}; use one of: {allowed}")

            sql_op = self.ALLOWED_OPERATORS[op]
            quoted_column = self._quote_identifier(column)

            if sql_op == "IN":
                if not isinstance(value, list) or not value:
                    raise ValidationError("the in operator requires a non-empty list value")
                placeholders = ", ".join("?" for _ in value)
                clauses.append(f"{quoted_column} IN ({placeholders})")
                params.extend(value)
            elif op == "contains":
                clauses.append(f"{quoted_column} LIKE ?")
                params.append(f"%{value}%")
            else:
                clauses.append(f"{quoted_column} {sql_op} ?")
                params.append(value)

        if not clauses:
            return "", []
        return " WHERE " + " AND ".join(clauses), params

    def _normalize_group_by(self, table: str, group_by: str | list[str] | None) -> list[str]:
        if group_by is None:
            return []
        if isinstance(group_by, str):
            group_columns = [group_by]
        elif isinstance(group_by, list) and group_by:
            group_columns = group_by
        else:
            raise ValidationError("group_by must be a column name, a non-empty list, or null")

        for column in group_columns:
            self._validate_column(table, column)
        return group_columns

    def _aggregate_expression(self, table: str, metric: str, column: str | None) -> str:
        if metric == "count" and column is None:
            return "COUNT(*)"
        if column is None:
            raise ValidationError(f"{metric} requires a column")

        self._validate_column(table, column)
        if metric in {"avg", "sum"}:
            column_type = self._column_types(table)[column]
            if not any(kind in column_type for kind in self.NUMERIC_TYPES):
                raise ValidationError(f"{metric} requires a numeric column; {column!r} is {column_type}")

        return f"{metric.upper()}({self._quote_identifier(column)})"

    @staticmethod
    def _quote_identifier(identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'
