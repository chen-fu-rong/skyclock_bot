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
phase_map_cache = {}
last_shard_refresh = None
cycle_version = 0
is_cache_loaded = False

def initialize_shard_cache():
    """Initialize and synchronize shard cache"""
    global phase_map_cache, is_cache_loaded
    
    if not is_cache_loaded:
        logger.info("Initializing shard cache...")
        
        # 1. First load from database
        if not load_shard_data_from_db():
            logger.warning("Failed to load from DB, saving default data...")
            # Save default data to DB
            save_shard_data_to_db(DEFAULT_PHASE_MAP)
            # Try loading from DB again
            if not load_shard_data_from_db():
                logger.error("Failed to load from DB after saving defaults. Using in-memory default.")
                # Fallback to in-memory default
                phase_map_cache = DEFAULT_PHASE_MAP.copy()
        
        # 2. Then refresh from GitHub to get latest data
        if not refresh_phase_map():
            logger.warning("Failed to refresh from GitHub. Using existing cache.")
        
        # 3. Ensure we have at least the default data
        if not phase_map_cache:
            logger.error("Cache is still empty! Loading default directly.")
            phase_map_cache = DEFAULT_PHASE_MAP.copy()
        
        logger.info(f"Shard cache initialized with {len(phase_map_cache)} entries")
        is_cache_loaded = True

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
                logger.error("PHASE_TO_SHARD not found in file")
                return False
        
        # Find the opening brace of the object
        start_idx = content.find('{', start_idx)
        if start_idx == -1:
            logger.error("Object start not found")
            return False
        
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
            logger.error("Unbalanced braces in object")
            return False
        
        ts_map = content[start_idx:current_idx]
        
        # Parse with regex
        json_map = {}
        pattern = re.compile(r'(\d+):\s*{\s*realm:\s*Realm\.(\w+),\s*area:\s*Area\.(\w+)(?:,\s*type:\s*ShardType\.(\w+))?', re.DOTALL)
        
        matches = pattern.findall(ts_map)
        if not matches:
            logger.error("No matches found in phase map")
            return False
            
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

# ... [Other functions unchanged] ...

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