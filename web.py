import asyncio
from base64 import b64encode
from datetime import timedelta
from html import escape
from pathlib import Path
from time import monotonic
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel, Field

from bot_meal import fetch_week_menus
from bot_notice import fetch_notices, search_notices
from config import APP_VERSION, TARGET_SITES
from utils import get_kst_now


router = APIRouter(prefix="/web", include_in_schema=False)
ASSETS = Path(__file__).resolve().with_name("web_assets")
FAVICON = b64encode((ASSETS / "favicon.png").read_bytes()).decode("ascii")
PAGE_HTML = (
    (ASSETS / "index.html").read_text(encoding="utf-8")
    .replace("{{APP_VERSION}}", escape(APP_VERSION))
    .replace("{{FAVICON}}", FAVICON)
)
BOARD_LABELS = {
    "haksa": "학사",
    "general": "일반",
    "dorm_general": "생활관 일반",
    "dorm_entrance": "생활관 입퇴사",
}
CACHE_SECONDS = 180
notice_lock = asyncio.Lock()
meal_locks = {0: asyncio.Lock(), 1: asyncio.Lock()}
notice_cache = None
meal_cache = {}
search_slots = asyncio.Semaphore(3)


class SearchQuery(BaseModel):
    q: str = Field(max_length=60)


@router.get("")
def page():
    return HTMLResponse(
        PAGE_HTML,
        headers={
            "Cache-Control": "no-cache",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "same-origin",
            "Content-Security-Policy": (
                "default-src 'none'; script-src 'self'; style-src 'self'; "
                "connect-src 'self'; img-src 'self' data:; base-uri 'none'; "
                "form-action 'none'; frame-ancestors 'none'"
            ),
        },
    )


@router.get("/app.css")
def stylesheet():
    return FileResponse(ASSETS / "app.css", media_type="text/css", headers={"Cache-Control": "no-cache"})


@router.get("/app.js")
def script():
    return FileResponse(ASSETS / "app.js", media_type="text/javascript", headers={"Cache-Control": "no-cache"})


@router.get("/meals")
async def meals(week: Literal["current", "next"] = "current"):
    offset = int(week == "next")
    today = get_kst_now().date()
    monday = today + timedelta(days=7 * offset - today.weekday())
    async with meal_locks[offset]:
        cached = meal_cache.get(offset)
        if cached and cached[0] == monday and cached[1] > monotonic():
            menus = cached[2]
        else:
            try:
                menus = await fetch_week_menus(monday, offset, timeout=5.0)
            except (httpx.HTTPError, TimeoutError):
                raise HTTPException(503, "학교 식단을 불러오지 못했습니다.") from None
            meal_cache[offset] = (monday, monotonic() + CACHE_SECONDS, menus)

    return {
        "today": today.isoformat(),
        "days": [
            {
                "date": day.isoformat(),
                "menus": [{"corner": corner, "items": menu.splitlines()} for corner, menu in entries],
            }
            for day, entries in menus.items()
        ],
    }


async def latest_board(site):
    try:
        async with asyncio.timeout(5.0):
            entries = await fetch_notices(site["url"], limit=4)
    except (httpx.HTTPError, TimeoutError):
        return None
    return [
        {
            "title": entry["title"],
            "link": entry["link"],
            "pinned": entry["is_fixed"],
        }
        for entry in entries
    ]


@router.get("/notices")
async def notices():
    global notice_cache
    async with notice_lock:
        if notice_cache and notice_cache[0] > monotonic():
            return notice_cache[1]

        results = await asyncio.gather(*(latest_board(site) for site in TARGET_SITES))
        if all(entries is None for entries in results):
            raise HTTPException(503, "학교 공지사항을 불러오지 못했습니다.")
        payload = {
            "boards": [
                {
                    "id": site["id"],
                    "label": BOARD_LABELS[site["id"]],
                    "available": entries is not None,
                    "items": entries or [],
                }
                for site, entries in zip(TARGET_SITES, results)
            ]
        }
        ttl = 30 if any(entries is None for entries in results) else CACHE_SECONDS
        notice_cache = (monotonic() + ttl, payload)
        return payload


@router.post("/search")
async def search(query: SearchQuery, response: Response):
    keyword = query.q.strip()
    if not keyword:
        raise HTTPException(422, "공지 제목에 들어갈 검색어를 입력해 주세요.")
    if search_slots.locked():
        raise HTTPException(429, "검색 요청이 많습니다. 잠시 후 다시 시도해 주세요.")

    async with search_slots:
        items, available, partial = await search_notices(keyword)
    if not available:
        raise HTTPException(503, "학교 공지사항을 검색하지 못했습니다.")
    response.headers["Cache-Control"] = "no-store"
    return {"items": items, "partial": partial}
