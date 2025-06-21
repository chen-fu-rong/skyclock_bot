# handlers/admin.py
import telebot
import psutil
from services.database import get_db
from services import shard_service
from utils.formatters import format_time
import logging
import os

logger = logging.getLogger(__name__)

def send_admin_menu(bot, chat_id):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('👥 User Stats', '📢 Broadcast')
    markup.row('⏰ Manage Reminders', '📊 System Status')
    markup.row('🔄 Update Shard Data', '✅ Validate Predictions')
    markup.row('🔄 Refresh Shard Data', '✅ Validate Shard Data')
    markup.row('🔍 Find User')
    markup.row('🔙 Main Menu')
    bot.send_message(chat_id, "Admin Panel:", reply_markup=markup)

def register_admin_handlers(bot, admin_user_id):
    def is_admin(user_id):
        return str(user_id) == admin_user_id

    @bot.message_handler(func=lambda msg: msg.text == '👤 Admin Panel' and is_admin(msg.from_user.id))
    def handle_admin_panel(message):
        from services.database import update_last_interaction
        update_last_interaction(message.from_user.id)
        send_admin_menu(bot, message.chat.id)

    @bot.message_handler(func=lambda msg: msg.text == '👥 User Stats' and is_admin(msg.from_user.id))
    def user_stats(message):
        from services.database import update_last_interaction
        update_last_interaction(message.from_user.id)
        try:
            with get_db() as conn:
                with conn.cursor() as cur:
                    # Total users
                    cur.execute("SELECT COUNT(*) FROM users")
                    total_users = cur.fetchone()[0]
                    
                    # Active users (last 7 days)
                    cur.execute("""
                        SELECT COUNT(*) 
                        FROM users 
                        WHERE last_interaction > NOW() - INTERVAL '7 days'
                    """)
                    active_users = cur.fetchone()[0]
                    
                    # Users with reminders
                    cur.execute("SELECT COUNT(DISTINCT user_id) FROM reminders")
                    users_with_reminders = cur.fetchone()[0]
        
            text = (
                f"👤 Total Users: {total_users}\n"
                f"🚀 Active Users (7 days): {active_users}\n"
                f"⏰ Users with Reminders: {users_with_reminders}"
            )
            bot.send_message(message.chat.id, text)
        except Exception as e:
            logger.error(f"Error in user_stats: {str(e)}")
            error_msg = f"❌ Error generating stats: {str(e)}"
            if "column \"last_interaction\" does not exist" in str(e):
                error_msg += "\n\n⚠️ Database needs migration! Please restart the bot."
            bot.send_message(message.chat.id, error_msg)

    @bot.message_handler(func=lambda msg: msg.text == '📢 Broadcast' and is_admin(msg.from_user.id))
    def start_broadcast(message):
        from services.database import update_last_interaction
        update_last_interaction(message.from_user.id)
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        markup.row('🔊 Broadcast to All')
        markup.row('👤 Send to Specific User')
        markup.row('🔙 Admin Panel')
        bot.send_message(message.chat.id, "Choose broadcast type:", reply_markup=markup)

    @bot.message_handler(func=lambda msg: msg.text == '🔊 Broadcast to All' and is_admin(msg.from_user.id))
    def broadcast_to_all(message):
        from services.database import update_last_interaction
        update_last_interaction(message.from_user.id)
        msg = bot.send_message(message.chat.id, "Enter message to broadcast to ALL users (type /cancel to abort):")
        bot.register_next_step_handler(msg, process_broadcast_all, message.chat.id)
    
    def process_broadcast_all(message, chat_id):
        if message.text.strip().lower() == '/cancel':
            send_admin_menu(bot, chat_id)
            return
            
        broadcast_text = message.text
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT chat_id FROM users")
                chat_ids = [row[0] for row in cur.fetchall()]
        
        success = 0
        failed = 0
        total = len(chat_ids)
        
        # Send with progress updates
        progress_msg = bot.send_message(chat_id, f"📤 Sending broadcast... 0/{total}")
        
        for i, chat_id in enumerate(chat_ids):
            try:
                bot.send_message(chat_id, f"📢 Admin Broadcast:\n\n{broadcast_text}")
                success += 1
            except Exception as e:
                logger.error(f"Broadcast failed for {chat_id}: {str(e)}")
                failed += 1
                
            # Update progress every 10 messages or last message
            if (i + 1) % 10 == 0 or (i + 1) == total:
                try:
                    bot.edit_message_text(
                        f"📤 Sending broadcast... {i+1}/{total}",
                        chat_id,
                        progress_msg.message_id
                    )
                except:
                    pass  # Fail silently on edit errors
        
        bot.send_message(
            chat_id,
            f"📊 Broadcast complete!\n"
            f"✅ Success: {success}\n"
            f"❌ Failed: {failed}\n"
            f"📩 Total: {total}"
        )
        send_admin_menu(bot, chat_id)

    @bot.message_handler(func=lambda msg: msg.text == '⏰ Manage Reminders' and is_admin(msg.from_user.id))
    def manage_reminders(message):
        from services.database import update_last_interaction
        update_last_interaction(message.from_user.id)
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT r.id, u.user_id, r.event_type, r.event_time_utc, r.notify_before
                    FROM reminders r
                    JOIN users u ON r.user_id = u.user_id
                    WHERE r.event_time_utc > NOW()
                    ORDER BY r.event_time_utc
                    LIMIT 50
                """)
                reminders = cur.fetchall()
        
        if not reminders:
            bot.send_message(message.chat.id, "No active reminders found")
            return
        
        text = "⏰ Active Reminders:\n\n"
        for i, rem in enumerate(reminders, 1):
            text += f"{i}. {rem[2]} @ {rem[3].strftime('%Y-%m-%d %H:%M')} UTC (User: {rem[1]})\n"
        
        text += "\nReply with reminder number to delete or /cancel"
        msg = bot.send_message(message.chat.id, text)
        bot.register_next_step_handler(msg, handle_reminder_action, reminders, message.chat.id)
    
    def handle_reminder_action(message, reminders, chat_id):
        from services.database import update_last_interaction
        update_last_interaction(message.from_user.id)
        if message.text.strip().lower() == '/cancel':
            send_admin_menu(bot, chat_id)
            return
        
        try:
            index = int(message.text) - 1
            if 0 <= index < len(reminders):
                rem_id = reminders[index][0]
                with get_db() as conn:
                    with conn.cursor() as cur:
                        cur.execute("DELETE FROM reminders WHERE id = %s", (rem_id,))
                        conn.commit()
                        
                # Also remove from scheduler if exists
                try:
                    scheduler.remove_job(f'rem_{rem_id}')
                    logger.info(f"Removed job for reminder {rem_id}")
                except:
                    pass
                    
                bot.send_message(chat_id, "✅ Reminder deleted")
            else:
                bot.send_message(chat_id, "Invalid selection")
        except ValueError:
            bot.send_message(chat_id, "Please enter a valid number")
        
        send_admin_menu(bot, chat_id)

    @bot.message_handler(func=lambda msg: msg.text == '📊 System Status' and is_admin(msg.from_user.id))
    def system_status(message):
        from services.database import update_last_interaction
        update_last_interaction(message.from_user.id)
        # Uptime calculation
        from main import start_time
        uptime = datetime.now() - start_time
        
        # Database status
        db_status = "✅ Connected"
        try:
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
        except Exception as e:
            db_status = f"❌ Error: {str(e)}"
        
        # Recent errors
        error_count = 0
        try:
            with open('bot.log', 'r') as f:
                for line in f:
                    if 'ERROR' in line:
                        error_count += 1
        except Exception as e:
            error_count = f"Error reading log: {str(e)}"
        
        # Memory usage
        memory = psutil.virtual_memory()
        memory_usage = f"{memory.used / (1024**3):.1f}GB / {memory.total / (1024**3):.1f}GB ({memory.percent}%)"
        
        # Active jobs
        try:
            job_count = len(scheduler.get_jobs())
        except:
            job_count = "N/A"
        
        # Shard cache status
        shard_status = "✅ Loaded" if shard_service.phase_map_cache else "❌ Not loaded"
        if shard_service.last_shard_refresh:
            shard_status += f" (Last refresh: {shard_service.last_shard_refresh.strftime('%Y-%m-%d %H:%M')})"
        
        text = (
            f"⏱ Uptime: {str(uptime).split('.')[0]}\n"
            f"🗄 Database: {db_status}\n"
            f"💾 Memory: {memory_usage}\n"
            f"❗️ Recent Errors: {error_count}\n"
            f"🤖 Active Jobs: {job_count}\n"
            f"💎 Shard Data: {shard_status}"
        )
        bot.send_message(message.chat.id, text)

    @bot.message_handler(func=lambda msg: msg.text == '🔍 Find User' and is_admin(msg.from_user.id))
    def find_user(message):
        from services.database import update_last_interaction
        update_last_interaction(message.from_user.id)
        msg = bot.send_message(message.chat.id, "Enter username or user ID to search (type /cancel to abort):")
        bot.register_next_step_handler(msg, process_user_search, message.chat.id)
    
    def process_user_search(message, chat_id):
        if message.text.strip().lower() == '/cancel':
            send_admin_menu(bot, chat_id)
            return
            
        search_term = message.text.strip()
        
        try:
            with get_db() as conn:
                with conn.cursor() as cur:
                    # Try searching by user ID
                    if search_term.isdigit():
                        cur.execute(
                            "SELECT user_id, chat_id, timezone FROM users WHERE user_id = %s",
                            (int(search_term),)
                        )
                        results = cur.fetchall()
                    # Search by timezone
                    else:
                        cur.execute(
                            "SELECT user_id, chat_id, timezone FROM users WHERE timezone ILIKE %s",
                            (f'%{search_term}%',)
                        )
                        results = cur.fetchall()
                
                    if not results:
                        bot.send_message(chat_id, "❌ No users found")
                        return send_admin_menu(bot, chat_id)
                
                    response = "🔍 Search Results:\n\n"
                    for i, user in enumerate(results, 1):
                        user_id, chat_id, tz = user
                        response += f"{i}. User ID: {user_id}\nChat ID: {chat_id}\nTimezone: {tz}\n\n"
                
                    bot.send_message(chat_id, response)
        except Exception as e:
            logger.error(f"User search error: {str(e)}")
            bot.send_message(chat_id, "❌ Error during search")
        
        send_admin_menu(bot, chat_id)

    def handle_refresh_shard_data(message):
        from services.database import update_last_interaction
        update_last_interaction(message.from_user.id)
        if shard_service.refresh_phase_map():
            bot.send_message(message.chat.id, "✅ Shard data refreshed successfully!")
        else:
            bot.send_message(message.chat.id, "⚠️ Failed to refresh shard data")

    def handle_validate_predictions(message):
        from services.database import update_last_interaction
        update_last_interaction(message.from_user.id)
        days = 7  # Default validation period
        msg = bot.send_message(message.chat.id, f"Enter number of days to validate (1-30, default {days}):")
        bot.register_next_step_handler(msg, process_validation_request, message.chat.id)
    
    def process_validation_request(message, chat_id):
        try:
            days = int(message.text.strip())
            if not 1 <= days <= 30:
                days = 7
        except ValueError:
            days = 7
        
        count = shard_service.validate_shard_predictions(days)
        if count == 0:
            bot.send_message(chat_id, f"✅ All predictions match for {days} days!")
        elif count > 0:
            bot.send_message(chat_id, f"⚠️ Found {count} discrepancies! Check admin notifications")
        else:
            bot.send_message(chat_id, "❌ Validation failed")