import os
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from aiohttp import web

import database as db

BOT_TOKEN = os.environ.get("BOT_TOKEN")
PRIVATE_GROUP_ID = int(os.environ.get("PRIVATE_GROUP_ID"))
ADMIN_ID = int(os.environ.get("ADMIN_ID"))
UPI_ID = os.environ.get("UPI_ID", "your-upi@upi")

# 1. /start command
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("1 Month Plan - ₹199", callback_data="plan_1_199")],
        [InlineKeyboardButton("3 Months Plan - ₹499", callback_data="plan_3_499")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "👋 Welcome! Private Group access ke liye apna plan chunein:",
        reply_markup=reply_markup
    )

# 2. Plan Select Callback
async def plan_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    _, months, amount = query.data.split("_")
    text = (
        f"✅ **Plan:** {months} Month(s)\n"
        f"💵 **Amount:** ₹{amount}\n\n"
        f"📌 **UPI ID:** `{UPI_ID}`\n\n"
        "Kisi bhi UPI App (PhonePe / GooglePay / Paytm) se upar di gayi UPI ID par payment karein.\n\n"
        "Payment ke baad **Transaction Screenshot** ya **12-digit UTR Number** yahan send karein."
    )
    await query.message.reply_text(text, parse_mode="Markdown")

# 3. Screenshot Handler
async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    keyboard = [
        [InlineKeyboardButton("Approve 1 Month", callback_data=f"app_{user.id}_1"),
         InlineKeyboardButton("Approve 3 Months", callback_data=f"app_{user.id}_3")],
        [InlineKeyboardButton("Reject", callback_data=f"rej_{user.id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await context.bot.send_photo(
        chat_id=ADMIN_ID,
        photo=update.message.photo[-1].file_id,
        caption=f"Payment Proof Aaya Hai!\nUser: @{user.username} (`{user.id}`)",
        reply_markup=reply_markup
    )
    await update.message.reply_text("Aapka screenshot mil gaya hai. Verify hote hi invite link mil jayega.")

# 4. Text / UTR Handler
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user
    keyboard = [
        [InlineKeyboardButton("Approve 1 Month", callback_data=f"app_{user.id}_1"),
         InlineKeyboardButton("Approve 3 Months", callback_data=f"app_{user.id}_3")],
        [InlineKeyboardButton("Reject", callback_data=f"rej_{user.id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await context.bot.send_message(
        chat_id=ADMIN_ID,
        text=f"Payment Proof / UTR:\n`{update.message.text}`\nUser: @{user.username} (`{user.id}`)",
        reply_markup=reply_markup
    )
    await update.message.reply_text("Details mil gayi hain. Verify hone par link mil jayega.")

# 5. Approval Handler
async def approval_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.from_user.id != ADMIN_ID:
        return

    data = query.data
    if data.startswith("app_"):
        _, user_id_str, months_str = data.split("_")
        user_id = int(user_id_str)
        months = int(months_str)

        expiry = await db.add_or_update_subscriber(user_id, months)
        invite = await context.bot.create_chat_invite_link(
            chat_id=PRIVATE_GROUP_ID,
            member_limit=1
        )

        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=(
                    f"🎉 **Payment Verified!**\n\n"
                    f"Subscription valid till: **{expiry.strftime('%d-%m-%Y')}**\n\n"
                    f"🔗 **Join Link:** {invite.invite_link}\n\n"
                    "⚠️ *Yeh link sirf 1 baar use ho sakti hai.*"
                ),
                parse_mode="Markdown"
            )
            await query.message.reply_text(f"User `{user_id}` ko invite link bhej di gayi hai.")
        except Exception as e:
            await query.message.reply_text(f"Send fail: {e}")

    elif data.startswith("rej_"):
        user_id = int(data.split("_")[1])
        try:
            await context.bot.send_message(chat_id=user_id, text="❌ Payment verify nahi ho paya.")
        except Exception:
            pass
        await query.message.reply_text(f"User `{user_id}` rejected.")

# 6. Background Auto-Kick Task
async def auto_kick_worker(app: Application):
    while True:
        try:
            expired_users = await db.get_expired_users()
            for u_id in expired_users:
                try:
                    await app.bot.ban_chat_member(chat_id=PRIVATE_GROUP_ID, user_id=u_id)
                    await app.bot.unban_chat_member(chat_id=PRIVATE_GROUP_ID, user_id=u_id)
                    await app.bot.send_message(chat_id=u_id, text="⚠️ Subscription expire ho gaya hai. Dobara join karne ke liye /start karein.")
                except Exception as e:
                    print(f"Kick error {u_id}: {e}")
                await db.remove_user(u_id)
        except Exception as err:
            print(f"Worker error: {err}")
        await asyncio.sleep(3600)

# Web server for Render
async def handle_ping(request):
    return web.Response(text="Bot is running active!")

async def start_web():
    server = web.Application()
    server.router.add_get('/', handle_ping)
    runner = web.AppRunner(server)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

async def main():
    await db.init_db()
    
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CallbackQueryHandler(plan_callback, pattern=r"^plan_"))
    app.add_handler(CallbackQueryHandler(approval_callback, pattern=r"^(app_|rej_)"))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    asyncio.create_task(auto_kick_worker(app))
    await start_web()

    while True:
        await asyncio.sleep(1000)

if __name__ == "__main__":
    asyncio.run(main())
    
