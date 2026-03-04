import sqlite3
import logging
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)

# ================= CONFIG =================
TOKEN =  "8708921630:AAHRcD16E0jmskVkjrAu8Wj-Uo256T-Hj2A"
ADMIN_ID = 8317899373
SUPPORT_USERNAME = "ezzy_sol"

logging.basicConfig(level=logging.INFO)

# ================= DATABASE =================
conn = sqlite3.connect("cvbot.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    credits INTEGER DEFAULT 1,
    is_pro INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS referrals (
    referrer_id INTEGER,
    referred_id INTEGER
)
""")

conn.commit()

# ================= HELPERS =================

def add_user(user):
    cursor.execute("SELECT user_id FROM users WHERE user_id=?", (user.id,))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO users (user_id, username, credits) VALUES (?, ?, ?)",
            (user.id, user.username, 1)
        )
        conn.commit()

def get_credits(user_id):
    cursor.execute("SELECT credits FROM users WHERE user_id=?", (user_id,))
    result = cursor.fetchone()
    return result[0] if result else 0

def add_credit(user_id, amount=1):
    cursor.execute(
        "UPDATE users SET credits = credits + ? WHERE user_id=?",
        (amount, user_id)
    )
    conn.commit()

def deduct_credit(user_id):
    cursor.execute(
        "UPDATE users SET credits = credits - 1 WHERE user_id=? AND credits > 0",
        (user_id,)
    )
    conn.commit()

def total_users():
    cursor.execute("SELECT COUNT(*) FROM users")
    return cursor.fetchone()[0]

# ================= START =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user)

    # Referral system
    if context.args:
        referrer_id = int(context.args[0])
        if referrer_id != user.id:
            cursor.execute("SELECT * FROM referrals WHERE referred_id=?", (user.id,))
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO referrals VALUES (?, ?)",
                    (referrer_id, user.id)
                )
                add_credit(referrer_id, 1)
                conn.commit()

    keyboard = [
        [InlineKeyboardButton("📝 Create CV", callback_data="create_cv")],
        [InlineKeyboardButton("💎 Upgrade to Pro", callback_data="upgrade")],
        [InlineKeyboardButton("📊 Dashboard", callback_data="dashboard")],
        [InlineKeyboardButton("📞 Support", url=f"https://t.me/{SUPPORT_USERNAME}")]
    ]

    await update.message.reply_text(
        f"Welcome {user.first_name}!\n\n"
        "You have 1 free CV credit.\n\n"
        "Use the buttons below to continue.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ================= BUTTON HANDLER =================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id

    if query.data == "create_cv":
        credits = get_credits(user_id)

        if credits <= 0:
            keyboard = [
                [InlineKeyboardButton("💎 Upgrade to Pro", callback_data="upgrade")]
            ]
            await query.message.reply_text(
                "❌ You have no credits left.\nUpgrade to continue.",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

        context.user_data["awaiting_details"] = True
        await query.message.reply_text(
            "Please send ALL your CV details in one message."
        )

    elif query.data == "upgrade":
        await query.message.reply_text(
            "💎 PRO BENEFITS:\n\n"
            "- Unlimited CV Requests\n"
            "- Priority Processing\n"
            "- Professional Formatting\n\n"
            "Send payment proof to continue."
        )

    elif query.data == "dashboard":
        credits = get_credits(user_id)
        await query.message.reply_text(
            f"📊 Your Dashboard\n\n"
            f"Credits: {credits}\n"
            f"Referral Link:\n"
            f"https://t.me/{context.bot.username}?start={user_id}"
        )

    elif query.data.startswith("confirm_"):
        target_id = int(query.data.split("_")[1])
        deduct_credit(target_id)

        await context.bot.send_message(
            chat_id=target_id,
            text="✅ Your CV request has been approved.\nYour CV is being prepared."
        )

        await query.message.edit_text("Request confirmed and credit deducted.")

    elif query.data.startswith("reject_"):
        target_id = int(query.data.split("_")[1])

        await context.bot.send_message(
            chat_id=target_id,
            text="❌ Your CV request was rejected.\nPlease resubmit correctly."
        )

        await query.message.edit_text("Request rejected.")

# ================= MESSAGE HANDLER =================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    # If awaiting CV details
    if context.user_data.get("awaiting_details"):
        context.user_data["awaiting_details"] = False

        keyboard = [
            [
                InlineKeyboardButton("✅ Confirm", callback_data=f"confirm_{user_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user_id}")
            ]
        ]

        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📥 New CV Request\n\nUser: @{user.username}\nID: {user_id}\n\nDetails:\n{update.message.text}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        await update.message.reply_text(
            "Your CV request has been submitted.\nYou will be notified after review."
        )

    # Payment proof forwarding
    elif update.message.photo or update.message.document:
        await context.bot.forward_message(
            chat_id=ADMIN_ID,
            from_chat_id=user_id,
            message_id=update.message.message_id
        )

        await update.message.reply_text(
            "Payment proof received.\nAwaiting admin confirmation."
        )

# ================= ADMIN SEND CV =================

async def sendcv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    if not context.args:
        await update.message.reply_text("Usage: /sendcv user_id")
        return

    target_id = int(context.args[0])
    context.user_data["send_to"] = target_id
    await update.message.reply_text("Send the CV file now.")

async def handle_admin_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id == ADMIN_ID and "send_to" in context.user_data:
        target_id = context.user_data["send_to"]

        await context.bot.forward_message(
            chat_id=target_id,
            from_chat_id=ADMIN_ID,
            message_id=update.message.message_id
        )

        await update.message.reply_text("CV sent successfully.")
        del context.user_data["send_to"]

# ================= MAIN =================

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("sendcv", sendcv))
app.add_handler(CallbackQueryHandler(button_handler))
app.add_handler(MessageHandler(filters.ALL, handle_message))
app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_admin_file))

print("Bot is running...")
app.run_polling()            
