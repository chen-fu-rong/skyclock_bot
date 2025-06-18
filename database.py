import psycopg2
import os
from contextlib import contextmanager
from datetime import datetime, timedelta

class Database:
    def __init__(self, db_url):
        self.db_url = db_url

    @contextmanager
    def get_cursor(self):
        conn = psycopg2.connect(self.db_url)
        conn.autocommit = False
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
    
    def ensure_user_exists(self, user_id, username):
        with self.get_cursor() as cur:
            cur.execute(
                "INSERT INTO users (user_id, username) "
                "VALUES (%s, %s) "
                "ON CONFLICT (user_id) DO UPDATE SET username = EXCLUDED.username",
                (user_id, username)
            )
    
    def get_timezone(self, user_id):
        with self.get_cursor() as cur:
            cur.execute("SELECT timezone FROM users WHERE user_id = %s", (user_id,))
            result = cur.fetchone()
            return result[0] if result else 'UTC'
    
    def set_timezone(self, user_id, timezone):
        with self.get_cursor() as cur:
            cur.execute(
                "UPDATE users SET timezone = %s WHERE user_id = %s",
                (timezone, user_id)
            )
    
    def get_user_nav_stack(self, user_id):
        with self.get_cursor() as cur:
            cur.execute("SELECT nav_stack FROM users WHERE user_id = %s", (user_id,))
            result = cur.fetchone()
            return result[0] if result else []
    
    def update_user_nav_stack(self, user_id, stack):
        with self.get_cursor() as cur:
            cur.execute(
                "UPDATE users SET nav_stack = %s WHERE user_id = %s",
                (stack, user_id)
            )
    
    def get_subscriptions(self, user_id):
        with self.get_cursor() as cur:
            cur.execute("SELECT event_type FROM subscriptions WHERE user_id = %s", (user_id,))
            return {row[0] for row in cur.fetchall()}
    
    def toggle_subscription(self, user_id, event_type):
        with self.get_cursor() as cur:
            try:
                cur.execute(
                    "INSERT INTO subscriptions (user_id, event_type) VALUES (%s, %s)",
                    (user_id, event_type)
                )
                return True
            except psycopg2.IntegrityError:  # Already exists
                cur.execute(
                    "DELETE FROM subscriptions WHERE user_id = %s AND event_type = %s",
                    (user_id, event_type)
                )
                return False
    
    def create_reminder(self, user_id, trigger_time, message, recurring=False, event_type='CUSTOM'):
        with self.get_cursor() as cur:
            cur.execute(
                "INSERT INTO reminders (user_id, trigger_time, message, is_recurring, event_type) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (user_id, trigger_time, message, recurring, event_type)
            )
            return cur.fetchone()[0]
    
    def get_user_reminders(self, user_id):
        with self.get_cursor() as cur:
            cur.execute(
                "SELECT id, trigger_time, message, is_recurring, event_type "
                "FROM reminders WHERE user_id = %s ORDER BY trigger_time",
                (user_id,)
            )
            return cur.fetchall()
    
    def delete_reminder(self, reminder_id, user_id):
        with self.get_cursor() as cur:
            cur.execute(
                "DELETE FROM reminders WHERE id = %s AND user_id = %s",
                (reminder_id, user_id)
            )
            return cur.rowcount > 0
    
    def toggle_reminder_recurring(self, reminder_id, user_id):
        with self.get_cursor() as cur:
            cur.execute(
                "UPDATE reminders SET is_recurring = NOT is_recurring "
                "WHERE id = %s AND user_id = %s RETURNING is_recurring",
                (reminder_id, user_id)
            )
            result = cur.fetchone()
            return result[0] if result else None
    
    def update_reminder_time(self, reminder_id, user_id, new_time):
        with self.get_cursor() as cur:
            cur.execute(
                "UPDATE reminders SET trigger_time = %s "
                "WHERE id = %s AND user_id = %s",
                (new_time, reminder_id, user_id)
            )
    
    def update_reminder_message(self, reminder_id, user_id, new_message):
        with self.get_cursor() as cur:
            cur.execute(
                "UPDATE reminders SET message = %s "
                "WHERE id = %s AND user_id = %s",
                (new_message, reminder_id, user_id)
            )
    
    def get_due_reminders(self, now, window_minutes=1):
        with self.get_cursor() as cur:
            cur.execute(
                "SELECT id, user_id, message, is_recurring "
                "FROM reminders "
                "WHERE trigger_time <= %s AND trigger_time > %s",
                (now + timedelta(minutes=window_minutes), now)
            )
            return cur.fetchall()