# main.py - Entry point for the Copperx Payout Telegram Bot

import os
import logging
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, ConversationHandler, filters
import asyncio
import json
import requests
import pusher
from typing import Dict, List, Optional, Union, Any
from datetime import datetime, timedelta

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Constants
BOT_TOKEN = os.getenv('BOT_TOKEN')
API_BASE_URL = "https://income-api.copperx.io/api"
PUSHER_APP_ID = os.getenv('PUSHER_APP_ID')
PUSHER_KEY = os.getenv('PUSHER_KEY')
PUSHER_SECRET = os.getenv('PUSHER_SECRET')
PUSHER_CLUSTER = os.getenv('PUSHER_CLUSTER')

# Conversation states
(
    START, MAIN_MENU, AUTH_EMAIL, AUTH_OTP, 
    WALLET_MENU, TRANSFER_MENU, SELECT_TRANSFER_TYPE,
    EMAIL_TRANSFER_RECIPIENT, EMAIL_TRANSFER_AMOUNT, EMAIL_TRANSFER_CONFIRM,
    WALLET_TRANSFER_ADDRESS, WALLET_TRANSFER_AMOUNT, WALLET_TRANSFER_CONFIRM,
    BANK_WITHDRAWAL_AMOUNT, BANK_WITHDRAWAL_CONFIRM
) = range(15)

# User session storage
user_data = {}

# Helper Functions
async def api_request(method: str, endpoint: str, token: Optional[str] = None, data: Optional[Dict] = None) -> Dict:
    """Make a request to the Copperx API"""
    url = f"{API_BASE_URL}{endpoint}"
    headers = {"Content-Type": "application/json"}
    
    if token:
        headers["Authorization"] = f"Bearer {token}"
    
    try:
        if method.lower() == "get":
            response = requests.get(url, headers=headers)
        elif method.lower() == "post":
            response = requests.post(url, headers=headers, json=data)
        elif method.lower() == "put":
            response = requests.put(url, headers=headers, json=data)
        else:
            return {"error": "Invalid method"}
        
        response.raise_for_status()  # Raise exception for 4XX/5XX responses
        return response.json()
    except requests.exceptions.RequestException as e:
        logger.error(f"API request error: {e}")
        return {"error": str(e)}

# Command Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start command handler"""
    user_id = update.effective_user.id
    user_data[user_id] = {}
    
    keyboard = [
        [InlineKeyboardButton("Login", callback_data="login")],
        [InlineKeyboardButton("About Copperx", callback_data="about")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Welcome to Copperx Payout Bot! 🚀\n\n"
        "This bot allows you to manage your Copperx account, view balances, and transfer funds directly from Telegram.",
        reply_markup=reply_markup
    )
    
    return START

async def about_copperx(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """About Copperx information"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("Login", callback_data="login")],
        [InlineKeyboardButton("Back to Start", callback_data="back_to_start")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "Copperx is building a stablecoin bank for individuals and businesses.\n\n"
        "Our platform allows you to manage USDC transactions easily and securely.\n\n"
        "Visit https://copperx.io for more information.",
        reply_markup=reply_markup
    )
    
    return START

async def initiate_login(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the login process"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "Please enter your email address to login to your Copperx account:"
    )
    
    return AUTH_EMAIL

async def process_email(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the email and request OTP"""
    user_id = update.effective_user.id
    email = update.message.text.strip()
    
    # Basic email validation
    if "@" not in email or "." not in email:
        await update.message.reply_text(
            "Invalid email format. Please enter a valid email address:"
        )
        return AUTH_EMAIL
    
    # Store email in user data
    user_data[user_id]["email"] = email
    
    # Request OTP via API
    response = await api_request(
        "post", 
        "/auth/email-otp/request", 
        data={"email": email}
    )
    
    if "error" in response:
        await update.message.reply_text(
            f"Error requesting OTP: {response['error']}\n\nPlease try again later."
        )
        return START
    
    await update.message.reply_text(
        f"An OTP has been sent to {email}. Please enter the code:"
    )
    
    return AUTH_OTP

async def process_otp(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process the OTP and authenticate user"""
    user_id = update.effective_user.id
    otp = update.message.text.strip()
    email = user_data[user_id]["email"]
    
    # Authenticate with API
    response = await api_request(
        "post", 
        "/auth/email-otp/authenticate", 
        data={"email": email, "code": otp}
    )
    
    if "error" in response or not response.get("token"):
        await update.message.reply_text(
            "Invalid OTP or authentication failed. Please try again."
        )
        return START
    
    # Store token in user data
    user_data[user_id]["token"] = response["token"]
    
    # Get user profile
    user_profile = await api_request(
        "get", 
        "/auth/me", 
        token=response["token"]
    )
    
    if "error" in user_profile:
        await update.message.reply_text(
            "Authentication successful, but failed to fetch your profile. Please try again."
        )
        return START
    
    # Store user profile information
    user_data[user_id]["profile"] = user_profile
    user_data[user_id]["organization_id"] = user_profile.get("organizationId")
    
    # Setup Pusher for notifications if available
    if PUSHER_APP_ID and PUSHER_KEY and PUSHER_SECRET and user_data[user_id]["organization_id"]:
        setup_pusher_notifications(user_id, user_data[user_id]["organization_id"], user_data[user_id]["token"])
    
    # Show main menu
    return await show_main_menu(update, context)

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Display the main menu"""
    user_id = update.effective_user.id
    profile = user_data[user_id].get("profile", {})
    name = profile.get("name", "User")
    
    keyboard = [
        [InlineKeyboardButton("👛 Wallet Management", callback_data="wallet_menu")],
        [InlineKeyboardButton("💸 Fund Transfers", callback_data="transfer_menu")],
        [InlineKeyboardButton("👤 My Profile", callback_data="profile")],
        [InlineKeyboardButton("🔑 KYC Status", callback_data="kyc_status")],
        [InlineKeyboardButton("📜 Transaction History", callback_data="transaction_history")],
        [InlineKeyboardButton("⚙️ Settings", callback_data="settings")],
        [InlineKeyboardButton("Logout", callback_data="logout")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            f"Hello {name}! 👋\n\nWelcome to your Copperx dashboard. What would you like to do today?",
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            f"Hello {name}! 👋\n\nWelcome to your Copperx dashboard. What would you like to do today?",
            reply_markup=reply_markup
        )
    
    return MAIN_MENU

# Wallet Management Handlers
async def wallet_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show wallet management menu"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    token = user_data[user_id]["token"]
    
    # Fetch wallet information
    wallets_response = await api_request("get", "/wallets", token=token)
    balances_response = await api_request("get", "/wallets/balances", token=token)
    
    if "error" in wallets_response or "error" in balances_response:
        await query.edit_message_text(
            "Failed to fetch wallet information. Please try again later.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Main Menu", callback_data="main_menu")]])
        )
        return MAIN_MENU
    
    # Format wallet information
    wallets = wallets_response.get("data", [])
    balances = balances_response.get("data", {})
    
    wallet_text = "Your Wallets:\n\n"
    
    for wallet in wallets:
        wallet_id = wallet.get("id")
        network = wallet.get("network", "Unknown")
        address = wallet.get("address", "N/A")
        is_default = wallet.get("isDefault", False)
        
        # Get balance for this wallet
        wallet_balance = next((b for b in balances if b.get("walletId") == wallet_id), {})
        balance = wallet_balance.get("balance", "0")
        
        wallet_text += f"{'✅ ' if is_default else ''}Network: {network}\n"
        wallet_text += f"Address: {address[:10]}...{address[-10:]}\n"
        wallet_text += f"Balance: {balance} USDC\n\n"
    
    keyboard = [
        [InlineKeyboardButton("Deposit Funds", callback_data="deposit_funds")],
        [InlineKeyboardButton("Set Default Wallet", callback_data="set_default_wallet")],
        [InlineKeyboardButton("View Transaction History", callback_data="transaction_history")],
        [InlineKeyboardButton("Back to Main Menu", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(wallet_text, reply_markup=reply_markup)
    return WALLET_MENU

async def deposit_funds(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show deposit instructions"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    token = user_data[user_id]["token"]
    
    # Fetch default wallet
    wallets_response = await api_request("get", "/wallets/default", token=token)
    
    if "error" in wallets_response or not wallets_response.get("data"):
        await query.edit_message_text(
            "Failed to fetch your default wallet. Please try again later.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Wallet Menu", callback_data="wallet_menu")]])
        )
        return WALLET_MENU
    
    default_wallet = wallets_response.get("data", {})
    network = default_wallet.get("network", "Unknown")
    address = default_wallet.get("address", "N/A")
    
    deposit_text = f"To deposit funds to your Copperx account, please send USDC to your wallet address:\n\n"
    deposit_text += f"Network: {network}\n"
    deposit_text += f"Address: `{address}`\n\n"
    deposit_text += "Important notes:\n"
    deposit_text += "• Only send USDC to this address\n"
    deposit_text += "• Ensure you're sending on the correct network\n"
    deposit_text += "• Deposits typically reflect in your account within minutes\n"
    deposit_text += "• You'll receive a notification when your deposit arrives"
    
    keyboard = [
        [InlineKeyboardButton("Back to Wallet Menu", callback_data="wallet_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(deposit_text, reply_markup=reply_markup, parse_mode="Markdown")
    return WALLET_MENU

async def set_default_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Set default wallet handler"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    token = user_data[user_id]["token"]
    
    # Fetch all wallets
    wallets_response = await api_request("get", "/wallets", token=token)
    
    if "error" in wallets_response or not wallets_response.get("data"):
        await query.edit_message_text(
            "Failed to fetch your wallets. Please try again later.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Wallet Menu", callback_data="wallet_menu")]])
        )
        return WALLET_MENU
    
    wallets = wallets_response.get("data", [])
    
    # Create keyboard with wallet options
    keyboard = []
    for wallet in wallets:
        wallet_id = wallet.get("id")
        network = wallet.get("network", "Unknown")
        is_default = wallet.get("isDefault", False)
        
        label = f"{'✅ ' if is_default else ''}{network}"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"set_default_{wallet_id}")])
    
    keyboard.append([InlineKeyboardButton("Back to Wallet Menu", callback_data="wallet_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "Select your default wallet for transactions:",
        reply_markup=reply_markup
    )
    
    return WALLET_MENU

async def update_default_wallet(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    token = user_data[user_id]["token"]
    wallet_id = query.data.split("_")[-1]
    
    # Update default wallet via API
    response = await api_request(
        "put", 
        "/wallets/default", 
        token=token,
        data={"walletId": wallet_id}
    )
    
    if "error" in response:
        await query.edit_message_text(
            f"Failed to update default wallet: {response.get('error')}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Wallet Menu", callback_data="wallet_menu")]])
        )
    else:
        await query.edit_message_text(
            "Default wallet updated successfully!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Wallet Menu", callback_data="wallet_menu")]])
        )
    
    return WALLET_MENU

# Fund Transfer Handlers
async def transfer_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show transfer options menu"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("Send to Email Address", callback_data="email_transfer")],
        [InlineKeyboardButton("Send to External Wallet", callback_data="wallet_transfer")],
        [InlineKeyboardButton("Withdraw to Bank Account", callback_data="bank_withdrawal")],
        [InlineKeyboardButton("View Recent Transfers", callback_data="recent_transfers")],
        [InlineKeyboardButton("Back to Main Menu", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "Select a transfer option:",
        reply_markup=reply_markup
    )
    
    return TRANSFER_MENU

async def email_transfer_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start email transfer process"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_data[user_id]["transfer_type"] = "email"
    
    await query.edit_message_text(
        "Please enter the recipient's email address:"
    )
    
    return EMAIL_TRANSFER_RECIPIENT

async def email_transfer_recipient(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process email recipient"""
    user_id = update.effective_user.id
    email = update.message.text.strip()
    
    # Basic email validation
    if "@" not in email or "." not in email:
        await update.message.reply_text(
            "Invalid email format. Please enter a valid email address:"
        )
        return EMAIL_TRANSFER_RECIPIENT
    
    # Store recipient email
    user_data[user_id]["recipient_email"] = email
    
    await update.message.reply_text(
        f"Please enter the amount in USDC to send to {email}:"
    )
    
    return EMAIL_TRANSFER_AMOUNT

async def email_transfer_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process transfer amount"""
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
        return EMAIL_TRANSFER_AMOUNT
    
    # Store amount
    user_data[user_id]["transfer_amount"] = amount
    
    # Fetch user's balance to confirm sufficient funds
    token = user_data[user_id]["token"]
    balances_response = await api_request("get", "/wallets/balances", token=token)
    
    if "error" in balances_response:
        await update.message.reply_text(
            "Failed to fetch your balance. Please try again later.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Transfer Menu", callback_data="transfer_menu")]])
        )
        return TRANSFER_MENU
    
    balances = balances_response.get("data", [])
    total_balance = sum(float(b.get("balance", 0)) for b in balances)
    
    if total_balance < amount:
        await update.message.reply_text(
            f"Insufficient funds. Your current balance is {total_balance} USDC.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Transfer Menu", callback_data="transfer_menu")]])
        )
        return TRANSFER_MENU
    
    # Show confirmation
    recipient_email = user_data[user_id]["recipient_email"]
    
    keyboard = [
        [InlineKeyboardButton("Confirm", callback_data="confirm_email_transfer")],
        [InlineKeyboardButton("Cancel", callback_data="transfer_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"Please confirm the transfer:\n\n"
        f"To: {recipient_email}\n"
        f"Amount: {amount} USDC\n"
        f"Fee: 0 USDC\n"
        f"Total: {amount} USDC",
        reply_markup=reply_markup
    )
    
    return EMAIL_TRANSFER_CONFIRM

async def email_transfer_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process email transfer confirmation"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    token = user_data[user_id]["token"]
    recipient_email = user_data[user_id]["recipient_email"]
    amount = user_data[user_id]["transfer_amount"]
    
    # Execute transfer via API
    transfer_data = {
        "amount": str(amount),
        "email": recipient_email,
        "message": "Transfer via Telegram bot"
    }
    
    response = await api_request(
        "post", 
        "/transfers/send", 
        token=token,
        data=transfer_data
    )
    
    if "error" in response:
        await query.edit_message_text(
            f"Transfer failed: {response.get('error')}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Transfer Menu", callback_data="transfer_menu")]])
        )
    else:
        transfer_id = response.get("data", {}).get("id", "Unknown")
        
        await query.edit_message_text(
            f"Success! {amount} USDC has been sent to {recipient_email}\n"
            f"Transfer ID: {transfer_id}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Transfer Menu", callback_data="transfer_menu")]])
        )
    
    return TRANSFER_MENU

async def wallet_transfer_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start wallet transfer process"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user_data[user_id]["transfer_type"] = "wallet"
    
    await query.edit_message_text(
        "Please enter the recipient's wallet address:"
    )
    
    return WALLET_TRANSFER_ADDRESS

async def wallet_transfer_address(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process wallet address"""
    user_id = update.effective_user.id
    address = update.message.text.strip()
    
    # Basic address validation (simple length check)
    if len(address) < 20:
        await update.message.reply_text(
            "Invalid wallet address. Please enter a valid address:"
        )
        return WALLET_TRANSFER_ADDRESS
    
    # Store recipient address
    user_data[user_id]["recipient_address"] = address
    
    # Fetch user's wallets to select network
    token = user_data[user_id]["token"]
    wallets_response = await api_request("get", "/wallets", token=token)
    
    if "error" in wallets_response:
        await update.message.reply_text(
            "Failed to fetch your wallets. Please try again later.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Transfer Menu", callback_data="transfer_menu")]])
        )
        return TRANSFER_MENU
    
    wallets = wallets_response.get("data", [])
    
    # Create keyboard for network selection
    keyboard = []
    for wallet in wallets:
        network = wallet.get("network", "Unknown")
        wallet_id = wallet.get("id")
        keyboard.append([InlineKeyboardButton(network, callback_data=f"network_{wallet_id}")])
    
    keyboard.append([InlineKeyboardButton("Cancel", callback_data="transfer_menu")])
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Please select the network for this transfer:",
        reply_markup=reply_markup
    )
    
    return WALLET_TRANSFER_AMOUNT

async def wallet_transfer_network(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process wallet network selection"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    wallet_id = query.data.split("_")[-1]
    
    # Store wallet ID for transfer
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
    
    # Store amount
    user_data[user_id]["transfer_amount"] = amount
    
    # Fetch user's balance to confirm sufficient funds
    token = user_data[user_id]["token"]
    balances_response = await api_request("get", "/wallets/balances", token=token)
    
    if "error" in balances_response:
        await update.message.reply_text(
            "Failed to fetch your balance. Please try again later.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Transfer Menu", callback_data="transfer_menu")]])
        )
        return TRANSFER_MENU
    
    balances = balances_response.get("data", [])
    total_balance = sum(float(b.get("balance", 0)) for b in balances)
    
    if total_balance < amount:
        await update.message.reply_text(
            f"Insufficient funds. Your current balance is {total_balance} USDC.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Transfer Menu", callback_data="transfer_menu")]])
        )
        return TRANSFER_MENU
    
    # Show confirmation
    recipient_address = user_data[user_id]["recipient_address"]
    wallet_id = user_data[user_id]["wallet_id"]
    
    # Get network name
    wallets_response = await api_request("get", "/wallets", token=token)
    wallets = wallets_response.get("data", [])
    network = next((w.get("network", "Unknown") for w in wallets if w.get("id") == wallet_id), "Unknown")
    
    keyboard = [
        [InlineKeyboardButton("Confirm", callback_data="confirm_wallet_transfer")],
        [InlineKeyboardButton("Cancel", callback_data="transfer_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"Please confirm the transfer:\n\n"
        f"To address: {recipient_address[:10]}...{recipient_address[-10:]}\n"
        f"Network: {network}\n"
        f"Amount: {amount} USDC\n"
        f"Fee: Varies by network\n"
        f"Total: ~{amount} USDC + network fees",
        reply_markup=reply_markup
    )
    
    return WALLET_TRANSFER_CONFIRM

async def wallet_transfer_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process wallet transfer confirmation"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    token = user_data[user_id]["token"]
    recipient_address = user_data[user_id]["recipient_address"]
    amount = user_data[user_id]["transfer_amount"]
    wallet_id = user_data[user_id]["wallet_id"]
    
    # Execute transfer via API
    transfer_data = {
        "amount": str(amount),
        "toAddress": recipient_address,
        "walletId": wallet_id
    }
    
    response = await api_request(
        "post", 
        "/transfers/wallet-withdraw", 
        token=token,
        data=transfer_data
    )
    
    if "error" in response:
        await query.edit_message_text(
            f"Transfer failed: {response.get('error')}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Transfer Menu", callback_data="transfer_menu")]])
        )
    else:
        transfer_id = response.get("data", {}).get("id", "Unknown")
        
        await query.edit_message_text(
            f"Success! {amount} USDC has been sent to the wallet address\n"
            f"Transfer ID: {transfer_id}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Transfer Menu", callback_data="transfer_menu")]])
        )
    
    return TRANSFER_MENU

async def bank_withdrawal_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start bank withdrawal process"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    token = user_data[user_id]["token"]
    
    # Check if user has completed KYC
    kyc_response = await api_request("get", "/kycs", token=token)
    
    if "error" in kyc_response:
        await query.edit_message_text(
            "Failed to verify KYC status. Please try again later.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Transfer Menu", callback_data="transfer_menu")]])
        )
        return TRANSFER_MENU
    
    kyc_data = kyc_response.get("data", {})
    kyc_status = kyc_data.get("status")
    
    if kyc_status != "APPROVED":
        await query.edit_message_text(
           "Bank withdrawals require completed KYC verification.\n\n"
            "Please complete your KYC on the Copperx web platform first.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Transfer Menu", callback_data="transfer_menu")]])
        )
        return TRANSFER_MENU
    
    user_data[user_id]["transfer_type"] = "bank"
    
    await query.edit_message_text(
        "Please enter the amount in USDC to withdraw to your bank account:"
    )
    
    return BANK_WITHDRAWAL_AMOUNT

async def bank_withdrawal_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process bank withdrawal amount"""
    user_id = update.effective_user.id
    amount_text = update.message.text.strip()
    
    try:
        amount = float(amount_text)
        if amount <= 0:
            raise ValueError("Amount must be positive")
        # Most platforms have minimum withdrawal amounts
        if amount < 10:
            await update.message.reply_text(
                "Minimum withdrawal amount is 10 USDC. Please enter a higher amount:"
            )
            return BANK_WITHDRAWAL_AMOUNT
    except ValueError:
        await update.message.reply_text(
            "Invalid amount. Please enter a valid number:"
        )
        return BANK_WITHDRAWAL_AMOUNT
    
    # Store amount
    user_data[user_id]["transfer_amount"] = amount
    
    # Fetch user's balance to confirm sufficient funds
    token = user_data[user_id]["token"]
    balances_response = await api_request("get", "/wallets/balances", token=token)
    
    if "error" in balances_response:
        await update.message.reply_text(
            "Failed to fetch your balance. Please try again later.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Transfer Menu", callback_data="transfer_menu")]])
        )
        return TRANSFER_MENU
    
    balances = balances_response.get("data", [])
    total_balance = sum(float(b.get("balance", 0)) for b in balances)
    
    if total_balance < amount:
        await update.message.reply_text(
            f"Insufficient funds. Your current balance is {total_balance} USDC.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Transfer Menu", callback_data="transfer_menu")]])
        )
        return TRANSFER_MENU
    
    # Show confirmation with estimated fees
    estimated_fee = max(5, amount * 0.01)  # Example fee calculation
    
    keyboard = [
        [InlineKeyboardButton("Confirm", callback_data="confirm_bank_withdrawal")],
        [InlineKeyboardButton("Cancel", callback_data="transfer_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"Please confirm the bank withdrawal:\n\n"
        f"Amount: {amount} USDC\n"
        f"Estimated Fee: {estimated_fee} USDC\n"
        f"Total to Receive: ~{amount - estimated_fee} USDC\n\n"
        f"Funds will be sent to your default bank account.",
        reply_markup=reply_markup
    )
    
    return BANK_WITHDRAWAL_CONFIRM

async def bank_withdrawal_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Process bank withdrawal confirmation"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    token = user_data[user_id]["token"]
    amount = user_data[user_id]["transfer_amount"]
    
    # Execute bank withdrawal via API
    withdrawal_data = {
        "amount": str(amount),
        "currency": "USD"
    }
    
    response = await api_request(
        "post", 
        "/transfers/offramp", 
        token=token,
        data=withdrawal_data
    )
    
    if "error" in response:
        await query.edit_message_text(
            f"Withdrawal failed: {response.get('error')}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Transfer Menu", callback_data="transfer_menu")]])
        )
    else:
        transfer_id = response.get("data", {}).get("id", "Unknown")
        
        await query.edit_message_text(
            f"Success! Your bank withdrawal of {amount} USDC has been initiated.\n"
            f"Transfer ID: {transfer_id}\n\n"
            f"Funds should arrive in your bank account within 1-3 business days.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Transfer Menu", callback_data="transfer_menu")]])
        )
    
    return TRANSFER_MENU

# Profile and KYC Handlers
async def view_profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """View user profile"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    token = user_data[user_id]["token"]
    
    # Refresh profile data
    profile_response = await api_request("get", "/auth/me", token=token)
    
    if "error" in profile_response:
        await query.edit_message_text(
            "Failed to fetch your profile. Please try again later.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Main Menu", callback_data="main_menu")]])
        )
        return MAIN_MENU
    
    profile = profile_response
    name = profile.get("name", "N/A")
    email = profile.get("email", "N/A")
    organization = profile.get("organizationName", "N/A")
    created_at = profile.get("createdAt", "N/A")
    
    if created_at != "N/A":
        # Format date if available
        try:
            created_date = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            created_at = created_date.strftime("%B %d, %Y")
        except:
            pass
    
    profile_text = f"📋 Your Profile\n\n"
    profile_text += f"👤 Name: {name}\n"
    profile_text += f"📧 Email: {email}\n"
    profile_text += f"🏢 Organization: {organization}\n"
    profile_text += f"📅 Member Since: {created_at}\n"
    
    keyboard = [
        [InlineKeyboardButton("Back to Main Menu", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(profile_text, reply_markup=reply_markup)
    return MAIN_MENU

async def view_kyc_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """View KYC status"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    token = user_data[user_id]["token"]
    
    # Fetch KYC status
    kyc_response = await api_request("get", "/kycs", token=token)
    
    if "error" in kyc_response:
        await query.edit_message_text(
            "Failed to fetch your KYC status. Please try again later.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Main Menu", callback_data="main_menu")]])
        )
        return MAIN_MENU
    
    kyc_data = kyc_response.get("data", {})
    kyc_status = kyc_data.get("status", "NOT_STARTED")
    kyc_type = kyc_data.get("type", "INDIVIDUAL")
    
    status_emoji = {
        "APPROVED": "✅",
        "PENDING": "⏳",
        "REJECTED": "❌",
        "NOT_STARTED": "🔴"
    }
    
    status_text = {
        "APPROVED": "Your KYC verification has been approved.",
        "PENDING": "Your KYC verification is being reviewed.",
        "REJECTED": "Your KYC verification was rejected. Please check the web platform for details.",
        "NOT_STARTED": "You haven't started the KYC verification process yet."
    }
    
    kyc_text = f"🔐 KYC Status\n\n"
    kyc_text += f"{status_emoji.get(kyc_status, '❓')} Status: {kyc_status}\n"
    kyc_text += f"📋 Type: {kyc_type}\n\n"
    kyc_text += status_text.get(kyc_status, "Unknown status")
    
    if kyc_status != "APPROVED":
        kyc_text += "\n\nComplete KYC verification on the Copperx web platform to access all features."
    
    keyboard = [
        [InlineKeyboardButton("Back to Main Menu", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(kyc_text, reply_markup=reply_markup)
    return MAIN_MENU

# Transaction History Handlers
async def view_transaction_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """View transaction history"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    token = user_data[user_id]["token"]
    
    # Fetch recent transactions
    transactions_response = await api_request("get", "/transfers?page=1&limit=10", token=token)
    
    if "error" in transactions_response:
        await query.edit_message_text(
            "Failed to fetch your transaction history. Please try again later.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Main Menu", callback_data="main_menu")]])
        )
        return MAIN_MENU
    
    transactions = transactions_response.get("data", [])
    
    if not transactions:
        await query.edit_message_text(
            "You don't have any transactions yet.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back to Main Menu", callback_data="main_menu")]])
        )
        return MAIN_MENU
    
    # Format transaction history
    history_text = "📜 Recent Transactions\n\n"
    
    for tx in transactions:
        tx_id = tx.get("id", "Unknown")[:8]
        tx_type = tx.get("type", "Unknown")
        amount = tx.get("amount", "0")
        status = tx.get("status", "Unknown")
        created_at = tx.get("createdAt", "Unknown")
        
        # Format date if available
        if created_at != "Unknown":
            try:
                tx_date = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                created_at = tx_date.strftime("%m/%d/%Y")
            except:
                pass
        
        # Determine direction and icon
        direction = ""
        if tx_type == "DEPOSIT":
            direction = "↓ IN"
            icon = "📥"
        elif tx_type in ["WITHDRAWAL", "EMAIL_TRANSFER", "WALLET_TRANSFER"]:
            direction = "↑ OUT"
            icon = "📤"
        else:
            icon = "🔄"
        
        history_text += f"{icon} {direction} {amount} USDC - {created_at} - {status}\n"
    
    keyboard = [
        [InlineKeyboardButton("Back to Main Menu", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(history_text, reply_markup=reply_markup)
    return MAIN_MENU

# Settings and Logout Handlers
async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Show settings menu"""
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("Enable Notifications", callback_data="toggle_notifications")],
        [InlineKeyboardButton("Back to Main Menu", callback_data="main_menu")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        "⚙️ Settings\n\n"
        "Configure your preferences for the Copperx bot:",
        reply_markup=reply_markup
    )
    
    return MAIN_MENU

async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Log out the user"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    if user_id in user_data:
        del user_data[user_id]
    
    await query.edit_message_text(
        "You have been logged out successfully.\n\n"
        "Thank you for using the Copperx Payout Bot!",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Login Again", callback_data="login")]])
    )
    
    return START

# Notification System
def setup_pusher_notifications(user_id, organization_id, token):
    """Setup Pusher client for real-time notifications"""
    if not (PUSHER_APP_ID and PUSHER_KEY and PUSHER_SECRET and PUSHER_CLUSTER):
        return
    
    try:
        # Get Pusher auth
        auth_response = requests.post(
            f"{API_BASE_URL}/notifications/auth",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            },
            json={
                "socket_id": f"bot-{user_id}",
                "channel_name": f"private-org-{organization_id}"
            }
        )
        
        if auth_response.status_code != 200:
            logger.error(f"Failed to authenticate with Pusher: {auth_response.text}")
            return
        
        # Initialize Pusher
        pusher_client = pusher.Pusher(
            app_id=PUSHER_APP_ID,
            key=PUSHER_KEY,
            secret=PUSHER_SECRET,
            cluster=PUSHER_CLUSTER,
            ssl=True
        )
        
        # Store in user data for later use
        user_data[user_id]["pusher"] = pusher_client
        
        logger.info(f"Pusher notifications set up for user {user_id}")
    except Exception as e:
        logger.error(f"Error setting up Pusher: {e}")

# Setup main conversation handler
def create_conversation_handler():
    """Create the main conversation handler"""
    return ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            START: [
                CallbackQueryHandler(initiate_login, pattern="^login$"),
                CallbackQueryHandler(about_copperx, pattern="^about$"),
                CallbackQueryHandler(start, pattern="^back_to_start$")
            ],
            AUTH_EMAIL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_email)
            ],
            AUTH_OTP: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_otp)
            ],
            MAIN_MENU: [
              CallbackQueryHandler(wallet_menu, pattern="^wallet_menu$"),
                CallbackQueryHandler(transfer_menu, pattern="^transfer_menu$"),
                CallbackQueryHandler(view_profile, pattern="^profile$"),
                CallbackQueryHandler(view_kyc_status, pattern="^kyc_status$"),
                CallbackQueryHandler(view_transaction_history, pattern="^transaction_history$"),
                CallbackQueryHandler(settings_menu, pattern="^settings$"),
                CallbackQueryHandler(logout, pattern="^logout$")
            ],
            WALLET_MENU: [
                CallbackQueryHandler(deposit_funds, pattern="^deposit_funds$"),
                CallbackQueryHandler(set_default_wallet, pattern="^set_default_wallet$"),
                CallbackQueryHandler(view_transaction_history, pattern="^transaction_history$"),
                CallbackQueryHandler(show_main_menu, pattern="^main_menu$"),
                CallbackQueryHandler(update_default_wallet, pattern="^set_default_.*$")
            ],
            TRANSFER_MENU: [
                CallbackQueryHandler(email_transfer_start, pattern="^email_transfer$"),
                CallbackQueryHandler(wallet_transfer_start, pattern="^wallet_transfer$"),
                CallbackQueryHandler(bank_withdrawal_start, pattern="^bank_withdrawal$"),
                CallbackQueryHandler(view_transaction_history, pattern="^recent_transfers$"),
                CallbackQueryHandler(show_main_menu, pattern="^main_menu$")
            ],
            EMAIL_TRANSFER_RECIPIENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, email_transfer_recipient)
            ],
            EMAIL_TRANSFER_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, email_transfer_amount)
            ],
            EMAIL_TRANSFER_CONFIRM: [
                CallbackQueryHandler(email_transfer_confirm, pattern="^confirm_email_transfer$"),
                CallbackQueryHandler(transfer_menu, pattern="^transfer_menu$")
            ],
            WALLET_TRANSFER_ADDRESS: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, wallet_transfer_address)
            ],
            WALLET_TRANSFER_AMOUNT: [
                CallbackQueryHandler(wallet_transfer_network, pattern="^network_.*$"),
                CallbackQueryHandler(transfer_menu, pattern="^transfer_menu$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, wallet_transfer_amount)
            ],
            WALLET_TRANSFER_CONFIRM: [
                CallbackQueryHandler(wallet_transfer_confirm, pattern="^confirm_wallet_transfer$"),
                CallbackQueryHandler(transfer_menu, pattern="^transfer_menu$")
            ],
            BANK_WITHDRAWAL_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bank_withdrawal_amount)
            ],
            BANK_WITHDRAWAL_CONFIRM: [
                CallbackQueryHandler(bank_withdrawal_confirm, pattern="^confirm_bank_withdrawal$"),
                CallbackQueryHandler(transfer_menu, pattern="^transfer_menu$")
            ]
        },
        fallbacks=[CommandHandler("start", start), CommandHandler("help", start)]
    )

# Create webhook handler
async def webhook(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Receive webhook updates from Pusher"""
    # Implementation depends on how Copperx webhooks are structured
    # This is a placeholder for the webhook handling logic
    user_id = update.effective_user.id
    message_data = update.message.text
    
    try:
        data = json.loads(message_data)
        event_type = data.get("event")
        
        if event_type == "deposit":
            amount = data.get("amount")
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🎉 Deposit Received! {amount} USDC has been credited to your account."
            )
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")

# Helper command to display help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Display help message"""
    help_text = (
        "🤖 Copperx Payout Bot Help\n\n"
        "Commands:\n"
        "/start - Start or restart the bot\n"
        "/help - Show this help message\n\n"
        "Features:\n"
        "• View wallet balances\n"
        "• Send funds to email addresses\n"
        "• Withdraw to external wallets\n"
        "• Bank withdrawals\n"
        "• Transaction history\n"
        "• Account management\n\n"
        "For support, please contact the Copperx team via https://t.me/copperxcommunity/2991"
    )
    await update.message.reply_text(help_text)

# Main function to run the bot
def main():
    """Start the bot"""
    # Create the Application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add conversation handler
    conv_handler = create_conversation_handler()
    application.add_handler(conv_handler)
    
    # Add standalone command handlers
    application.add_handler(CommandHandler("help", help_command))
    
    # Start the Bot
    application.run_polling()

if __name__ == "__main__":
    main()