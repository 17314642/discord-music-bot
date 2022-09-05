#!/usr/bin/env python3

# -*- coding: utf-8 -*-
import asyncio
import time
import re
import os

# Discord bot API
import discord
import youtube_dl.YoutubeDL
from discord.errors import ClientException
from discord.ext import commands
from discord import FFmpegPCMAudio
from discord.utils import get
from discord.voice_client import VoiceClient

# Video download
from youtube_dl import YoutubeDL

try:
    # BOT_TOKEN = os.environ['BOT_TOKEN']
    BOT_TOKEN = "NzM1MDcwMjM4MzcwMDM3ODIw.Xxa5gQ.bfNEXcPg6-rJdKhUh29DTOKsK6w"
except KeyError:
    print("Токен не был указан. Укажите его в \"start.sh\"")
    exit()

TRACK_QUEUE = {}

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="-", description="This is a Random Bot", intents=intents)

bIsSearchStarted = False
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
    return string[:string.rfind(replace_string)] + string[string.rfind(replace_string) + 1:]


def add_track_to_queue(track, guild: discord.Guild):
    global TRACK_QUEUE

    try:
        TRACK_QUEUE[guild.id].append(
            {"title": track["title"], "url": track["formats"][0]["url"], "duration": track["duration"],
             "isCurrentTrack": False})
    except KeyError:
        TRACK_QUEUE[guild.id] = []
        TRACK_QUEUE[guild.id].append(
            {"title": track["title"], "url": track["formats"][0]["url"], "duration": track["duration"],
             "isCurrentTrack": False})

    # os.system("clear")
    # print(f"Numbers of servers: {len(TRACK_QUEUE)}")
    # i = 0
    # for server in TRACK_QUEUE:
    #     i += 1
    #     print(f"{i}. {bot.get_guild(server)}")
    #     for k in range(len(TRACK_QUEUE[server])):
    #         print(f"    {i}.{k + 1}. {TRACK_QUEUE[server][k]['title']}")
    #     print()

    return len(TRACK_QUEUE) - 1


def get_current_track(guild: discord.Guild):
    if guild.id not in TRACK_QUEUE:
        return None

    for track in TRACK_QUEUE[guild.id]:
        if track["isCurrentTrack"]:
            return track


def set_current_track(track, guild):
    for track_in_queue in TRACK_QUEUE[guild.id]:
        if track['title'] == track_in_queue['title'] and track['duration'] == track_in_queue['duration']:
            for current_active_track in TRACK_QUEUE[guild.id]:
                if current_active_track['isCurrentTrack']:
                    current_active_track['isCurrentTrack'] = False
                track_in_queue['isCurrentTrack'] = True


def check_queue(current_index, guild: discord.Guild):
    global TRACK_QUEUE

    if current_index is None or len(TRACK_QUEUE[guild.id]) == 0:
        return

    if not current_index == len(TRACK_QUEUE[guild.id]) - 1:
        current_index = current_index + 1
        set_current_track(TRACK_QUEUE[guild.id][current_index], guild)
        voice: VoiceClient = guild.voice_client
        voice.play(FFmpegPCMAudio(TRACK_QUEUE[guild.id][current_index]['url'], **FFMPEG_OPTS),
                   after=lambda e: check_queue(current_index, guild))
    else:
        # Clear track queue
        TRACK_QUEUE[guild.id] = []


@bot.command(aliases=['s', 'S'])
async def search(ctx: commands.Context, *, search: str = None):
    if search is None:
        await ctx.send("Требуется минимум одно ключевое слово!")
        return

    voice: discord.VoiceProtocol = ctx.author.voice

    if voice is None:
        await ctx.send("Вы должны быть в голосовом чате чтобы пользоваться ботом...")
        return

    try:
        await voice.channel.connect()
    except ClientException as e:
        if str(e) != "Already connected to a voice channel.":
            pass
        else:
            exception_msg = f"Exception caught (author=\"{ctx.author}\", query=\"{query}\"): {e}"
            print(exception_msg)
            await ctx.send(f"К сожалению произошла ошибка. Попробуйте ещё раз... ({exception_msg})")

    last_message = await ctx.send("Обрабатываю...")
    channel = bot.get_channel(ctx.channel.id)
    message = await channel.fetch_message(last_message.id)

    global bIsSearchStarted
    bIsSearchStarted = True

    response = ""

    with YoutubeDL({'format': 'bestaudio', 'noplaylist': 'True', 'quiet': 'True', 'cookiefile': 'cookies.txt',
                    "logger": YoutubeDL_Logger}) as ydl:
        videos = ydl.extract_info(f"ytsearch15:{search}", download=False)['entries']

        for i in range(len(videos)):
            video_duration = time.strftime('%H:%M:%S', time.gmtime(videos[i]['duration']))

            if not re.search("^00:", video_duration) is None:
                video_duration = time.strftime('%M:%S', time.gmtime(videos[i]['duration']))

            response += f"> **{i + 1})** `{videos[i]['title']}` **`[{video_duration}]`**\n> \n"

    await message.edit(content=response[:response.rfind(">")] + response[response.rfind(">") + 1:])

    def is_digit(m):
        return bIsSearchStarted and m.author == ctx.author and m.content.isdigit()

    try:
        msg = await bot.wait_for('message', check=is_digit, timeout=30.0)
    except asyncio.TimeoutError:
        await message.edit(content="Время ожидания истекло (30 секунд). Попробуйте ещё раз.")
        return

    selected_track = videos[int(msg.content) - 1]
    add_track_to_queue(selected_track, ctx.guild)

    if not ctx.voice_client.is_playing():
        global TRACK_QUEUE

        current_track = TRACK_QUEUE[ctx.guild.id][0]
        set_current_track(current_track, ctx.guild)

        await message.edit(content=f"Проигрываю `{selected_track['title']}`")

        try:
            ctx.voice_client.play(FFmpegPCMAudio(selected_track['formats'][0]['url'], **FFMPEG_OPTS),
                                  after=lambda e: check_queue(0, ctx.guild))
        except Exception as e:
            print(f'Exception: {str(e)}')
    else:
        await message.edit(content=f"Трек был добавлен в очередь: `{selected_track['title']}`")


@bot.command()
async def leave(ctx: commands.Context):
    await ctx.voice_client.disconnect()
    global TRACK_QUEUE
    TRACK_QUEUE[ctx.guild.id] = []


@bot.command(aliases=['p', 'P'])
async def play(ctx: commands.Context, *, query: str = None):
    if query is None:
        await ctx.send("Требуется минимум одно ключевое слово!")
        return

    voice: discord.VoiceProtocol = ctx.author.voice

    if voice is None:
        await ctx.send("Вы должны быть в голосовом чате чтобы пользоваться ботом...")
        return

    if query.startswith(('http://', 'https://')) and not query.startswith(('http://youtube.com/', 'http://youtu.be/',
                                                                           'http://www.youtube.com/', 'http://www.youtu.be/',
                                                                           'https://youtube.com/', 'https://youtu.be/',
                                                                           'https://www.youtube.com/', 'https://www.youtu.be/')):
        await ctx.send("Разрешён только YouTube.")
        return

    try:
        await voice.channel.connect()
    except ClientException as e:
        if str(e) != "Already connected to a voice channel.":
            await ctx.send("Exception caught:" + str(e))

    last_message = await ctx.send("Обрабатываю...")
    channel: discord.TextChannel = bot.get_channel(ctx.channel.id)
    message = await channel.fetch_message(last_message.id)

    with YoutubeDL({'format': 'bestaudio', 'quiet': 'True', 'cookiefile': 'cookies.txt',
                    "logger": YoutubeDL_Logger}) as ydl:
        try:
            videos = ydl.extract_info(query, download=False)
            try:
                for video_num, video_in_playlist in enumerate(videos['entries']):
                    add_track_to_queue(video_in_playlist, ctx.guild)
                video = videos['entries'][-1]
            except KeyError:
                video = videos
                add_track_to_queue(video, ctx.guild)
        except youtube_dl.utils.DownloadError as error:
            try:
                video = ydl.extract_info(f"ytsearch:{query}", download=False)['entries'][0]
                add_track_to_queue(video, ctx.guild)
            except IndexError:
                await last_message.edit(content=f"Поиск на YouTube вернул 0 результатов.")
                return


    if not ctx.voice_client.is_playing():
        global TRACK_QUEUE

        current_track = TRACK_QUEUE[ctx.guild.id][0]
        set_current_track(current_track, ctx.guild)

        await message.edit(content=f"Проигрываю `{current_track['title']}`")

        try:
            ctx.voice_client.play(FFmpegPCMAudio(current_track['url'], **FFMPEG_OPTS),
                                  after=lambda e: check_queue(0, ctx.guild))
        except Exception as e:
            print(f'Exception: {str(e)}')
    else:
        await message.edit(content=f"Трек был добавлен в очередь: `{video['title']}`")


@bot.command(aliases=["q"])
async def queue(ctx: commands.Context):
    if ctx.guild.id not in TRACK_QUEUE:
        await ctx.send("> `Очередь пустая.`\n")
        return

    response = ""
    i = 0
    for track in TRACK_QUEUE[ctx.guild.id]:
        i += 1
        video_duration = time.strftime('%H:%M:%S', time.gmtime(track['duration']))

        if not re.search("^00:", video_duration) is None:
            video_duration = time.strftime('%M:%S', time.gmtime(track['duration']))

        response += f"> **{i})** `{track['title']}` **`[{video_duration}]`**\n> \n"
    if response == "":
        await ctx.send("> `Очередь пустая.`\n")
    else:
        await ctx.send(response[:response.rfind(">")] + response[response.rfind(">") + 1:])


@bot.command()
async def skip(ctx: commands.Context):
    voice = get(bot.voice_clients)
    if voice is not None:
        voice.stop()


@bot.command()
async def np(ctx: commands.Context):
    current_track = get_current_track(ctx.guild)

    if current_track is None:
        await ctx.send("> Сейчас ничего не играет.")
        return

    video_duration = time.strftime('%H:%M:%S', time.gmtime(current_track['duration']))
    if not re.search("^00:", video_duration) is None:
        video_duration = time.strftime('%M:%S', time.gmtime(current_track['duration']))

    await ctx.send(f"> Сейчас играет: `{current_track['title']}` **`{video_duration}`**")


bot.run(BOT_TOKEN)
