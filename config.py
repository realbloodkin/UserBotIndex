import os
from dotenv import load_dotenv

# Load environment variables from a .env file if it exists
load_dotenv()

class Config:
    """
    Loads configuration variables from environment settings.
    This is a secure way to handle sensitive data like API keys.
    """
    try:
        # --- Essential Credentials ---
        
        # Get these from my.telegram.org
        API_ID = int(os.environ.get("API_ID", 0))
        API_HASH = os.environ.get("API_HASH", "")
        
        # Get this from @BotFather on Telegram
        BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
        
        # Your MongoDB connection string.
        DATABASE_URI = os.environ.get("DATABASE_URI", "")
        
        # The Telegram user ID of the person authorized to use this bot (you).
        # You can get your ID from bots like @userinfobot.
        ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))

        # --- Optional Userbot Session ---
        
        # A Pyrogram session string. If you don't have one, the bot will help you generate it.
        # This is the recommended way to log in the userbot for repeated runs.
        SESSION_STRING = os.environ.get("SESSION_STRING", None)

        # --- Behavior Settings ---

        # Delay in seconds between sending each file during the /forward command.
        # A 2-second delay is safe to avoid Telegram's API rate limits (FloodWait).
        FORWARD_DELAY = int(os.environ.get("FORWARD_DELAY", 2))

    except (ValueError, TypeError) as e:
        print(f"Error loading configuration: One of the environment variables is missing or has the wrong type. Details: {e}")
        # You might want to exit the script if config is invalid
        exit(1)

# Create an instance of the configuration to be imported by other modules
cfg = Config()
