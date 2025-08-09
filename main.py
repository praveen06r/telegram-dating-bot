import os
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler
from database import User, get_db, SessionLocal
from sqlalchemy.orm import Session

# 🔹 Bot token is securely stored in Render environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")  # <-- Set in Render Dashboard (Environment tab)
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is missing. Please set it in Render environment variables.")

# 🔹 Multiple owners can be hardcoded here (add more IDs as needed)
OWNER_IDS = [5518634633, 108099033]

app = FastAPI()
telegram_app = Application.builder().token(BOT_TOKEN).build()

# ----------------- Helper functions -----------------
def get_or_create_user(telegram_id, db: Session):
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user:
        user = User(telegram_id=telegram_id)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user

# ----------------- Handlers -----------------
async def start(update: Update, context):
    db = SessionLocal()
    get_or_create_user(update.effective_user.id, db)
    await update.message.reply_text("Welcome! Send your gender (M/F) to start.")

async def set_gender(update: Update, context):
    gender = update.message.text.upper()
    if gender not in ["M", "F"]:
        await update.message.reply_text("Please send 'M' or 'F'.")
        return
    db = SessionLocal()
    user = get_or_create_user(update.effective_user.id, db)
    user.gender = gender
    db.commit()
    await update.message.reply_text(f"Gender set to {gender}.")

async def find_partner(update: Update, context):
    db = SessionLocal()
    user = get_or_create_user(update.effective_user.id, db)

    # Check subscription limit
    if user.chats_seen >= 5 and not user.subscribed:
        button = InlineKeyboardButton("Subscribe for $2/month", callback_data="subscribe")
        await update.message.reply_text(
            "Free limit reached. Subscribe to continue.",
            reply_markup=InlineKeyboardMarkup([[button]])
        )
        return

    # Find partner
    partner = db.query(User).filter(User.gender != user.gender, User.telegram_id != user.telegram_id).first()
    if partner:
        user.chats_seen += 1
        db.commit()
        await update.message.reply_text(f"Matched with gender: {partner.gender}")

        # Owner(s) can see Telegram ID
        if update.effective_user.id in OWNER_IDS:
            await update.message.reply_text(f"(Owner View) Partner ID: {partner.telegram_id}")
    else:
        await update.message.reply_text("No partner found right now.")

async def handle_subscribe(update: Update, context):
    db = SessionLocal()
    user = get_or_create_user(update.effective_user.id, db)
    user.subscribed = True
    db.commit()
    await update.callback_query.answer("Subscribed successfully!")
    await update.callback_query.edit_message_text("You are now subscribed!")

# ----------------- Register handlers -----------------
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(MessageHandler(filters.Regex("^(M|F|m|f)$"), set_gender))
telegram_app.add_handler(CommandHandler("find", find_partner))
telegram_app.add_handler(CallbackQueryHandler(handle_subscribe, pattern="subscribe"))

# ----------------- Webhook -----------------
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"status": "ok"}
