import os
import random
import discord
import asyncio
import aiohttp
import gc
from discord.ext import commands, tasks
from discord import app_commands
from dotenv import load_dotenv
from intel_db import init_db, add_monitor, remove_monitor, get_monitor, list_monitors

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
OWNER_ID = int(os.getenv('OWNER_ID', 0))
RESPONSE_CHANCE = float(os.getenv('RESPONSE_CHANCE', 0.05))

# --- Memory Optimization ---
# Disable caching for objects we don't need to stay under 100MB
intents = discord.Intents.default()
intents.message_content = True
intents.members = False # Disabling members intent saves a lot of RAM in large servers
intents.guilds = True
intents.presences = False

# Configure custom member/user cache to keep memory usage low
bot = commands.Bot(
    command_prefix='!', 
    intents=intents,
    chunk_guilds_at_startup=False,
    member_cache_flags=discord.MemberCacheFlags.none() # Don't cache members
)

@tasks.loop(minutes=30)
async def clear_cache():
    """Periodically clear internal caches and trigger garbage collection."""
    bot.clear() # Clear internal command/context cache
    gc.collect() # Force garbage collection
    print("Memory optimization: Cache cleared and GC collected.")

# --- Global Webhook Session ---
bot.session = None

async def update_status():
    """Helper to update the bot's status with server count."""
    guild_count = len(bot.guilds)
    await bot.change_presence(
        status=discord.Status.online,
        activity=discord.Activity(
            type=discord.ActivityType.watching, 
            name=f"{guild_count} servers"
        )
    )
    print(f"Status updated: Watching {guild_count} servers")

@bot.event
async def setup_hook():
    """Called once when the bot starts."""
    await init_db()
    bot.session = aiohttp.ClientSession()
    clear_cache.start() # Start memory optimization task
    try:
        # Syncing slash commands globally.
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash command(s) globally.")
    except Exception as e:
        print(f"Failed to sync slash commands: {e}")

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} ({bot.user.id})')
    await update_status()
    print('Bot is ready, online, and active.')

@bot.event
async def on_guild_join(guild):
    """Update status when joining a new server."""
    await update_status()
    # Auto-discovery logging: alert owner in console or a specific channel
    print(f"NEW DISCOVERY: Joined {guild.name} ({guild.id}) with {guild.member_count} members.")

@bot.event
async def on_guild_remove(guild):
    """Update status when leaving a server."""
    await update_status()

# --- Slash Commands (Owner Only) ---
def is_owner_check(interaction: discord.Interaction) -> bool:
    return interaction.user.id == OWNER_ID

@bot.tree.command(name="monitor", description="[OWNER ONLY] Start monitoring a channel")
@app_commands.describe(source_channel_id="ID of the channel to spy on", webhook_url="Target webhook URL")
@app_commands.check(is_owner_check)
async def monitor(interaction: discord.Interaction, source_channel_id: str, webhook_url: str):
    try:
        source_id = int(source_channel_id)
        await add_monitor(source_id, webhook_url, interaction.user.id)
        await interaction.response.send_message(f"Monitoring active for channel ID {source_id}.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Error adding monitor: {e}", ephemeral=True)

@bot.tree.command(name="unmonitor", description="[OWNER ONLY] Stop monitoring a channel")
@app_commands.describe(source_channel_id="ID of the channel to stop spying on")
@app_commands.check(is_owner_check)
async def unmonitor(interaction: discord.Interaction, source_channel_id: str):
    try:
        source_id = int(source_channel_id)
        await remove_monitor(source_id)
        await interaction.response.send_message(f"Monitoring stopped for channel ID {source_id}.", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"Error removing monitor: {e}", ephemeral=True)

@bot.tree.command(name="setup_intel", description="[OWNER ONLY] Automatically setup a webhook and monitor a channel")
@app_commands.describe(source_channel_id="ID of the channel to spy on", target_channel="Channel in THIS server to receive intel")
@app_commands.check(is_owner_check)
async def setup_intel(interaction: discord.Interaction, source_channel_id: str, target_channel: discord.TextChannel):
    await interaction.response.defer(ephemeral=True)
    try:
        source_id = int(source_channel_id)
        
        # Check if the bot has permission to create webhooks in the target channel
        if not target_channel.permissions_for(interaction.guild.me).manage_webhooks:
            await interaction.followup.send("I need 'Manage Webhooks' permission in the target channel.", ephemeral=True)
            return

        # Create the webhook
        webhook_name = f"Intel-Feed-{source_id}"
        webhook = await target_channel.create_webhook(name=webhook_name, reason="Automated Intel Setup")
        
        # Add to database
        await add_monitor(source_id, webhook.url, interaction.user.id)
        
        await interaction.followup.send(
            f"✅ Success! Webhook created in {target_channel.mention} and monitoring active for channel `{source_id}`.", 
            ephemeral=True
        )
    except ValueError:
        await interaction.followup.send("Invalid Channel ID. Please provide a numeric ID.", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Error setting up intel: {e}", ephemeral=True)

@bot.tree.command(name="intel_status", description="[OWNER ONLY] List all active intel monitors")
@app_commands.check(is_owner_check)
async def intel_status(interaction: discord.Interaction):
    monitors = await list_monitors()
    if not monitors:
        await interaction.response.send_message("No active intel monitors.", ephemeral=True)
        return
    
    status_msg = "**Active Intel Monitors:**\n"
    for source_id, webhook_url in monitors:
        status_msg += f"- Source: {source_id} -> Target: {webhook_url[:50]}...\n"
    
    await interaction.response.send_message(status_msg, ephemeral=True)

@bot.tree.command(name="ping", description="Check if the bot is alive")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"Pong! Latency: {round(bot.latency * 1000)}ms")

# --- Sync command for owner ---
@bot.command()
@commands.is_owner()
async def sync(ctx):
    try:
        bot.tree.copy_global_to(guild=ctx.guild)
        synced = await bot.tree.sync(guild=ctx.guild)
        await ctx.send(f"Synced {len(synced)} commands to this guild.")
    except Exception as e:
        await ctx.send(f"Error syncing: {e}")

# --- Chat Bot Logic ---
CHAT_RESPONSES = [
    "Yeah, for sure.", "Exactly!", "Lmao", "Fr fr", "Interesting...", "Bet", "No way!", "That's wild.", "Whatever you say."
]

KEYWORD_TRIGGERS = {
    "opps": ["They stay talking", "Stay safe fr", "Wild how they be"],
    "raid": ["Wait what?", "No way that's happening", "Bet"],
    "turf": ["Gotta hold it down", "Respect"],
    "money": ["Stacking it up", "Gotta get that bread"]
}

async def send_mirror_message(webhook_url, message):
    """Mirror the original message using a webhook for high-fidelity."""
    webhook = discord.Webhook.from_url(webhook_url, session=bot.session)
    
    # Mirror username and avatar
    username = f"{message.author.name} ({message.guild.name})" if message.guild else message.author.name
    avatar_url = message.author.display_avatar.url
    
    # Handle attachments
    files = []
    for attachment in message.attachments:
        try:
            file = await attachment.to_file()
            files.append(file)
        except:
            pass
            
    try:
        await webhook.send(
            content=message.content,
            username=username,
            avatar_url=avatar_url,
            files=files,
            allowed_mentions=discord.AllowedMentions.none() # Don't ping people in target server
        )
    except Exception as e:
        print(f"Failed to mirror message: {e}")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # --- Intel Gathering (Mass Monitoring) ---
    webhook_url = await get_monitor(message.channel.id)
    if webhook_url:
        asyncio.create_task(send_mirror_message(webhook_url, message))

    # --- Chat Bot Responses ---
    # 1. Keyword Triggers
    triggered = False
    for keyword, responses in KEYWORD_TRIGGERS.items():
        if keyword in message.content.lower():
            if random.random() < 0.3: # Higher chance for specific keywords
                async with message.channel.typing():
                    await asyncio.sleep(random.uniform(1.0, 3.0))
                    await message.reply(random.choice(responses))
                    triggered = True
                    break
    
    # 2. Random Responses
    if not triggered and random.random() < RESPONSE_CHANCE:
        async with message.channel.typing():
            await asyncio.sleep(random.uniform(1.0, 3.0))
            await message.reply(random.choice(CHAT_RESPONSES))

    await bot.process_commands(message)

if __name__ == "__main__":
    if not TOKEN:
        print("Error: DISCORD_TOKEN not found in environment.")
    else:
        bot.run(TOKEN)
