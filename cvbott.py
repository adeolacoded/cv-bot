import logging
import sqlite3
import os
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

# ========== CONFIG ==========
BOT_TOKEN = "8708921630:AAHRcD16E0jmskVkjrAu8Wj-Uo256T-Hj2A"
ADMIN_ID = 8317899373
SUPPORT_USERNAME = "@ezzy_sol"

# ========== DATABASE ==========
conn = sqlite3.connect("bot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    credits INTEGER DEFAULT 1,
    is_pro INTEGER DEFAULT 0,
    pro_expiry TEXT
)
""")
conn.commit()

# ========== FUNCTIONS ==========
def add_user(user_id):
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()

def get_user(user_id):
    cursor.execute("SELECT credits, is_pro, pro_expiry FROM users WHERE user_id=?", (user_id,))
    return cursor.fetchone()

def set_pro(user_id):
    expiry = datetime.now() + timedelta(days=30)
    cursor.execute("UPDATE users SET is_pro=1, pro_expiry=? WHERE user_id=?", (expiry.isoformat(), user_id))
    conn.commit()

def check_pro(user_id):
    cursor.execute("SELECT is_pro, pro_expiry FROM users WHERE user_id=?", (user_id,))
    data = cursor.fetchone()
    if not data:
        return False
    is_pro, expiry = data
    if is_pro == 1 and expiry:
        if datetime.fromisoformat(expiry) > datetime.now():
            return True
    return False

# ========== COMMANDS ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    add_user(user_id)

    keyboard = [
        [InlineKeyboardButton("🚀 Upgrade to Pro", callback_data="upgrade")],
        [InlineKeyboardButton("💳 Check Credits", callback_data="credits")],
        [InlineKeyboardButton("📞 Support", url=f"https://t.me/{SUPPORT_USERNAME.replace('@','')}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Welcome to CV Bot!\n\nFree users get 1 credit.\nUpgrade to Pro for unlimited access.",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if query.data == "upgrade":
        await query.message.reply_text(
            "Send payment proof screenshot after payment.\n\nAdmin will review and upgrade you."
        )

    elif query.data == "credits":
        user = get_user(user_id)
        if user:
            credits, is_pro, expiry = user
            if check_pro(user_id):
                await query.message.reply_text("You are a PRO user ✅ Unlimited access.")
            else:
                await query.message.reply_text(f"You have {credits} credit(s).")

# ========== PAYMENT PROOF ==========
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    photo = update.message.photo[-1].file_id

    caption = f"New payment proof from user: {user_id}"

    keyboard = [
        [
            InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user_id}")
        ]
    ]

    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=photo,
        caption=caption,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    await update.message.reply_text("Payment proof sent to admin for review.")

# ========== ADMIN BUTTONS ==========
async def admin_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.from_user.id != ADMIN_ID:
        return

    data = query.data

    if data.startswith("approve_"):
        user_id = int(data.split("_")[1])
        set_pro(user_id)
        await context.bot.send_message(user_id, "🎉 You have been upgraded to PRO for 30 days!")
        await query.edit_message_caption("Approved ✅")

    elif data.startswith("reject_"):
        user_id = int(data.split("_")[1])
        await context.bot.send_message(user_id, "❌ Your payment proof was rejected. Contact support.")
        await query.edit_message_caption("Rejected ❌")

# ========== MAIN ==========
logging.basicConfig(level=logging.INFO)

app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CallbackQueryHandler(button_handler, pattern="upgrade|credits"))
app.add_handler(CallbackQueryHandler(admin_buttons))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

print("Bot is running...")
app.run_polling()
