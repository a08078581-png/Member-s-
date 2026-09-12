import os
import asyncio
from datetime import datetime
from telethon import TelegramClient, events, Button
from telethon.tl.functions.messages import ExportChatInviteRequest
from telethon.tl.functions.channels import EditBannedRequest
from telethon.tl.types import ChatBannedRights
from aiohttp import web

import database as db

API_ID = int(os.environ.get("API_ID", 38398715))
API_HASH = os.environ.get("API_HASH", "6d70a41fbc67908aad547a31c3cfa9c3a")
BOT_TOKEN = os.environ.get("BOT_TOKEN")
PRIVATE_GROUP_ID = int(os.environ.get("PRIVATE_GROUP_ID", "-1005466448251"))
ADMIN_ID = int(os.environ.get("ADMIN_ID"))
UPI_ID = os.environ.get("UPI_ID", "your-upi@upi")

bot = TelegramClient('sub_manager_bot', API_ID, API_HASH)

# 1. /start command
@bot.on(events.NewMessage(pattern=r'^/start'))
async def start_handler(event):
    if not event.is_private:
        return
    buttons = [
        [Button.inline("1 Month Plan - ₹199", b"plan_1_199")],
        [Button.inline("3 Months Plan - ₹499", b"plan_3_499")]
    ]
    await event.respond(
        "👋 Welcome! Private Group access pane ke liye apna plan select karein:",
        buttons=buttons
    )

# 2. Plan Selection Callback
@bot.on(events.CallbackQuery(pattern=rb"^plan_"))
async def plan_cb(event):
    data = event.data.decode().split("_")
    months, amount = data[1], data[2]
    text = (
        f"✅ **Plan Selected:** {months} Month(s)\n"
        f"💵 **Amount:** ₹{amount}\n\n"
        f"📌 **UPI ID:** `{UPI_ID}`\n\n"
        "Kisi bhi UPI app (Paytm / GPay / PhonePe) se payment karein.\n\n"
        "Payment complete hone ke baad uska **Screenshot** ya **12-digit UTR/Txn ID** yahan send karein."
    )
    await event.respond(text)
    await event.answer()

# 3. Handle Payment Screenshots & Text (UTR)
@bot.on(events.NewMessage())
async def payment_submission(event):
    if not event.is_private or event.text.startswith('/'):
        return
    
    sender = await event.get_sender()
    sender_id = sender.id
    username = f"@{sender.username}" if sender.username else str(sender_id)

    if sender_id == ADMIN_ID:
        return

    admin_buttons = [
        [Button.inline("Approve 1 Month", f"app_{sender_id}_1".encode()),
         Button.inline("Approve 3 Months", f"app_{sender_id}_3".encode())],
        [Button.inline("Reject", f"rej_{sender_id}".encode())]
    ]

    if event.photo:
        await bot.send_file(
            ADMIN_ID,
            file=event.photo,
            caption=f"Payment Proof Aaya Hai!\nUser: {username} (`{sender_id}`)",
            buttons=admin_buttons
        )
    else:
        await bot.send_message(
            ADMIN_ID,
            f"Payment UTR/Text Mila:\n`{event.text}`\nUser: {username} (`{sender_id}`)",
            buttons=admin_buttons
        )
        
    await event.reply("Aapka payment proof mil chuka hai! Verification hote hi automatic access link mil jayegi.")

# 4. Admin Approval & Single-Use Link
@bot.on(events.CallbackQuery(pattern=rb"^(app_|rej_)"))
async def admin_decision(event):
    if event.sender_id != ADMIN_ID:
        return await event.answer("Sirf Admin approve kar sakta hai.", alert=True)

    data = event.data.decode().split("_")
    action = data[0]
    user_id = int(data[1])

    if action == "app":
        months = int(data[2])
        expiry = db.add_or_update_subscriber(user_id, months)

        try:
            invite = await bot(ExportChatInviteRequest(
                peer=PRIVATE_GROUP_ID,
                usage_limit=1
            ))
            invite_link = invite.link

            await bot.send_message(
                user_id,
                f"🎉 **Payment Verified Successfully!**\n\n"
                f"Subscription Valid Till: **{expiry.strftime('%d-%m-%Y')}**\n\n"
                f"🔗 **Group Join Link:** {invite_link}\n\n"
                "⚠️ *Yeh link sirf 1 member ke liye valid hai.*"
            )
            await event.respond(f"User `{user_id}` ko access link bhej di gayi hai.")
        except Exception as e:
            await event.respond(f"Error sending link: {e}")

    elif action == "rej":
        try:
            await bot.send_message(user_id, "❌ Aapka payment verify nahi ho saka. Kripya sahi screenshot ya UTR details bhejein.")
        except Exception:
            pass
        await event.respond(f"User `{user_id}` reject kar diya gaya.")

    await event.answer("Processed!")

# 5. Background Auto-Kick Task
async def auto_kick_worker():
    kick_rights = ChatBannedRights(until_date=None, view_messages=True)
    unban_rights = ChatBannedRights(until_date=None, view_messages=False)

    while True:
        try:
            expired = db.get_expired_users()
            for uid in expired:
                try:
                    await bot(EditBannedRequest(PRIVATE_GROUP_ID, uid, kick_rights))
                    await bot(EditBannedRequest(PRIVATE_GROUP_ID, uid, unban_rights))
                    await bot.send_message(uid, "⚠️ Aapka subscription period expire ho gaya hai. Phir se join karne ke liye /start karein.")
                except Exception as e:
                    print(f"Kick error for {uid}: {e}")
                db.remove_user(uid)
        except Exception as err:
            print(f"Worker error: {err}")
        await asyncio.sleep(3600)

# Render dummy web server
async def handle_ping(request):
    return web.Response(text="Subscription Bot is Running!")

async def start_web():
    server = web.Application()
    server.router.add_get('/', handle_ping)
    runner = web.AppRunner(server)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

async def main():
    db.init_db()
    await bot.start(bot_token=BOT_TOKEN)
    asyncio.create_task(auto_kick_worker())
    await start_web()
    print("Bot Active and Ready!")
    await bot.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
    
