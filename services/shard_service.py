# services/shard_service.py
import pytz
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Sky timezone
SKY_TZ = pytz.timezone('UTC')

# Constants
SHARD_START_DATE = datetime(2022, 11, 14, tzinfo=pytz.UTC)
CYCLE_DAYS = 112
SHARD_TIMES_UTC = [2.25, 6.25, 10.25, 14.25, 18.25, 22.25]  # Hours

# COMPLETE PHASE MAPPING (112 phases)
PHASE_MAP = {
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
    
    # Get info from phase map
    info = PHASE_MAP.get(phase)
    
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