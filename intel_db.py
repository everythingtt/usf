import aiosqlite
import os

DB_PATH = 'intel.db'

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Table for monitoring mappings: Source Channel -> Target Webhook URL
        await db.execute('''
            CREATE TABLE IF NOT EXISTS monitor_mappings (
                source_channel_id INTEGER PRIMARY KEY,
                target_webhook_url TEXT NOT NULL,
                added_by_user_id INTEGER,
                is_active BOOLEAN DEFAULT 1
            )
        ''')
        # Table for auto-discovery settings
        await db.execute('''
            CREATE TABLE IF NOT EXISTS discovery_settings (
                guild_id INTEGER PRIMARY KEY,
                discovery_webhook_url TEXT NOT NULL
            )
        ''')
        await db.commit()

async def add_monitor(source_id: int, webhook_url: str, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('''
            INSERT OR REPLACE INTO monitor_mappings (source_channel_id, target_webhook_url, added_by_user_id)
            VALUES (?, ?, ?)
        ''', (source_id, webhook_url, user_id))
        await db.commit()

async def remove_monitor(source_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute('DELETE FROM monitor_mappings WHERE source_channel_id = ?', (source_id,))
        await db.commit()

async def get_monitor(source_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT target_webhook_url FROM monitor_mappings WHERE source_channel_id = ? AND is_active = 1', (source_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None

async def list_monitors():
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute('SELECT source_channel_id, target_webhook_url FROM monitor_mappings') as cursor:
            return await cursor.fetchall()
