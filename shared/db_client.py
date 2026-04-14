"""Direct PostgreSQL database client using psycopg2.

This module provides a database client that can replace Supabase client
for local PostgreSQL connections.
"""
import os
from contextlib import contextmanager
from typing import Any, Optional
import psycopg2
from psycopg2.extras import RealDictCursor

# Global connection pool
_connection = None

def get_database_url() -> str:
    """Get database URL from environment or default."""
    return os.getenv(
        'DATABASE_URL',
        'postgresql://tms:tms_secret_password@tms-postgres:5432/tms_main'
    )

def get_connection():
    """Get a database connection."""
    global _connection
    if _connection is None or _connection.closed:
        _connection = psycopg2.connect(get_database_url())
    return _connection

def close_connection():
    """Close the database connection."""
    global _connection
    if _connection and not _connection.closed:
        _connection.close()
        _connection = None

@contextmanager
def get_cursor(dict_cursor: bool = True):
    """Context manager for database cursor."""
    conn = get_connection()
    cursor_factory = RealDictCursor if dict_cursor else None
    cursor = conn.cursor(cursor_factory=cursor_factory)
    try:
        yield cursor
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cursor.close()


class TableQuery:
    """Query builder for PostgreSQL that mimics Supabase patterns."""

    def __init__(self, table_name: str):
        self.table_name = table_name
        self._columns = "*"
        self._filters = []
        self._order_by = None
        self._limit_val = None
        self._offset_val = None
        self._returning = "*"

    def select(self, columns: str = "*"):
        self._columns = columns
        return self

    def eq(self, column: str, value: Any):
        # Handle UUID type
        if isinstance(value, str) and len(value) == 36 and '-' in value:
            self._filters.append(f"{column} = '{value}'::uuid")
        else:
            # Escape single quotes
            if isinstance(value, str):
                value = value.replace("'", "''")
            self._filters.append(f"{column} = '{value}'")
        return self

    def neq(self, column: str, value: Any):
        if isinstance(value, str) and len(value) == 36 and '-' in value:
            self._filters.append(f"{column} != '{value}'::uuid")
        else:
            if isinstance(value, str):
                value = value.replace("'", "''")
            self._filters.append(f"{column} != '{value}'")
        return self

    def like(self, column: str, value: str):
        value = value.replace("%", "%%").replace("_", "__")
        self._filters.append(f"{column} ILIKE '%{value}%'")
        return self

    def ilike(self, column: str, value: str):
        value = value.replace("%", "%%").replace("_", "__")
        self._filters.append(f"{column} ILIKE '%{value}%'")
        return self

    def in_(self, column: str, values: list):
        if not values:
            self._filters.append("1=0")
            return self
        formatted = []
        for v in values:
            if isinstance(v, str):
                v = v.replace("'", "''")
                formatted.append(f"'{v}'")
            else:
                formatted.append(str(v))
        self._filters.append(f"{column} IN ({','.join(formatted)})")
        return self

    def order(self, column: str, desc: bool = False):
        direction = "DESC" if desc else "ASC"
        self._order_by = f"{column} {direction}"
        return self

    def limit(self, n: int):
        self._limit_val = n
        return self

    def offset(self, n: int):
        self._offset_val = n
        return self

    def update(self, data: dict):
        """Build UPDATE query."""
        sets = []
        for k, v in data.items():
            if v is None:
                sets.append(f"{k} = NULL")
            elif isinstance(v, str):
                v = v.replace("'", "''")
                sets.append(f"{k} = '{v}'")
            elif isinstance(v, bool):
                sets.append(f"{k} = {str(v).lower()}")
            else:
                sets.append(f"{k} = {v}")
        return UpdateQuery(self.table_name, sets, self._filters)

    def insert(self, data: list):
        """Build INSERT query."""
        if not data:
            return None
        if isinstance(data, dict):
            data = [data]

        columns = list(data[0].keys())
        values = []
        for row in data:
            row_values = []
            for v in row.values():
                if v is None:
                    row_values.append("NULL")
                elif isinstance(v, str):
                    v = v.replace("'", "''")
                    row_values.append(f"'{v}'")
                elif isinstance(v, bool):
                    row_values.append(str(v).lower())
                else:
                    row_values.append(str(v))
            values.append(f"({','.join(row_values)})")

        return InsertQuery(self.table_name, columns, values)

    def delete(self):
        """Build DELETE query."""
        return DeleteQuery(self.table_name, self._filters)

    def execute(self):
        """Execute the query and return results."""
        query = self._build_select()
        with get_cursor() as cur:
            cur.execute(query)
            if cur.description:
                return Results(cur.fetchall())
            return Results([])

    def _build_select(self) -> str:
        query = f"SELECT {self._columns} FROM {self.table_name}"
        if self._filters:
            query += " WHERE " + " AND ".join(self._filters)
        if self._order_by:
            query += f" ORDER BY {self._order_by}"
        if self._limit_val:
            query += f" LIMIT {self._limit_val}"
        if self._offset_val:
            query += f" OFFSET {self._offset_val}"
        return query


class UpdateQuery:
    """UPDATE query builder."""

    def __init__(self, table: str, sets: list, filters: list):
        self.table = table
        self.sets = sets
        self.filters = filters

    def eq(self, column: str, value: Any):
        if isinstance(value, str):
            value = value.replace("'", "''")
        self.filters.append(f"{column} = '{value}'")
        return self

    def execute(self):
        query = f"UPDATE {self.table} SET " + ", ".join(self.sets)
        if self.filters:
            query += " WHERE " + " AND ".join(self.filters)
        query += " RETURNING *"
        with get_cursor() as cur:
            cur.execute(query)
            return Results(cur.fetchall())


class InsertQuery:
    """INSERT query builder."""

    def __init__(self, table: str, columns: list, values: list):
        self.table = table
        self.columns = columns
        self.values = values

    def execute(self):
        cols_str = ", ".join(self.columns)
        vals_str = ", ".join(self.values)
        query = f"INSERT INTO {self.table} ({cols_str}) VALUES {vals_str} RETURNING *"
        with get_cursor() as cur:
            cur.execute(query)
            return Results(cur.fetchall())


class DeleteQuery:
    """DELETE query builder."""

    def __init__(self, table: str, filters: list):
        self.table = table
        self.filters = filters

    def eq(self, column: str, value: Any):
        if isinstance(value, str):
            value = value.replace("'", "''")
        self.filters.append(f"{column} = '{value}'")
        return self

    def execute(self):
        query = f"DELETE FROM {self.table}"
        if self.filters:
            query += " WHERE " + " AND ".join(self.filters)
        query += " RETURNING *"
        with get_cursor() as cur:
            cur.execute(query)
            return Results(cur.fetchall())


class Results:
    """Query results wrapper."""

    def __init__(self, rows: list):
        self.data = rows
        self._count = None

    @property
    def count(self) -> int:
        if self._count is None:
            self._count = len(self.data)
        return self._count

    def __len__(self):
        return len(self.data)

    def __getitem__(self, key):
        return self.data[key]

    @property
    def items(self) -> list:
        return self.data


class DbClient:
    """Database client that mimics Supabase table access pattern."""

    def __init__(self, url: str = None, key: str = None):
        self.url = url

    def table(self, name: str) -> TableQuery:
        return TableQuery(name)


def create_client(url: str, key: str) -> DbClient:
    """Create a database client."""
    return DbClient(url, key)
