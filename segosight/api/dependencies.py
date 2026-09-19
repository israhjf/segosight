"""Warehouse access for the API.

DuckDB permits a single read-write *process*. The API therefore owns the
database for its lifetime, and the pipeline runs through the API rather than as
a competing process -- which is also why "incorporate the next data batch" is
an action in the product instead of a terminal command.

Within the process, concurrency needs care. FastAPI runs synchronous endpoints
in a threadpool, so the Overview screen's three requests execute in parallel.
A DuckDB connection is not safe to use from several threads at once: the result
set lives on the connection, so two interleaved queries clobber each other and
an endpoint can fetch rows belonging to a different request. `cursor()` creates
an independent handle onto the same database, which is the supported way to fan
out inside one process, so every request gets its own.

Writes are additionally serialised behind a lock, because promotion and the
pipeline both read-modify-write and must not interleave with each other.
"""

from __future__ import annotations

import threading
from pathlib import Path

import duckdb

from ..warehouse import connect

_lock = threading.RLock()
_connection: duckdb.DuckDBPyConnection | None = None
_path: Path | str | None = None


def configure(path: Path | str | None) -> None:
    global _path
    _path = path


def get_database() -> duckdb.DuckDBPyConnection:
    """The long-lived connection that holds the database open."""
    global _connection
    with _lock:
        if _connection is None:
            _connection = connect(_path)
        return _connection


def get_connection() -> duckdb.DuckDBPyConnection:
    """An independent handle for this request.

    Never share the returned object across threads, and never hand out the
    base connection directly -- that is what caused concurrent requests to read
    one another's result sets.
    """
    return get_database().cursor()


def close_connection() -> None:
    global _connection
    with _lock:
        if _connection is not None:
            _connection.close()
            _connection = None


def write_lock() -> threading.RLock:
    return _lock
