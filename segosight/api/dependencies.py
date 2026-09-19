"""Warehouse access for the API.

DuckDB permits a single read-write process. The API therefore owns the
connection for its lifetime, and the pipeline runs *through* the API rather
than as a competing process -- which is also why "incorporate the next data
batch" is an action in the product instead of a terminal command.

Writes are serialised behind a lock. Reads are concurrent-safe on one
connection for the traffic a single-office tool sees.
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


def get_connection() -> duckdb.DuckDBPyConnection:
    global _connection
    with _lock:
        if _connection is None:
            _connection = connect(_path)
        return _connection


def close_connection() -> None:
    global _connection
    with _lock:
        if _connection is not None:
            _connection.close()
            _connection = None


def write_lock() -> threading.RLock:
    return _lock
