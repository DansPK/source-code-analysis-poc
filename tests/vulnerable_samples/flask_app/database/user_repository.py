"""Data layer -- holds both the vulnerable sink and the safe control."""

import sqlite3

DB_PATH = "users.db"


def _connect():
    return sqlite3.connect(DB_PATH)


def search_users_by_name(name):
    """VULNERABLE: user input concatenated straight into the SQL statement."""
    conn = _connect()
    cursor = conn.cursor()
    query = "SELECT id, name, email FROM users WHERE name LIKE '%" + name + "%'"
    cursor.execute(query)  # SINK
    return cursor.fetchall()


def find_user_by_id(user_id):
    """SAFE control: parameterized query. Must not be reported as vulnerable."""
    conn = _connect()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, email FROM users WHERE id = ?", (user_id,))
    return cursor.fetchone()
