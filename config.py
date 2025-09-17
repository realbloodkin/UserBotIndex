import os
from dotenv import load_dotenv

# Load environment variables from a .env file if it exists
load_dotenv()

class Config:
    """
    Loads configuration variables from environment settings.
    """
    try:
        # --- Essential Credentials ---
        API_ID = int(os.environ.get("API_ID", 0))
        API_HASH = os.environ.get("API_HASH", "")
        BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
        DATABASE_URI = os.environ.get("DATABASE_URI", "")
        ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))

        # --- Optional Userbot Session ---
        SESSION_STRING = os.environ.get("SESSION_STRING", None)

        # --- Behavior Settings ---
        FORWARD_DELAY = int(os.environ.get("FORWARD_DELAY", 2)) # Delay for /forward command

        # --- NEW: Delay for the /index command ---
        # Delay in seconds between fetching batches of messages during indexing.
        # A higher value (5-10s) is safer for restricted chats but slower.
        # A lower value (1-2s) is faster for normal chats.
        INDEXING_DELAY = int(os.environ.get("INDEXING_DELAY", 3))

    except (ValueError, TypeError) as e:
        print(f"Error loading configuration: {e}")
        exit(1)

# Create an instance of the configuration
cfg = Config()
