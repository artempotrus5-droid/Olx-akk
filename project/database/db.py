# -*- coding: utf-8 -*-
"""Работа с SQLite: инициализация, атомарные операции над аккаунтами, история."""

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "data/accounts.db")

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


@contextmanager
def get_conn():
    _ensure_dir()
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


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
        row = conn.execute("SELECT * FROM accounts WHERE id = ?", (new_id,)).fetchone()
        return dict(row)


def get_account(account_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        return dict(row) if row else None


def list_active_accounts():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM accounts WHERE status != ? ORDER BY id ASC", (STATUS_DELETED,)
        ).fetchall()
        return [dict(r) for r in rows]


def list_user_accounts(user_id):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM accounts WHERE status = ? AND taken_by_user_id = ? ORDER BY id ASC",
            (STATUS_TAKEN, user_id),
        ).fetchall()
        return [dict(r) for r in rows]


def take_account(account_id, user_id, username):
    """Атомарно берёт аккаунт. Возвращает (row, None) при успехе,
    либо (None, conflict_row_or_None) при неудаче."""
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        if row is None:
            return None, None
        if row["status"] != STATUS_FREE:
            return None, dict(row)
        conn.execute(
            """
            UPDATE accounts
            SET status = ?, taken_by_user_id = ?, taken_by_username = ?, taken_at = ?
            WHERE id = ? AND status = ?
            """,
            (STATUS_TAKEN, user_id, username, now_str(), account_id, STATUS_FREE),
        )
        if conn.total_changes == 0:
            return None, dict(row)
        new_row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        return dict(new_row), None


def return_account(account_id, user_id):
    """Возвращает аккаунт, если он числится взятым этим пользователем."""
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        if row is None:
            return None, None
        if row["status"] != STATUS_TAKEN or row["taken_by_user_id"] != user_id:
            return None, dict(row)
        conn.execute(
            """
            UPDATE accounts
            SET status = ?, taken_by_user_id = NULL, taken_by_username = NULL, returned_at = ?
            WHERE id = ?
            """,
            (STATUS_FREE, now_str(), account_id),
        )
        new_row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        return dict(new_row), None


def delete_account(account_id):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        if row is None or row["status"] == STATUS_DELETED:
            return None
        conn.execute(
            "UPDATE accounts SET status = ?, deleted_at = ? WHERE id = ?",
            (STATUS_DELETED, now_str(), account_id),
        )
        new_row = conn.execute("SELECT * FROM accounts WHERE id = ?", (account_id,)).fetchone()
        return dict(new_row)


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
        rows = conn.execute(
            "SELECT * FROM history ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
