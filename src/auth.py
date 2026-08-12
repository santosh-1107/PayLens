"""
auth.py
=======
Simple authentication layer for the UPI Transaction Intelligence Platform.
Validates credentials against the SQLite users table.
"""

import hashlib
import sqlite3

def login_user(conn: sqlite3.Connection, username: str, password: str) -> tuple[str, str] | None:
    """
    Validates user credentials against the database.
    Checks user_id or name (exactly/case-sensitively) and SHA-256 hashed password.
    
    Returns:
        (user_id, role) if authentication succeeds, else None.
        
    NOTE: Demo-grade security. In production, use strong salted hashing (e.g. bcrypt)
    and proper secure session handling.
    """
    if not username or not password:
        return None
        
    username = username.strip()
    password = password.strip()
    hashed_pwd = hashlib.sha256(password.encode("utf-8")).hexdigest()
    
    cur = conn.cursor()
    cur.execute(
        """
        SELECT user_id, role
        FROM users
        WHERE (user_id = ? OR name = ?) AND password = ?
        """,
        (username, username, hashed_pwd)
    )
    row = cur.fetchone()
    if row:
        return row[0], row[1]  # returns (user_id, role)
        
    return None
