import os
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, CallbackQueryHandler, ContextTypes
from database import User, get_db, SessionLocal
from sqlalchemy.orm import Session

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN is missing. Please set it in Render environment variables.")

OWNER_IDS = [5518634633, 108099033]  # Your Telegram IDs

app = FastAPI()
telegram_app = Application.builder().token(BOT_TOKEN).build()

# Helper: get or create user
def get_or_create_user(telegram_id: int, db: Session):
    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    if not user:
        user = User(telegram_id=telegram_id, chats_seen=0, subscribed=False, likes=0, dislikes=0)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user

# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    get_or_create_user(update.effective_user.id, db)
    await update.message.reply_text("👋 Welcome! Send your gender (M/F) to start.")

# Set gender handler
async def set_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    gender = update.message.text.upper()
    if gender not in ["M", "F"]:
        await update.message.reply_text("❌ Please send only 'M' or 'F'.")
        return
    db = SessionLocal()
    user = get_or_create_user(update.effective_user.id, db)
    if user.gender and user.gender != gender:
        # Changing gender does NOT reset chats_seen as per your requirement
        user.gender = gender
        db.commit()
        await update.message.reply_text(f"✅ Gender updated to {gender}. Free chat limit remains the same.")
    elif not user.gender:
        user.gender = gender
        db.commit()
        await update.message.reply_text(f"✅ Gender set to {gender}. You can now find partners using /find.")
    else:
        await update.message.reply_text(f"ℹ️ Your gender is already set to {gender}.")

# Find partner handler
async def find_partner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    user = get_or_create_user(update.effective_user.id, db)
    if not user.gender:
        await update.message.reply_text("⚠️ Please set your gender first by sending 'M' or 'F'.")
        return

    # Check free limit
    if user.chats_seen >= 5 and not user.subscribed:
        spoiler_text = "||⚠️ Free chat limit reached. Please subscribe to continue chatting.||"
        button = InlineKeyboardButton("Subscribe for $2/month", callback_data="subscribe")
        await update.message.reply_text(
            spoiler_text,
            reply_markup=InlineKeyboardMarkup([[button]]),
            parse_mode="MarkdownV2",
        )
        return

    # Find partner of opposite gender
    partner = (
        db.query(User)
        .filter(User.gender != user.gender)
        .filter(User.telegram_id != user.telegram_id)
        .first()
    )
    if partner:
        user.chats_seen += 1
        db.commit()

        # If user subscribed or under limit, show partner gender else spoiler
        if user.subscribed or user.chats_seen <= 5:
            msg = f"💬 Matched with partner (Gender: {partner.gender})"
            # Owner sees Telegram ID as well
            if update.effective_user.id in OWNER_IDS:
                msg += f"\n🔎 (Owner view) Partner ID: {partner.telegram_id}"
            # Send partner info
            await update.message.reply_text(msg)
        else:
            # Spoiler instead of gender
            spoiler_msg = "Matched partner gender: ||Subscription needed to view||"
            await update.message.reply_text(spoiler_msg, parse_mode="MarkdownV2")

        # Show thumbs up/down inline buttons to rate after chat ended
        buttons = [
            InlineKeyboardButton("👍", callback_data=f"like_{partner.telegram_id}"),
            InlineKeyboardButton("👎", callback_data=f"dislike_{partner.telegram_id}"),
        ]
        await update.message.reply_text("Rate your partner:", reply_markup=InlineKeyboardMarkup([buttons]))
    else:
        await update.message.reply_text("😞 No partner found right now. Try again later.")

# Subscribe callback
async def handle_subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    user = get_or_create_user(update.effective_user.id, db)
    user.subscribed = True
    db.commit()
    await update.callback_query.answer("Subscribed successfully! 🎉")
    await update.callback_query.edit_message_text("✅ You are now subscribed!")

# Like/dislike callback
async def handle_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    db = SessionLocal()

    if data.startswith("like_") or data.startswith("dislike_"):
        action, partner_id_str = data.split("_")
        partner_id = int(partner_id_str)
        partner = db.query(User).filter(User.telegram_id == partner_id).first()
        if not partner:
            await query.answer("User not found.")
            return

        if action == "like":
            partner.likes += 1
            await query.answer("You liked this partner 👍")
        else:
            partner.dislikes += 1
            await query.answer("You disliked this partner 👎")

        db.commit()
        await query.edit_message_text("Thank you for your feedback!")

# Register handlers
telegram_app.add_handler(CommandHandler("start", start))
telegram_app.add_handler(MessageHandler(filters.Regex("^(M|F|m|f)$"), set_gender))
telegram_app.add_handler(CommandHandler("find", find_partner))
telegram_app.add_handler(CallbackQueryHandler(handle_subscribe, pattern="subscribe"))
telegram_app.add_handler(CallbackQueryHandler(handle_rating, pattern="^(like|dislike)_"))

# Webhook endpoint
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, telegram_app.bot)
    await telegram_app.process_update(update)
    return {"status": "ok"}
