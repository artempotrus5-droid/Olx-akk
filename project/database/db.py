# -*- coding: utf-8 -*-
"""
Работа с базой данных: атомарные операции над аккаунтами, история.

Поддерживает два режима, определяемые переменными окружения:

1) Локальный SQLite (по умолчанию) — если TURSO_DATABASE_URL не задан.
   Данные хранятся только в файле на диске контейнера и будут потеряны
   при пересоздании контейнера на бесплатном тарифе Render.

2) Turso (рекомендуется для продакшена) — если заданы TURSO_DATABASE_URL
   и TURSO_AUTH_TOKEN. Используется "embedded replica": локальный файл
   служит быстрым кэшем для чтения, а каждая запись сразу уходит в
   облачную базу Turso, поэтому данные переживают любой передеплой или
   пересоздание контейнера.
"""

import os
from contextlib import contextmanager
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "data/accounts.db")
TURSO_DATABASE_URL = os.getenv("TURSO_DATABASE_URL", "").strip()
TURSO_AUTH_TOKEN = os.getenv("TURSO_AUTH_TOKEN", "").strip()

USE_TURSO = bool(TURSO_DATABASE_URL)

if USE_TURSO:
    import libsql as _driver
else:
    import sqlite3 as _driver

EVENT_ADDED = "added"
EVENT_DELETED = "deleted"
EVENT_TAKEN = "taken"
EVENT_RETURNED = "returned"

STATUS_FREE = "free"
STATUS_TAKEN = "taken"
STATUS_DELETED = "deleted"


def _ensure_dir():
    d = os.path.dirname(DB_PATH)
    if d:
        os.makedirs(d, exist_ok=True)


def _connect():
    _ensure_dir()
    if USE_TURSO:
        conn = _driver.connect(DB_PATH, sync_url=TURSO_DATABASE_URL, auth_token=TURSO_AUTH_TOKEN)
        conn.sync()  # подтягиваем актуальное состояние из облака перед работой
    else:
        conn = _driver.connect(DB_PATH, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
    return conn


@contextmanager
def get_conn():
    conn = _connect()
    try:
        yield conn
        conn.commit()
        if USE_TURSO:
            conn.sync()  # гарантированно проталкиваем изменения в облако
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _row_to_dict(cursor, row):
    if row is None:
        return None
    cols = [d[0] for d in cursor.description]
    return dict(zip(cols, row))


def _rows_to_dicts(cursor, rows):
    cols = [d[0] for d in cursor.description]
    return [dict(zip(cols, r)) for r in rows]


def now_str() -> str:
    return datetime.now().strftime("%d.%m.%Y %H:%M")


def init_db():
    with get_conn() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                password TEXT NOT NULL,
                year INTEGER NOT NULL,
                description TEXT,
                status TEXT NOT NULL DEFAULT 'free',
                taken_by_user_id INTEGER,
                taken_by_username TEXT,
                added_by_user_id INTEGER,
                added_by_username TEXT,
                created_at TEXT,
                taken_at TEXT,
                returned_at TEXT,
                deleted_at TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                email TEXT,
                password TEXT,
                year INTEGER,
                description TEXT,
                username TEXT,
                created_at TEXT
            )
            """
        )


def add_account(email, password, year, description, user_id, username):
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT INTO accounts
                (email, password, year, description, status,
                 added_by_user_id, added_by_username, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (email, password, year, description, STATUS_FREE, user_id, username, now_str()),
        )
        new_id = cur.lastrowid
        cur2 = conn.execute("SELECT * FROM accounts WHERE id = ?", (new_id,))
        return _row_to_dict(cur2, cur2.fetchone())


def get_account(account_id):
    with get_conn() as conn:
        cur = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,))
        return _row_to_dict(cur, cur.fetchone())


def list_active_accounts():
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT * FROM accounts WHERE status != ? ORDER BY id ASC", (STATUS_DELETED,)
        )
        return _rows_to_dicts(cur, cur.fetchall())


def list_user_accounts(user_id):
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT * FROM accounts WHERE status = ? AND taken_by_user_id = ? ORDER BY id ASC",
            (STATUS_TAKEN, user_id),
        )
        return _rows_to_dicts(cur, cur.fetchall())


def take_account(account_id, user_id, username):
    """Атомарно берёт аккаунт. Возвращает (row, None) при успехе,
    либо (None, conflict_row_or_None) при неудаче."""
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,))
        row = _row_to_dict(cur, cur.fetchone())
        if row is None:
            return None, None
        if row["status"] != STATUS_FREE:
            return None, row
        cur2 = conn.execute(
            """
            UPDATE accounts
            SET status = ?, taken_by_user_id = ?, taken_by_username = ?, taken_at = ?
            WHERE id = ? AND status = ?
            """,
            (STATUS_TAKEN, user_id, username, now_str(), account_id, STATUS_FREE),
        )
        if cur2.rowcount == 0:
            return None, row
        cur3 = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,))
        return _row_to_dict(cur3, cur3.fetchone()), None


def return_account(account_id, user_id):
    """Возвращает аккаунт, если он числится взятым этим пользователем."""
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,))
        row = _row_to_dict(cur, cur.fetchone())
        if row is None:
            return None, None
        if row["status"] != STATUS_TAKEN or row["taken_by_user_id"] != user_id:
            return None, row
        conn.execute(
            """
            UPDATE accounts
            SET status = ?, taken_by_user_id = NULL, taken_by_username = NULL, returned_at = ?
            WHERE id = ?
            """,
            (STATUS_FREE, now_str(), account_id),
        )
        cur2 = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,))
        return _row_to_dict(cur2, cur2.fetchone()), None


def delete_account(account_id):
    with get_conn() as conn:
        cur = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,))
        row = _row_to_dict(cur, cur.fetchone())
        if row is None or row["status"] == STATUS_DELETED:
            return None
        conn.execute(
            "UPDATE accounts SET status = ?, deleted_at = ? WHERE id = ?",
            (STATUS_DELETED, now_str(), account_id),
        )
        cur2 = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,))
        return _row_to_dict(cur2, cur2.fetchone())


def add_history(account_id, event_type, email, password, year, description, username):
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO history
                (account_id, event_type, email, password, year, description, username, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (account_id, event_type, email, password, year, description, username, now_str()),
        )


def list_history(limit=300):
    with get_conn() as conn:
        cur = conn.execute(
            "SELECT * FROM history ORDER BY id DESC LIMIT ?", (limit,)
        )
        return _rows_to_dicts(cur, cur.fetchall())
