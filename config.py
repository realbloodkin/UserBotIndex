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
        API_ID = int(os.environ.get("API_ID", 0))
        API_HASH = os.environ.get("API_HASH", "")
        BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
        DATABASE_URI = os.environ.get("DATABASE_URI", "")
        ADMIN_ID = int(os.environ.get("ADMIN_ID", 0))

        # --- Optional Userbot Session ---
        SESSION_STRING = os.environ.get("SESSION_STRING", None)

        # --- Behavior Settings ---
        FORWARD_DELAY = int(os.environ.get("FORWARD_DELAY", 2))

        # --- Web Server Settings (ADD THIS) ---
        # The port for the web service. Render.com will set this automatically.
        # Defaults to 8080 if not set.
        PORT = int(os.environ.get("PORT", 8080))

    except (ValueError, TypeError) as e:
        print(f"Error loading configuration: One of the environment variables is missing or has the wrong type. Details: {e}")
        exit(1)

# Create an instance of the configuration to be imported by other modules
cfg = Config()
