import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Bot Configuration
BOT_TOKEN = os.getenv('BOT_TOKEN')
API_BASE_URL = "https://income-api.copperx.io/api"

# Pusher Configuration
PUSHER_APP_ID = os.getenv('PUSHER_APP_ID')
PUSHER_KEY = os.getenv('PUSHER_KEY')
PUSHER_SECRET = os.getenv('PUSHER_SECRET')

# Conversation States
(MAIN_MENU, TRANSFER_MENU, WALLET_TRANSFER_AMOUNT, 
 BANK_WITHDRAWAL_AMOUNT, BANK_WITHDRAWAL_CONFIRM, 
 WALLET_TRANSFER_CONFIRM) = range(6)