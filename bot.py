import asyncio
import time
from pyrogram import Client, filters, idle
from pyrogram.types import Message
from pyrogram.errors import FloodWait, ApiIdInvalid, AuthKeyUnregistered
from aiohttp import web

# Import your configuration and database files
from config import cfg
from database import db

# --- Main Bot Class ---
class Bot(Client):
    def __init__(self):
        super().__init__(
            "UserbotIndexerBot",
            api_id=cfg.API_ID,
            api_hash=cfg.API_HASH,
            bot_token=cfg.BOT_TOKEN
        )
        self.userbot = None
        self.active_tasks = {"indexing": False, "forwarding": False}
        self.admin_filter = filters.private & filters.user(cfg.ADMIN_ID)

    async def start_services(self):
        """Starts all bot services, including the web server."""
        await super().start()
        me = await self.get_me()
        print(f"✅ Bot connected as @{me.username}")

        await self.initialize_userbot()

        app = web.Application()
        app.add_routes([web.get('/', lambda r: web.json_response({"status": "running"}))])
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', cfg.PORT)
        await site.start()
        print(f"✅ Web server running on http://0.0.0.0:{cfg.PORT}")
        print("🚀 Bot is fully operational.")
        await idle()

    async def initialize_userbot(self):
        """Logs in the userbot account."""
        if not cfg.SESSION_STRING:
            print("INFO: No session string found, userbot will not be started.")
            return
            
        print("INFO: Initializing userbot from session string...")
        self.userbot = Client("userbot_session", session_string=cfg.SESSION_STRING, api_id=cfg.API_ID, api_hash=cfg.API_HASH)
        try:
            await self.userbot.start()
            user_info = await self.userbot.get_me()
            print(f"✅ Userbot logged in as: {user_info.first_name}")
        except Exception as e:
            print(f"❌ Userbot login failed: {e}")
            self.userbot = None

# --- Initialize Bot Instance ---
try:
    app = Bot()
except Exception as e:
    print(f"❌ Failed to initialize bot: {e}")
    exit()

# --- Command Handlers ---

@app.on_message(filters.command("start") & app.admin_filter)
async def start_handler(client: Bot, message: Message):
    if client.userbot and client.userbot.is_connected:
        await message.reply_text("👋 **Welcome!**\n\nThe userbot is logged in and ready. Send /help for a list of commands.")
    else:
        await message.reply_text("👋 **Welcome!**\n\nTo begin, please set your `SESSION_STRING` and restart the bot to log in the userbot.")

@app.on_message(filters.command("help") & app.admin_filter)
async def help_handler(_, message: Message):
    await message.reply_text(
        "**Here are the available commands:**\n\n"
        "**/index** `<chat_id>`\n"
        "Index all media from a specific chat.\n\n"
        "**/forward** `<target_chat_id>`\n"
        "Forward all indexed media to a target chat.\n\n"
        "**/status**\n"
        "Show the current status and number of indexed files."
    )

@app.on_message(filters.command("status") & app.admin_filter)
async def status_handler(client: Bot, message: Message):
    total_files = await db.get_total_files_count()
    await message.reply_text(
        f"**📊 Bot Status**\n\n"
        f"**Userbot Logged In:** {'✅ Yes' if client.userbot and client.userbot.is_connected else '❌ No'}\n"
        f"**Total Indexed Files:** `{total_files}`\n"
        f"**Indexing Active:** {'🏃‍♂️ Yes' if client.active_tasks['indexing'] else ' idle'}\n"
        f"**Forwarding Active:** {'🏃‍♂️ Yes' if client.active_tasks['forwarding'] else ' idle'}"
    )

@app.on_message(filters.command("index") & app.admin_filter)
async def index_handler(client: Bot, message: Message):
    if client.active_tasks["indexing"] or client.active_tasks["forwarding"]:
        return await message.reply_text("❌ A task is already in progress.")
    if not client.userbot or not client.userbot.is_connected:
        return await message.reply_text("❌ Userbot is not logged in.")
    if len(message.command) != 2:
        return await message.reply_text("<b>Usage:</b> <code>/index &lt;chat_id&gt;</code>")

    chat_id_str = message.command[1]
    client.active_tasks["indexing"] = True
    status_msg = await message.reply_text(f"✅ Starting indexing for chat: <code>{chat_id_str}</code>...")
    
    saved_count = 0
    start_time = time.time()
    try:
        chat_id = int(chat_id_str) if chat_id_str.lstrip('-').isdigit() else chat_id_str
        async for msg in client.userbot.get_chat_history(chat_id):
            media = msg.document or msg.video
            if not media: continue
            
            file_data = { "chat_id": msg.chat.id, "message_id": msg.id, "file_id": media.file_id, "file_unique_id": media.file_unique_id, "file_name": getattr(media, 'file_name', 'N/A'), "file_size": media.file_size, "caption": msg.caption.html if msg.caption else "" }
            await db.save_file(file_data)
            saved_count += 1

            if saved_count % 50 == 0:
                elapsed = time.time() - start_time
                await status_msg.edit_text(f"**🔄 Indexing...** `{saved_count}` files saved.\n**Time:** {time.strftime('%H:%M:%S', time.gmtime(elapsed))}")
    except Exception as e:
        await status_msg.edit_text(f"❌ **Error during indexing:**\n`{e}`")
    else:
        total_time = time.time() - start_time
        await status_msg.edit_text(f"**✅ Indexing Complete!**\n\n**New Files:** `{saved_count}`\n**Duration:** {time.strftime('%Hh %Mm %Ss', time.gmtime(total_time))}")
    finally:
        client.active_tasks["indexing"] = False

@app.on_message(filters.command("forward") & app.admin_filter)
async def forward_handler(client: Bot, message: Message):
    """Handles the /forward command to send all indexed files."""
    if client.active_tasks["indexing"] or client.active_tasks["forwarding"]:
        return await message.reply_text("❌ A task is already in progress.")
    if not client.userbot or not client.userbot.is_connected:
        return await message.reply_text("❌ Userbot is not logged in.")
    if len(message.command) != 2:
        return await message.reply_text("<b>Usage:</b> <code>/forward &lt;target_chat_id&gt;</code>")

    target_chat_str = message.command[1]
    client.active_tasks["forwarding"] = True
    status_msg = await message.reply_text("`🔍 Counting total files...`")
    
    sent_count, error_count = 0, 0
    start_time = time.time()
    try:
        total_files = await db.get_total_files_count()
        if total_files == 0:
            client.active_tasks["forwarding"] = False
            return await status_msg.edit_text("🤷‍♂️ The database is empty. No files to forward.")

        target_chat_id = int(target_chat_str) if target_chat_str.lstrip('-').isdigit() else target_chat_str
        await status_msg.edit_text(f"✅ Found **{total_files}** files. Starting to forward to <code>{target_chat_id}</code>...")
        
        all_files = db.get_all_files()
        async for file_doc in all_files:
            try:
                await client.userbot.send_document(
                    chat_id=target_chat_id, document=file_doc.get("file_id"), caption=file_doc.get("caption", "")
                )
                sent_count += 1
            except FloodWait as e:
                print(f"INFO: Rate limit exceeded. Waiting for {e.value} seconds.")
                await asyncio.sleep(e.value)
                await client.userbot.send_document(target_chat_id, file_doc.get("file_id"), caption=file_doc.get("caption", ""))
                sent_count += 1
            except Exception as e:
                error_count += 1
                print(f"ERROR: Could not send file {file_doc.get('file_id')}. Error: {e}")

            if (sent_count + error_count) % 10 == 0:
                elapsed = time.time() - start_time
                await status_msg.edit_text(f"**🔄 Forwarding...**\n\n**Sent:** `{sent_count}/{total_files}`\n**Errors:** `{error_count}`\n**Time:** {time.strftime('%H:%M:%S', time.gmtime(elapsed))}")
            
            await asyncio.sleep(cfg.FORWARD_DELAY)
    except Exception as e:
        await status_msg.edit_text(f"❌ **An error occurred during forwarding:**\n`{e}`")
    else:
        total_time = time.time() - start_time
        await status_msg.edit_text(f"**✅ Forwarding Complete!**\n\n**Sent:** `{sent_count}`\n**Failed:** `{error_count}`\n**Duration:** {time.strftime('%Hh %Mm', time.gmtime(total_time))}")
    finally:
        client.active_tasks["forwarding"] = False

# --- Main Execution ---
if __name__ == "__main__":
    try:
        app.run(app.start_services())
    except (ApiIdInvalid, AuthKeyUnregistered):
        print("❌ CRITICAL: Your API_ID/HASH or BOT_TOKEN is invalid. Please check your .env file.")
    except KeyboardInterrupt:
        print("\nBot stopped by user.")
    except Exception as e:
        print(f"❌ An unexpected error occurred: {e}")
