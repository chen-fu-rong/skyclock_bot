import os
import logging
import psycopg2
from datetime import datetime, timedelta
from contextlib import contextmanager

# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

@contextmanager
def get_db_connection():
    conn = None
    try:
        if 'RENDER' in os.environ:
            conn = psycopg2.connect(os.getenv('DATABASE_URL'), sslmode='require')
        else:
            import sqlite3
            conn = sqlite3.connect('skyclock.db')
        yield conn
    except Exception as e:
        logger.error(f"Database connection failed: {str(e)}")
        raise
    finally:
        if conn:
            conn.close()

def init_db():
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                if 'RENDER' in os.environ:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS users (
                            user_id BIGINT PRIMARY KEY,
                            username TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                else:
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS users (
                            user_id INTEGER PRIMARY KEY,
                            username TEXT,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {str(e)}")
        raise

def get_user(user_id):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
                return cursor.fetchone()
    except Exception as e:
        logger.error(f"Failed to get user: {str(e)}")
        return None

def update_user(user_id, username):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO users (user_id, username)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id) DO UPDATE
                    SET username = EXCLUDED.username
                """, (user_id, username))
        logger.info(f"Updated user {user_id} in database")
    except Exception as e:
        logger.error(f"Failed to update user: {str(e)}")
        raise

def get_myanmar_time():
    """Returns current Myanmar time (UTC+6:30)"""
    utc_time = datetime.utcnow()
    return utc_time + timedelta(hours=6, minutes=30)