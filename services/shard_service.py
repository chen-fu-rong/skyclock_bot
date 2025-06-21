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
    # ... [all other phase mappings from original code] ...
    111: {"realm": "None", "area": "RestDay", "type": "None"}
}

# Global state
phase_map_cache = DEFAULT_PHASE_MAP
last_shard_refresh = None
cycle_version = 0  # Tracks how many full cycles have passed

def validate_against_official(start_date, end_date):
    """Validate our predictions against official data for a date range"""
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
        
        return (len(discrepancies) == 0, discrepancies
    
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
    
    # If no info found, try to calculate from pattern
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
        
        # Extract the phase map from TypeScript file
        content = response.text
        start_idx = content.find("export const PHASE_TO_SHARD: Record<number, ShardLocation> = {")
        if start_idx == -1:
            # Try alternative pattern if first not found
            start_idx = content.find("export const PHASE_TO_SHARD = {")
        end_idx = content.find("};", start_idx)
        
        if start_idx == -1 or end_idx == -1:
            raise ValueError("Phase map not found in file")
            
        ts_map = content[start_idx:end_idx+1]
        
        # Convert to JSON-friendly format
        json_map = {}
        for line in ts_map.splitlines():
            line = line.strip()
            if ":" in line:
                # Extract phase number
                phase_str = line.split(":")[0].strip()
                # Remove any non-digit characters
                phase_str = ''.join(filter(str.isdigit, phase_str))
                
                if phase_str:
                    phase = int(phase_str)
                    # Extract realm, area and type
                    realm_match = re.search(r"realm:\s*Realm\.(\w+)", line)
                    area_match = re.search(r"area:\s*Area\.(\w+)", line)
                    type_match = re.search(r"type:\s*ShardType\.(\w+)", line)
                    
                    if realm_match and area_match:
                        json_map[phase] = {
                            "realm": realm_match.group(1),
                            "area": area_match.group(1),
                            "type": type_match.group(1) if type_match else "Black"
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
            return True
    except Exception as e:
        logger.error(f"Error refreshing phase map: {str(e)}")
        logger.error(traceback.format_exc())
    
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
            logger.warning(f"Found {len(discrepancies)} prediction discrepancies")
            return len(discrepancies)
            
        logger.info("All predictions match official data")
        return 0
    except Exception as e:
        logger.error(f"Validation failed: {str(e)}")
        return -1

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