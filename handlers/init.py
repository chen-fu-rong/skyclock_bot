# handlers/__init__.py
from .admin import register_admin_handlers
from .core import register_core_handlers
from .reminders import register_reminder_handlers
from .shards import register_shard_handlers
from .wax_events import register_wax_handlers
import os

def register_handlers(bot):
    admin_user_id = os.getenv("ADMIN_USER_ID") or "YOUR_ADMIN_USER_ID"
    
    register_core_handlers(bot, admin_user_id)
    register_shard_handlers(bot, admin_user_id)
    register_wax_handlers(bot)
    register_reminder_handlers(bot)
    register_admin_handlers(bot, admin_user_id)