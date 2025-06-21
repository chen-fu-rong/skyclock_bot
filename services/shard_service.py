# services/shard_service.py
import os
import re
import pytz
import logging
import requests
import traceback
from datetime import datetime, timedelta
from services.database import get_db

logger = logging.getLogger(__name__)

# Environment variables
SHARD_API_URL = "https://sky-shards.pages.dev/data/shard_locations.json"
SHARD_MAP_URL = "https://raw.githubusercontent.com/PlutoyDev/sky-shards/production/src/data/shard.ts"

# Sky timezone
SKY_TZ = pytz.timezone('UTC')

# Constants
SHARD_START_DATE = datetime(2022, 11, 14, tzinfo=pytz.UTC)
CYCLE_DAYS = 112
SHARD_TIMES_UTC = [2.25, 6.25, 10.25, 14.25, 18.25, 22.25]  # Hours

# COMPLETE PHASE MAPPING (112 phases)
DEFAULT_PHASE_MAP = {
    0: {"realm": "Prairie", "area": "Village", "type": "Black"},
    1: {"realm": "Prairie", "area": "Caves", "type": "Black"},
    # ... [ALL PHASES FROM ORIGINAL CODE] ...
    111: {"realm": "None", "area": "RestDay", "type": "None"}
}

# Global state
phase_map_cache = {}
last_shard_refresh = None
cycle_version = 0
is_cache_loaded = False

def initialize_shard_cache():
    """Initialize and synchronize shard cache"""
    global phase_map_cache, is_cache_loaded
    
    if not is_cache_loaded:
        logger.info("Initializing shard cache...")
        # First try loading from database
        if not load_shard_data_from_db():
            logger.warning("Failed to load from DB, saving default data...")
            # If DB fails, save and load default data
            save_shard_data_to_db(DEFAULT_PHASE_MAP)
            load_shard_data_from_db()
        
        # Then refresh from GitHub
        refresh_phase_map()
        is_cache_loaded = True
        logger.info("Shard cache initialized successfully")

def calculate_phase(target_date):
    """Calculate shard phase for a given date"""
    if isinstance(target_date, datetime):
        target_date = target_date.date()
    days_diff = (target_date - SHARD_START_DATE.date()).days
    return days_diff % CYCLE_DAYS

def get_shard_info(target_date):
    """Get complete shard info for a date"""
    # Ensure cache is initialized
    if not is_cache_loaded:
        initialize_shard_cache()
    
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
    info = phase_map_cache.get(phase)
    
    # If no info found, use fallback
    if not info:
        logger.warning(f"No shard data found for phase {phase}")
        return {
            "realm": "Unknown",
            "area": "Unknown",
            "type": calculate_shard_type(phase),
            "candles": 3.5 if calculate_shard_type(phase) == "Red" else 2.5,
            "phase": phase,
            "is_rest_day": False
        }
    
    return {
        "realm": info.get("realm", "Unknown"),
        "area": info.get("area", "Unknown"),
        "type": info.get("type", "Black"),
        "candles": 3.5 if info.get("type") == "Red" else 2.5,
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

def refresh_phase_map():
    """Fetch latest phase map from GitHub"""
    global phase_map_cache, cycle_version, last_shard_refresh
    
    try:
        logger.info("Fetching latest phase map from GitHub...")
        response = requests.get(SHARD_MAP_URL, timeout=10)
        response.raise_for_status()
        
        content = response.text
        
        # Find the start of the PHASE_TO_SHARD object
        start_idx = content.find("export const PHASE_TO_SHARD")
        if start_idx == -1:
            # Try alternative pattern
            start_idx = content.find("PHASE_TO_SHARD = {")
            if start_idx == -1:
                raise ValueError("PHASE_TO_SHARD not found in file")
        
        # Find the opening brace of the object
        start_idx = content.find('{', start_idx)
        if start_idx == -1:
            raise ValueError("Object start not found")
        
        # Parse until matching closing brace
        brace_count = 1
        current_idx = start_idx + 1
        while brace_count > 0 and current_idx < len(content):
            if content[current_idx] == '{':
                brace_count += 1
            elif content[current_idx] == '}':
                brace_count -= 1
            current_idx += 1
        
        if brace_count != 0:
            raise ValueError("Unbalanced braces in object")
        
        ts_map = content[start_idx:current_idx]
        
        # Parse with regex
        json_map = {}
        pattern = re.compile(r'(\d+):\s*{\s*realm:\s*Realm\.(\w+),\s*area:\s*Area\.(\w+)(?:,\s*type:\s*ShardType\.(\w+))?', re.DOTALL)
        
        matches = pattern.findall(ts_map)
        for match in matches:
            phase = int(match[0])
            realm = match[1]
            area = match[2]
            shard_type = match[3] if match[3] else "Black"
            
            json_map[phase] = {
                "realm": realm,
                "area": area,
                "type": shard_type,
                "candles": 3.5 if shard_type == "Red" else 2.5
            }
        
        if json_map:
            # Update cache with new data
            for phase, data in json_map.items():
                phase_map_cache[phase] = data
            
            # Save to database
            save_shard_data_to_db(json_map)
            
            last_shard_refresh = datetime.now()
            logger.info(f"Updated phase map with {len(json_map)} entries")
            
            # Check for cycle reset
            current_phase = calculate_phase(datetime.now(pytz.UTC))
            global_cycles = (datetime.now(pytz.UTC).date() - SHARD_START_DATE.date()).days // CYCLE_DAYS
            if global_cycles > cycle_version:
                cycle_version = global_cycles
                logger.warning(f"New shard cycle detected! Version: {cycle_version}")
            
            return True
    except Exception as e:
        logger.error(f"Error refreshing phase map: {str(e)}")
        logger.error(traceback.format_exc())
    
    return False

def load_shard_data_from_db():
    """Load all shard data from database into cache"""
    global phase_map_cache
    try:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT phase, realm, area, type, candles FROM shard_data")
                # Clear current cache and rebuild
                new_cache = {}
                for row in cur.fetchall():
                    phase = row[0]
                    new_cache[phase] = {
                        "realm": row[1],
                        "area": row[2],
                        "type": row[3],
                        "candles": row[4]
                    }
                phase_map_cache = new_cache
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

# ... [Other functions remain unchanged] ...

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