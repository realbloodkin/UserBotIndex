import asyncio
import time
from pyrogram import Client, filters, idle
from pyrogram.types import Message
from pyrogram.errors import FloodWait, UserNotParticipant, ChatAdminRequired
from pyrogram.enums import ParseMode

from config import cfg
from database import db

# --- Globals ---
# The userbot client instance will be stored here after login
userbot = None
# A dictionary to keep track of ongoing tasks to prevent multiple tasks at once
active_tasks = {"indexing": False, "forwarding": False}


# --- Bot Initialization ---
# This is the main bot that interacts with the user
app = Client(
    "UserbotIndexerBot",
    api_id=cfg.API_ID,
    api_hash=cfg.API_HASH,
    bot_token=cfg.BOT_TOKEN
)


# --- Userbot Session Management ---
async def initialize_userbot():
    """

    Initializes the userbot client. It first tries to log in using a session string.
    If that fails or isn't provided, it falls back to an interactive login process.
    """
    global userbot
    if cfg.SESSION_STRING:
        print("Attempting to log in with session string...")
        userbot = Client("userbot_session", session_string=cfg.SESSION_STRING, api_id=cfg.API_ID, api_hash=cfg.API_HASH)
    else:
        print("No session string found. Starting interactive login...")
        userbot = Client("userbot_session", api_id=cfg.API_ID, api_hash=cfg.API_HASH)

    try:
        await userbot.start()
        user_info = await userbot.get_me()
        print(f"Userbot logged in as: {user_info.first_name} (@{user_info.username})")
        
        # If login was interactive, generate and send the session string for future use
        if not cfg.SESSION_STRING:
            session_string = await userbot.export_session_string()
            startup_message = (
                "<b>✅ Userbot login successful!</b>\n\n"
                "To avoid this interactive login in the future, please set the following value as the "
                "<code>SESSION_STRING</code> environment variable:\n\n"
                f"<code>{session_string}</code>\n\n"
                "The bot is now ready. Send /help for commands."
            )
            await app.send_message(cfg.ADMIN_ID, startup_message)
            
        return True
    except Exception as e:
        print(f"❌ Failed to start userbot: {e}")
        await app.send_message(cfg.ADMIN_ID, f"<b>❌ Userbot Login Failed</b>\n\nError: <code>{e}</code>\n\nPlease check your credentials and restart the bot.")
        return False


# --- Command Handlers ---
admin_filter = filters.private & filters.user(cfg.ADMIN_ID)

@app.on_message(filters.command("start") & admin_filter)
async def start_handler(_, message: Message):
    """Handler for the /start command."""
    if userbot and userbot.is_connected:
        await message.reply_text("👋 **Welcome!**\n\nThe userbot is already logged in and I'm ready to work. Send /help to see available commands.")
    else:
        await message.reply_text("👋 **Welcome!**\n\nThe userbot is not yet logged in. I will attempt to initialize it now. Please check your terminal or bot logs.")
        await initialize_userbot()

@app.on_message(filters.command("help") & admin_filter)
async def help_handler(_, message: Message):
    """Handler for the /help command."""
    help_text = (
        "**Userbot Indexer & Forwarder**\n\n"
        "Here are the available commands:\n\n"
        "**/index** `<chat_id>`\n"
        "Starts indexing all media files from the specified chat. The chat ID can be a username (e.g., `@channel_name`) or a numeric ID.\n\n"
        "**/forward** `<target_chat_id>`\n"
        "Forwards all indexed files from the database to the specified target chat. The bot does not need to be in the target chat, but your user account must have permission to post there.\n\n"
        "**/status**\n"
        "Shows the current status, including the total number of files indexed in the database."
    )
    await message.reply_text(help_text)

@app.on_message(filters.command("status") & admin_filter)
async def status_handler(_, message: Message):
    """Handler for the /status command."""
    total_files = await db.get_total_files_count()
    status_text = (
        f"**📊 Bot Status**\n\n"
        f"**Userbot Logged In:** {'✅ Yes' if userbot and userbot.is_connected else '❌ No'}\n"
        f"**Total Indexed Files:** `{total_files}`\n"
        f"**Indexing Active:** {'🏃‍♂️ Yes' if active_tasks['indexing'] else ' idle'}\n"
        f"**Forwarding Active:** {'🏃‍♂️ Yes' if active_tasks['forwarding'] else ' idle'}"
    )
    await message.reply_text(status_text)

@app.on_message(filters.command("index") & admin_filter)
async def index_handler(_, message: Message):
    """
    Handles the /index command to start indexing a chat.
    Usage: /index <chat_id>
    """
    if active_tasks["indexing"] or active_tasks["forwarding"]:
        await message.reply_text("❌ A task is already in progress. Please wait for it to complete before starting a new one.")
        return
        
    if not userbot or not userbot.is_connected:
        await message.reply_text("❌ The userbot is not logged in. Please restart the bot and complete the login process.")
        return

    if len(message.command) != 2:
        await message.reply_text("<b>⚠️ Invalid command format.</b>\n\nUse: <code>/index &lt;chat_id&gt;</code>")
        return

    chat_id_str = message.command[1]
    try:
        # If the ID is numeric, convert it to an integer. Otherwise, keep it as a string (for usernames).
        chat_id = int(chat_id_str) if chat_id_str.lstrip('-').isdigit() else chat_id_str
    except ValueError:
        await message.reply_text("❌ Invalid Chat ID provided.")
        return

    active_tasks["indexing"] = True
    status_msg = await message.reply_text(f"✅ Starting indexing for chat: <code>{chat_id}</code>. Please wait...")

    try:
        # Check if userbot can access the chat
        await userbot.get_chat(chat_id)
    except Exception as e:
        await status_msg.edit_text(f"❌ **Error:** The userbot could not access the chat <code>{chat_id}</code>.\n\nDetails: <code>{e}</code>\n\nPlease ensure your user account is a member of the chat.")
        active_tasks["indexing"] = False
        return

    saved_count = 0
    start_time = time.time()
    
    async for msg in userbot.get_chat_history(chat_id):
        media = msg.document or msg.video
        if not media:
            continue
        
        file_data = {
            "chat_id": msg.chat.id,
            "message_id": msg.id,
            "file_id": media.file_id,
            "file_unique_id": media.file_unique_id,
            "file_name": getattr(media, 'file_name', 'N/A'),
            "file_size": media.file_size,
            "caption": msg.caption.html if msg.caption else ""
        }
        await db.save_file(file_data)
        saved_count += 1

        # Update status every 50 files to avoid hitting API limits
        if saved_count % 50 == 0:
            elapsed_time = time.time() - start_time
            await status_msg.edit_text(
                f"**🔄 Indexing in Progress...**\n\n"
                f"**Chat:** <code>{chat_id}</code>\n"
                f"**Files Saved:** `{saved_count}`\n"
                f"**Elapsed Time:** {time.strftime('%H:%M:%S', time.gmtime(elapsed_time))}"
            )
    
    total_time = time.time() - start_time
    await status_msg.edit_text(
        f"**✅ Indexing Complete!**\n\n"
        f"**Chat:** <code>{chat_id}</code>\n"
        f"**Total New/Updated Files:** `{saved_count}`\n"
        f"**Duration:** {time.strftime('%H hours %M minutes %S seconds', time.gmtime(total_time))}"
    )
    active_tasks["indexing"] = False

@app.on_message(filters.command("forward") & admin_filter)
async def forward_handler(client, message: Message):
    """
    Handles the /forward command to send all indexed files to a target channel.
    Usage: /forward <target_chat_id>
    """
    if active_tasks["indexing"] or active_tasks["forwarding"]:
        await message.reply_text("❌ A task is already in progress. Please wait for it to complete.")
        return
        
    if not userbot or not userbot.is_connected:
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

    active_tasks["forwarding"] = True
    status_msg = await message.reply_text("`🔍 Counting total files in the database...`")
    total_files = await db.get_total_files_count()

    if total_files == 0:
        await status_msg.edit_text("🤷‍♂️ The database is empty. There are no files to forward.")
        active_tasks["forwarding"] = False
        return

    await status_msg.edit_text(f"✅ Found **{total_files}** files. Starting to forward to <code>{target_chat_id}</code>...")

    sent_count = 0
    error_count = 0
    start_time = time.time()
    
    all_files = db.get_all_files()
    async for file_doc in all_files:
        file_id = file_doc.get("file_id")
        caption = file_doc.get("caption", "")

        try:
            # Use the userbot to send the media, as the file_id is tied to its account
            await userbot.send_document(
                chat_id=target_chat_id,
                document=file_id,
                caption=caption
            )
            sent_count += 1
        except FloodWait as e:
            print(f"Rate limit exceeded. Waiting for {e.value} seconds.")
            await asyncio.sleep(e.value)
            # Retry sending
            try:
                await userbot.send_document(target_chat_id, file_id, caption=caption)
                sent_count += 1
            except Exception as retry_e:
                error_count += 1
                print(f"Failed to send file {file_id} after waiting. Error: {retry_e}")
        except Exception as e:
            error_count += 1
            print(f"Could not send file {file_id}. Error: {e}")

        # Update status message every 10 files
        if (sent_count + error_count) % 10 == 0:
            elapsed_time = time.time() - start_time
            await status_msg.edit_text(
                f"**🔄 Forwarding in Progress...**\n\n"
                f"**Sent:** `{sent_count} / {total_files}`\n"
                f"**Errors:** `{error_count}`\n"
                f"**Elapsed Time:** {time.strftime('%H:%M:%S', time.gmtime(elapsed_time))}"
            )

        await asyncio.sleep(cfg.FORWARD_DELAY)

    total_time = time.time() - start_time
    await status_msg.edit_text(
        f"**✅ Forwarding Complete!**\n\n"
        f"**Sent:** `{sent_count}`\n"
        f"**Failed:** `{error_count}`\n"
        f"**Duration:** {time.strftime('%H hours %M minutes', time.gmtime(total_time))}"
    )
    active_tasks["forwarding"] = False


# --- Main Execution ---
async def main():
    print("Starting the main bot...")
    await app.start()
    
    print("Initializing userbot...")
    # Initialize userbot after the main bot starts to be able to send status messages
    await initialize_userbot()
    
    print("Bot is now running. Press Ctrl+C to stop.")
    await idle()
    
    print("Shutting down...")
    await app.stop()
    if userbot and userbot.is_connected:
        await userbot.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped by user.")
