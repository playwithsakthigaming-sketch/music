import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp
import asyncio
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import os

TOKEN = os.getenv("DISCORD_TOKEN")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
    client_id=SPOTIFY_CLIENT_ID,
    client_secret=SPOTIFY_CLIENT_SECRET
))

ytdl_opts = {
    "format": "bestaudio/best",
    "quiet": True,
    "default_search": "ytsearch",
    "noplaylist": True
}

ffmpeg_opts = {
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
    data = await loop.run_in_executor(None, lambda: ytdl.extract_info(query, download=False))
    if "entries" in data:
        data = data["entries"][0]
    return data["url"], data["title"]


def spotify_to_search(url):
    if "track" in url:
        track = sp.track(url)
        return [f"{track['name']} {track['artists'][0]['name']}"]
    elif "playlist" in url:
        playlist = sp.playlist_items(url)
        songs = []
        for item in playlist["items"]:
            track = item["track"]
            if track:
                songs.append(f"{track['name']} {track['artists'][0]['name']}")
        return songs
    return []


async def play_next(interaction: discord.Interaction):
    queue = get_queue(interaction.guild.id)

    if not queue:
        return

    url, title = queue.pop(0)
    vc = interaction.guild.voice_client

    source = discord.FFmpegPCMAudio(url, **ffmpeg_opts)

    def after_play(error):
        asyncio.run_coroutine_threadsafe(play_next(interaction), bot.loop)

    vc.play(source, after=after_play)

    await interaction.channel.send(f"🎶 Now Playing: **{title}**")


@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    await bot.tree.sync()


@bot.tree.command(name="play", description="Play music from YouTube or Spotify")
@app_commands.describe(query="Song name or YouTube/Spotify link")
async def play(interaction: discord.Interaction, query: str):

    if not interaction.user.voice:
        await interaction.response.send_message("❌ Join a voice channel first", ephemeral=True)
        return

    if not interaction.guild.voice_client:
        await interaction.user.voice.channel.connect()

    await interaction.response.defer()

    queue = get_queue(interaction.guild.id)

    # Spotify link
    if "spotify.com" in query:
        searches = spotify_to_search(query)
        if not searches:
            await interaction.followup.send("❌ Invalid Spotify link")
            return

        for song in searches:
            url, title = await get_audio(song)
            queue.append((url, title))

        await interaction.followup.send(f"✅ Added {len(searches)} Spotify song(s)")

    else:
        url, title = await get_audio(query)
        queue.append((url, title))
        await interaction.followup.send(f"✅ Added: **{title}**")

    if not interaction.guild.voice_client.is_playing():
        await play_next(interaction)


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
