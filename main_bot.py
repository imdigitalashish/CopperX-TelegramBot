import os
from datetime import datetime
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, MessageHandler, filters
import requests
import pusher
import json

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# States for conversation handler
LOGIN, OTP_VERIFICATION = range(2)

# API Base URL
API_BASE_URL = "https://income-api.copperx.io/api"

# Pusher configuration
pusher_client = pusher.Pusher(
    app_id='YOUR_APP_ID',
    key='YOUR_KEY',
    secret='YOUR_SECRET',
    cluster='YOUR_CLUSTER',
    ssl=True
)

class CopperxBot:
    def __init__(self):
        self.user_sessions = {}  # Store user tokens
        
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command handler"""
        keyboard = [
            [InlineKeyboardButton("Login", callback_data='login')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "Welcome to Copperx Bot! Please login to continue.",
            reply_markup=reply_markup
        )
        return LOGIN

    async def login_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle login process"""
        query = update.callback_query
        await query.answer()
        await query.message.reply_text("Please enter your email:")
        return OTP_VERIFICATION

    async def otp_verification(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle OTP verification"""
        email = update.message.text
        # Request OTP
        response = requests.post(f"{API_BASE_URL}/auth/email-otp/request", json={"email": email})
        if response.status_code == 200:
            context.user_data['email'] = email
            await update.message.reply_text("OTP sent to your email. Please enter the OTP:")
            return OTP_VERIFICATION
        else:
            await update.message.reply_text("Failed to send OTP. Please try again.")
            return ConversationHandler.END

    async def verify_otp(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Verify OTP and complete authentication"""
        otp = update.message.text
        email = context.user_data.get('email')
        
        response = requests.post(
            f"{API_BASE_URL}/auth/email-otp/authenticate",
            json={"email": email, "otp": otp}
        )
        
        if response.status_code == 200:
            token = response.json().get('token')
            self.user_sessions[update.effective_user.id] = token
            await self.setup_pusher_notification(update.effective_user.id, token)
            await update.message.reply_text("Login successful! Use /help to see available commands.")
            return ConversationHandler.END
        else:
            await update.message.reply_text("Invalid OTP. Please try again.")
            return ConversationHandler.END

    async def setup_pusher_notification(self, user_id: int, token: str):
        """Setup Pusher notifications for the user"""
        # Get user organization ID
        headers = {'Authorization': f'Bearer {token}'}
        response = requests.get(f"{API_BASE_URL}/auth/me", headers=headers)
        if response.status_code == 200:
            org_id = response.json().get('organizationId')
            # Subscribe to private channel
            channel = f'private-org-{org_id}'
            pusher_client.subscribe(channel)

    async def get_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Get wallet balances"""
        token = self.user_sessions.get(update.effective_user.id)
        if not token:
            await update.message.reply_text("Please login first using /start")
            return

        headers = {'Authorization': f'Bearer {token}'}
        response = requests.get(f"{API_BASE_URL}/wallets/balances", headers=headers)
        
        if response.status_code == 200:
            balances = response.json()
            balance_text = "Your Balances:\n"
            for balance in balances:
                balance_text += f"Network: {balance['network']}\nAmount: {balance['amount']} {balance['currency']}\n\n"
            await update.message.reply_text(balance_text)
        else:
            await update.message.reply_text("Failed to fetch balances.")

    async def send_funds(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send funds to email"""
        if len(context.args) != 2:
            await update.message.reply_text("Usage: /send <email> <amount>")
            return

        token = self.user_sessions.get(update.effective_user.id)
        if not token:
            await update.message.reply_text("Please login first using /start")
            return

        recipient_email = context.args[0]
        amount = context.args[1]

        headers = {'Authorization': f'Bearer {token}'}
        payload = {
            "recipient": recipient_email,
            "amount": float(amount),
            "currency": "USDC"
        }

        response = requests.post(f"{API_BASE_URL}/transfers/send", headers=headers, json=payload)
        
        if response.status_code == 200:
            await update.message.reply_text(f"Successfully sent {amount} USDC to {recipient_email}")
        else:
            await update.message.reply_text("Transfer failed. Please try again.")

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Help command handler"""
        help_text = """
Available commands:
/start - Start the bot and login
/balance - Check your wallet balances
/send <email> <amount> - Send USDC to an email address
/history - View last 10 transactions
/help - Show this help message
        """
        await update.message.reply_text(help_text)

def main():
    """Start the bot"""
    # Create the bot instance
    bot = CopperxBot()
    
    # Create the Application and pass it your bot's token
    application = Application.builder().token("YOUR_BOT_TOKEN").build()

    # Add conversation handler for login flow
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", bot.start)],
        states={
            LOGIN: [CallbackQueryHandler(bot.login_handler)],
            OTP_VERIFICATION: [
                CommandHandler("cancel", lambda u, c: ConversationHandler.END),
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot.otp_verification)
            ],
        },
        fallbacks=[CommandHandler("cancel", lambda u, c: ConversationHandler.END)],
    )

    # Add handlers
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("balance", bot.get_balance))
    application.add_handler(CommandHandler("send", bot.send_funds))
    application.add_handler(CommandHandler("help", bot.help))

    # Start the bot
    application.run_polling()

if __name__ == '__main__':
    main()