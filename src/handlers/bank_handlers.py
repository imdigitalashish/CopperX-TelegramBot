from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from datetime import datetime
from src.services.api_service import api_request
from src.config.config import TRANSFER_MENU, BANK_WITHDRAWAL_AMOUNT, BANK_WITHDRAWAL_CONFIRM
from src.utils.logger import logger

# Import user_data from transfer_handlers
from src.handlers.transfer_handlers import user_data

async def bank_withdrawal_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start bank withdrawal process"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    token = user_data[user_id]["token"]
    
    kyc_response = await api_request("get", "/kycs", token=token)
    
    # Rest of your existing bank_withdrawal_start code...

async def bank_withdrawal_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process bank withdrawal amount"""
    # Your existing bank_withdrawal_amount code...

async def bank_withdrawal_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process bank withdrawal confirmation"""
    # Your existing bank_withdrawal_confirm code...