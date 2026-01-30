import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio
import os
import logging

# Reduce discord logs
logging.getLogger("discord.gateway").setLevel(logging.ERROR)

TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# yt-dlp options (bypass YouTube bot detection)
ytdl_opts = {
    "format": "bestaudio/best",
    "quiet": True,
    "default_search": "ytsearch",
    "noplaylist": True,
    "nocheckcertificate": True,
    "ignoreerrors": True,
    "source_address": "0.0.0.0",
    "extractor_args": {
        "youtube": {
            "player_client": ["android"]
        }
    },
    "http_headers": {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64)"
    }
}

ffmpeg_opts = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn"
}

ytdl = yt_dlp.YoutubeDL(ytdl_opts)

queues = {}


def get_queue(guild_id):
    if guild_id not in queues:
        queues[guild_id] = []
    return queues[guild_id]


async def get_audio(query):
    loop = asyncio.get_event_loop()

    data = await loop.run_in_executor(
        None, lambda: ytdl.extract_info(query, download=False)
    )

    if not data:
        raise Exception("No data returned")

    if "entries" in data:
        data = data["entries"][0]

    if not data or "url" not in data:
        raise Exception("No playable URL found")

    return data["url"], data["title"]


async def play_next(interaction: discord.Interaction):
    queue = get_queue(interaction.guild.id)

    if not queue:
        return

    url, title = queue.pop(0)
    vc = interaction.guild.voice_client

    if not vc:
        return

    source = discord.FFmpegPCMAudio(url, **ffmpeg_opts)

    def after_play(error):
        if error:
            print("Player error:", error)
        asyncio.run_coroutine_threadsafe(play_next(interaction), bot.loop)

    vc.play(source, after=after_play)
    await interaction.channel.send(f"🎶 Now Playing: **{title}**")


@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await bot.tree.sync()
        print(f"🔁 Synced {len(synced)} commands")
    except Exception as e:
        print(e)


@bot.tree.command(name="play", description="Play music from YouTube")
@app_commands.describe(query="Song name or YouTube link")
async def play(interaction: discord.Interaction, query: str):

    if not interaction.user.voice:
        await interaction.response.send_message(
            "❌ Join a voice channel first", ephemeral=True
        )
        return

    await interaction.response.defer()

    try:
        if not interaction.guild.voice_client:
            await interaction.user.voice.channel.connect()

        url, title = await get_audio(query)

        queue = get_queue(interaction.guild.id)
        queue.append((url, title))

        await interaction.followup.send(f"✅ Added: **{title}**")

        if not interaction.guild.voice_client.is_playing():
            await play_next(interaction)

    except Exception as e:
        print("PLAY ERROR:", e)
        await interaction.followup.send(
            "❌ YouTube blocked this song or it is unavailable. Try another song."
        )


@bot.tree.command(name="skip", description="Skip current song")
async def skip(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.stop()
        await interaction.response.send_message("⏭ Skipped")
    else:
        await interaction.response.send_message("❌ Nothing playing")


@bot.tree.command(name="pause", description="Pause music")
async def pause(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_playing():
        vc.pause()
        await interaction.response.send_message("⏸ Paused")
    else:
        await interaction.response.send_message("❌ Nothing playing")


@bot.tree.command(name="resume", description="Resume music")
async def resume(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    if vc and vc.is_paused():
        vc.resume()
        await interaction.response.send_message("▶ Resumed")
    else:
        await interaction.response.send_message("❌ Nothing paused")


@bot.tree.command(name="stop", description="Stop music and clear queue")
async def stop(interaction: discord.Interaction):
    vc = interaction.guild.voice_client
    queue = get_queue(interaction.guild.id)

    if vc:
        queue.clear()
        vc.stop()
        await vc.disconnect()
        await interaction.response.send_message("⏹ Stopped and disconnected")
    else:
        await interaction.response.send_message("❌ Not connected")


@bot.tree.command(name="queue", description="Show music queue")
async def show_queue(interaction: discord.Interaction):
    queue = get_queue(interaction.guild.id)

    if not queue:
        await interaction.response.send_message("📭 Queue empty")
        return

    msg = "\n".join([f"{i+1}. {song[1]}" for i, song in enumerate(queue)])
    await interaction.response.send_message(f"🎵 Queue:\n{msg}")


bot.run(TOKEN)
