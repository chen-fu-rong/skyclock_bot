import asyncpg
import os

DB_URL = os.getenv("DATABASE_URL")

async def init_db():
    conn = await asyncpg.connect(DB_URL)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            utc_offset INT
        );
    """)
    await conn.close()

async def set_user_timezone(user_id: int, offset: int):
    conn = await asyncpg.connect(DB_URL)
    await conn.execute("""
        INSERT INTO users (user_id, utc_offset)
        VALUES ($1, $2)
        ON CONFLICT (user_id)
        DO UPDATE SET utc_offset = EXCLUDED.utc_offset;
    """, user_id, offset)
    await conn.close()

async def get_user_timezone(user_id: int):
    conn = await asyncpg.connect(DB_URL)
    row = await conn.fetchrow("SELECT utc_offset FROM users WHERE user_id = $1", user_id)
    await conn.close()
    return row["utc_offset"] if row else 0
