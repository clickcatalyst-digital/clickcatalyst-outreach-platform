# db_factory.py
# Single connection factory for the MAIN database.
#
#   TURSO_URL + TURSO_AUTH_TOKEN set  -> connect to Turso (libSQL, remote)
#   otherwise                    -> local SQLite at the given path
#
# Returns a connection whose rows are dict-accessible (sqlite3.Row-compatible:
# row['col'], row[0], dict(row), .keys()) so the existing codebase works unchanged.
# libSQL returns plain tuples with no row_factory, so we wrap it.
#
# NOTE: the us_leads.db discovery DB and the India-only scripts intentionally do
# NOT use this factory — they stay on local SQLite (us_leads is Mac-only; India
# needs the heavy MCA tables that aren't in Turso).

import os
import sqlite3

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

TURSO_URL = os.getenv("TURSO_URL")
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN")


def using_turso() -> bool:
    return bool(TURSO_URL and TURSO_AUTH_TOKEN)


# --- sqlite3.Row-compatible row over a libSQL tuple ---
class _Row:
    __slots__ = ("_cols", "_vals", "_map")

    def __init__(self, cols, vals):
        self._cols = cols
        self._vals = vals
        self._map = {c: v for c, v in zip(cols, vals)}

    def __getitem__(self, k):
        if isinstance(k, (int, slice)):
            return self._vals[k]
        return self._map[k]

    def keys(self):
        return list(self._cols)

    def get(self, k, default=None):
        return self._map.get(k, default)

    def __iter__(self):
        return iter(self._vals)

    def __len__(self):
        return len(self._vals)


class _Cursor:
    def __init__(self, cur):
        self._cur = cur

    def execute(self, sql, params=()):
        self._cur.execute(sql, params)
        return self

    def executemany(self, sql, seq):
        self._cur.executemany(sql, seq)
        return self

    def _cols(self):
        return [d[0] for d in (self._cur.description or [])]

    def fetchone(self):
        r = self._cur.fetchone()
        return _Row(self._cols(), r) if r is not None else None

    def fetchall(self):
        cols = self._cols()
        return [_Row(cols, r) for r in self._cur.fetchall()]

    def __iter__(self):
        cols = self._cols()
        for r in self._cur.fetchall():
            yield _Row(cols, r)

    @property
    def lastrowid(self):
        return self._cur.lastrowid

    @property
    def rowcount(self):
        return self._cur.rowcount

    @property
    def description(self):
        return self._cur.description


class _Conn:
    """Wraps a libSQL connection to present the sqlite3 dict-row interface."""

    def __init__(self, conn):
        self._conn = conn
        self.row_factory = None  # accepted + ignored; rows are always dict-accessible

    def cursor(self):
        return _Cursor(self._conn.cursor())

    def execute(self, sql, params=()):
        c = self.cursor()
        c.execute(sql, params)
        return c

    def executescript(self, script):
        self._conn.executescript(script)
        return self

    def commit(self):
        self._conn.commit()

    def close(self):
        try:
            self._conn.close()
        except Exception:
            pass


def connect(local_path):
    """Main-DB connection. Turso when configured, else local SQLite at local_path."""
    if using_turso():
        import libsql_experimental as libsql
        return _Conn(libsql.connect(TURSO_URL, auth_token=TURSO_AUTH_TOKEN))

    conn = sqlite3.connect(local_path, timeout=10, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA busy_timeout = 5000")
    except Exception:
        pass
    return conn
