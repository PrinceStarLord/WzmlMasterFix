#!/usr/bin/env python3
import re
import asyncio
from aiohttp import ClientSession, ClientTimeout
from bs4 import BeautifulSoup

from pyrogram.handlers import MessageHandler
from pyrogram.filters import command

from bot import LOGGER, bot
from bot.helper.telegram_helper.filters import CustomFilters
from bot.helper.telegram_helper.bot_commands import BotCommands
from bot.helper.telegram_helper.message_utils import editMessage, sendMessage
from bot.helper.ext_utils.bot_utils import is_url

DIRECT_URL_RE = re.compile(
    r"https://video-downloads\.googleusercontent\.com/[^\s'\"]+", re.I
)

SKIP_TEXTS = {"login", "vpn", "idm", "ida"}
BRACKET_NAME_RE = re.compile(r"\[(.*?)\]")


async def _resolve(session, url):
    try:
        async with session.get(
            url, allow_redirects=True, timeout=ClientTimeout(total=10)
        ) as resp:
            if resp.status != 200:
                return url
            text = await resp.text(errors="ignore")
            match = DIRECT_URL_RE.search(text)
            return match.group(0) if match else url
    except Exception:
        return url


async def _fetch(session, url):
    async with session.get(url, timeout=ClientTimeout(total=15)) as resp:
        if resp.status != 200:
            raise Exception(f"HTTP {resp.status}")
        return await resp.text()


async def extract_hubcloud_links(url):
    for attempt in range(3):
        try:
            async with ClientSession() as session:
                html1 = await _fetch(session, url)
                soup1 = BeautifulSoup(html1, "lxml")
                dl_tag = soup1.find("a", {"id": "download"})
                if not dl_tag or "href" not in dl_tag.attrs:
                    raise Exception("Download link not found")
                second_url = dl_tag["href"]

                html2 = await _fetch(session, second_url)
                soup2 = BeautifulSoup(html2, "lxml")

                title_tag = soup2.find("div", {"class": "card-header"})
                title = title_tag.get_text(strip=True) if title_tag else None

                size_tag = soup2.find("i", {"id": "size"})
                size = size_tag.get_text(strip=True) if size_tag else None

                links = []
                for a in soup2.find_all("a", href=True):
                    href = a["href"].strip(" ").replace(" ", "%20")
                    text = a.get_text(strip=True)
                    if not href.startswith("http"):
                        continue
                    if text.lower() in SKIP_TEXTS or "download" not in text.lower():
                        continue
                    if "?id=" in href:
                        href = await _resolve(session, href)
                    if bmatch := BRACKET_NAME_RE.search(text):
                        name = bmatch.group(1)
                    else:
                        name = re.sub(r"(?i)download", "", text).strip(" :-")
                    links.append((name, href))

                if not links:
                    raise Exception("No valid download links found")

                return title, size, links
        except Exception as e:
            if attempt < 2:
                await asyncio.sleep(1)
                continue
            raise RuntimeError(f"Failed after 3 attempts: {e}")


async def bypass_link(_, message):
    help_msg = (
        "<b>By replying to a HubCloud link:</b>"
        f"\n<code>/{BotCommands.BypassCommand[0]} or /{BotCommands.BypassCommand[1]}</code>"
        "\n\n<b>By sending a HubCloud link:</b>"
        f"\n<code>/{BotCommands.BypassCommand[0]} or /{BotCommands.BypassCommand[1]}"
        + " {link}"
        + "</code>"
    )

    rply = message.reply_to_message
    link = None
    if len(message.command) > 1:
        link = message.command[1].strip()
    elif rply and rply.text:
        link = rply.text.split("\n", 1)[0].strip()

    if not link or not is_url(link):
        return await sendMessage(message, help_msg)

    temp_send = await sendMessage(message, "<i>Bypassing link, please wait...</i>")
    try:
        title, size, links = await extract_hubcloud_links(link)
    except Exception as e:
        LOGGER.error(str(e))
        return await editMessage(temp_send, f"<b>Bypass Failed:</b> <i>{e}</i>")

    msg = "┌ 📁 <b>File Name :-</b> "
    msg += f"<code>{title}</code>\n" if title else "\n"
    msg += "│\n"
    msg += "├ 📂 <b>File Size :-</b> "
    msg += f"{size}\n" if size else "\n"
    msg += "│\n"
    msg += "└ 🔗 <b>Links :-</b> "
    msg += " | ".join(f'<a href="{href}">{name}</a>' for name, href in links)

    await editMessage(temp_send, msg.strip())


bot.add_handler(
    MessageHandler(
        bypass_link,
        filters=command(BotCommands.BypassCommand)
        & CustomFilters.authorized
        & ~CustomFilters.blacklisted,
    )
)
