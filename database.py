from motor.motor_asyncio import AsyncIOMotorClient
from config import cfg

class Database:
    """
    Handles all interactions with the MongoDB database.
    """
    def __init__(self, uri):
        # Establish connection to the database
        self._client = AsyncIOMotorClient(uri)
        self.db = self._client["userbot_indexer"] # Database name
        self.files = self.db["files"] # Collection name

    async def save_file(self, file_data):
        """
        Saves a single file's metadata to the database.
        Prevents duplicates based on the unique file_id and chat_id combination.
        """
        # We use a unique ID combining chat and message ID to allow re-indexing
        unique_id = f"{file_data['chat_id']}_{file_data['message_id']}"
        
        # Using update_one with upsert=True is an efficient way to insert or update.
        await self.files.update_one(
            {'_id': unique_id},
            {'$set': file_data},
            upsert=True
        )

    async def get_total_files_count(self):
        """Returns the total number of files indexed in the database."""
        return await self.files.count_documents({})

    def get_all_files(self):
        """
        Returns an async generator to iterate over all files in the database.
        This is memory-efficient for very large databases.
        """
        return self.files.find({})

# Create a single database instance to be used across the bot
db = Database(cfg.DATABASE_URI)
