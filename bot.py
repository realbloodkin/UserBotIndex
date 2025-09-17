import asyncio
import time
import os
from aiohttp import web
from pyrogram import Client, filters, idle
from pyrogram.types import Message
from pyrogram.errors import FloodWait

from config import cfg
from database import db

# --- Globals & Web Server ---
userbot = None
active_tasks = {"indexing": False, "forwarding": False}

async def health_check(request):
    return web.Response(text="Hello, I am alive!")

web_app = web.Application()
web_app.add_routes([web.get('/', health_check)])

# --- Bot & Userbot Initialization (No changes here) ---
app = Client("UserbotIndexerBot", api_id=cfg.API_ID, api_hash=cfg.API_HASH, bot_token=cfg.BOT_TOKEN)

async def initialize_userbot():
    global userbot
    if cfg.SESSION_STRING:
        userbot = Client("userbot_session", session_string=cfg.SESSION_STRING, api_id=cfg.API_ID, api_hash=cfg.API_HASH)
    else:
        userbot = Client("userbot_session", api_id=cfg.API_ID, api_hash=cfg.API_HASH)
    try:
        await userbot.start()
        user_info = await userbot.get_me()
        print(f"Userbot logged in as: {user_info.first_name}")
        if not cfg.SESSION_STRING:
            session_string = await userbot.export_session_string()
            await app.send_message(cfg.ADMIN_ID, f"<b>✅ Userbot Login Successful!</b>\n\nYour <code>SESSION_STRING</code> is:\n\n<code>{session_string}</code>\n\nPlease set this in your environment variables to avoid future logins.")
        return True
    except Exception as e:
        print(f"❌ Failed to start userbot: {e}")
        await app.send_message(cfg.ADMIN_ID, f"<b>❌ Userbot Login Failed</b>\n\nError: <code>{e}</code>")
        return False

# --- Command Handlers ---
admin_filter = filters.private & filters.user(cfg.ADMIN_ID)

# Unchanged handlers: /start, /help, /status
@app.on_message(filters.command("start") & admin_filter)
async def start_handler(_, message: Message):
    if userbot and userbot.is_connected:
        await message.reply_text("👋 **Welcome!** Userbot is logged in. Send /help for commands.")
    else:
        await message.reply_text("👋 **Welcome!** Userbot is not logged in. I will attempt to initialize it now.")
        await initialize_userbot()

@app.on_message(filters.command("help") & admin_filter)
async def help_handler(_, message: Message):
    await message.reply_text(
        "**/index** `<chat_id>`\nIndexes media from a chat.\n\n"
        "**/forward** `<target_chat_id>`\nForwards all indexed files.\n\n"
        "**/status**\nShows current status."
    )

@app.on_message(filters.command("status") & admin_filter)
async def status_handler(_, message: Message):
    total_files = await db.get_total_files_count()
    await message.reply_text(
        f"**📊 Bot Status**\n\n"
        f"**Userbot Logged In:** {'✅ Yes' if userbot and userbot.is_connected else '❌ No'}\n"
        f"**Total Indexed Files:** `{total_files}`\n"
        f"**Indexing Active:** {'🏃‍♂️ Yes' if active_tasks['indexing'] else ' idle'}\n"
        f"**Forwarding Active:** {'🏃‍♂️ Yes' if active_tasks['forwarding'] else ' idle'}"
    )

# --- REVISED INDEX HANDLER ---
@app.on_message(filters.command("index") & admin_filter)
async def index_handler(_, message: Message):
    """
    Handles the /index command with a revised, safer iteration method.
    """
    if active_tasks["indexing"] or active_tasks["forwarding"]:
        await message.reply_text("❌ A task is already in progress.")
        return
    if not userbot or not userbot.is_connected:
        await message.reply_text("❌ The userbot is not logged in.")
        return
    if len(message.command) != 2:
        await message.reply_text("<b>⚠️ Invalid format.</b> Use: <code>/index &lt;chat_id&gt;</code>")
        return

    chat_id_str = message.command[1]
    chat_id = int(chat_id_str) if chat_id_str.lstrip('-').isdigit() else chat_id_str
    
    active_tasks["indexing"] = True
    status_msg = await message.reply_text(f"✅ Preparing to index chat: <code>{chat_id}</code>. This may take a moment.")

    try:
        # Get the ID of the last message to know our upper limit
        last_message = await userbot.get_chat_history(chat_id, limit=1)
        if not last_message:
            await status_msg.edit_text("🤷‍♂️ Could not find any messages in this chat.")
            active_tasks["indexing"] = False
            return
        total_messages = last_message[0].id
        await status_msg.edit_text(f"Found ~{total_messages} messages. Starting methodical indexing...")
    except Exception as e:
        await status_msg.edit_text(f"❌ **Error:** Could not access chat <code>{chat_id}</code>.\n\nDetails: <code>{e}</code>")
        active_tasks["indexing"] = False
        return

    saved_count = 0
    processed_count = 0
    start_time = time.time()
    
    # Iterate backwards from the last message ID in batches of 100
    for i in range(total_messages, 0, -100):
        # Create a list of message IDs for the current batch
        message_ids = list(range(i, max(0, i - 100), -1))
        
        try:
            # Fetch the batch of messages directly
            messages = await userbot.get_messages(chat_id, message_ids)
            
            for msg in messages:
                if not msg: continue # Skip if message was deleted
                processed_count += 1
                media = msg.document or msg.video
                if not media: continue
                
                file_data = {
                    "chat_id": msg.chat.id, "message_id": msg.id, "file_id": media.file_id,
                    "file_unique_id": media.file_unique_id, "file_name": getattr(media, 'file_name', 'N/A'),
                    "file_size": media.file_size, "caption": msg.caption.html if msg.caption else ""
                }
                await db.save_file(file_data)
                saved_count += 1

            elapsed = time.time() - start_time
            await status_msg.edit_text(
                f"**🔄 Indexing...**\n\n"
                f"**Progress:** `{processed_count} / {total_messages}` messages\n"
                f"**Files Saved:** `{saved_count}`\n"
                f"**Elapsed:** {time.strftime('%H:%M:%S', time.gmtime(elapsed))}"
            )
            
            # This delay is CRITICAL for not getting banned
            await asyncio.sleep(cfg.INDEXING_DELAY)

        except FloodWait as e:
            print(f"Rate limit hit. Sleeping for {e.value} seconds.")
            await asyncio.sleep(e.value)
        except Exception as e:
            print(f"An error occurred while fetching batch around message {i}: {e}")
            # Optional: Add a longer sleep here on error
            await asyncio.sleep(5)

    total_time = time.time() - start_time
    await status_msg.edit_text(f"**✅ Indexing Complete!**\n\n**Files Found & Saved:** `{saved_count}`\n**Duration:** {time.strftime('%Hh %Mm %Ss', time.gmtime(total_time))}")
    active_tasks["indexing"] = False


# /forward handler remains unchanged
@app.on_message(filters.command("forward") & admin_filter)
async def forward_handler(_, message: Message):
    # This function's code does not need to be changed.
    # It correctly uses the file_ids already stored in the database.
    if active_tasks["indexing"] or active_tasks["forwarding"]:
        await message.reply_text("❌ A task is already in progress.")
        return
    if not userbot or not userbot.is_connected:
        await message.reply_text("❌ The userbot is not logged in.")
        return
    if len(message.command) != 2:
        await message.reply_text("<b>⚠️ Invalid format.</b> Use: <code>/forward &lt;target_chat_id&gt;</code>")
        return

    target_chat_str = message.command[1]
    target_chat_id = int(target_chat_str) if target_chat_str.lstrip('-').isdigit() else target_chat_str
    
    active_tasks["forwarding"] = True
    status_msg = await message.reply_text("`🔍 Counting total files...`")
    total_files = await db.get_total_files_count()

    if total_files == 0:
        await status_msg.edit_text("🤷‍♂️ No files in database.")
        active_tasks["forwarding"] = False
        return

    await status_msg.edit_text(f"✅ Found **{total_files}** files. Starting forward to <code>{target_chat_id}</code>...")

    sent, error, start_time = 0, 0, time.time()
    
    async for file_doc in db.get_all_files():
        try:
            await userbot.send_document(target_chat_id, file_doc["file_id"], caption=file_doc.get("caption", ""))
            sent += 1
        except FloodWait as e:
            await asyncio.sleep(e.value)
            await userbot.send_document(target_chat_id, file_doc["file_id"], caption=file_doc.get("caption", ""))
            sent += 1
        except Exception as e:
            error += 1
            print(f"Failed to send file {file_doc['file_id']}: {e}")

        if (sent + error) % 10 == 0:
            elapsed = time.time() - start_time
            await status_msg.edit_text(f"**🔄 Forwarding...**\n\n**Sent:** `{sent}/{total_files}`\n**Errors:** `{error}`\n**Elapsed:** {time.strftime('%H:%M:%S', time.gmtime(elapsed))}")

        await asyncio.sleep(cfg.FORWARD_DELAY)

    total_time = time.time() - start_time
    await status_msg.edit_text(f"**✅ Forwarding Complete!**\n\n**Sent:** `{sent}`\n**Failed:** `{error}`\n**Duration:** {time.strftime('%Hh %Mm', time.gmtime(total_time))}")
    active_tasks["forwarding"] = False


# --- Main Execution (No changes here) ---
async def main():
    await asyncio.gather(app.start(), initialize_userbot())
    runner = web.AppRunner(web_app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"✅ Web server started on port {port}")
    await idle()
    await runner.cleanup()
    await app.stop()
    if userbot and userbot.is_connected:
        await userbot.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped.")
