from telegram import InlineKeyboardButton, InlineKeyboardMarkup
import pytz
from datetime import datetime, time
from utils import get_next_reset_utc, convert_to_user_tz, format_timedelta
from time_input import get_time_input_keyboard

def build_menu_content(nav_manager, db, user_id, state, context_data=None):
    """Generate content and buttons for each menu state"""
    user_tz = db.get_timezone(user_id) or 'UTC'
    
    if state == "main_menu":
        content = "✨ *Sky: CotL Assistant* ✨\nChoose an option:"
        buttons = [
            [InlineKeyboardButton("⏰ Reset Timer", callback_data="menu_reset")],
            [InlineKeyboardButton("📅 Events Hub", callback_data="menu_events")],
            [InlineKeyboardButton("⏰ My Reminders", callback_data="menu_reminders")],
            [InlineKeyboardButton("🌤️ Current Info", callback_data="menu_current")]
        ]
        nav_manager.push_state(user_id, "main_menu")
        
    elif state == "reset_menu":
        reset_utc = get_next_reset_utc()
        time_left = reset_utc - datetime.utcnow().replace(tzinfo=pytz.utc)
        user_reset_time = convert_to_user_tz(reset_utc, user_tz)
        
        content = (
            f"⏰ *Reset Timer*\n\n"
            f"Next reset in: `{format_timedelta(time_left)}`\n"
            f"• Your time: `{user_reset_time.strftime('%H:%M')}`\n"
            f"• PST: `00:00`\n\n"
            f"Notifications: {'🔔 ON' if 'reset' in db.get_subscriptions(user_id) else '🔕 OFF'}"
        )
        
        buttons = [
            [InlineKeyboardButton("🔔 Toggle Alerts", callback_data="toggle_reset")],
            [InlineKeyboardButton("⏳ 30-min Warning", callback_data="set_30min_alert")]
        ]
        nav_manager.push_state(user_id, "reset_menu")
        
    elif state == "events_menu":
        subscriptions = db.get_subscriptions(user_id)
        event_types = ['reset', 'traveling_spirit', 'shards', 'season_end']
        
        content = "📅 *Events Hub*\n\n🔔 *Your Subscriptions:*"
        buttons = []
        for event in event_types:
            icon = "✅" if event in subscriptions else "⚪"
            buttons.append([
                InlineKeyboardButton(
                    f"{icon} {event.replace('_', ' ').title()}", 
                    callback_data=f"toggle_{event}"
                )
            ])
        nav_manager.push_state(user_id, "events_menu")
    
    elif state == "reminders_menu":
        reminders = db.get_user_reminders(user_id)
        reminders_text = ""
        if reminders:
            for i, (id, trigger_time, message, recurring, event_type) in enumerate(reminders, 1):
                user_time = convert_to_user_tz(trigger_time, user_tz)
                recurring_icon = "🔄 " if recurring else ""
                reminders_text += f"{i}. {recurring_icon}`{user_time.strftime('%H:%M')}` - {message[:20]}{'...' if len(message)>20 else ''}\n"
        else:
            reminders_text = "No active reminders\n"
        
        content = (
            f"⏰ *Your Reminders*\n\n"
            f"{reminders_text}\n"
            f"Total: {len(reminders)}/10"
        )
        buttons = [
            [InlineKeyboardButton("➕ Create New", callback_data="create_reminder")],
            [InlineKeyboardButton("📋 Quick Templates", callback_data="reminder_templates")]
        ]
        # Add edit buttons for each reminder
        if reminders:
            for i, (id, *_) in enumerate(reminders, 1):
                buttons.append([InlineKeyboardButton(f"✏️ Edit #{i}", callback_data=f"edit_{id}")])
        nav_manager.push_state(user_id, "reminders_menu")
    
    elif state == "current_menu":
        # Mock data for current info
        reset_utc = get_next_reset_utc()
        time_left = reset_utc - datetime.utcnow().replace(tzinfo=pytz.utc)
        
        content = (
            f"🌤️ *CURRENT GAME STATUS*\n\n"
            f"⏱️ Reset in: `{format_timedelta(time_left)}`\n\n"
            f"🕯️ *Today's Quests:*\n"
            f"- Relive Pleaful Parent\n"
            f"- Meditate at Temple\n\n"
            f"💥 *Shard Forecast:*\n"
            f"- Red @ Prairie (14:00-16:00)\n"
            f"- Black @ Wasteland (19:30-21:30)\n\n"
            f"👻 *Next Traveling Spirit:*\n"
            f"- Arrives in `2d 4h`\n"
        )
        buttons = [
            [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_current")]
        ]
        nav_manager.push_state(user_id, "current_menu")
    
    elif state.startswith("edit_reminder_"):
        reminder_id = int(state.split("_", 2)[2])
        reminders = db.get_user_reminders(user_id)
        reminder = next((r for r in reminders if r[0] == reminder_id), None)
        if not reminder:
            # Fallback to reminders menu
            return build_menu_content(nav_manager, db, user_id, "reminders_menu")
        
        id, trigger_time, message, recurring, event_type = reminder
        user_time = convert_to_user_tz(trigger_time, user_tz)
        
        content = (
            f"✏️ *Editing Reminder*\n\n"
            f"⏰ Time: `{user_time.strftime('%H:%M')}`\n"
            f"📝 Message: `{message}`\n"
            f"🔄 Recurring: `{'Yes' if recurring else 'No'}`\n\n"
            f"Choose action:"
        )
        buttons = [
            [InlineKeyboardButton("🕒 Change Time", callback_data=f"edit_time_{id}")],
            [InlineKeyboardButton("📝 Edit Message", callback_data=f"edit_msg_{id}")],
            [InlineKeyboardButton(f"🔄 Toggle Recurring", callback_data=f"toggle_rec_{id}")],
            [InlineKeyboardButton("🗑️ Delete", callback_data=f"confirm_del_{id}")]
        ]
    
    # Add back button if not in main menu
    if state != "main_menu":
        buttons.append([InlineKeyboardButton("🔙 Back", callback_data="nav_back")])
    
    # Always show home button
    buttons.append([InlineKeyboardButton("🏠 Main Menu", callback_data="menu_main")])
    
    return {
        "text": content,
        "reply_markup": InlineKeyboardMarkup(buttons),
        "parse_mode": "Markdown"
    }

def build_reminder_templates_menu():
    content = "⏰ *Quick Reminder Templates*\n\nChoose a preset:"
    buttons = [
        [InlineKeyboardButton("🕯️ Daily Candle Run", callback_data="template_candle_run")],
        [InlineKeyboardButton("🌋 Geyser ( :00/:50 )", callback_data="template_geyser")],
        [InlineKeyboardButton("💀 Grandma Dinner", callback_data="template_grandma")],
        [InlineKeyboardButton("✨ Daily Quests Reset", callback_data="template_reset")],
        [InlineKeyboardButton("🔙 Back", callback_data="nav_reminders")]
    ]
    return {
        "text": content,
        "reply_markup": InlineKeyboardMarkup(buttons),
        "parse_mode": "Markdown"
    }