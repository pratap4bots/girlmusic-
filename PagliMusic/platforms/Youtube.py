import asyncio
import os
import re
from typing import Union

import aiohttp
import yt_dlp
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from py_yt import VideosSearch

from PagliMusic import LOGGER
from PagliMusic.utils.formatters import time_to_seconds

# ================= CONFIG ================= #

YOUR_API_URL = None
FALLBACK_API_URL = "https://shrutibots.site"

# ================= API LOADER ================= #

async def load_api_url():
    global YOUR_API_URL
    logger = LOGGER("PagliMusic.platforms.Youtube")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://pastebin.com/raw/rLsBhAQa",
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status == 200:
                    YOUR_API_URL = (await response.text()).strip()
                    logger.info("API URL loaded successfully")
                else:
                    YOUR_API_URL = FALLBACK_API_URL
    except Exception:
        YOUR_API_URL = FALLBACK_API_URL


try:
    loop = asyncio.get_event_loop()
    if loop.is_running():
        asyncio.create_task(load_api_url())
    else:
        loop.run_until_complete(load_api_url())
except RuntimeError:
    pass

# ================= DOWNLOAD HELPERS ================= #

async def download_song(link: str) -> Union[str, None]:
    global YOUR_API_URL

    if not YOUR_API_URL:
        await load_api_url()

    video_id = link.split("v=")[-1].split("&")[0] if "v=" in link else link
    if not video_id or len(video_id) < 3:
        return None

    os.makedirs("downloads", exist_ok=True)
    file_path = f"downloads/{video_id}.mp3"

    if os.path.exists(file_path):
        return file_path

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{YOUR_API_URL}/download",
                params={"url": video_id, "type": "audio"},
                timeout=aiohttp.ClientTimeout(total=60),
            ) as response:
                if response.status != 200:
                    return None

                data = await response.json()
                token = data.get("download_token")
                if not token:
                    return None

            async with session.get(
                f"{YOUR_API_URL}/stream/{video_id}?type=audio",
                headers={"X-Download-Token": token},
                timeout=aiohttp.ClientTimeout(total=300),
            ) as file_response:
                if file_response.status != 200:
                    return None

                with open(file_path, "wb") as f:
                    async for chunk in file_response.content.iter_chunked(16384):
                        f.write(chunk)

        return file_path
    except Exception:
        return None


async def download_video(link: str) -> Union[str, None]:
    global YOUR_API_URL

    if not YOUR_API_URL:
        await load_api_url()

    video_id = link.split("v=")[-1].split("&")[0] if "v=" in link else link
    if not video_id or len(video_id) < 3:
        return None

    os.makedirs("downloads", exist_ok=True)
    file_path = f"downloads/{video_id}.mp4"

    if os.path.exists(file_path):
        return file_path

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{YOUR_API_URL}/download",
                params={"url": video_id, "type": "video"},
                timeout=aiohttp.ClientTimeout(total=60),
            ) as response:
                if response.status != 200:
                    return None

                data = await response.json()
                token = data.get("download_token")
                if not token:
                    return None

            async with session.get(
                f"{YOUR_API_URL}/stream/{video_id}?type=video",
                headers={"X-Download-Token": token},
                timeout=aiohttp.ClientTimeout(total=600),
            ) as file_response:
                if file_response.status != 200:
                    return None

                with open(file_path, "wb") as f:
                    async for chunk in file_response.content.iter_chunked(16384):
                        f.write(chunk)

        return file_path
    except Exception:
        return None


async def shell_cmd(cmd):
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, err = await proc.communicate()
    return (out or err).decode("utf-8")

# ================= YOUTUBE API CLASS ================= #

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.listbase = "https://youtube.com/playlist?list="
        self.regex = r"(youtube\.com|youtu\.be)"

    async def exists(self, link: str, videoid=None):
        if videoid:
            link = self.base + link
        return bool(re.search(self.regex, link))

    async def url(self, message: Message):
        msgs = [message, message.reply_to_message] if message.reply_to_message else [message]
        for msg in msgs:
            entities = msg.entities or msg.caption_entities or []
            for e in entities:
                if e.type in (MessageEntityType.URL, MessageEntityType.TEXT_LINK):
                    return e.url if e.url else msg.text[e.offset : e.offset + e.length]
        return None

    async def details(self, link: str, videoid=None):
        if videoid:
            link = self.base + link
        link = link.split("&")[0]

        results = VideosSearch(link, limit=1)
        r = (await results.next())["result"][0]

        return (
            r["title"],
            r["duration"],
            int(time_to_seconds(r["duration"])) if r["duration"] else 0,
            r["thumbnails"][0]["url"].split("?")[0],
            r["id"],
        )

    async def track(self, link: str, videoid=None):
        if videoid:
            link = self.base + link
        link = link.split("&")[0]

        results = VideosSearch(link, limit=1)
        r = (await results.next())["result"][0]

        track_details = {
            "title": r["title"],
            "link": r["link"],
            "vidid": r["id"],
            "duration_min": r["duration"],
            "thumb": r["thumbnails"][0]["url"].split("?")[0],
        }
        return track_details, r["id"]

    async def playlist(self, link, limit, user_id, videoid=None):
        if videoid:
            link = self.listbase + link
        link = link.split("&")[0]

        data = await shell_cmd(
            f"yt-dlp -i --get-id --flat-playlist --playlist-end {limit} {link}"
        )
        return [x for x in data.split("\n") if x]

    async def formats(self, link: str, videoid=None):
        if videoid:
            link = self.base + link
        link = link.split("&")[0]

        ydl = yt_dlp.YoutubeDL({"quiet": True})
        info = ydl.extract_info(link, download=False)

        formats = []
        for f in info.get("formats", []):
            if "dash" not in str(f.get("format", "")).lower():
                formats.append(
                    {
                        "format": f.get("format"),
                        "filesize": f.get("filesize"),
                        "format_id": f.get("format_id"),
                        "ext": f.get("ext"),
                        "format_note": f.get("format_note"),
                        "yturl": link,
                    }
                )
        return formats, link

    async def slider(self, link: str, index: int, videoid=None):
        if videoid:
            link = self.base + link
        link = link.split("&")[0]

        r = (await VideosSearch(link, limit=10).next())["result"][index]
        return (
            r["title"],
            r["duration"],
            r["thumbnails"][0]["url"].split("?")[0],
            r["id"],
        )

    async def download(self, link: str, mystic, video=False, videoid=None, **kwargs):
        if videoid:
            link = self.base + link

        try:
            file = await download_video(link) if video else await download_song(link)
            return (file, True) if file else (None, False)
        except Exception:
            return None, False
