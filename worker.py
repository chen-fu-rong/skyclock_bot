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

# [Keep all other existing functions exactly the same]
# init_db(), get_user(), update_user(), get_myanmar_time() remain unchanged