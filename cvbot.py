import sqlite3
import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ================= CONFIG =================
TOKEN = os.getenv("8708921630:AAHRcD16E0jmskVkjrAu8Wj-Uo256T-Hj2A")
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

# ================= DATABASE FUNCTIONS =================

def add_user(user):
    cursor.execute("SELECT user_id FROM users WHERE user_id=?", (user.id,))
    if not cursor.fetchone():
        cursor.execute(
            "INSERT INTO users (user_id, username, credits, is_pro) VALUES (?, ?, ?, ?)",
            (user.id, user.username, 1, 0)
        )
        conn.commit()

def get_user(user_id):
    cursor.execute("SELECT credits, is_pro FROM users WHERE user_id=?", (user_id,))
    return cursor.fetchone()

def add_credit(user_id, amount=1):
    cursor.execute("UPDATE users SET credits = credits + ? WHERE user_id=?", (amount, user_id))
    conn.commit()

def deduct_credit(user_id):
    cursor.execute("UPDATE users SET credits = credits - 1 WHERE user_id=? AND credits > 0", (user_id,))
    conn.commit()

def activate_pro(user_id):
    cursor.execute("UPDATE users SET is_pro=1 WHERE user_id=?", (user_id,))
    conn.commit()

# ================= START =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    add_user(user)

    # Referral
    if context.args:
        referrer_id = int(context.args[0])
        if referrer_id != user.id:
            cursor.execute("SELECT * FROM referrals WHERE referred_id=?", (user.id,))
            if not cursor.fetchone():
                cursor.execute("INSERT INTO referrals VALUES (?, ?)", (referrer_id, user.id))
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
        "You have 1 FREE CV credit.\nUpgrade to PRO for unlimited CV requests.",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ================= BUTTON HANDLER =================

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    user_data = get_user(user_id)
    if not user_data:
        return

    credits, is_pro = user_data

    if query.data == "create_cv":
        if not is_pro and credits <= 0:
            await query.message.reply_text("❌ No credits left. Upgrade to PRO.")
            return

        context.user_data["awaiting_details"] = True
        await query.message.reply_text("Send all your CV details in one message.")

    elif query.data == "upgrade":
        await query.message.reply_text(
            "💎 PRO UPGRADE\n\n"
            "Price: ₦1,500\n\n"
            "Payment Details:\n"
            "Bank: Opay\n"
            "Account Name: Oyenekan Ezekiel Adeola\n"
            "Account Number: 8123465260\n\n"
            "After payment, send screenshot here.\n"
            "Admin will confirm and activate PRO."
        )

    elif query.data == "dashboard":
        status = "PRO User (Unlimited)" if is_pro else "Free User"
        await query.message.reply_text(
            f"📊 DASHBOARD\n\nStatus: {status}\nCredits: {credits}\n\n"
            f"Referral Link:\nhttps://t.me/{context.bot.username}?start={user_id}"
        )

    elif query.data.startswith("confirm_"):
        target_id = int(query.data.split("_")[1])
        target_data = get_user(target_id)
        if target_data:
            t_credits, t_is_pro = target_data
            if not t_is_pro:
                deduct_credit(target_id)

        await context.bot.send_message(
            chat_id=target_id,
            text="✅ CV request approved. Your CV is being prepared."
        )
        await query.message.edit_text("Request confirmed.")

    elif query.data.startswith("reject_"):
        target_id = int(query.data.split("_")[1])
        await context.bot.send_message(
            chat_id=target_id,
            text="❌ CV request rejected. Please resend properly."
        )
        await query.message.edit_text("Request rejected.")

    elif query.data.startswith("activatepro_"):
        if user_id != ADMIN_ID:
            return
        target_id = int(query.data.split("_")[1])
        activate_pro(target_id)

        await context.bot.send_message(
            chat_id=target_id,
            text="🎉 PRO activated! Unlimited CV requests unlocked."
        )
        await query.message.edit_text("PRO activated.")

    elif query.data == "total_users":
        cursor.execute("SELECT COUNT(*) FROM users")
        total = cursor.fetchone()[0]
        await query.message.reply_text(f"👥 Total Users: {total}")

    elif query.data == "total_pro":
        cursor.execute("SELECT COUNT(*) FROM users WHERE is_pro=1")
        total = cursor.fetchone()[0]
        await query.message.reply_text(f"💎 Total PRO Users: {total}")

    elif query.data == "broadcast":
        context.user_data["broadcast"] = True
        await query.message.reply_text("Send broadcast message.")

# ================= MESSAGE HANDLER =================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id

    # Broadcast
    if context.user_data.get("broadcast") and user_id == ADMIN_ID:
        context.user_data["broadcast"] = False
        cursor.execute("SELECT user_id FROM users")
        users = cursor.fetchall()
        for u in users:
            try:
                await context.bot.send_message(chat_id=u[0], text=update.message.text)
            except:
                pass
        await update.message.reply_text("✅ Broadcast sent.")
        return

    # CV submission
    if context.user_data.get("awaiting_details"):
        context.user_data["awaiting_details"] = False

        keyboard = [[
            InlineKeyboardButton("✅ Confirm", callback_data=f"confirm_{user_id}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user_id}")
        ]]

        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"📥 New CV Request\nUser: @{user.username}\nID: {user_id}\n\n{update.message.text}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        await update.message.reply_text("CV request submitted.")
        return

    # Payment proof
    if update.message.photo or update.message.document:
        await context.bot.forward_message(
            chat_id=ADMIN_ID,
            from_chat_id=user_id,
            message_id=update.message.message_id
        )

        keyboard = [[
            InlineKeyboardButton("✅ Activate PRO", callback_data=f"activatepro_{user_id}")
        ]]

        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"Payment proof from @{user.username} (ID: {user_id})",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        await update.message.reply_text("Payment proof received. Awaiting confirmation.")

# ================= ADMIN PANEL =================

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    keyboard = [
        [InlineKeyboardButton("📊 Total Users", callback_data="total_users")],
        [InlineKeyboardButton("💎 Total PRO Users", callback_data="total_pro")],
        [InlineKeyboardButton("📨 Broadcast", callback_data="broadcast")],
    ]

    await update.message.reply_text(
        "🔐 ADMIN PANEL",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ================= ADMIN SEND CV =================

async def sendcv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return

    if not context.args:
        await update.message.reply_text("Usage: /sendcv user_id")
        return

    context.user_data["send_to"] = int(context.args[0])
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
app.add_handler(CommandHandler("admin", admin_panel))
app.add_handler(CommandHandler("sendcv", sendcv))
app.add_handler(CallbackQueryHandler(button_handler))
app.add_handler(MessageHandler(filters.ALL, handle_message))
app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_admin_file))

print("Bot is running...")
app.run_polling()
