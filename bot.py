import os
import time
import asyncio
import uuid
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiohttp import web

import database as db

BOT_TOKEN = os.environ.get("BOT_TOKEN")
PRIVATE_GROUP_ID = int(os.environ.get("PRIVATE_GROUP_ID"))
UPI_GATEWAY_KEY = os.environ.get("UPI_GATEWAY_KEY", "YOUR_GATEWAY_KEY")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# 1. /start Command - Plans Show Karega
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    builder = InlineKeyboardBuilder()
    builder.button(text="1 Month - ₹199", callback_data="plan_1_199")
    builder.button(text="3 Months - ₹499", callback_data="plan_3_499")
    builder.adjust(1)
    
    await message.answer(
        "👋 Welcome! Hamare Private Group ka premium access lene ke liye plan select karein:",
        reply_markup=builder.as_markup()
    )

# 2. Automated Payment Link Generator
@dp.callback_query(F.data.startswith("plan_"))
async def create_payment_order(callback: types.CallbackQuery):
    _, months_str, amount_str = callback.data.split("_")
    months = int(months_str)
    amount = float(amount_str)
    user_id = callback.from_user.id
    
    order_id = f"SUB_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    await db.create_order(order_id, user_id, months)
    
    # Standard UPI Payment Gateway URL
    payment_url = f"https://api.ekqr.in/api/create_order?key={UPI_GATEWAY_KEY}&client_txn_id={order_id}&amount={amount}&p_info=Subscription&customer_name={user_id}&customer_email=user@bot.com&customer_mobile=9999999999&redirect_url=https://t.me/"
    
    builder = InlineKeyboardBuilder()
    builder.button(text=f"Pay ₹{amount} Now (UPI)", url=payment_url)
    builder.button(text="Check Status", callback_data=f"check_{order_id}")
    builder.adjust(1)

    await callback.message.answer(
        f"💳 **Order Created!**\n\n"
        f"• Plan: **{months} Month(s)**\n"
        f"• Amount: **₹{amount}**\n"
        f"• Order ID: `{order_id}`\n\n"
        "Neeche button par click karke GPay/PhonePe/Paytm se pay karein. Payment hone ke baad bot turant aapko join link bhej dega.",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown"
    )
    await callback.answer()

# 3. Manual Status Check Button
@dp.callback_query(F.data.startswith("check_"))
async def check_status_btn(callback: types.CallbackQuery):
    order_id = callback.data.split("_")[1]
    order = await db.get_order(order_id)
    if order and order[2] == "PAID":
        await callback.answer("Payment already verified!", show_alert=True)
    else:
        await callback.answer("Payment verify nahi hua hai. Agar aap pay kar chuke hain toh 1 minute wait karein.", show_alert=True)

# 4. Webhook Server: Payment Gateway Instant Callback
async def handle_payment_webhook(request):
    try:
        data = await request.post()
        if not data:
            data = await request.json()

        # Gateway response verification
        status = data.get("status")
        order_id = data.get("client_txn_id")

        if status == "success" and order_id:
            order = await db.get_order(order_id)
            if order and order[2] != "PAID":
                user_id, months, _ = order
                await db.mark_order_paid(order_id)
                expiry = await db.add_or_update_subscriber(user_id, months)

                # Generate 1-time single use invite link
                invite_link = await bot.create_chat_invite_link(
                    chat_id=PRIVATE_GROUP_ID,
                    member_limit=1
                )

                # Send link to user
                await bot.send_message(
                    chat_id=user_id,
                    text=(
                        f"🎉 **Payment Successful!**\n\n"
                        f"Aapka membership activate ho gaya hai.\n"
                        f"📅 Expiry Date: **{expiry.strftime('%d-%m-%Y')}**\n\n"
                        f"🔗 **Group Join Link:** {invite_link.invite_link}\n\n"
                        "⚠️ *Yeh link sirf aapke liye hai aur ek baar join karne ke baad expire ho jayegi.*"
                    ),
                    parse_mode="Markdown"
                )
        return web.Response(text="OK")
    except Exception as e:
        print(f"Webhook error: {e}")
        return web.Response(text="Error", status=500)

async def handle_ping(request):
    return web.Response(text="Bot is running active!")

# 5. Background Task: Auto Kick Expired Members
async def auto_kick_worker():
    while True:
        try:
            expired_users = await db.get_expired_users()
            for u_id in expired_users:
                try:
                    await bot.ban_chat_member(chat_id=PRIVATE_GROUP_ID, user_id=u_id)
                    await bot.unban_chat_member(chat_id=PRIVATE_GROUP_ID, user_id=u_id)
                    await bot.send_message(
                        chat_id=u_id,
                        text="⚠️ Aapka subscription plan expire ho gaya hai. Dobara access paane ke liye /start karein."
                    )
                except Exception as e:
                    print(f"Auto-kick issue for {u_id}: {e}")
                
                await db.remove_user(u_id)
        except Exception as err:
            print(f"Worker check error: {err}")
        
        # Har 1 hour me check karega
        await asyncio.sleep(3600)

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle_ping)
    app.router.add_post('/webhook', handle_payment_webhook)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

async def main():
    await db.init_db()
    asyncio.create_task(auto_kick_worker())
    await start_web_server()
    print("Bot polling started...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
      
