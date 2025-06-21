# services/database.py
import os
import psycopg2
import logging
import pytz

logger = logging.getLogger(__name__)
DB_URL = os.getenv("DATABASE_URL") or "postgresql://user:pass@host:port/db"

def get_db():
    try:
        conn = psycopg2.connect(DB_URL, sslmode='require')
        return conn
    except Exception as e:
        logger.error(f"Database connection failed: {str(e)}")
        raise

def init_db():
    with get_db() as conn:
        with conn.cursor() as cur:
            # Create users table if not exists
            cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                chat_id BIGINT NOT NULL,
                timezone TEXT NOT NULL,
                time_format TEXT DEFAULT '12hr',
                last_interaction TIMESTAMP DEFAULT NOW()
            );
            """)
            
            # Create reminders table if not exists
            cur.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id SERIAL PRIMARY KEY,
                user_id BIGINT REFERENCES users(user_id),
                event_type TEXT,
                event_time_utc TIMESTAMP,
                notify_before INT,
                is_daily BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT NOW()
            );
            """)
            
            # Add any missing columns
            try:
                cur.execute("""
                ALTER TABLE reminders 
                ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW();
                """)
                logger.info("Ensured created_at column exists in reminders")
            except Exception as e:
                logger.error(f"Error ensuring created_at column: {str(e)}")
            
            try:
                cur.execute("""
                ALTER TABLE reminders 
                ADD COLUMN IF NOT EXISTS is_daily BOOLEAN DEFAULT FALSE;
                """)
            except:
                pass  # Already exists
            
            conn.commit()

def get_user(user_id):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT timezone, time_format FROM users WHERE user_id = %s", (user_id,))
            return cur.fetchone()

def set_timezone(user_id, chat_id, tz):
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO users (user_id, chat_id, timezone, last_interaction) 
                    VALUES (%s, %s, %s, NOW())
                    ON CONFLICT (user_id) DO UPDATE 
                    SET chat_id = EXCLUDED.chat_id, timezone = EXCLUDED.timezone, last_interaction = NOW();
                """, (user_id, chat_id, tz))
                conn.commit()
        logger.info(f"Timezone set for user {user_id}: {tz}")
        return True
    except Exception as e:
        logger.error(f"Failed to set timezone for user {user_id}: {str(e)}")
        return False

def set_time_format(user_id, fmt):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE users 
                SET time_format = %s, last_interaction = NOW() 
                WHERE user_id = %s
            """, (fmt, user_id))
            conn.commit()

def update_last_interaction(user_id):
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE users 
                    SET last_interaction = NOW() 
                    WHERE user_id = %s
                """, (user_id,))
                conn.commit()
        return True
    except Exception as e:
        logger.error(f"Error updating last interaction for {user_id}: {str(e)}")
        return False
    
# services/database.py (add this function)
def get_db_connection():
    """Get a database connection with autocommit off"""
    try:
        conn = psycopg2.connect(DB_URL, sslmode='require')
        conn.autocommit = False
        return conn
    except Exception as e:
        logger.error(f"Database connection failed: {str(e)}")
        raise