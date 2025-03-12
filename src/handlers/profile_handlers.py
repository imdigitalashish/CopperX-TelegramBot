from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from datetime import datetime
from src.services.api_service import api_request
from src.config.config import MAIN_MENU
from src.utils.logger import logger

# Import user_data from transfer_handlers
from src.handlers.transfer_handlers import user_data

async def view_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """View user profile"""
    # Your existing view_profile code...

async def view_kyc_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """View KYC status"""
    # Your existing view_kyc_status code...