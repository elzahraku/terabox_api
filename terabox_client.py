"""
Terabox API Client - untuk dipakai di bot Telegram kamu
Taruh file ini di folder bot kamu, misal: colong/terabox_client.py
"""

import aiohttp
from typing import Optional

# Ganti dengan IP/domain server kamu jika API di server berbeda
TERABOX_API = "http://localhost:8000"


async def get_terabox_info(url: str) -> Optional[dict]:
    """Ambil info dasar (cepat, tidak rekursif)"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{TERABOX_API}/terabox",
                params={"url": url},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception as e:
        print(f"[Terabox] Error get_info: {e}")
    return None


async def get_terabox_all_files(url: str, max_depth: int = 5) -> Optional[dict]:
    """Ambil SEMUA file termasuk subfolder + download link"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{TERABOX_API}/terabox/files",
                params={"url": url, "max_depth": max_depth},
                timeout=aiohttp.ClientTimeout(total=120)  # folder besar butuh waktu
            ) as resp:
                if resp.status == 200:
                    return await resp.json()
    except Exception as e:
        print(f"[Terabox] Error get_all_files: {e}")
    return None


def format_file_list(data: dict) -> str:
    """Format response jadi teks untuk dikirim ke user Telegram"""
    if not data or not data.get("success"):
        return "❌ Gagal mengambil data dari Terabox"

    title = data.get("title", "Tidak ada judul")
    total = data.get("total_files", 0)
    total_size = data.get("total_size", "?")
    files = data.get("files", [])

    text = f"📁 **{title}**\n"
    text += f"📦 Total: {total} file ({total_size})\n\n"

    for i, f in enumerate(files[:20], 1):  # Tampilkan max 20
        name = f.get("file_name", "?")
        size = f.get("size_readable", "?")
        dlink = f.get("download_url")
        text += f"{i}. `{name}` — {size}\n"
        if dlink:
            text += f"   [⬇️ Download]({dlink})\n"

    if total > 20:
        text += f"\n... dan {total - 20} file lainnya"

    return text


# ─── Contoh penggunaan di handler bot ───────
# from colong.terabox_client import get_terabox_all_files, format_file_list
#
# @bot.on_message(filters.regex(r'terabox\.com|1drv\.ms'))
# async def handle_terabox(client, message):
#     msg = await message.reply("⏳ Mengambil info file...")
#     data = await get_terabox_all_files(message.text)
#     text = format_file_list(data)
#     await msg.edit(text, disable_web_page_preview=True)

