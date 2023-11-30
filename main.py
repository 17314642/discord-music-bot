#!/usr/bin/env python3

# -*- coding: utf-8 -*-
import asyncio
import time
import re
import os
import typing
import functools
import json
import logging
import logging.handlers

# Discord bot API
import discord
from discord.errors import ClientException
from discord.ext import commands
from discord import FFmpegPCMAudio
from discord.voice_client import VoiceClient

# Video download
import yt_dlp.YoutubeDL
from yt_dlp import YoutubeDL

try:
    BOT_TOKEN = os.environ['BOT_TOKEN']
except KeyError:
    print("Токен не был указан. Укажите его в \"start.sh\"")
    exit()

TRACK_QUEUE = {}
LOGGER = None

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="-", description="This is a Random Bot", intents=intents)

IS_SEARCH_STARTED = False
FFMPEG_OPTS = {"before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
               "options": "-vn -bufsize 8192k"}


# My own implementation of logger is here because youtube-dl with quiet option still shows errors in console.
class YoutubeDL_Logger:
    def error(msg):
        return

    def warning(msg):
        return

    def debug(msg):
        return


def replace_from_end(string: str, replace_string: str):
    idx = string.rfind(replace_string)
    return string[:idx] + string[idx + 1:]


def get_pretty_exception_str(e, **kwargs):
    lines = []

    lines.append("================================")
    lines.append("Exception caught:")
    lines.append(f"    e = \"{e}\"")
    lines.append(f"    type = \"{type(e)}\"")

    for k in kwargs.keys():
        lines.append(f"    {k} = {kwargs[k]}")

    lines.append("================================")

    return "\n".join(lines)


def yt_dlp_search_blocking(cmd, query, is_query_url):
    options = {
        'format': 'bestaudio',
        'quiet': 'True',
        'cookiefile': 'cookies.txt',
        "logger": YoutubeDL_Logger
    }

    with YoutubeDL(options) as ydl:
        ytsearch_str = "ytsearch:"
        if cmd == "search":
            ytsearch_str = "ytsearch15:" # Extract 15 videos

        if is_query_url:
            output = ydl.extract_info(query, download=False)
        else:
            output = ydl.extract_info(f"{ytsearch_str}{query}", download=False)

        if "playlist_count" in output.keys() or cmd == "search":
            output = output["entries"]
        else:
            output = [output]

        with open("output.json", "w") as f:
            f.write(json.dumps(output, indent=4))

        LOGGER.info(f"yt_dlp_search_blocking(): query=\"{query}\" type=\"{type(output)}\"")
        return output


async def yt_dlp_search_async(*args, **kwargs) -> typing.Any:
    """Runs a blocking function in a non-blocking way"""
    blocking_func: typing.Callable = yt_dlp_search_blocking
    # `run_in_executor` doesn't support kwargs, `functools.partial` does
    func = functools.partial(blocking_func, *args, **kwargs)
    return await bot.loop.run_in_executor(None, func)


def init_track_list(guild_id: int):
    global TRACK_QUEUE
    TRACK_QUEUE[guild_id] = {}
    TRACK_QUEUE[guild_id]["tracks"] = []
    TRACK_QUEUE[guild_id]["current_track"] = 0


def add_tracks_to_queue(tracks: list, guild: discord.Guild):
    if not guild.id in TRACK_QUEUE.keys():
        init_track_list(guild.id)

    for t in tracks:
        if type(t) == str:
            print(f"t = \"{t}\"")
        TRACK_QUEUE[guild.id]["tracks"].append({
            "title": t["title"],
            "yt_id": t["id"],
            "duration": t["duration"]
        })

    return len(TRACK_QUEUE) - 1


def get_current_track_id(guild_id: int):
    if guild_id not in TRACK_QUEUE:
        return None

    return TRACK_QUEUE[guild_id]["current_track"]


def set_current_track_id(idx, guild_id):
    global TRACK_QUEUE
    TRACK_QUEUE[guild_id]["current_track"] = idx


async def get_track_url(yt_id):
    output = await yt_dlp_search_async("retrieve_url", yt_id, True)
    return output[0]["url"]


async def check_queue(guild_id):
    LOGGER.info(f"check_queue({guild_id})")
    #await message.edit(content=f"Проигрываю `{current_track['title']}`")
    #await message.edit(content=f"Трек был добавлен в очередь: `{current_track['title']}`")

    guild: discord.Guild = await bot.fetch_guild(guild_id)
    voice: VoiceClient = guild.voice_client

    if voice.is_playing():
        LOGGER.info("Already playing. Returning.")
        return

    cur_idx = get_current_track_id(guild_id)

    if cur_idx is None:
        LOGGER.info(f"cur_idx is None. Returning.")
        # Clear track queue
        init_track_list(guild_id)
        return

    track_len = len(TRACK_QUEUE[guild_id]["tracks"])
    if cur_idx >= track_len:
        init_track_list(guild_id)
        return

    # print(json.dumps(TRACK_QUEUE, indent=4))
    track_url = await get_track_url(TRACK_QUEUE[guild_id]["tracks"][cur_idx]["yt_id"])
    LOGGER.info(f"track_url = \"{track_url[:32]}\"")

    try:
        voice.play(FFmpegPCMAudio(track_url, **FFMPEG_OPTS))
    except Exception as e:
        msg = get_pretty_exception_str(e)
        print(msg)
        #await ctx.send(f"К сожалению произошла ошибка при попытке проиграть трек.\n\n{msg}")
        return

    set_current_track_id(cur_idx + 1, guild_id)


def is_url_compliant(url: str):
    allowed_urls = (
        'http://youtube.com/', 'http://youtu.be/',
        'http://www.youtube.com/', 'http://www.youtu.be/',
        'https://youtube.com/', 'https://youtu.be/',
        'https://www.youtube.com/', 'https://www.youtu.be/'
    )

    if url.startswith(allowed_urls):
        return True

    return False


async def play_or_search_track(cmd: str, ctx: commands.Context, query: str = None):
    global IS_SEARCH_STARTED

    voice: discord.VoiceProtocol = ctx.author.voice
    is_query_url = False

    if query is None:
        await ctx.send("Требуется минимум одно ключевое слово!")
        return

    if voice is None:
        await ctx.send("Вы должны быть в голосовом чате чтобы пользоваться ботом...")
        return

    if cmd == "play" and query.startswith(('http://', 'https://')):
        is_query_url = True
        if not is_url_compliant(query):
            await ctx.send("Разрешён только YouTube.")
            return

    try:
        await voice.channel.connect()
    except ClientException as e:
        if str(e) != "Already connected to a voice channel.":
            msg = get_pretty_exception_str(e, author=ctx.author, query=query)
            print(msg)
            await ctx.send(f"К сожалению произошла ошибка. Попробуйте ещё раз...\n\n{msg}")
            return

    last_message = await ctx.send("Обрабатываю...")
    channel = bot.get_channel(ctx.channel.id)
    message = await channel.fetch_message(last_message.id)

    videos = await yt_dlp_search_async(cmd, query, is_query_url)

    if cmd == "search":
        IS_SEARCH_STARTED = True
        response = ""

        for i in range(len(videos)):
            video_duration = time.strftime('%H:%M:%S', time.gmtime(videos[i]['duration']))

            if not re.search("^00:", video_duration) is None:
                video_duration = time.strftime('%M:%S', time.gmtime(videos[i]['duration']))

            response += f"> **{i + 1})** `{videos[i]['title']}` **`[{video_duration}]`**\n> \n"

        await message.edit(content=response[:response.rfind(">")] + response[response.rfind(">") + 1:])

        def is_digit(m):
            return IS_SEARCH_STARTED and m.author == ctx.author and m.content.isdigit()

        try:
            msg = await bot.wait_for('message', check=is_digit, timeout=30.0)
        except asyncio.TimeoutError:
            await message.edit(content="Время ожидания истекло (30 секунд). Попробуйте ещё раз.")
            return

        videos = [videos[int(msg.content) - 1]]

    # print(json.dumps(videos, indent=4))
    add_tracks_to_queue(videos, ctx.guild)


class MusicBot(commands.Cog):
    def __init__(self, bot):
        self.bot = bot


    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        LOGGER.info(f"Voice state changed from {before} to {after}.")


    @commands.command(aliases=['p', 'P'])
    async def play(self, ctx: commands.Context, *, query: str = None):
        await play_or_search_track("play", ctx, query)


    @commands.command(aliases=['s', 'S'])
    async def search(self, ctx: commands.Context, *, query: str = None):
        await play_or_search_track("search", ctx, query)


    @commands.command(aliases=['q'])
    async def queue(self, ctx: commands.Context):
        if ctx.guild.id not in TRACK_QUEUE:
            await ctx.send("> `Очередь пустая.`\n")
            return

        response = ""
        i = 0
        for track in TRACK_QUEUE[ctx.guild.id]["tracks"]:
            i += 1
            video_duration = time.strftime('%H:%M:%S', time.gmtime(track['duration']))

            if not re.search("^00:", video_duration) is None:
                video_duration = time.strftime('%M:%S', time.gmtime(track['duration']))

            response += f"> **{i})** `{track['title']}` **`[{video_duration}]`**\n> \n"
        if response == "":
            await ctx.send("> `Очередь пустая.`\n")
        else:
            await ctx.send(response[:response.rfind(">")] + response[response.rfind(">") + 1:])


    @commands.command()
    async def np(self, ctx: commands.Context):
        idx = get_current_track_id(ctx.guild.id)

        if not idx:
            await ctx.send("> Сейчас ничего не играет.")
            return

        current_track = TRACK_QUEUE[ctx.guild.id]["tracks"][idx]
        video_duration = time.strftime('%H:%M:%S', time.gmtime(current_track['duration']))
        if not re.search("^00:", video_duration) is None:
            video_duration = time.strftime('%M:%S', time.gmtime(current_track['duration']))

        await ctx.send(f"> Сейчас играет: `{current_track['title']}` **`{video_duration}`**")


    @commands.command()
    async def skip(self, ctx: commands.Context):
        voice = discord.utils.get(bot.voice_clients)
        if voice is not None:
            voice.stop()


    @commands.command()
    async def leave(self, ctx: commands.Context):
        await ctx.voice_client.disconnect()
        init_track_list(ctx.guild.id)


    async def run(self):
        while True:
            for guild_id in TRACK_QUEUE.keys():
                if len(TRACK_QUEUE[guild_id]["tracks"]) > 0:
                    await check_queue(guild_id)

            await asyncio.sleep(3)


def setup_logger():
    logger = logging.getLogger('discord')
    logger.setLevel(logging.DEBUG)

    logging.getLogger('discord.http').setLevel(logging.FATAL)
    logging.getLogger('discord.gateway').setLevel(logging.FATAL)
    logging.getLogger('discord.client').setLevel(logging.FATAL)
    logging.getLogger('discord.voice_client').setLevel(logging.FATAL)
    logging.getLogger('discord.player').setLevel(logging.FATAL)

    handler = logging.StreamHandler()

    dt_fmt = '%H:%M:%S %d-%m-%Y '
    formatter = logging.Formatter('[{asctime}] [{levelname:<8}] {name}: {message}', dt_fmt, style='{')
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


async def main():
    music_bot = MusicBot(bot)
    await bot.add_cog(music_bot)
    asyncio.create_task(bot.start(BOT_TOKEN))
    await music_bot.run()


if __name__ == "__main__":
    LOGGER = setup_logger()
    asyncio.run(main())
