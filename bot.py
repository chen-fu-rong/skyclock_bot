# bot.py - Enhanced Shard Prediction System (Complete)
import os
import pytz
import logging
import traceback
import psycopg2
import psutil
import requests
import re
from flask import Flask, request
import telebot
from apscheduler.schedulers.background import BackgroundScheduler
from datetime import datetime, timedelta, date
from psycopg2 import errors as psycopg2_errors

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Environment variables
API_TOKEN = os.getenv("BOT_TOKEN") or "YOUR_BOT_TOKEN"
WEBHOOK_URL = os.getenv("WEBHOOK_URL") or "https://skyclock-bot.onrender.com/webhook"
DB_URL = os.getenv("DATABASE_URL") or "postgresql://user:pass@host:port/db"
ADMIN_USER_ID = os.getenv("ADMIN_USER_ID") or "YOUR_ADMIN_USER_ID"
SHARD_API_URL = "https://sky-shards.pages.dev/data/shard_locations.json"
SHARD_MAP_URL = "https://raw.githubusercontent.com/PlutoyDev/sky-shards/production/src/data/shard.ts"

bot = telebot.TeleBot(API_TOKEN)
app = Flask(__name__)
scheduler = BackgroundScheduler()
scheduler.start()

# Track bot start time for uptime
start_time = datetime.now()

# Sky timezone
SKY_TZ = pytz.timezone('UTC')

# ====================== SHARD PREDICTION ENGINE ======================
SHARD_START_DATE = datetime(2022, 11, 14, tzinfo=pytz.UTC)
CYCLE_DAYS = 112
SHARD_TIMES_UTC = [2.25, 6.25, 10.25, 14.25, 18.25, 22.25]  # Hours

# COMPLETE PHASE MAPPING (112 phases)
DEFAULT_PHASE_MAP = {
    0: {"realm": "Prairie", "area": "Village", "type": "Black"},
    1: {"realm": "Prairie", "area": "Caves", "type": "Black"},
    2: {"realm": "Forest", "area": "BrokenBridge", "type": "Red"},
    3: {"realm": "Forest", "area": "ElevatedClearing", "type": "Black"},
    4: {"realm": "Valley", "area": "Village", "type": "Black"},
    5: {"realm": "Valley", "area": "IceRink", "type": "Red"},
    6: {"realm": "Wasteland", "area": "Battlefield", "type": "Red"},
    7: {"realm": "Wasteland", "area": "Graveyard", "type": "Red"},
    8: {"realm": "Vault", "area": "FirstFloor", "type": "Black"},
    9: {"realm": "Prairie", "area": "BirdNest", "type": "Black"},
    10: {"realm": "Prairie", "area": "ButterflyFields", "type": "Red"},
    11: {"realm": "Forest", "area": "Boneyard", "type": "Red"},
    12: {"realm": "Forest", "area": "ForestBrook", "type": "Black"},
    13: {"realm": "Valley", "area": "HermitValley", "type": "Red"},
    14: {"realm": "Valley", "area": "VillageOfDreams", "type": "Red"},
    15: {"realm": "Wasteland", "area": "ForgottenArk", "type": "Black"},
    16: {"realm": "Wasteland", "area": "CrabField", "type": "Black"},
    17: {"realm": "Vault", "area": "SecondFloor", "type": "Red"},
    18: {"realm": "Prairie", "area": "Sanctuary", "type": "Black"},
    19: {"realm": "Forest", "area": "Gloom", "type": "Black"},
    20: {"realm": "Forest", "area": "Treehouse", "type": "Red"},
    21: {"realm": "Valley", "area": "DreamVillage", "type": "Red"},
    22: {"realm": "Valley", "area": "ValleyArena", "type": "Black"},
    23: {"realm": "Wasteland", "area": "Battlefield", "type": "Black"},
    24: {"realm": "Wasteland", "area": "Graveyard", "type": "Red"},
    25: {"realm": "Vault", "area": "ThirdFloor", "type": "Red"},
    26: {"realm": "Vault", "area": "StarlightDesert", "type": "Black"},
    27: {"realm": "Prairie", "area": "Caves", "type": "Black"},
    28: {"realm": "Forest", "area": "ElevatedClearing", "type": "Red"},
    29: {"realm": "Valley", "area": "Village", "type": "Red"},
    30: {"realm": "Valley", "area": "IceRink", "type": "Black"},
    31: {"realm": "Wasteland", "area": "Battlefield", "type": "Black"},
    32: {"realm": "Wasteland", "area": "Graveyard", "type": "Red"},
    33: {"realm": "Vault", "area": "FirstFloor", "type": "Red"},
    34: {"realm": "Prairie", "area": "BirdNest", "type": "Black"},
    35: {"realm": "Prairie", "area": "ButterflyFields", "type": "Black"},
    36: {"realm": "Forest", "area": "Boneyard", "type": "Red"},
    37: {"realm": "Forest", "area": "ForestBrook", "type": "Red"},
    38: {"realm": "Valley", "area": "HermitValley", "type": "Black"},
    39: {"realm": "Valley", "area": "VillageOfDreams", "type": "Black"},
    40: {"realm": "Wasteland", "area": "ForgottenArk", "type": "Red"},
    41: {"realm": "Wasteland", "area": "CrabField", "type": "Red"},
    42: {"realm": "Vault", "area": "SecondFloor", "type": "Black"},
    43: {"realm": "Prairie", "area": "Sanctuary", "type": "Black"},
    44: {"realm": "Forest", "area": "Gloom", "type": "Red"},
    45: {"realm": "Forest", "area": "Treehouse", "type": "Red"},
    46: {"realm": "Valley", "area": "DreamVillage", "type": "Black"},
    47: {"realm": "Valley", "area": "ValleyArena", "type": "Black"},
    48: {"realm": "Wasteland", "area": "Battlefield", "type": "Red"},
    49: {"realm": "Wasteland", "area": "Graveyard", "type": "Red"},
    50: {"realm": "Vault", "area": "ThirdFloor", "type": "Black"},
    51: {"realm": "Vault", "area": "StarlightDescent", "type": "Black"},
    52: {"realm": "Prairie", "area": "Caves", "type": "Red"},
    53: {"realm": "Forest", "area": "ElevatedClearing", "type": "Red"},
    54: {"realm": "Vault", "area": "StarlightDescent", "type": "Red"},
    55: {"realm": "Wasteland", "area": "Graveyard", "type": "Red"},
    56: {"realm": "Prairie", "area": "ButterflyFields", "type": "Black"},
    57: {"realm": "Forest", "area": "ForestBrook", "type": "Black"},
    58: {"realm": "Valley", "area": "VillageOfDreams", "type": "Red"},
    59: {"realm": "Wasteland", "area": "ForgottenArk", "type": "Red"},
    60: {"realm": "Vault", "area": "Archives", "type": "Black"},
    61: {"realm": "Prairie", "area": "Sanctuary", "type": "Black"},
    62: {"realm": "Forest", "area": "HiddenForestBrokenBridge", "type": "Red"},
    63: {"realm": "Valley", "area": "ValleyIceRink", "type": "Red"},
    64: {"realm": "Wasteland", "area": "CrabField", "type": "Black"},
    65: {"realm": "Vault", "area": "FirstFloor", "type": "Black"},
    66: {"realm": "Prairie", "area": "BirdNest", "type": "Red"},
    67: {"realm": "Forest", "area": "Boneyard", "type": "Red"},
    68: {"realm": "Valley", "area": "HermitValley", "type": "Black"},
    69: {"realm": "Wasteland", "area": "Battlefield", "type": "Black"},
    70: {"realm": "Vault", "area": "SecondFloor", "type": "Red"},
    71: {"realm": "Prairie", "area": "Caves", "type": "Red"},
    72: {"realm": "Forest", "area": "ElevatedClearing", "type": "Black"},
    73: {"realm": "Valley", "area": "Village", "type": "Black"},
    74: {"realm": "Wasteland", "area": "Graveyard", "type": "Red"},
    75: {"realm": "Vault", "area": "ThirdFloor", "type": "Red"},
    76: {"realm": "Prairie", "area": "ButterflyFields", "type": "Black"},
    77: {"realm": "Forest", "area": "ForestBrook", "type": "Black"},
    78: {"realm": "Valley", "area": "IceRink", "type": "Red"},
    79: {"realm": "Wasteland", "area": "ForgottenArk", "type": "Red"},
    80: {"realm": "Vault", "area": "StarlightDescent", "type": "Black"},
    81: {"realm": "Prairie", "area": "Sanctuary", "type": "Black"},
    82: {"realm": "Forest", "area": "Treehouse", "type": "Red"},
    83: {"realm": "Valley", "area": "DreamVillage", "type": "Red"},
    84: {"realm": "Wasteland", "area": "CrabField", "type": "Black"},
    85: {"realm": "Vault", "area": "FirstFloor", "type": "Black"},
    86: {"realm": "Prairie", "area": "BirdNest", "type": "Red"},
    87: {"realm": "Forest", "area": "Boneyard", "type": "Red"},
    88: {"realm": "Valley", "area": "HermitValley", "type": "Black"},
    89: {"realm": "Wasteland", "area": "Battlefield", "type": "Black"},
    90: {"realm": "Vault", "area": "SecondFloor", "type": "Red"},
    91: {"realm": "Prairie", "area": "Caves", "type": "Red"},
    92: {"realm": "Forest", "area": "ElevatedClearing", "type": "Black"},
    93: {"realm": "Valley", "area": "Village", "type": "Black"},
    94: {"realm": "Wasteland", "area": "Graveyard", "type": "Red"},
    95: {"realm": "Vault", "area": "ThirdFloor", "type": "Red"},
    96: {"realm": "Prairie", "area": "ButterflyFields", "type": "Black"},
    97: {"realm": "Forest", "area": "ForestBrook", "type": "Black"},
    98: {"realm": "Valley", "area": "IceRink", "type": "Red"},
    99: {"realm": "Wasteland", "area": "ForgottenArk", "type": "Red"},
    100: {"realm": "Vault", "area": "Archives", "type": "Black"},
    101: {"realm": "Prairie", "area": "Sanctuary", "type": "Black"},
    102: {"realm": "Forest", "area": "HiddenForestBrokenBridge", "type": "Red"},
    103: {"realm": "Valley", "area": "ValleyIceRink", "type": "Red"},
    104: {"realm": "Wasteland", "area": "CrabField", "type": "Black"},
    105: {"realm": "Vault", "area": "FirstFloor", "type": "Black"},
    106: {"realm": "Prairie", "area": "BirdNest", "type": "Red"},
    107: {"realm": "Forest", "area": "Boneyard", "type": "Red"},
    108: {"realm": "Valley", "area": "HermitValley", "type": "Black"},
    109: {"realm": "None", "area": "RestDay", "type": "None"},
    110: {"realm": "None", "area": "RestDay", "type": "None"},
    111: {"realm": "None", "area": "RestDay", "type": "None"}
}

# Global state
phase_map_cache = DEFAULT_PHASE_MAP
last_shard_refresh = None
cycle_version = 0  # Tracks how many full cycles have passed

# ====================== SHARD VALIDATION & UPDATE ======================
def validate_against_official(start_date, end_date):
    """
    Validate our predictions against official data for a date range
    Returns: (is_valid, discrepancies)
    """
    try:
        # Fetch official data
        official_data = {}
        response = requests.get(SHARD_API_URL, timeout=15)
        if response.status_code == 200:
            for item in response.json():
                official_data[item["date"]] = item
        
        # Test date range
        current_date = start_date
        discrepancies = []
        
        while current_date <= end_date:
            date_str = current_date.strftime("%Y-%m-%d")
            official = official_data.get(date_str)
            
            if not official:
                current_date += timedelta(days=1)
                continue
                
            # Our prediction
            our_pred = get_shard_info(current_date)
            
            # Skip rest days
            if our_pred["is_rest_day"]:
                current_date += timedelta(days=1)
                continue
                
            # Compare
            mismatch = False
            details = []
            
            if our_pred["realm"] != official.get("realm", ""):
                mismatch = True
                details.append(f"Realm: {our_pred['realm']} vs {official.get('realm')}")
                
            if our_pred["area"] != official.get("area", ""):
                mismatch = True
                details.append(f"Area: {our_pred['area']} vs {official.get('area')}")
                
            if our_pred["type"] != official.get("type", ""):
                mismatch = True
                details.append(f"Type: {our_pred['type']} vs {official.get('type')}")
                
            if mismatch:
                discrepancies.append({
                    "date": date_str,
                    "details": details,
                    "our": our_pred,
                    "official": official
                })
            
            current_date += timedelta(days=1)
        
        return (len(discrepancies) == 0, discrepancies)
    
    except Exception as e:
        logger.error(f"Validation error: {str(e)}")
        return (False, [{"error": str(e)}])

def update_shard_data_with_validation():
    """Update shard data with comprehensive validation"""
    try:
        logger.info("Starting validated shard data update...")
        
        # Step 1: Fetch official data
        logger.info("Fetching official shard data...")
        response = requests.get(SHARD_API_URL, timeout=15)
        response.raise_for_status()
        official_data = response.json()
        
        if not official_data:
            raise ValueError("No data returned from official source")
        
        # Step 2: Determine validation range (next 30 days)
        today = datetime.now(pytz.UTC).date()
        validation_start = today
        validation_end = today + timedelta(days=30)
        
        # Step 3: Validate before processing
        logger.info(f"Validating predictions from {validation_start} to {validation_end}...")
        is_valid, discrepancies = validate_against_official(validation_start, validation_end)
        
        if not is_valid:
            error_msg = "❌ Validation failed! Found discrepancies:\n"
            for d in discrepancies[:5]:  # Show first 5 errors
                error_msg += f"{d['date']}:\n" + "\n".join(d['details']) + "\n\n"
            if len(discrepancies) > 5:
                error_msg += f"... and {len(discrepancies)-5} more\n"
            
            logger.error(error_msg)
            notify_admin(error_msg)
            return False
        
        # Step 4: Process and save data
        phase_data = {}
        for item in official_data:
            try:
                # Extract phase from date
                event_date = datetime.strptime(item["date"], "%Y-%m-%d").date()
                phase = calculate_phase(event_date)
                
                # Map to our structure
                phase_data[phase] = {
                    "realm": item["realm"],
                    "area": item["area"],
                    "type": item["type"],
                    "candles": 3.5 if item["type"] == "Red" else 2.5
                }
            except Exception as e:
                logger.error(f"Error processing item: {item} - {str(e)}")
        
        # Step 5: Save to DB
        if save_shard_data_to_db(phase_data):
            # Refresh cache
            load_shard_data_from_db()
            logger.info("Shard data updated successfully after validation")
            return True
    
    except Exception as e:
        logger.error(f"Update with validation failed: {str(e)}")
    
    return False

# ====================== ADMIN COMMANDS ======================
@bot.message_handler(func=lambda msg: msg.text == '🔄 Update Shard Data' and is_admin(msg.from_user.id))
def handle_update_shard_data(message):
    update_last_interaction(message.from_user.id)
    bot.send_message(message.chat.id, "🔍 Validating shard data before update...")
    
    if update_shard_data_with_validation():
        bot.send_message(message.chat.id, "✅ Shard data updated successfully!")
    else:
        bot.send_message(message.chat.id, "❌ Update failed! Check admin notifications")

@bot.message_handler(func=lambda msg: msg.text == '✅ Validate Shard Data' and is_admin(msg.from_user.id))
def handle_validate_shard_data(message):
    update_last_interaction(message.from_user.id)
    msg = bot.send_message(
        message.chat.id,
        "Enter validation date range (format: YYYY-MM-DD to YYYY-MM-DD) or press /cancel:"
    )
    bot.register_next_step_handler(msg, process_validation_range)

def process_validation_range(message):
    if message.text.strip().lower() == '/cancel':
        send_admin_menu(message.chat.id)
        return
        
    try:
        parts = message.text.split(" to ")
        start_date = datetime.strptime(parts[0].strip(), "%Y-%m-%d").date()
        end_date = datetime.strptime(parts[1].strip(), "%Y-%m-%d").date()
        
        if start_date > end_date:
            raise ValueError("Start date must be before end date")
            
        bot.send_message(
            message.chat.id,
            f"🔍 Validating shard data from {start_date} to {end_date}..."
        )
        
        is_valid, discrepancies = validate_against_official(start_date, end_date)
        
        if is_valid:
            bot.send_message(
                message.chat.id,
                f"✅ All predictions match official data for {start_date} to {end_date}!"
            )
        else:
            report = f"❌ Found {len(discrepancies)} discrepancies:\n\n"
            for i, d in enumerate(discrepancies[:10]):  # Show first 10
                report += f"{d['date']}:\n" + "\n".join(d['details']) + "\n\n"
            if len(discrepancies) > 10:
                report += f"... and {len(discrepancies)-10} more\n"
            
            # Send summary to user
            bot.send_message(
                message.chat.id,
                f"❌ Found {len(discrepancies)} discrepancies. Details sent to admin."
            )
            
            # Send full report to admin
            notify_admin(report)
            
    except Exception as e:
        bot.send_message(
            message.chat.id,
            f"❌ Validation failed: {str(e)}. Use format: YYYY-MM-DD to YYYY-MM-DD"
        )
    
    send_admin_menu(message.chat.id)

# ====================== SCHEDULED TASKS ======================
def setup_scheduled_tasks():
    """Setup recurring maintenance tasks"""
    # ... existing tasks ...
    
    # Weekly shard data update with validation
    scheduler.add_job(
        update_shard_data_with_validation,
        'cron',
        day_of_week='mon',
        hour=4,
        minute=0,
        name="weekly_validated_shard_update"
    )

# ====================== SHARD CALCULATION FUNCTIONS ======================
def calculate_phase(target_date):
    """Calculate shard phase for a given date"""
    if isinstance(target_date, datetime):
        target_date = target_date.date()
    days_diff = (target_date - SHARD_START_DATE.date()).days
    return days_diff % CYCLE_DAYS

def get_shard_info(target_date):
    """Get complete shard info for a date"""
    phase = calculate_phase(target_date)
    
    # Handle rest days
    if phase >= 109:
        return {
            "realm": "None",
            "area": "Rest Day",
            "type": "None",
            "candles": 0,
            "phase": phase,
            "is_rest_day": True
        }
    
    # Get info from cache
    info = phase_map_cache.get(phase, {})
    
    return {
        "realm": info.get("realm", "Unknown"),
        "area": info.get("area", "Unknown"),
        "type": info.get("type", "Unknown"),
        "candles": info.get("candles", 0),
        "phase": phase,
        "is_rest_day": False
    }
    
    # Get info from cache
    info = phase_map_cache.get(phase, {})
    
    # Calculate shard type if missing
    if "type" not in info:
        info["type"] = calculate_shard_type(phase)
    
    return {
        "realm": info.get("realm", "Unknown"),
        "area": info.get("area", "Unknown"),
        "type": info["type"],
        "phase": phase,
        "is_rest_day": False
    }

def calculate_shard_type(phase):
    """Fallback type calculation if not in map"""
    pattern = {
        0: "Black", 1: "Black", 2: "Red", 3: "Black", 4: "Black",
        5: "Red", 6: "Red", 7: "Red", 8: "Black", 9: "Black",
        10: "Red", 11: "Red", 12: "Black", 13: "Red", 14: "Red", 15: "Black"
    }
    return pattern.get(phase % 16, "Unknown")

# ====================== AUTO-UPDATE MECHANISMS ======================
def refresh_phase_map():
    """Fetch latest phase map from GitHub"""
    global phase_map_cache, cycle_version, last_shard_refresh
    
    try:
        logger.info("Fetching latest phase map from GitHub...")
        response = requests.get(SHARD_MAP_URL, timeout=10)
        response.raise_for_status()
        
        # Extract the phase map from TypeScript file
        content = response.text
        start_idx = content.find("export const PHASE_TO_SHARD: Record<number, ShardLocation> = {")
        end_idx = content.find("};", start_idx)
        
        if start_idx == -1 or end_idx == -1:
            raise ValueError("Phase map not found in file")
            
        ts_map = content[start_idx:end_idx+1]
        
        # Convert to JSON-friendly format
        json_map = {}
        for line in ts_map.splitlines():
            if ":" in line:
                phase_str = line.split(":")[0].strip()
                if phase_str.isdigit():
                    phase = int(phase_str)
                    # Extract realm and area
                    realm_match = re.search(r"realm:\s+Realm\.(\w+)", line)
                    area_match = re.search(r"area:\s+Area\.(\w+)", line)
                    type_match = re.search(r"type:\s+ShardType\.(\w+)", line)
                    
                    if realm_match and area_match:
                        json_map[phase] = {
                            "realm": realm_match.group(1),
                            "area": area_match.group(1),
                            "type": type_match.group(1) if type_match else "Unknown"
                        }
        
        if json_map:
            phase_map_cache = json_map
            last_shard_refresh = datetime.now()
            logger.info(f"Updated phase map with {len(json_map)} entries")
            
            # Check for cycle reset
            current_phase = calculate_phase(datetime.now(pytz.UTC))
            global_cycles = (datetime.now(pytz.UTC).date() - SHARD_START_DATE.date()).days // CYCLE_DAYS
            if global_cycles > cycle_version:
                cycle_version = global_cycles
                logger.warning(f"New shard cycle detected! Version: {cycle_version}")
                notify_admin(f"⚠️ New shard cycle detected! Now on version {cycle_version}")
            
            return True
    except Exception as e:
        logger.error(f"Error refreshing phase map: {str(e)}")
    
    return False

def validate_shard_predictions(days=7):
    """Compare predictions with official source"""
    try:
        logger.info(f"Validating shard predictions for {days} days...")
        today = datetime.now(pytz.UTC).date()
        discrepancies = []
        
        # Get official data
        official_data = {}
        response = requests.get(SHARD_API_URL, timeout=15)
        if response.status_code == 200:
            for item in response.json():
                official_data[item["date"]] = item
        
        # Check specified days
        for i in range(days):
            check_date = today + timedelta(days=i)
            date_str = check_date.strftime("%Y-%m-%d")
            
            # Our prediction
            our_pred = get_shard_info(check_date)
            
            # Official data
            official = official_data.get(date_str, {})
            
            # Compare
            if official:
                if (our_pred["realm"] != official.get("realm", "") or
                    our_pred["area"] != official.get("area", "") or
                    our_pred["type"] != official.get("type", "")):
                    discrepancies.append({
                        "date": date_str,
                        "our": our_pred,
                        "official": official
                    })
        
        if discrepancies:
            report = "🔴 Shard Prediction Discrepancies:\n\n"
            for d in discrepancies:
                report += (
                    f"📅 {d['date']}:\n"
                    f"  Our: {d['our']['realm']}/{d['our']['area']}/{d['our']['type']}\n"
                    f"  Official: {d['official'].get('realm', '?')}/{d['official'].get('area', '?')}/{d['official'].get('type', '?')}\n\n"
                )
            notify_admin(report)
            logger.warning(f"Found {len(discrepancies)} prediction discrepancies")
            return len(discrepancies)
            
        logger.info("All predictions match official data")
        return 0
    except Exception as e:
        logger.error(f"Validation failed: {str(e)}")
        return -1

# ====================== NOTIFICATION HELPERS ======================
def notify_admin(message):
    """Send important notifications to admin"""
    try:
        bot.send_message(ADMIN_USER_ID, message)
    except Exception as e:
        logger.error(f"Failed to notify admin: {str(e)}")

# ====================== SHARD INFO DISPLAY ======================
def send_shard_info(chat_id, user_id, target_date=None):
    user = get_user(user_id)
    if not user: 
        bot.send_message(chat_id, "Please set your timezone first with /start")
        return
        
    tz, fmt = user
    user_tz = pytz.timezone(tz)
    
    # Default to today if no date specified
    if not target_date:
        target_date = datetime.now(user_tz).date()
    
    # Get shard info
    shard_info = get_shard_info(target_date)
    
    # Format message
    if shard_info["is_rest_day"]:
        message = (
            f"💎 <b>Shard - {target_date.strftime('%b %d, %Y')}</b>\n\n"
            "🌿 <b>Rest Day</b>\n"
            "No shard eruptions today"
        )
    else:
        type_emoji = "🔴" if shard_info["type"] == "Red" else "⚫"
        message = (
            f"💎 <b>Shard - {target_date.strftime('%b %d, %Y')}</b>\n\n"
            f"<b>Realm:</b> {shard_info['realm']}\n"
            f"<b>Area:</b> {shard_info['area']}\n"
            f"<b>Type:</b> {type_emoji} {shard_info['type']}\n"
        )
    
    # Add eruption schedule
    message += "\n⏰ <b>Eruption Schedule (UTC):</b>\n"
    for hour in SHARD_TIMES_UTC:
        hours = int(hour)
        minutes = int((hour - hours) * 60)
        message += f"• {hours:02d}:{minutes:02d}\n"
    
    # Add next eruption in user's timezone
    next_eruption = get_next_eruption(user_tz)
    if next_eruption:
        user_time = format_time(next_eruption, fmt)
        time_diff = next_eruption - datetime.now(user_tz)
        hours, remainder = divmod(int(time_diff.total_seconds()), 3600)
        minutes = remainder // 60
        message += f"\n⏱ <b>Next Eruption:</b> {user_time} ({hours}h {minutes}m)"
    
    # Create navigation buttons
    keyboard = telebot.types.InlineKeyboardMarkup()
    prev_date = target_date - timedelta(days=1)
    next_date = target_date + timedelta(days=1)
    
    keyboard.row(
        telebot.types.InlineKeyboardButton("⬅️ Previous", callback_data=f"shard:{prev_date}"),
        telebot.types.InlineKeyboardButton("Next ➡️", callback_data=f"shard:{next_date}")
    )
    
    # Add today button if not viewing today
    today = datetime.now(user_tz).date()
    if target_date != today:
        keyboard.add(telebot.types.InlineKeyboardButton("⏩ Today", callback_data=f"shard:{today}"))
    
    try:
        bot.send_message(
            chat_id, 
            message, 
            parse_mode='HTML', 
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Error sending shard info: {str(e)}")
        bot.send_message(chat_id, "⚠️ Failed to load shard data")

def get_next_eruption(user_tz):
    """Calculate next eruption in user's timezone"""
    now = datetime.now(pytz.UTC)
    today = now.date()
    
    # Find next eruption UTC time
    for hour in SHARD_TIMES_UTC:
        hours = int(hour)
        minutes = int((hour - hours) * 60)
        eruption_utc = datetime(
            today.year, today.month, today.day,
            hours, minutes, 0, tzinfo=pytz.UTC
        )
        
        if eruption_utc > now:
            return eruption_utc.astimezone(user_tz)
    
    # If none today, use first tomorrow
    tomorrow = today + timedelta(days=1)
    hours = int(SHARD_TIMES_UTC[0])
    minutes = int((SHARD_TIMES_UTC[0] - hours) * 60)
    eruption_utc = datetime(
        tomorrow.year, tomorrow.month, tomorrow.day,
        hours, minutes, 0, tzinfo=pytz.UTC
    )
    
    return eruption_utc.astimezone(user_tz)

# ====================== SCHEDULED TASKS ======================
def setup_scheduled_tasks():
    """Setup recurring maintenance tasks"""
    # Daily validation at 00:05 UTC
    scheduler.add_job(
        lambda: validate_shard_predictions(7),
        'cron',
        hour=0,
        minute=5,
        name="daily_shard_validation"
    )
    
    # Weekly phase map refresh
    scheduler.add_job(
        refresh_phase_map,
        'cron',
        day_of_week='sun',
        hour=3,
        minute=0,
        name="weekly_phase_map_refresh"
    )
    
    # Monthly full validation
    scheduler.add_job(
        lambda: validate_shard_predictions(30),
        'cron',
        day=1,
        hour=1,
        minute=0,
        name="monthly_full_validation"
    )
    
    # Weekly shard data update
    scheduler.add_job(
        update_shard_data_from_official,
        'cron',
        day_of_week='mon',
        hour=4,
        minute=0,
        name="weekly_shard_data_update"
    )

    logger.info("Scheduled tasks registered")

# ====================== ADMIN COMMANDS ======================
@bot.message_handler(func=lambda msg: msg.text == '🔄 Refresh Shard Data' and is_admin(msg.from_user.id))
def handle_refresh_shard_data(message):
    update_last_interaction(message.from_user.id)
    if refresh_phase_map():
        bot.send_message(message.chat.id, "✅ Shard data refreshed successfully!")
    else:
        bot.send_message(message.chat.id, "⚠️ Failed to refresh shard data")

@bot.message_handler(func=lambda msg: msg.text == '✅ Validate Predictions' and is_admin(msg.from_user.id))
def handle_validate_predictions(message):
    update_last_interaction(message.from_user.id)
    days = 7  # Default validation period
    msg = bot.send_message(message.chat.id, f"Enter number of days to validate (1-30, default {days}):")
    bot.register_next_step_handler(msg, process_validation_request)

def process_validation_request(message):
    try:
        days = int(message.text.strip())
        if not 1 <= days <= 30:
            days = 7
    except ValueError:
        days = 7
    
    count = validate_shard_predictions(days)
    if count == 0:
        bot.send_message(message.chat.id, f"✅ All predictions match for {days} days!")
    elif count > 0:
        bot.send_message(message.chat.id, f"⚠️ Found {count} discrepancies! Check admin notifications")
    else:
        bot.send_message(message.chat.id, "❌ Validation failed")

@bot.message_handler(func=lambda msg: msg.text == '🔄 Update Shard Data' and is_admin(msg.from_user.id))
def handle_update_shard_data(message):
    update_last_interaction(message.from_user.id)
    bot.send_message(message.chat.id, "🔄 Updating shard data from official source...")
    
    if update_shard_data_from_official():
        bot.send_message(message.chat.id, "✅ Shard data updated successfully!")
    else:
        bot.send_message(message.chat.id, "❌ Failed to update shard data")

# ========================== DATABASE ===========================
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
            
            # Create reminders table if not exists with created_at column
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

            cur.execute("""
            CREATE TABLE IF NOT EXISTS shard_data (
                phase INT PRIMARY KEY,
                realm TEXT NOT NULL,
                area TEXT NOT NULL,
                type TEXT NOT NULL,
                candles REAL NOT NULL
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
            
            cur.execute("CREATE INDEX IF NOT EXISTS idx_shard_data_phase ON shard_data(phase)")
            conn.commit()

# ======================== UTILITIES ============================
def format_time(dt, fmt):
    return dt.strftime('%I:%M %p') if fmt == '12hr' else dt.strftime('%H:%M')

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
        logger.error(traceback.format_exc())
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

# ===================== ADMIN UTILITIES =========================
def is_admin(user_id):
    return str(user_id) == ADMIN_USER_ID

# ===================== NAVIGATION HELPERS ======================
def send_main_menu(chat_id, user_id=None):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('🕒 Sky Clock', '🕯 Wax Events')
    markup.row('💎 Shards', '⚙️ Settings')
    
    if user_id and is_admin(user_id):
        markup.row('👤 Admin Panel')
    
    bot.send_message(chat_id, "Main Menu:", reply_markup=markup)

def send_wax_menu(chat_id):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('🧓 Grandma', '🐢 Turtle', '🌋 Geyser')
    markup.row('🔙 Main Menu')
    bot.send_message(chat_id, "Wax Events:", reply_markup=markup)

def send_settings_menu(chat_id, current_format):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row(f'🕰 Change Time Format (Now: {current_format})')
    markup.row('🔙 Main Menu')
    bot.send_message(chat_id, "Settings:", reply_markup=markup)

def send_admin_menu(chat_id):
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('👥 User Stats', '📢 Broadcast')
    markup.row('⏰ Manage Reminders', '📊 System Status')
    markup.row('🔄 Update Shard Data', '✅ Validate Predictions')
    markup.row('🔄 Refresh Shard Data', '✅ Validate Predictions')
    markup.row('🔍 Find User')
    markup.row('🔙 Main Menu')
    bot.send_message(chat_id, "Admin Panel:", reply_markup=markup)

# ====================== SHARD DATABASE UTILITIES ======================
def load_shard_data_from_db():
    """Load all shard data from database into cache"""
    global phase_map_cache
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT phase, realm, area, type, candles FROM shard_data")
                phase_map_cache = {row[0]: {
                    "realm": row[1],
                    "area": row[2],
                    "type": row[3],
                    "candles": row[4]
                } for row in cur.fetchall()}
        logger.info(f"Loaded {len(phase_map_cache)} shard records from database")
        return True
    except Exception as e:
        logger.error(f"Error loading shard data from DB: {str(e)}")
        return False

def save_shard_data_to_db(data):
    """Save shard data to database (upsert)"""
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                for phase, info in data.items():
                    cur.execute("""
                        INSERT INTO shard_data (phase, realm, area, type, candles)
                        VALUES (%s, %s, %s, %s, %s)
                        ON CONFLICT (phase) DO UPDATE
                        SET realm = EXCLUDED.realm,
                            area = EXCLUDED.area,
                            type = EXCLUDED.type,
                            candles = EXCLUDED.candles
                    """, (phase, info["realm"], info["area"], info["type"], info["candles"]))
                conn.commit()
        logger.info(f"Saved {len(data)} shard records to database")
        return True
    except Exception as e:
        logger.error(f"Error saving shard data to DB: {str(e)}")
        return False

def update_shard_data_from_official():
    """Fetch official data and update database"""
    try:
        logger.info("Fetching official shard data...")
        response = requests.get(SHARD_API_URL, timeout=15)
        response.raise_for_status()
        official_data = response.json()
        
        # Transform to our format: {phase: {realm, area, type, candles}}
        phase_data = {}
        for item in official_data:
            try:
                # Extract phase from date
                event_date = datetime.strptime(item["date"], "%Y-%m-%d").date()
                phase = calculate_phase(event_date)
                
                # Map to our structure
                phase_data[phase] = {
                    "realm": item["realm"],
                    "area": item["area"],
                    "type": item["type"],
                    "candles": 3.5 if item["type"] == "Red" else 2.5
                }
            except Exception as e:
                logger.error(f"Error processing item: {item} - {str(e)}")
        
        # Save to DB
        if save_shard_data_to_db(phase_data):
            # Refresh cache
            load_shard_data_from_db()
            return True
    except Exception as e:
        logger.error(f"Error updating from official source: {str(e)}")
    return False

# ======================= GLOBAL HANDLERS =======================
@bot.message_handler(func=lambda msg: msg.text == '🔙 Main Menu')
def handle_back_to_main(message):
    update_last_interaction(message.from_user.id)
    send_main_menu(message.chat.id, message.from_user.id)

@bot.message_handler(func=lambda msg: msg.text == '🔙 Admin Panel')
def handle_back_to_admin(message):
    update_last_interaction(message.from_user.id)
    if is_admin(message.from_user.id):
        send_admin_menu(message.chat.id)

# ======================= START FLOW ============================
@bot.message_handler(commands=['start'])
def start(message):
    try:
        update_last_interaction(message.from_user.id)
        markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        markup.row('🇲🇲 Set to Myanmar Time')
        bot.send_message(
            message.chat.id,
            f"Hello {message.from_user.first_name}! 👋\nWelcome to Sky Clock Bot!\n\n"
            "Please type your timezone (e.g. Asia/Yangon), or choose an option:",
            reply_markup=markup
        )
        bot.register_next_step_handler(message, save_timezone)
    except Exception as e:
        logger.error(f"Error in /start: {str(e)}")
        bot.send_message(message.chat.id, "⚠️ Error in /start command")

def save_timezone(message):
    user_id = message.from_user.id
    chat_id = message.chat.id
    try:
        if message.text == '🇲🇲 Set to Myanmar Time':
            tz = 'Asia/Yangon'
        else:
            try:
                pytz.timezone(message.text)
                tz = message.text
            except pytz.UnknownTimeZoneError:
                bot.send_message(chat_id, "❌ Invalid timezone. Please try again:")
                return bot.register_next_step_handler(message, save_timezone)

        if set_timezone(user_id, chat_id, tz):
            bot.send_message(chat_id, f"✅ Timezone set to: {tz}")
            send_main_menu(chat_id, user_id)
        else:
            bot.send_message(chat_id, "⚠️ Failed to save timezone to database. Please try /start again.")
    except Exception as e:
        logger.error(f"Error saving timezone: {str(e)}")
        bot.send_message(chat_id, "⚠️ Unexpected error saving timezone. Please try /start again.")

# ===================== MAIN MENU HANDLERS ======================
@bot.message_handler(func=lambda msg: msg.text == '🕒 Sky Clock')
def sky_clock(message):
    update_last_interaction(message.from_user.id)
    user = get_user(message.from_user.id)
    if not user: 
        bot.send_message(message.chat.id, "Please set your timezone first with /start")
        return
        
    tz, fmt = user
    user_tz = pytz.timezone(tz)
    now = datetime.now()
    local = now.astimezone(user_tz)
    sky = now.astimezone(SKY_TZ)
    
    time_diff = local - sky
    hours, remainder = divmod(abs(time_diff.seconds), 3600)
    minutes = remainder // 60
    direction = "ahead" if time_diff.total_seconds() > 0 else "behind"
    
    text = (
        f"🌥 Sky Time: {format_time(sky, fmt)}\n"
        f"🌍 Your Time: {format_time(local, fmt)}\n"
        f"⏱ You are {hours}h {minutes}m {direction} Sky Time"
    )
    bot.send_message(message.chat.id, text)

@bot.message_handler(func=lambda msg: msg.text == '🕯 Wax Events')
def wax_menu(message):
    update_last_interaction(message.from_user.id)
    send_wax_menu(message.chat.id)

@bot.message_handler(func=lambda msg: msg.text == '⚙️ Settings')
def settings_menu(message):
    update_last_interaction(message.from_user.id)
    user = get_user(message.from_user.id)
    if not user: 
        bot.send_message(message.chat.id, "Please set your timezone first with /start")
        return
        
    _, fmt = user
    send_settings_menu(message.chat.id, fmt)

# ===================== SHARD HANDLERS =========================
@bot.callback_query_handler(func=lambda call: call.data.startswith('shard:'))
def handle_shard_callback(call):
    try:
        date_str = call.data.split(':')[1]
        target_date = date.fromisoformat(date_str)
        send_shard_info(call.message.chat.id, call.from_user.id, target_date)
        
        # Edit original message instead of sending new one
        try:
            bot.edit_message_reply_markup(
                call.message.chat.id,
                call.message.message_id,
                reply_markup=None
            )
        except:
            pass  # Fail silently if message can't be edited
    except Exception as e:
        logger.error(f"Error handling shard callback: {str(e)}")
        bot.answer_callback_query(call.id, "❌ Failed to load shard data")

@bot.message_handler(func=lambda msg: msg.text == '💎 Shards')
def shards_menu(message):
    update_last_interaction(message.from_user.id)
    send_shard_info(message.chat.id, message.from_user.id)

# ====================== WAX EVENT HANDLERS =====================
@bot.message_handler(func=lambda msg: msg.text in ['🧓 Grandma', '🐢 Turtle', '🌋 Geyser'])
def handle_event(message):
    update_last_interaction(message.from_user.id)
    mapping = {
        '🧓 Grandma': ('Grandma', 'every 2 hours at :05', 'even'),
        '🐢 Turtle': ('Turtle', 'every 2 hours at :20', 'even'),
        '🌋 Geyser': ('Geyser', 'every 2 hours at :35', 'odd')
    }
    
    event_name, event_schedule, hour_type = mapping[message.text]
    user = get_user(message.from_user.id)
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
    update_last_interaction(message.from_user.id)
    # Handle back navigation
    if message.text.strip() == '🔙 Wax Events':
        send_wax_menu(message.chat.id)
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
        send_wax_menu(message.chat.id)

def ask_reminder_minutes(message, event_type, selected_time):
    update_last_interaction(message.from_user.id)
    # Handle back navigation
    if message.text.strip() == '🔙 Wax Events':
        send_wax_menu(message.chat.id)
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
        send_wax_menu(message.chat.id)

import re

def save_reminder(message, event_type, selected_time, is_daily):
    update_last_interaction(message.from_user.id)
    if message.text.strip() == '🔙 Wax Events':
        send_wax_menu(message.chat.id)
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

        user = get_user(message.from_user.id)
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
        send_main_menu(message.chat.id, message.from_user.id)

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
        send_main_menu(message.chat.id, message.from_user.id)

# ==================== REMINDER SCHEDULING =====================
def schedule_reminder(user_id, reminder_id, event_type, event_time_utc, notify_before, is_daily):
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
    try:
        # Get user info
        user_info = get_user(user_id)
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
        # Attempt to notify admin
        try:
            bot.send_message(ADMIN_USER_ID, f"⚠️ Reminder failed: {reminder_id}\nError: {str(e)}")
        except:
            pass

# ====================== ADMIN PANEL ===========================
@bot.message_handler(func=lambda msg: msg.text == '👤 Admin Panel' and is_admin(msg.from_user.id))
def handle_admin_panel(message):
    update_last_interaction(message.from_user.id)
    send_admin_menu(message.chat.id)

# User Statistics
@bot.message_handler(func=lambda msg: msg.text == '👥 User Stats' and is_admin(msg.from_user.id))
def user_stats(message):
    try:
        update_last_interaction(message.from_user.id)
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

# Broadcast Messaging
@bot.message_handler(func=lambda msg: msg.text == '📢 Broadcast' and is_admin(msg.from_user.id))
def start_broadcast(message):
    update_last_interaction(message.from_user.id)
    markup = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row('🔊 Broadcast to All')
    markup.row('👤 Send to Specific User')
    markup.row('🔙 Admin Panel')
    bot.send_message(message.chat.id, "Choose broadcast type:", reply_markup=markup)

@bot.message_handler(func=lambda msg: msg.text == '🔊 Broadcast to All' and is_admin(msg.from_user.id))
def broadcast_to_all(message):
    update_last_interaction(message.from_user.id)
    msg = bot.send_message(message.chat.id, "Enter message to broadcast to ALL users (type /cancel to abort):")
    bot.register_next_step_handler(msg, process_broadcast_all)

@bot.message_handler(func=lambda msg: msg.text == '👤 Send to Specific User' and is_admin(msg.from_user.id))
def send_to_user(message):
    update_last_interaction(message.from_user.id)
    msg = bot.send_message(message.chat.id, "Enter target USER ID (type /cancel to abort):")
    bot.register_next_step_handler(msg, get_target_user)

def get_target_user(message):
    update_last_interaction(message.from_user.id)
    if message.text.strip().lower() == '/cancel':
        send_admin_menu(message.chat.id)
        return
        
    try:
        user_id = int(message.text.strip())
        # Store user ID in message object for next step
        message.target_user_id = user_id
        msg = bot.send_message(message.chat.id, f"Enter message for user {user_id}:")
        bot.register_next_step_handler(msg, process_user_message)
    except ValueError:
        bot.send_message(message.chat.id, "❌ Invalid user ID. Must be a number. Try again:")
        bot.register_next_step_handler(message, get_target_user)

def process_user_message(message):
    update_last_interaction(message.from_user.id)
    if message.text.strip().lower() == '/cancel':
        send_admin_menu(message.chat.id)
        return
        
    target_user_id = getattr(message, 'target_user_id', None)
    if not target_user_id:
        bot.send_message(message.chat.id, "❌ Error: User ID not found. Please start over.")
        return send_admin_menu(message.chat.id)
        
    try:
        # Get user's chat_id from database
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT chat_id FROM users WHERE user_id = %s", (target_user_id,))
                result = cur.fetchone()
                
                if result:
                    chat_id = result[0]
                    try:
                        bot.send_message(chat_id, f"📢 Admin Message:\n\n{message.text}")
                        bot.send_message(message.chat.id, f"✅ Message sent to user {target_user_id}")
                    except Exception as e:
                        logger.error(f"Failed to send to user {target_user_id}: {str(e)}")
                        bot.send_message(message.chat.id, f"❌ Failed to send to user {target_user_id}. They may have blocked the bot.")
                else:
                    bot.send_message(message.chat.id, f"❌ User {target_user_id} not found in database")
    except Exception as e:
        logger.error(f"Error sending to specific user: {str(e)}")
        bot.send_message(message.chat.id, "❌ Error sending message. Please try again.")
    
    send_admin_menu(message.chat.id)

def process_broadcast_all(message):
    update_last_interaction(message.from_user.id)
    if message.text.strip().lower() == '/cancel':
        send_admin_menu(message.chat.id)
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
    progress_msg = bot.send_message(message.chat.id, f"📤 Sending broadcast... 0/{total}")
    
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
                    message.chat.id,
                    progress_msg.message_id
                )
            except:
                pass  # Fail silently on edit errors
    
    bot.send_message(
        message.chat.id,
        f"📊 Broadcast complete!\n"
        f"✅ Success: {success}\n"
        f"❌ Failed: {failed}\n"
        f"📩 Total: {total}"
    )
    send_admin_menu(message.chat.id)

# Reminder Management
@bot.message_handler(func=lambda msg: msg.text == '⏰ Manage Reminders' and is_admin(msg.from_user.id))
def manage_reminders(message):
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
    bot.register_next_step_handler(msg, handle_reminder_action, reminders)

def handle_reminder_action(message, reminders):
    update_last_interaction(message.from_user.id)
    if message.text.strip().lower() == '/cancel':
        send_admin_menu(message.chat.id)
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
                
            bot.send_message(message.chat.id, "✅ Reminder deleted")
        else:
            bot.send_message(message.chat.id, "Invalid selection")
    except ValueError:
        bot.send_message(message.chat.id, "Please enter a valid number")
    
    send_admin_menu(message.chat.id)

# System Status
@bot.message_handler(func=lambda msg: msg.text == '📊 System Status' and is_admin(msg.from_user.id))
def system_status(message):
    update_last_interaction(message.from_user.id)
    # Uptime calculation
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
    shard_status = "✅ Loaded" if phase_map_cache else "❌ Not loaded"
    if last_shard_refresh:
        shard_status += f" (Last refresh: {last_shard_refresh.strftime('%Y-%m-%d %H:%M')})"
    
    text = (
        f"⏱ Uptime: {str(uptime).split('.')[0]}\n"
        f"🗄 Database: {db_status}\n"
        f"💾 Memory: {memory_usage}\n"
        f"❗️ Recent Errors: {error_count}\n"
        f"🤖 Active Jobs: {job_count}\n"
        f"💎 Shard Data: {shard_status}"
    )
    bot.send_message(message.chat.id, text)

# User Search
@bot.message_handler(func=lambda msg: msg.text == '🔍 Find User' and is_admin(msg.from_user.id))
def find_user(message):
    update_last_interaction(message.from_user.id)
    msg = bot.send_message(message.chat.id, "Enter username or user ID to search (type /cancel to abort):")
    bot.register_next_step_handler(msg, process_user_search)

def process_user_search(message):
    update_last_interaction(message.from_user.id)
    if message.text.strip().lower() == '/cancel':
        send_admin_menu(message.chat.id)
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
                    bot.send_message(message.chat.id, "❌ No users found")
                    return send_admin_menu(message.chat.id)
            
                response = "🔍 Search Results:\n\n"
                for i, user in enumerate(results, 1):
                    user_id, chat_id, tz = user
                    response += f"{i}. User ID: {user_id}\nChat ID: {chat_id}\nTimezone: {tz}\n\n"
            
                bot.send_message(message.chat.id, response)

                
    except Exception as e:
        logger.error(f"User search error: {str(e)}")
        bot.send_message(message.chat.id, "❌ Error during search")
    
    send_admin_menu(message.chat.id)

# ========================== WEBHOOK ============================
@app.route('/webhook', methods=['POST'])
def webhook():
    try:
        if request.headers.get('content-type') == 'application/json':
            json_data = request.get_json()
            update = telebot.types.Update.de_json(json_data)
            bot.process_new_updates([update])
            return 'OK', 200
        else:
            logger.warning("Invalid content-type for webhook")
            return 'Invalid content-type', 400
    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        return 'Error processing webhook', 500

@app.route('/')
def index():
    return 'Sky Clock Bot is running.'

# ========================== MAIN ===============================
if __name__ == '__main__':
    logger.info("Initializing database...")
    init_db()
    logger.info("Database initialized")

    # Load shard data from DB
    logger.info("Loading shard data from database...")
    if not load_shard_data_from_db():
        # First-time setup: load default data
        logger.info("Loading default shard data...")
        save_shard_data_to_db(DEFAULT_PHASE_MAP)
        load_shard_data_from_db()
    
    # Load shard data
    logger.info("Loading shard data...")
    refresh_phase_map()
    
    # Schedule tasks
    logger.info("Setting up scheduled tasks...")
    setup_scheduled_tasks()
    
    # Initial validation
    logger.info("Running initial validation...")
    validate_shard_predictions(7)
    
    # Schedule existing reminders
    logger.info("Scheduling existing reminders...")
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
    
    logger.info("Setting up webhook...")
    bot.remove_webhook()
    bot.set_webhook(url=WEBHOOK_URL)
    logger.info(f"Webhook set to: {WEBHOOK_URL}")
    
    logger.info("Starting Flask app...")
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 10000)))