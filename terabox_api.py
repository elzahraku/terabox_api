"""
Terabox API - Support Folder, Subfolder & Direct Download
Jalankan: uvicorn terabox_api:app --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import aiohttp
import re
import asyncio
from typing import Optional

app = FastAPI(title="Terabox API", version="2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.terabox.com/",
    "Origin": "https://www.terabox.com",
}

# ─────────────────────────────────────────────
# HELPER: Ambil surl dari berbagai format link
# ─────────────────────────────────────────────
def extract_surl(url: str) -> Optional[str]:
    patterns = [
        r'surl=([^&\s]+)',
        r'/s/([^/?&\s]+)',
        r'sharing/link\?surl=([^&\s]+)',
    ]
    for p in patterns:
        m = re.search(p, url)
        if m:
            return m.group(1)
    return None


# ─────────────────────────────────────────────
# HELPER: Ambil info share (file + folder list)
# ─────────────────────────────────────────────
async def fetch_share_info(session: aiohttp.ClientSession, surl: str, dir_path: str = "/") -> dict:
    api_url = "https://www.terabox.com/api/shorturlinfo"
    params = {
        "app_id": "250528",
        "shorturl": surl,
        "root": "1",
        "dir": dir_path,
        "page": "1",
        "num": "1000",
        "order": "name",
        "desc": "0",
    }
    async with session.get(api_url, params=params, headers=HEADERS) as resp:
        return await resp.json(content_type=None)


# ─────────────────────────────────────────────
# HELPER: Ambil direct download link
# ─────────────────────────────────────────────
async def fetch_download_link(
    session: aiohttp.ClientSession,
    uk: str,
    shareid: str,
    sign: str,
    timestamp: str,
    fs_id: str,
) -> Optional[str]:
    api_url = "https://www.terabox.com/api/download"
    params = {
        "app_id": "250528",
        "uk": uk,
        "shareid": shareid,
        "sign": sign,
        "timestamp": timestamp,
        "fid_list": f"[{fs_id}]",
    }
    try:
        async with session.get(api_url, params=params, headers=HEADERS) as resp:
            data = await resp.json(content_type=None)
            if data.get("errno") == 0:
                dlink = data.get("dlink", [])
                if dlink:
                    return dlink[0].get("url")
    except Exception:
        pass
    return None


# ─────────────────────────────────────────────
# CORE: Rekursif ambil semua file dalam folder
# ─────────────────────────────────────────────
async def collect_files(
    session: aiohttp.ClientSession,
    surl: str,
    uk: str,
    shareid: str,
    sign: str,
    timestamp: str,
    dir_path: str = "/",
    depth: int = 0,
    max_depth: int = 5,
) -> list:
    if depth > max_depth:
        return []

    data = await fetch_share_info(session, surl, dir_path)
    if data.get("errno") != 0:
        return []

    items = data.get("list", [])
    files = []
    folder_tasks = []

    for item in items:
        name = item.get("server_filename", "unknown")
        size = item.get("size", 0)
        fs_id = str(item.get("fs_id", ""))
        is_dir = item.get("isdir") == 1
        path = item.get("path", "")

        if is_dir:
            # Rekursif masuk subfolder
            folder_tasks.append(
                collect_files(session, surl, uk, shareid, sign, timestamp, path, depth + 1, max_depth)
            )
        else:
            # Ambil direct download link
            dlink = await fetch_download_link(session, uk, shareid, sign, timestamp, fs_id)
            files.append({
                "file_name": name,
                "path": path,
                "size": size,
                "size_readable": format_size(size),
                "fs_id": fs_id,
                "download_url": dlink,
                "is_dir": False,
            })

    # Proses semua subfolder secara paralel
    if folder_tasks:
        results = await asyncio.gather(*folder_tasks)
        for result in results:
            files.extend(result)

    return files


def format_size(size: int) -> str:
    if size >= 1_073_741_824:
        return f"{size / 1_073_741_824:.2f} GB"
    elif size >= 1_048_576:
        return f"{size / 1_048_576:.2f} MB"
    elif size >= 1024:
        return f"{size / 1024:.2f} KB"
    return f"{size} B"


# ─────────────────────────────────────────────
# ENDPOINT UTAMA
# ─────────────────────────────────────────────
@app.get("/")
async def root():
    return {"status": "✅ Terabox API berjalan", "version": "2.0", "endpoints": ["/terabox", "/terabox/files"]}


@app.get("/terabox")
async def terabox_info(url: str = Query(..., description="Link Terabox")):
    """Ambil info dasar share (tidak rekursif)"""
    surl = extract_surl(url)
    if not surl:
        # Coba follow redirect dulu
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, allow_redirects=True, headers=HEADERS) as resp:
                    final_url = str(resp.url)
                    surl = extract_surl(final_url)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Gagal follow redirect: {e}")

    if not surl:
        raise HTTPException(status_code=400, detail="Tidak bisa ambil surl dari link ini")

    async with aiohttp.ClientSession() as session:
        data = await fetch_share_info(session, surl)

    if data.get("errno") != 0:
        raise HTTPException(status_code=400, detail=f"Terabox error: {data.get('errmsg', 'Unknown')}")

    items = data.get("list", [])
    file_list = []
    for item in items:
        file_list.append({
            "file_name": item.get("server_filename"),
            "size": item.get("size", 0),
            "size_readable": format_size(item.get("size", 0)),
            "is_dir": item.get("isdir") == 1,
            "fs_id": str(item.get("fs_id", "")),
            "path": item.get("path", ""),
        })

    return {
        "success": True,
        "title": data.get("share_title", ""),
        "uk": data.get("uk"),
        "shareid": data.get("shareid"),
        "sign": data.get("sign"),
        "timestamp": data.get("timestamp"),
        "total_files": len([f for f in file_list if not f["is_dir"]]),
        "total_folders": len([f for f in file_list if f["is_dir"]]),
        "files": file_list,
    }


@app.get("/terabox/files")
async def terabox_all_files(
    url: str = Query(..., description="Link Terabox"),
    max_depth: int = Query(5, description="Kedalaman subfolder maksimal (default: 5)"),
):
    """Ambil SEMUA file termasuk isi subfolder + direct download link"""
    surl = extract_surl(url)
    if not surl:
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(url, allow_redirects=True, headers=HEADERS) as resp:
                    surl = extract_surl(str(resp.url))
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Gagal follow redirect: {e}")

    if not surl:
        raise HTTPException(status_code=400, detail="Tidak bisa ambil surl dari link ini")

    async with aiohttp.ClientSession() as session:
        # Ambil info dasar dulu
        base_data = await fetch_share_info(session, surl)
        if base_data.get("errno") != 0:
            raise HTTPException(status_code=400, detail=f"Terabox error: {base_data.get('errmsg')}")

        uk = str(base_data.get("uk", ""))
        shareid = str(base_data.get("shareid", ""))
        sign = base_data.get("sign", "")
        timestamp = str(base_data.get("timestamp", ""))

        # Rekursif ambil semua file
        all_files = await collect_files(
            session, surl, uk, shareid, sign, timestamp,
            dir_path="/", max_depth=max_depth
        )

    total_size = sum(f["size"] for f in all_files)

    return {
        "success": True,
        "title": base_data.get("share_title", ""),
        "total_files": len(all_files),
        "total_size": format_size(total_size),
        "files": all_files,
    }

