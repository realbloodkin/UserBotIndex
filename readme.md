Userbot Powered Telegram Indexer
This project provides a powerful Telegram bot that uses a hybrid approach to index and forward files. A user-friendly standard bot provides the command interface, while a high-access userbot (automating your personal account) performs the heavy lifting of scraping and sending files, even from protected or inaccessible chats.
Features
Hybrid Bot/Userbot System: Secure and easy-to-use bot interface powered by a userbot with full access to your account's chats.
Interactive Userbot Login: If you don't provide a session string, the bot will guide you through a secure, private login process and generate a session string for you.
Powerful Indexing: Scrape and save metadata for all video and document files from any chat your user account is in (/index).
Bulk Forwarding: Forward all indexed files to any target chat your user account has access to (/forward).
Rate-Limit Safe: Includes a configurable delay to prevent your account from being flagged for spam.
Secure Configuration: All sensitive data (API keys, tokens, database URI) is handled securely via environment variables.
Persistent Database: Uses MongoDB to store file metadata, allowing you to stop and resume tasks without losing progress.
⚠️ Important Warning
Automating a user account is against Telegram's Terms of Service. Indexing content from protected channels or using this bot for spammy behavior can get your personal Telegram account permanently banned. Use this tool responsibly and at your own risk. It is recommended to use a secondary, non-critical Telegram account for the userbot.
Setup and Deployment
1. Prerequisites
Python 3.8 or higher.
A MongoDB database and its connection URI.
A Telegram account to be used for the userbot.
2. Get Telegram Credentials
API_ID and API_HASH:
Go to my.telegram.org and log in.
Click on "API development tools" and create a new application.
Copy the api_id and api_hash values.
BOT_TOKEN:
Open Telegram and talk to @BotFather.
Create a new bot using the /newbot command.
Copy the bot token he gives you.
ADMIN_ID:
Talk to a bot like @userinfobot.
Send the /start command, and it will give you your numeric User ID.
3. Installation
