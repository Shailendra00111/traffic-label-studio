"""
core/auth.py
=============
Simple local authentication: register + login backed by a SQLite database
stored next to the app (users.db). Passwords are never stored in plain
text — each password is hashed with PBKDF2-HMAC-SHA256 + a random salt
(both from Python's stdlib, no extra install needed).
"""

import os
import sqlite3
import hashlib
import secrets
from dataclasses import dataclass
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "users.db")

PBKDF2_ITERATIONS = 200_000


@dataclass
class AuthResult:
    success: bool
    message: str


def _get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            username TEXT PRIMARY KEY,
            salt TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn


def _hash_password(password: str, salt: bytes) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return dk.hex()


def register_user(username: str, password: str) -> AuthResult:
    username = username.strip()

    if not username or not password:
        return AuthResult(False, "Username and password cannot be empty.")
    if len(username) < 3:
        return AuthResult(False, "Username must be at least 3 characters.")
    if len(password) < 4:
        return AuthResult(False, "Password must be at least 4 characters.")

    conn = _get_connection()
    try:
        existing = conn.execute(
            "SELECT 1 FROM users WHERE username = ?", (username,)
        ).fetchone()
        if existing:
            return AuthResult(False, "That username is already taken.")

        salt = secrets.token_bytes(16)
        password_hash = _hash_password(password, salt)

        conn.execute(
            "INSERT INTO users (username, salt, password_hash) VALUES (?, ?, ?)",
            (username, salt.hex(), password_hash),
        )
        conn.commit()
        return AuthResult(True, "Account created successfully.")
    finally:
        conn.close()


def login_user(username: str, password: str) -> AuthResult:
    username = username.strip()

    if not username or not password:
        return AuthResult(False, "Username and password cannot be empty.")

    conn = _get_connection()
    try:
        row = conn.execute(
            "SELECT salt, password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()
        if row is None:
            return AuthResult(False, "No account found with that username.")

        salt_hex, stored_hash = row
        salt = bytes.fromhex(salt_hex)
        attempted_hash = _hash_password(password, salt)

        if secrets.compare_digest(attempted_hash, stored_hash):
            return AuthResult(True, "Login successful.")
        return AuthResult(False, "Incorrect password.")
    finally:
        conn.close()


def user_exists(username: str) -> bool:
    conn = _get_connection()
    try:
        row = conn.execute(
            "SELECT 1 FROM users WHERE username = ?", (username.strip(),)
        ).fetchone()
        return row is not None
    finally:
        conn.close()