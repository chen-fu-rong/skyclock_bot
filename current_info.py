def build_current_info_menu(db):
    """Generate real-time game status"""
    # Get next reset
    reset_utc = get_next_reset_utc()
    reset_in = reset_utc - datetime.utcnow().replace(tzinfo=pytz.utc)
    
    # Get shard schedule (mock data)
    shards = [
        {"type": "Red", "location": "Prairie", "start": "14:00", "end": "16:00"},
        {"type": "Black", "location": "Wasteland", "start": "19:30", "end": "21:30"}
    ]
    
    # Get next spirit (mock data)
    spirit_arrival = reset_utc + timedelta(days=3, hours=8)
    
    content = (
        f"🌤️ *CURRENT GAME STATUS*\n\n"
        f"⏱️ Reset in: `{format_timedelta(reset_in)}`\n\n"
        f"🕯️ *Today's Quests:*\n"
        f"- Relive Pleaful Parent\n"
        f"- Meditate at Temple\n\n"
        f"💥 *Shard Forecast:*\n" +
        "\n".join([f"- {s['type']} @ {s['location']} ({s['start']}-{s['end']})" for s in shards]) + "\n\n"
        f"👻 *Next Traveling Spirit:*\n"
        f"- Arrives in `{format_timedelta(spirit_arrival - datetime.utcnow().replace(tzinfo=pytz.utc))}`\n"
        f"- [View History]"
    )
    
    buttons = [
        [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_current")],
        [InlineKeyboardButton("🔙 Back", callback_data="nav_back")]
    ]
    
    return {
        "text": content,
        "reply_markup": InlineKeyboardMarkup(buttons),
        "parse_mode": "Markdown"
    }