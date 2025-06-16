import os
import logging
import psycopg2
from psycopg2 import sql
from contextlib import contextmanager

# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

@contextmanager
def get_db_connection():
    conn = None
    try:
        conn = psycopg2.connect(os.getenv('DATABASE_URL'), sslmode='require')
        yield conn
    except Exception as e:
        logger.error(f"Database connection error: {str(e)}")
        raise
    finally:
        if conn:
            conn.close()

@contextmanager
def get_db_cursor():
    with get_db_connection() as conn:
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except:
            conn.rollback()
            raise
        finally:
            cursor.close()

def init_db():
    try:
        with get_db_cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
        logger.info("✅ Database initialized")
    except Exception as e:
        logger.error(f"Database initialization error: {str(e)}")

def get_user(user_id):
    try:
        with get_db_cursor() as cursor:
            cursor.execute("SELECT * FROM users WHERE user_id = %s", (user_id,))
            return cursor.fetchone()
    except Exception as e:
        logger.error(f"Error getting user: {str(e)}")
        return None

def update_user(user_id, username):
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