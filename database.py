import psycopg2
from contextlib import contextmanager

class Database:
    def __init__(self, db_url):
        self.db_url = db_url

    @contextmanager
    def get_cursor(self):
        conn = psycopg2.connect(self.db_url)
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            cursor.close()
            conn.close()
    
    def add_user(self, user_id, username, timezone):
        with self.get_cursor() as cur:
            cur.execute(
                "INSERT INTO users (user_id, username, timezone) "
                "VALUES (%s, %s, %s) "
                "ON CONFLICT (user_id) DO UPDATE SET timezone = EXCLUDED.timezone",
                (user_id, username, timezone)
            )
    
    def create_reminder(self, user_id, event_type, trigger_time, message, recurring=False):
        # Implementation
        pass