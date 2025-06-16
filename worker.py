import os
import logging
from contextlib import contextmanager
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

def get_db_connection():
    """Connect to PostgreSQL on Render or use SQLite locally"""
    if 'RENDER' in os.environ:
        import psycopg2
        return psycopg2.connect(os.getenv('DATABASE_URL'), sslmode='require')
    else:
        import sqlite3
        return sqlite3.connect('skyclock.db')

@contextmanager
def get_db_cursor():
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        yield cursor
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error(f"Database error: {str(e)}")
        raise
    finally:
        cursor.close()
        conn.close()

def init_db():
    """Initialize database tables"""
    try:
        with get_db_cursor() as cursor:
            if 'RENDER' in os.environ:
                # PostgreSQL syntax
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id BIGINT PRIMARY KEY,
                        username TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
            else:
                # SQLite syntax
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        user_id INTEGER PRIMARY KEY,
                        username TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.error(f"Database initialization error: {str(e)}")
        raise

def get_user(user_id):
    """Get user from database"""
    try:
        with get_db_cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
            return cursor.fetchone()
    except Exception as e:
        logger.error(f"Error getting user: {str(e)}")
        return None

def update_user(user_id, username):
    """Update or create user in database"""
    try:
        with get_db_cursor() as cursor:
            cursor.execute("""
                INSERT INTO users (user_id, username)
                VALUES (%s, %s)
                ON CONFLICT (user_id) DO UPDATE
                SET username = EXCLUDED.username
            """, (user_id, username))
        logger.info(f"Updated user {user_id} in database")
    except Exception as e:
        logger.error(f"Error updating user: {str(e)}")
        raise

def get_myanmar_time():
    """Get current Myanmar time (UTC+6:30)"""
    utc_time = datetime.utcnow()
    return utc_time + timedelta(hours=6, minutes=30)