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
        try:
            import psycopg2
            conn = psycopg2.connect(os.getenv('DATABASE_URL'), sslmode='require')
            logger.info("Connected to PostgreSQL on Render")
            return conn
        except ImportError:
            logger.warning("psycopg2 not found, trying pg8000")
            try:
                import pg8000
                conn = pg8000.connect(os.getenv('DATABASE_URL'))
                logger.info("Connected using pg8000")
                return conn
            except Exception as e:
                logger.error(f"PostgreSQL connection failed: {str(e)}")
                raise
    else:
        import sqlite3
        conn = sqlite3.connect('skyclock.db')
        logger.info("Connected to SQLite for local development")
        return conn

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

def get_myanmar_time():
    """Get current Myanmar time (UTC+6:30)"""
    utc_time = datetime.utcnow()
    return utc_time + timedelta(hours=6, minutes=30)