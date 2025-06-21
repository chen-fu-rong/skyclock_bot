# handlers/reminders.py
import telebot
from datetime import datetime, timedelta
import pytz
import re
from services.database import get_db
from services.scheduler import scheduler
from utils.formatters import format_time
import logging

logger = logging.getLogger(__name__)

def schedule_reminder(user_id, reminder_id, event_type, event_time_utc, notify_before, is_daily):
    """Schedule a reminder job"""
    try:
        # Calculate when to send the notification (UTC)
        notify_time = event_time_utc - timedelta(minutes=notify_before)
        current_time = datetime.now(pytz.utc)
        
        # If notification time is in the past, adjust for daily or skip
        if notify_time < current_time:
            if is_daily:
                notify_time += timedelta(days=1)
                event_time_utc += timedelta(days=1)
                # Update database with new time
                with get_db() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            UPDATE reminders 
                            SET event_time_utc = %s 
                            WHERE id = %s
                        """, (event_time_utc, reminder_id))
                        conn.commit()
            else:
                logger.warning(f"Reminder {reminder_id} is in the past, skipping")
                return
        
        # Schedule the job
        scheduler.add_job(
            send_reminder_notification,
            'date',
            run_date=notify_time,
            args=[user_id, reminder_id, event_type, event_time_utc, notify_before, is_daily],
            id=f'rem_{reminder_id}'
        )
        
        logger.info(f"Scheduled reminder: ID={reminder_id}, RunAt={notify_time}, "
                    f"EventTime={event_time_utc}, NotifyBefore={notify_before} mins")
        
    except Exception as e:
        logger.error(f"Error scheduling reminder {reminder_id}: {str(e)}")

def send_reminder_notification(user_id, reminder_id, event_type, event_time_utc, notify_before, is_daily):
    """Send reminder notification to user"""
    from bot import bot
    try:
        # Get user info
        user_info = get_db().get_user(user_id)
        if not user_info:
            logger.warning(f"User {user_id} not found for reminder {reminder_id}")
            return
            
        tz, fmt = user_info
        user_tz = pytz.timezone(tz)
        
        # Convert event time to user's timezone
        event_time_user = event_time_utc.astimezone(user_tz)
        event_time_str = format_time(event_time_user, fmt)
        
        # Prepare message
        message = (
            f"⏰ Reminder: {event_type} is starting in {notify_before} minutes!\n"
            f"🕑 Event Time: {event_time_str}"
        )
        
        # Send message
        bot.send_message(user_id, message)
        logger.info(f"Sent reminder for {event_type} to user {user_id}")
        
        # Reschedule if daily
        if is_daily:
            new_event_time = event_time_utc + timedelta(days=1)
            schedule_reminder(user_id, reminder_id, event_type, 
                             new_event_time, notify_before, True)
            
            # Update database
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE reminders 
                        SET event_time_utc = %s 
                        WHERE id = %s
                    """, (new_event_time, reminder_id))
                    conn.commit()
                    
    except Exception as e:
        logger.error(f"Error sending reminder {reminder_id}: {str(e)}")

def schedule_existing_reminders():
    """Schedule all existing reminders from database"""
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, user_id, event_type, event_time_utc, notify_before, is_daily
                    FROM reminders
                    WHERE event_time_utc > NOW() - INTERVAL '1 day'
                """)
                reminders = cur.fetchall()
                for rem in reminders:
                    schedule_reminder(rem[1], rem[0], rem[2], rem[3], rem[4], rem[5])
                logger.info(f"Scheduled {len(reminders)} existing reminders")
    except Exception as e:
        logger.error(f"Error scheduling existing reminders: {str(e)}")

def register_reminder_handlers(bot):
    @bot.message_handler(func=lambda msg: msg.text in ['🧓 Grandma', '🐢 Turtle', '🌋 Geyser'])
    def handle_event(message):
        from services.database import update_last_interaction
        update_last_interaction(message.from_user.id)
        mapping = {
            '🧓 Grandma': ('Grandma', 'every 2 hours at :05', 'even'),
            '🐢 Turtle': ('Turtle', 'every 2 hours at :20', 'even'),
            '🌋 Geyser': ('Geyser', 'every 2 hours at :35', 'odd')
        }
        
        event_name, event_schedule, hour_type = mapping[message.text]
        user = get_db().get_user(message.from_user.id)
        if not user: 
            bot.send_message(message.chat.id, "Please set your timezone first with /start")
            return
            
        tz, fmt = user
        user_tz = pytz.timezone(tz)
        now_user = datetime.now(user_tz)

        # Generate all event times for today in user's timezone
        today_user = now_user.replace(hour=0, minute=0, second=0, microsecond=0)
        event_times = []
        for hour in range(24):
            if hour_type == 'even' and hour % 2 == 0:
                event_times.append(today_user.replace(hour=hour, minute=int(event_schedule.split(':')[1])))
            elif hour_type == 'odd' and hour % 2 == 1:
                event_times.append(today_user.replace(hour=hour, minute=int(event_schedule.split(':')[1])))
        
        # Calculate next occurrences for each event time
        next_occurrences = []
        for et in event_times:
            if et < now_user:
                # If event already passed today, use tomorrow's time
                next_occurrences.append(et + timedelta(days=1))
            else:
                next_occurrences.append(et)
        
        # Sort by next occurrence
        sorted_indices = sorted(range(len(next_occurrences)), key=lambda i: next_occurrences[i])
        sorted_event_times = [event_times[i] for i in sorted_indices]
        next_event = next_occurrences[sorted_indices[0]]
        
        # Format the next event time for display
        next_event_formatted = format_time(next_event, fmt)
        
        # Calculate time until next event
        diff = next_event - now_user
        hrs, mins = divmod(diff.seconds // 60, 60)
        
        # Create event description
        description = {
            'Grandma': "🕯 Grandma offers wax at Hidden Forest every 2 hours",
            'Turtle': "🐢 Dark Turtle appears at Sanctuary Islands every 2 hours",
            'Geyser': "🌋 Geyser erupts at Sanctuary Islands every 2 hours"
        }[event_name]
        
        text = (
            f"{description}\n\n"
            f"⏰ Next Event: {next_event_formatted}\n"
            f"⏳ Time Remaining: {hrs}h {mins}m\n\n"
            "Choose a time to set a reminder:"
        )

        # Send buttons for event times sorted by next occurrence
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
        
        # Highlight next event with a special emoji
        next_event_time_str = format_time(sorted_event_times[0], fmt)
        markup.row(f"⏩ {next_event_time_str} (Next)")
        
        # Add other times in pairs
        for i in range(1, len(sorted_event_times), 2):
            row = []
            # Add current time
            time_str = format_time(sorted_event_times[i], fmt)
            row.append(time_str)
            
            # Add next time if exists
            if i+1 < len(sorted_event_times):
                time_str2 = format_time(sorted_event_times[i+1], fmt)
                row.append(time_str2)
            
            markup.row(*row)
        
        markup.row('🔙 Wax Events')
        
        bot.send_message(message.chat.id, text, reply_markup=markup)
        bot.register_next_step_handler(message, ask_reminder_frequency, event_name)
    
    def ask_reminder_frequency(message, event_type):
        from services.database import update_last_interaction
        update_last_interaction(message.from_user.id)
        # Handle back navigation
        if message.text.strip() == '🔙 Wax Events':
            send_wax_menu(bot, message.chat.id)
            return
            
        try:
            # Clean up selected time (remove emojis and indicators)
            selected_time = message.text.replace("⏩", "").replace("(Next)", "").strip()
            
            # Ask for reminder frequency
            markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.row('⏰ One Time Reminder')
            markup.row('🔄 Daily Reminder')
            markup.row('🔙 Wax Events')
            
            bot.send_message(
                message.chat.id,
                f"⏰ You selected: {selected_time}\n\n"
                "Choose reminder frequency:",
                reply_markup=markup
            )
            # Pass selected_time to next handler
            bot.register_next_step_handler(message, ask_reminder_minutes, event_type, selected_time)
        except Exception as e:
            logger.error(f"Error in frequency selection: {str(e)}")
            bot.send_message(message.chat.id, "⚠️ Invalid selection. Please try again.")
            send_wax_menu(bot, message.chat.id)
    
    def ask_reminder_minutes(message, event_type, selected_time):
        from services.database import update_last_interaction
        update_last_interaction(message.from_user.id)
        # Handle back navigation
        if message.text.strip() == '🔙 Wax Events':
            send_wax_menu(bot, message.chat.id)
            return
            
        try:
            # Get frequency choice
            if message.text == '⏰ One Time Reminder':
                is_daily = False
            elif message.text == '🔄 Daily Reminder':
                is_daily = True
            else:
                bot.send_message(message.chat.id, "Please select a valid option")
                return
                
            # Create keyboard with common minute options
            markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.row('5', '10', '15')
            markup.row('20', '30', '45')
            markup.row('60', '🔙 Wax Events')
            
            bot.send_message(
                message.chat.id, 
                f"⏰ Event: {event_type}\n"
                f"🕑 Time: {selected_time}\n"
                f"🔄 Frequency: {'Daily' if is_daily else 'One-time'}\n\n"
                "How many minutes before should I remind you?\n"
                "Choose an option or type a number (1-60):",
                reply_markup=markup
            )
            # Pass all needed parameters to next handler
            bot.register_next_step_handler(message, save_reminder, event_type, selected_time, is_daily)
        except Exception as e:
            logger.error(f"Error in minutes selection: {str(e)}")
            bot.send_message(message.chat.id, "⚠️ Failed to set reminder. Please try again.")
            send_wax_menu(bot, message.chat.id)
    
    def save_reminder(message, event_type, selected_time, is_daily):
        from services.database import update_last_interaction
        update_last_interaction(message.from_user.id)
        if message.text.strip() == '🔙 Wax Events':
            send_wax_menu(bot, message.chat.id)
            return

        try:
            import re
            # Extract numbers from input text (handles button clicks and typed numbers)
            input_text = message.text.strip()
            match = re.search(r'\d+', input_text)
            if not match:
                raise ValueError("No numbers found in input")

            mins = int(match.group())
            if mins < 1 or mins > 60:
                raise ValueError("Minutes must be between 1-60")

            user = get_db().get_user(message.from_user.id)
            if not user:
                bot.send_message(message.chat.id, "Please set your timezone first with /start")
                return

            tz, fmt = user
            user_tz = pytz.timezone(tz)
            now = datetime.now(user_tz)

            # Clean time string from button text (remove emojis, parentheses, etc.)
            clean_time = selected_time.strip()
            clean_time = re.sub(r'[^\d:apmAPM\s]', '', clean_time)
            clean_time = re.sub(r'\s+', '', clean_time)

            # Parse time based on user's format
            try:
                if fmt == '12hr':
                    try:
                        time_obj = datetime.strptime(clean_time, '%I:%M%p')
                    except:
                        time_obj = datetime.strptime(clean_time, '%I:%M')
                else:
                    time_obj = datetime.strptime(clean_time, '%H:%M')
            except ValueError:
                try:
                    time_obj = datetime.strptime(clean_time, '%H:%M')
                except:
                    raise ValueError(f"Couldn't parse time: {clean_time}")

            # Create datetime in user's timezone
            event_time_user = now.replace(
                hour=time_obj.hour,
                minute=time_obj.minute,
                second=0,
                microsecond=0
            )

            if event_time_user < now:
                event_time_user += timedelta(days=1)

            event_time_utc = event_time_user.astimezone(pytz.utc)
            trigger_time = event_time_utc - timedelta(minutes=mins)

            logger.info(f"[DEBUG] Trying to insert reminder: "
                        f"user_id={message.from_user.id}, "
                        f"event_type={event_type}, "
                        f"event_time_utc={event_time_utc}, "
                        f"trigger_time={trigger_time}, "
                        f"notify_before={mins}, "
                        f"is_daily={is_daily}")

            with get_db() as conn:
                with conn.cursor() as cur:
                    chat_id = message.chat.id

                    cur.execute("""
                    INSERT INTO reminders (
                        user_id, chat_id, event_type, event_time_utc, trigger_time,
                        notify_before, is_daily, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                    RETURNING id
                    """, (
                        message.from_user.id, chat_id, event_type, event_time_utc,
                        trigger_time, mins, is_daily
                        ))

                    reminder_id = cur.fetchone()[0]
                    conn.commit()

            schedule_reminder(message.from_user.id, reminder_id, event_type,
                              event_time_utc, mins, is_daily)

            frequency = "daily" if is_daily else "one time"
            emoji = "🔄" if is_daily else "⏰"

            bot.send_message(
                message.chat.id,
                f"✅ Reminder set!\n\n"
                f"⏰ Event: {event_type}\n"
                f"🕑 Time: {selected_time}\n"
                f"⏱ Remind: {mins} minutes before\n"
                f"{emoji} Frequency: {frequency}"
            )
            from handlers.core import send_main_menu
            send_main_menu(bot, message.chat.id, message.from_user.id)

        except ValueError as ve:
            logger.warning(f"User input error: {str(ve)}")
            bot.send_message(
                message.chat.id,
                f"❌ Invalid input: {str(ve)}. Please choose minutes from buttons or type 1-60."
            )
            markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
            markup.row('5', '10', '15')
            markup.row('20', '30', '45')
            markup.row('60', '🔙 Wax Events')
            bot.send_message(
                message.chat.id,
                "Please choose how many minutes before the event to remind you:",
                reply_markup=markup
            )
            bot.register_next_step_handler(message, save_reminder, event_type, selected_time, is_daily)

        except Exception as e:
            logger.error("Reminder save failed", exc_info=True)
            bot.send_message(
                message.chat.id,
                "⚠️ Failed to set reminder. Please try again later."
            )
            from handlers.core import send_main_menu
            send_main_menu(bot, message.chat.id, message.from_user.id)