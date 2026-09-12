import sqlite3
from datetime import datetime, timedelta

DB_NAME = "subscriptions.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            expiry_date TEXT,
            plan_months INTEGER
        )
    ''')
    conn.commit()
    conn.close()

def add_or_update_subscriber(user_id: int, months: int):
    days_to_add = months * 30
    new_expiry = datetime.utcnow() + timedelta(days=days_to_add)
    expiry_str = new_expiry.isoformat()

    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('''
        INSERT INTO users (user_id, expiry_date, plan_months)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
        expiry_date = ?,
        plan_months = ?
    ''', (user_id, expiry_str, months, expiry_str, months))
    conn.commit()
    conn.close()
    return new_expiry

def get_expired_users():
    now_str = datetime.utcnow().isoformat()
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('SELECT user_id FROM users WHERE expiry_date <= ?', (now_str,))
    rows = cur.fetchall()
    conn.close()
    return [row[0] for row in rows]

def remove_user(user_id: int):
    conn = sqlite3.connect(DB_NAME)
    cur = conn.cursor()
    cur.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()
    
