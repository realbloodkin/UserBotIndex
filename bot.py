import asyncio
import time
from pyrogram import Client, filters, idle
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from aiohttp import web

from config import cfg
from database import db
from plugins.routes import routes

# --- Filters ---
admin_filter = filters.private & filters.user(cfg.ADMIN_ID)

class Bot(Client):
    """
    Main Bot class that inherits from Pyrogram's Client.
    It handles both the Telegram bot and the web server.
    """
    def __init__(self):
        super().__init__(
            "UserbotIndexerBot",
            api_id=cfg.API_ID,
            api_hash=cfg.API_HASH,
            bot_token=cfg.BOT_TOKEN
        )
        self.userbot = None
        self.active_tasks = {"indexing": False, "forwarding": False}

    async def start_services(self):
        """Starts the Pyrogram client and the aiohttp web server."""
        await super().start()
        print("✅ Main bot started successfully.")

        # Initialize the userbot
        await self.initialize_userbot()

        # Setup and start the web server
        app = web.Application()
        app.add_routes(routes)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', getattr(cfg, 'PORT', 8080))
        await site.start()
        print(f"✅ Web server started on port {getattr(cfg, 'PORT', 8080)}.")
        
        print("🚀 Bot is now running and listening for commands.")
        await idle()
        
        print("Shutting down...")
        await self.stop()
        if self.userbot and self.userbot.is_connected:
            await self.userbot.stop()

    async def initialize_userbot(self):
        """Initializes the userbot client from a session string or through interactive login."""
        if cfg.SESSION_STRING:
            print("INFO: Attempting to log in with session string...")
            self.userbot = Client("userbot_session", session_string=cfg.SESSION_STRING, api_id=cfg.API_ID, api_hash=cfg.API_HASH)
        else:
            print("WARNING: No session string found. Starting interactive login...")
            self.userbot = Client("userbot_session", api_id=cfg.API_ID, api_hash=cfg.API_HASH)

        try:
            await self.userbot.start()
            user_info = await self.userbot.get_me()
            print(f"✅ Userbot logged in as: {user_info.first_name} (@{user_info.username})")

            if not cfg.SESSION_STRING:
                session_string = await self.userbot.export_session_string()
                startup_message = (
                    "<b>✅ Userbot login successful!</b>\n\n"
                    "To avoid this interactive login in the future, please set the following value as the "
                    "<code>SESSION_STRING</code> environment variable:\n\n"
                    f"<code>{session_string}</code>\n\n"
                    "The bot is now ready. Send /help for commands."
                )
                await self.send_message(cfg.ADMIN_ID, startup_message)
            return True
        except Exception as e:
            print(f"❌ ERROR: Failed to start userbot: {e}")
            await self.send_message(cfg.ADMIN_ID, f"<b>❌ Userbot Login Failed</b>\n\nError: <code>{e}</code>\n\nPlease check your credentials and restart the bot.")
            return False

    def run(self):
        """A convenience method to run the start_services coroutine."""
        super().run(self.start_services())

# --- Bot Instance ---
app = Bot()

# --- Command Handlers ---

@app.on_message(filters.command("start") & admin_filter)
async def start_handler(client: Bot, message: Message):
    if client.userbot and client.userbot.is_connected:
        await message.reply_text("👋 **Welcome!**\n\nThe userbot is logged in and I'm ready to work. Send /help to see commands.")
    else:
        await message.reply_text("👋 **Welcome!**\n\nThe userbot isn't logged in yet. I will try to initialize it now. Check your terminal for login prompts if needed.")
        await client.initialize_userbot()

@app.on_message(filters.command("help") & admin_filter)
async def help_handler(_, message: Message):
    help_text = (
        "**Userbot Indexer & Forwarder**\n\n"
        "Here are the available commands:\n\n"
        "**/index** `<chat_id>`\n"
        "Starts indexing all media files from the specified chat.\n\n"
        "**/forward** `<target_chat_id>`\n"
        "Forwards all indexed files to the specified target chat.\n\n"
        "**/status**\n"
        "Shows the current status of the bot and indexed files."
    )
    await message.reply_text(help_text)

@app.on_message(filters.command("status") & admin_filter)
async def status_handler(client: Bot, message: Message):
    total_files = await db.get_total_files_count()
    status_text = (
        f"**📊 Bot Status**\n\n"
        f"**Userbot Logged In:** {'✅ Yes' if client.userbot and client.userbot.is_connected else '❌ No'}\n"
        f"**Total Indexed Files:** `{total_files}`\n"
        f"**Indexing Active:** {'🏃‍♂️ Yes' if client.active_tasks['indexing'] else ' idle'}\n"
        f"**Forwarding Active:** {'🏃‍♂️ Yes' if client.active_tasks['forwarding'] else ' idle'}"
    )
    await message.reply_text(status_text)

@app.on_message(filters.command("index") & admin_filter)
async def index_handler(client: Bot, message: Message):
    if client.active_tasks["indexing"] or client.active_tasks["forwarding"]:
        await message.reply_text("❌ A task is already in progress. Please wait for it to complete.")
        return
        
    if not client.userbot or not client.userbot.is_connected:
        await message.reply_text("❌ The userbot is not logged in. Please restart and complete the login process.")
        return

    if len(message.command) != 2:
        await message.reply_text("<b>⚠️ Invalid command format.</b>\n\nUse: <code>/index &lt;chat_id&gt;</code>")
        return

    chat_id_str = message.command[1]
    try:
        chat_id = int(chat_id_str) if chat_id_str.lstrip('-').isdigit() else chat_id_str
    except ValueError:
        await message.reply_text("❌ Invalid Chat ID provided.")
        return

    client.active_tasks["indexing"] = True
    status_msg = await message.reply_text(f"✅ Starting indexing for chat: <code>{chat_id}</code>...")
    
    try:
        await client.userbot.get_chat(chat_id)
    except Exception as e:
        await status_msg.edit_text(f"❌ **Error:** Could not access chat <code>{chat_id}</code>.\n\nDetails: <code>{e}</code>")
        client.active_tasks["indexing"] = False
        return

    saved_count = 0
    start_time = time.time()
    
    async for msg in client.userbot.get_chat_history(chat_id):
        media = msg.document or msg.video
        if not media:
            continue
        
        file_data = {
            "chat_id": msg.chat.id, "message_id": msg.id, "file_id": media.file_id,
            "file_unique_id": media.file_unique_id, "file_name": getattr(media, 'file_name', 'N/A'),
            "file_size": media.file_size, "caption": msg.caption.html if msg.caption else ""
        }
        await db.save_file(file_data)
        saved_count += 1

        if saved_count % 50 == 0:
            elapsed = time.time() - start_time
            await status_msg.edit_text(f"**🔄 Indexing...**\n\n**Chat:** `{chat_id}`\n**Files Saved:** `{saved_count}`\n**Time:** {time.strftime('%H:%M:%S', time.gmtime(elapsed))}")
    
    total_time = time.time() - start_time
    await status_msg.edit_text(f"**✅ Indexing Complete!**\n\n**Chat:** `{chat_id}`\n**New/Updated Files:** `{saved_count}`\n**Duration:** {time.strftime('%Hh %Mm %Ss', time.gmtime(total_time))}")
    client.active_tasks["indexing"] = False

@app.on_message(filters.command("forward") & admin_filter)
async def forward_handler(client: Bot, message: Message):
    if client.active_tasks["indexing"] or client.active_tasks["forwarding"]:
        await message.reply_text("❌ A task is already in progress. Please wait for it to complete.")
        return
        
    if not client.userbot or not client.userbot.is_connected:
        await message.reply_text("❌ The userbot is not logged in. Please restart the bot.")
        return

    if len(message.command) != 2:
        await message.reply_text("<b>⚠️ Invalid command format.</b>\n\nUse: <code>/forward &lt;target_chat_id&gt;</code>")
        return

    target_chat_str = message.command[1]
    try:
        target_chat_id = int(target_chat_str) if target_chat_str.lstrip('-').isdigit() else target_chat_str
    except ValueError:
        await message.reply_text("❌ Invalid Target Chat ID provided.")
        return

    client.active_tasks["forwarding"] = True
    status_msg = await message.reply_text("`🔍 Counting total files...`")
    total_files = await db.get_total_files_count()

    if total_files == 0:
        await status_msg.edit_text("🤷‍♂️ The database is empty. No files to forward.")
        client.active_tasks["forwarding"] = False
        return

    await status_msg.edit_text(f"✅ Found **{total_files}** files. Starting to forward to <code>{target_chat_id}</code>...")

    sent_count, error_count = 0, 0
    start_time = time.time()
    
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
            try:
                await client.userbot.send_document(target_chat_id, file_doc.get("file_id"), caption=file_doc.get("caption", ""))
                sent_count += 1
            except Exception as retry_e:
                error_count += 1
                print(f"ERROR: Failed to send file {file_doc.get('file_id')} after waiting. Error: {retry_e}")
        except Exception as e:
            error_count += 1
            print(f"ERROR: Could not send file {file_doc.get('file_id')}. Error: {e}")

        if (sent_count + error_count) % 10 == 0:
            elapsed = time.time() - start_time
            await status_msg.edit_text(f"**🔄 Forwarding...**\n\n**Sent:** `{sent_count}/{total_files}`\n**Errors:** `{error_count}`\n**Time:** {time.strftime('%H:%M:%S', time.gmtime(elapsed))}")

        await asyncio.sleep(cfg.FORWARD_DELAY)

    total_time = time.time() - start_time
    await status_msg.edit_text(f"**✅ Forwarding Complete!**\n\n**Sent:** `{sent_count}`\n**Failed:** `{error_count}`\n**Duration:** {time.strftime('%Hh %Mm', time.gmtime(total_time))}")
    client.active_tasks["forwarding"] = False

# --- Main Execution ---
if __name__ == "__main__":
    try:
        app.run()
    except KeyboardInterrupt:
        print("Bot stopped by user.")
