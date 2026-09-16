import asyncio
import io
import os
import threading
import discord
from discord.ext import commands, tasks
from flask import Flask
import yt_dlp

# --- سيرفر Flask لضمان استمرار عمل البوت على Render ---
app = Flask("")

@app.route("/")
def home():
    return "Music Bot is Alive!"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()

# --- إعدادات البوت والـ Intents ---
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True

bot = commands.Bot(command_prefix="", intents=intents)

VOICE_CHANNEL_ID = 1549566092777619556  # أيدي روم الصوت
TEXT_CHANNEL_ID = 1549566092777619556   # أيدي الشات

current_volume = 1.0
current_song_info = {}

# خيارات البحث من SoundCloud لتفادي حظر يوتيوب نهائياً
YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "extractaudio": True,
    "audioformat": "mp3",
    "restrictfilenames": True,
    "noplaylist": True,
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "logtostderr": False,
    "quiet": True,
    "no_warnings": True,
    "default_search": "scsearch", # استخدام SoundCloud للبحث المباشر
    "source_address": "0.0.0.0",
}

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}

ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

@bot.event
async def on_ready():
    print(f"تم تسجيل الدخول بنجاح باسم: {bot.user.name}")
    keep_afk_voice.start()

@tasks.loop(seconds=10)
async def keep_afk_voice():
    try:
        channel = bot.get_channel(VOICE_CHANNEL_ID)
        if not channel:
            return

        guild = channel.guild
        voice_client = guild.voice_client

        if not voice_client or not voice_client.is_connected():
            await channel.connect(reconnect=True, self_deaf=True)
    except Exception as e:
        print(f"خطأ في الاتصال بالروم الصوتي: {e}")

@bot.event
async def on_message(message):
    global current_volume, current_song_info

    if message.author.bot:
        return

    if TEXT_CHANNEL_ID and message.channel.id != TEXT_CHANNEL_ID:
        return

    content = message.content.strip()

    # 1. أمر التشغيل (SoundCloud)
    if content.startswith("ش "):
        song_query = content[2:].strip()
        if not song_query:
            return

        voice_client = message.guild.voice_client
        if not voice_client or not voice_client.is_connected():
            channel = bot.get_channel(VOICE_CHANNEL_ID)
            if channel:
                voice_client = await channel.connect(reconnect=True, self_deaf=True)

        async with message.channel.typing():
            try:
                loop = asyncio.get_event_loop()
                data = await loop.run_in_executor(
                    None,
                    lambda: ytdl.extract_info(f"scsearch:{song_query}", download=False),
                )

                if "entries" in data and len(data["entries"]) > 0:
                    data = data["entries"][0]

                stream_url = data["url"]
                song_title = data.get("title", "Unknown Title")

                current_song_info = {
                    "title": song_title,
                    "url": stream_url,
                    "duration": data.get("duration", 0),
                    "requester": message.author.display_name,
                    "current_position": 0
                }

                if voice_client.is_playing() or voice_client.is_paused():
                    voice_client.stop()

                source = discord.FFmpegPCMAudio(stream_url, **FFMPEG_OPTIONS)
                transformer = discord.PCMVolumeTransformer(source, volume=current_volume)

                voice_client.play(
                    transformer,
                    after=lambda e: print(f"خطأ بالتشغيل: {e}") if e else None,
                )

                response_text = f"*Playing song* : **{song_title}**\n*by* : **{message.author.display_name}**"
                await message.reply(response_text, mention_author=False)

            except Exception as e:
                print(f"خطأ أثناء جلب الأغنية: {e}")
                await message.reply("حدث خطأ أثناء محاولة تشغيل الأغنية.", mention_author=False)

    # 2. أمر الإيقاف
    elif content == "وقف":
        voice_client = message.guild.voice_client
        if voice_client and (voice_client.is_playing() or voice_client.is_paused()):
            voice_client.stop()
            try:
                await message.add_reaction("⛔")
            except Exception:
                pass
            stop_text = f"*Stopped playing by* : **{message.author.display_name}**"
            await message.reply(stop_text, mention_author=False)

    # 3. أمر تقديم الثواني (مُصلح بالكامل ومستقر)
    elif content.startswith("قدم"):
        parts = content.split()
        if len(parts) > 1 and parts[1].isdigit():
            seconds_to_seek = int(parts[1])
            voice_client = message.guild.voice_client

            if voice_client and (voice_client.is_playing() or voice_client.is_paused()) and current_song_info.get("url"):
                try:
                    current_song_info["current_position"] = current_song_info.get("current_position", 0) + seconds_to_seek
                    new_pos = current_song_info["current_position"]

                    voice_client.stop()

                    # إعدادات ثابتة ومستقرة تجبر FFmpeg على معالجة التقديم بدقة بدون إيقاف الصوت أو التسريع
                    seek_options = {
                        "before_options": f"-ss {new_pos} -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
                        "options": "-vn -fflags +genpts"
                    }

                    source = discord.FFmpegPCMAudio(current_song_info["url"], **seek_options)
                    transformer = discord.PCMVolumeTransformer(source, volume=current_volume)

                    voice_client.play(transformer)

                    try:
                        await message.add_reaction("✅")
                    except Exception:
                        pass

                    seek_text = f"*Forwarded* `{seconds_to_seek}` *seconds by* : **{message.author.display_name}**"
                    await message.reply(seek_text, mention_author=False)

                except Exception as e:
                    print(f"خطأ أثناء تقديم الأغنية: {e}")

    # 4. أمر التحكم بالصوت
    elif content.startswith("ص "):
        parts = content.split()
        if len(parts) > 1 and parts[1].isdigit():
            new_vol = int(parts[1])
            if 0 <= new_vol <= 200:
                old_vol_percent = int(current_volume * 100)
                current_volume = new_vol / 100.0

                voice_client = message.guild.voice_client
                if voice_client and voice_client.source:
                    voice_client.source.volume = current_volume

                reply_text = f"*Volume changed from* `{old_vol_percent}%` *to* `{new_vol}%` ."
                await message.reply(reply_text, mention_author=False)

    # 5. أمر استئناف التشغيل
    elif content == "كمل":
        voice_client = message.guild.voice_client
        if voice_client and voice_client.is_paused():
            voice_client.resume()
            try:
                await message.add_reaction("▶️")
            except Exception:
                pass
            await message.reply(f"*Resumed by* : **{message.author.display_name}**", mention_author=False)

    # 6. أمر دخول خروج
    elif content == "دخول خروج":
        channel = bot.get_channel(VOICE_CHANNEL_ID)
        if channel:
            voice_client = message.guild.voice_client
            try:
                if voice_client and voice_client.is_connected():
                    await voice_client.disconnect(force=True)
                    await asyncio.sleep(1)

                await channel.connect(reconnect=True, self_deaf=True)
                
                try:
                    await message.add_reaction("🔄")
                except Exception:
                    pass
                
                reply_text = f"*Reconnected to voice channel by* : **{message.author.display_name}**"
                await message.reply(reply_text, mention_author=False)
            except Exception as e:
                print(f"خطأ أثناء إعادة الدخول للروم: {e}")
                await message.reply("حدث خطأ أثناء محاولة إعادة الاتصال بالروم.", mention_author=False)

    await bot.process_commands(message)

keep_alive()

TOKEN = os.environ.get("DISCORD_TOKEN", "YOUR_BOT_TOKEN_HERE")
bot.run(TOKEN)
