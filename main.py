import asyncio
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

bot = commands.Bot(command_prefix="!", intents=intents)

VOICE_CHANNEL_ID = 1545761345352507503 
TEXT_CHANNEL_ID = 1545761345352507503   

current_volume = 1.0  # الصوت الافتراضي (100%)

# إعدادات البحث من SoundCloud
YTDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "nocheckcertificate": True,
    "ignoreerrors": False,
    "logtostderr": False,
    "quiet": True,
    "no_warnings": True,
    "default_search": "scsearch",
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
    try:
        channel = bot.get_channel(VOICE_CHANNEL_ID)
        if channel:
            voice_client = channel.guild.voice_client
            if not voice_client or not voice_client.is_connected():
                await channel.connect(reconnect=True, self_deaf=True)
                print("تم الاتصال بالروم الصوتي بنجاح!")
    except Exception as e:
        print(f"خطأ في الاتصال الأولي بالروم: {e}")
        
    if not keep_afk_voice.is_running():
        keep_afk_voice.start()

@tasks.loop(seconds=15)
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
        print(f"خطأ في الاتصال الدوري بالروم: {e}")

@bot.event
async def on_message(message):
    global current_volume

    if message.author.bot:
        return

    if TEXT_CHANNEL_ID and message.channel.id != TEXT_CHANNEL_ID:
        return

    content = message.content.strip()

    # 1. أمر تعال مع منشن البوت
    if bot.user in message.mentions and "تعال" in content:
        if message.author.voice and message.author.voice.channel:
            target_channel = message.author.voice.channel
            voice_client = message.guild.voice_client
            try:
                if voice_client and voice_client.is_connected():
                    await voice_client.move_to(target_channel)
                else:
                    await target_channel.connect(reconnect=True, self_deaf=True)
                
                try:
                    await message.add_reaction("✅")
                except Exception:
                    pass
                return await message.reply(f"تم الانضمام إلى **{target_channel.name}** 👋", mention_author=False)
            except Exception as e:
                print(f"خطأ عند دخول الروم عبر أمر تعال: {e}")
                return await message.reply(f"تعذر الانضمام: `{e}`", mention_author=False)
        else:
            return await message.reply("يجب أن تكون متواجدًا في روم صوتي أولاً!", mention_author=False)

    # 2. أمر التشغيل (ش <اسم الأغنية>)
    elif content.startswith("ش "):
        song_query = content[2:].strip()
        if not song_query:
            return

        voice_client = message.guild.voice_client
        if not voice_client or not voice_client.is_connected():
            if message.author.voice and message.author.voice.channel:
                try:
                    voice_client = await message.author.voice.channel.connect(reconnect=True, self_deaf=True)
                except Exception as e:
                    return await message.reply(f"فشل الاتصال بالروم: `{e}`", mention_author=False)
            else:
                channel = bot.get_channel(VOICE_CHANNEL_ID)
                if channel:
                    try:
                        voice_client = await channel.connect(reconnect=True, self_deaf=True)
                    except Exception as e:
                        return await message.reply(f"فشل الاتصال بالروم الافتراضي: `{e}`", mention_author=False)

        try:
            loop = asyncio.get_event_loop()
            search_target = song_query if song_query.startswith(("http://", "https://")) else f"scsearch:{song_query}"
            
            data = await loop.run_in_executor(
                None,
                lambda: ytdl.extract_info(search_target, download=False),
            )

            if "entries" in data and len(data["entries"]) > 0:
                data = data["entries"][0]

            stream_url = data["url"]
            song_title = data.get("title", "Unknown Title")

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
            print(f"خطأ أثناء جلب المقطع من ساوندكلاود: {e}")
            await message.reply(f"حدث خطأ أثناء التشغيل: `{e}`", mention_author=False)

    # 3. أمر التحكم بالصوت (ص <الرقم>)
    elif content.startswith("ص "):
        parts = content.split()
        if len(parts) > 1 and parts[1].isdigit():
            new_vol = int(parts[1])
            if 0 <= new_vol <= 200:
                old_vol_percent = int(current_volume * 100)
                current_volume = new_vol / 100.0

                voice_client = message.guild.voice_client
                if voice_client and voice_client.source:
                    if isinstance(voice_client.source, discord.PCMVolumeTransformer):
                        voice_client.source.volume = current_volume

                reply_text = f"*Volume changed from* `{old_vol_percent}%` *to* `{new_vol}%` ."
                await message.reply(reply_text, mention_author=False)

    # 4. أمر الإيقاف (وقف)
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

    # 5. أمر الخروج (خروج)
    elif content == "خروج":
        voice_client = message.guild.voice_client
        if voice_client and voice_client.is_connected():
            try:
                await voice_client.disconnect(force=True)
                try:
                    await message.add_reaction("👋")
                except Exception:
                    pass
                await message.reply("تم الخروج من الروم الصوتي بنجاح.", mention_author=False)
            except Exception as e:
                print(f"خطأ أثناء خروج البوت: {e}")
                await message.reply(f"حدث خطأ أثناء الخروج: `{e}`", mention_author=False)

keep_alive()

TOKEN = os.environ.get("DISCORD_TOKEN", "YOUR_BOT_TOKEN_HERE")
bot.run(TOKEN)
