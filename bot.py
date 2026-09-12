import os
import asyncio
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiohttp import web

import database as db

# Render Environment Variables
BOT_TOKEN = os.environ.get("BOT_TOKEN")
PRIVATE_GROUP_ID = int(os.environ.get("PRIVATE_GROUP_ID"))
ADMIN_ID = int(os.environ.get("ADMIN_ID"))
UPI_ID = os.environ.get("UPI_ID", "your-upi@upi")  # Render me apni actual UPI ID daalein

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# 1. /start command
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="1 Month Plan - ₹199", callback_data="plan_1_199")
    builder.button(text="3 Months Plan - ₹499", callback_data="plan_3_499")
    builder.adjust(1)
    
    await message.answer(
        "👋 Welcome! Private Group access ke liye apna plan chunein:",
        reply_markup=builder.as_markup()
    )

# 2. Plan Selection
@dp.callback_query(F.data.startswith("plan_"))
async def select_plan(callback: types.CallbackQuery):
    _, months, amount = callback.data.split("_")
    
    text = (
        f"✅ **Plan:** {months} Month(s)\n"
        f"💵 **Amount:** ₹{amount}\n\n"
        f"📌 **UPI ID:** `{UPI_ID}`\n\n"
        "Kisi bhi UPI App (PhonePe / GooglePay / Paytm) se upar di gayi UPI ID par payment karein.\n\n"
        "Payment ke baad **Transaction Screenshot** ya **12-digit UTR Number** yahan send karein."
    )
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()

# 3. Screenshot Proof Handler
@dp.message(F.photo)
async def handle_photo(message: types.Message):
    user = message.from_user
    builder = InlineKeyboardBuilder()
    builder.button(text="Approve 1 Month", callback_data=f"app_{user.id}_1")
    builder.button(text="Approve 3 Months", callback_data=f"app_{user.id}_3")
    builder.button(text="Reject", callback_data=f"rej_{user.id}")
    builder.adjust(2)
    
    await bot.send_photo(
        chat_id=ADMIN_ID,
        photo=message.photo[-1].file_id,
        caption=f"Payment Proof Aaya Hai!\nUser: @{user.username} (`{user.id}`)",
        reply_markup=builder.as_markup()
    )
    await message.answer("Aapka screenshot mil gaya hai. Verify hote hi aapko invite link mil jayega.")

# 4. Text / UTR Proof Handler
@dp.message(F.text)
async def handle_text(message: types.Message):
    if message.text.startswith('/'):
        return
    user = message.from_user
    builder = InlineKeyboardBuilder()
    builder.button(text="Approve 1 Month", callback_data=f"app_{user.id}_1")
    builder.button(text="Approve 3 Months", callback_data=f"app_{user.id}_3")
    builder.button(text="Reject", callback_data=f"rej_{user.id}")
    builder.adjust(2)
    
    await bot.send_message(
        chat_id=ADMIN_ID,
        text=f"UTR / Payment Message:\n`{message.text}`\nUser: @{user.username} (`{user.id}`)",
        reply_markup=builder.as_markup()
    )
    await message.answer("Details mil gayi hain. Verification ke baad automatic link activate ho jayegi.")

# 5. Admin Approval & Auto Single-Use Invite Link
@dp.callback_query(F.data.startswith("app_"))
async def approve_user(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("Sirf Admin approve kar sakta hai.", show_alert=True)
    
    _, user_id_str, months_str = callback.data.split("_")
    user_id = int(user_id_str)
    months = int(months_str)

    expiry = await db.add_or_update_subscriber(user_id, months)

    # 1-time usable private invite link
    invite = await bot.create_chat_invite_link(
        chat_id=PRIVATE_GROUP_ID,
        member_limit=1
    )

    try:
        await bot.send_message(
            chat_id=user_id,
            text=(
                f"🎉 **Payment Verified Successfully!**\n\n"
                f"Aapka subscription active ho gaya hai.\n"
                f"📅 Expiry Date: **{expiry.strftime('%d-%m-%Y')}**\n\n"
                f"🔗 **Group Join Link:** {invite.invite_link}\n\n"
                "⚠️ *Yeh link sirf 1 baar use hogi, kisi aur ko share na karein.*"
            ),
            parse_mode="Markdown"
        )
        await callback.message.reply(f"User `{user_id}` ko link bhej di gayi hai.")
    except Exception as e:
        await callback.message.reply(f"Link send fail: {e}")
        
    await callback.answer("Approved!")

# Reject Callback
@dp.callback_query(F.data.startswith("rej_"))
async def reject_user(callback: types.CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        return await callback.answer("Sirf Admin reject kar sakta hai.", show_alert=True)
    user_id = int(callback.data.split("_")[1])
    try:
        await bot.send_message(chat_id=user_id, text="❌ Aapka payment verify nahi ho paya. Kripya sahi screenshot ya UTR bhejein.")
    except Exception:
        pass
    await callback.answer("Rejected")

# 6. Auto-Kick Expired Users Background Task
async def auto_kick_worker():
    while True:
        try:
            expired_users = await db.get_expired_users()
            for u_id in expired_users:
                try:
                    await bot.ban_chat_member(chat_id=PRIVATE_GROUP_ID, user_id=u_id)
                    await bot.unban_chat_member(chat_id=PRIVATE_GROUP_ID, user_id=u_id)
                    await bot.send_message(chat_id=u_id, text="⚠️ Aapka subscription plan khatam ho gaya hai. Dobara judne ke liye /start karein.")
                except Exception as e:
                    print(f"Kick error for {u_id}: {e}")
                await db.remove_user(u_id)
        except Exception as err:
            print(f"Worker check error: {err}")
        await asyncio.sleep(3600)

# Render dummy web server
async def handle_ping(request):
    return web.Response(text="Subscription Bot is Running Active!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

async def main():
    await db.init_db()
    asyncio.create_task(auto_kick_worker())
    await start_web_server()
    print("Subscription Bot is Polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
    
