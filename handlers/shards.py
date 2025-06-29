# handlers/shards.py
def register_shard_handlers(bot, admin_user_id):
    @bot.message_handler(func=lambda msg: msg.text == '💎 Shards')
    def shards_menu(message):
        from services.database import update_last_interaction
        update_last_interaction(message.from_user.id)
        
        # Show only coming soon message
        bot.send_message(
            message.chat.id,
            "🔮 Shard predictions are coming soon!\n\n"
            "We're working hard to bring you accurate shard eruption predictions. "
            "This feature will show:\n"
            "• Daily shard locations\n"
            "• Eruption schedules\n"
            "• Reward types\n\n"
            "Stay tuned for updates! ⏳"
        )
    
    @bot.callback_query_handler(func=lambda call: call.data.startswith('shard:'))
    def handle_shard_callback(call):
        from services.database import update_last_interaction
        update_last_interaction(call.from_user.id)
        
        # Show alert for callback queries
        try:
            bot.answer_callback_query(
                call.id,
                "⚠️ Shard predictions are not available yet. Please check back later!",
                show_alert=True
            )
        except Exception as e:
            logger.error(f"Error handling shard callback: {str(e)}")