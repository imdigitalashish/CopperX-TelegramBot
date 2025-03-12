from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ConversationHandler
from src.config.config import BOT_TOKEN
from src.handlers.transfer_handlers import (
    wallet_transfer_network,
    wallet_transfer_amount,
    wallet_transfer_confirm
)
from src.handlers.bank_handlers import (
    bank_withdrawal_start,
    bank_withdrawal_amount,
    bank_withdrawal_confirm
)
from src.handlers.profile_handlers import view_profile, view_kyc_status
from src.utils.logger import logger

def main():
    """Initialize and start the bot"""
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()

    # Add handlers
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", view_profile)],
        states={
            # Your conversation states...
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)]
    )

    application.add_handler(conv_handler)
    
    # Add other handlers
    application.add_handler(CallbackQueryHandler(wallet_transfer_network, pattern="^network_"))
    application.add_handler(CallbackQueryHandler(bank_withdrawal_start, pattern="^bank_withdrawal$"))
    application.add_handler(CallbackQueryHandler(view_profile, pattern="^profile$"))
    application.add_handler(CallbackQueryHandler(view_kyc_status, pattern="^kyc_status$"))

    # Start the bot
    logger.info("Bot started")
    application.run_polling()

if __name__ == "__main__":
    main()