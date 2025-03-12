from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from src.services.api_service import api_request
from src.config.config import (TRANSFER_MENU, WALLET_TRANSFER_AMOUNT, 
                             BANK_WITHDRAWAL_AMOUNT, BANK_WITHDRAWAL_CONFIRM,
                             WALLET_TRANSFER_CONFIRM)
from src.utils.logger import logger

# Store user data (in production, use a proper database)
user_data = {}

async def wallet_transfer_network(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process wallet network selection"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    wallet_id = query.data.split("_")[-1]
    
    user_data[user_id]["wallet_id"] = wallet_id
    
    await query.edit_message_text(
        "Please enter the amount in USDC to send:"
    )
    
    return WALLET_TRANSFER_AMOUNT

async def wallet_transfer_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process wallet transfer amount"""
    user_id = update.effective_user.id
    amount_text = update.message.text.strip()
    
    try:
        amount = float(amount_text)
        if amount <= 0:
            raise ValueError("Amount must be positive")
    except ValueError:
        await update.message.reply_text(
            "Invalid amount. Please enter a valid number:"
        )
        return WALLET_TRANSFER_AMOUNT
    
    user_data[user_id]["transfer_amount"] = amount
    token = user_data[user_id]["token"]
    balances_response = await api_request("get", "/wallets/balances", token=token)
    
    if "error" in balances_response:
        await update.message.reply_text(
            "Failed to fetch your balance. Please try again later.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Transfer Menu", callback_data="transfer_menu")]])
        )
        return TRANSFER_MENU
    
    # Rest of your existing wallet_transfer_amount code...