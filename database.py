import aiosqlite
from datetime import datetime, timedelta

DB_NAME = "subscriptions.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                expiry_date TEXT,
                plan_months INTEGER
            )
        ''')
        await db.execute('''
            CREATE TABLE IF NOT EXISTS orders (
                order_id TEXT PRIMARY KEY,
                user_id INTEGER,
                plan_months INTEGER,
                status TEXT
            )
        ''')
        await db.commit()

async def create_order(order_id: str, user_id: int, months: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            INSERT INTO orders (order_id, user_id, plan_months, status)
            VALUES (?, ?, ?, 'PENDING')
        ''', (order_id, user_id, months))
        await db.commit()

async def get_order(order_id: str):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute('SELECT user_id, plan_months, status FROM orders WHERE order_id = ?', (order_id,)) as cursor:
            return await cursor.fetchone()

async def mark_order_paid(order_id: str):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('UPDATE orders SET status = "PAID" WHERE order_id = ?', (order_id,))
        await db.commit()

async def add_or_update_subscriber(user_id: int, months: int):
    days_to_add = months * 30
    new_expiry = datetime.utcnow() + timedelta(days=days_to_add)
    expiry_str = new_expiry.isoformat()

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('''
            INSERT INTO users (user_id, expiry_date, plan_months)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
            expiry_date = ?,
            plan_months = ?
        ''', (user_id, expiry_str, months, expiry_str, months))
        await db.commit()
    return new_expiry

async def get_expired_users():
    now_str = datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute('SELECT user_id FROM users WHERE expiry_date <= ?', (now_str,)) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows]

async def remove_user(user_id: int):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
        await db.commit()
