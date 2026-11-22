# utils.py

import asyncio
import datetime
import logging
import re
import unicodedata
from time import perf_counter

import httpx

import config
from typing import Tuple, Optional

def get_kst_now() -> datetime.datetime:
    """
    서버가 외국(UTC)에 배포되더라도 무조건 한국 시간(KST)을 기준으로 계산하도록 강제합니다.
    """
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    kst_tz = datetime.timezone(datetime.timedelta(hours=9))
    return utc_now.astimezone(kst_tz)

def parse_date_from_kakao_entity(utterance: str) -> Tuple[Optional[datetime.date], Optional[str]]:
    """
    사용자가 챗봇에 입력한 텍스트에서 날짜를 지능적으로 추출합니다.
    (예: "내일", "7월 18일", "0718" 등을 파이썬 날짜 객체로 변환)
    """
    kst_now = get_kst_now()
    today = kst_now.date()
    
    # 공백을 모두 제거하여 정규식 매칭 확률을 높입니다.
    text = utterance.strip().replace(" ", "")
    
    # 1. 일상어(상대적 날짜) 매칭
    if any(keyword in text for keyword in ["오늘", "지금", "현재"]): 
        return today, "오늘"
    if any(keyword in text for keyword in ["내일", "낼"]): 
        return today + datetime.timedelta(days=1), "내일"
    if "모레" in text: 
        return today + datetime.timedelta(days=2), "모레"

    # 2. "O월O일" 형태 매칭 (예: 7월18일)
    match_korean = re.search(r'(\d{1,2})월(\d{1,2})일', text)
    if match_korean: 
        month, day = int(match_korean.group(1)), int(match_korean.group(2))
        return datetime.date(today.year, month, day), f"{month}월 {day}일"
        
    # 3. "O/O" 또는 "O-O" 형태 매칭 (예: 7/18, 7-18)
    match_slash = re.search(r'(\d{1,2})[/-](\d{1,2})', text)
    if match_slash: 
        month, day = int(match_slash.group(1)), int(match_slash.group(2))
        return datetime.date(today.year, month, day), f"{month}월 {day}일"

    # 4. "OOOO" 형태의 연속된 숫자 매칭 (예: 0718)
    match_num = re.search(r'(?<!\d)(\d{2})(\d{2})(?!\d)', text)
    if match_num: 
        month, day = int(match_num.group(1)), int(match_num.group(2))
        return datetime.date(today.year, month, day), f"{month}월 {day}일"

    # 매칭되는 날짜가 없으면 None 반환
    return None, None

def normalize_search_text(text: str) -> str:
    return "".join(unicodedata.normalize("NFKC", text).casefold().split())


async def fetch_school_page(
    url: str | httpx.URL, *, operation: str, timeout: float, follow_redirects: bool = False,
) -> httpx.Response:
    url = httpx.URL(url)
    logger = logging.getLogger("uvicorn.error")
    started = perf_counter()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                url, headers={"User-Agent": "Mozilla/5.0"}, follow_redirects=follow_redirects,
            )
        response.raise_for_status()
    except (httpx.HTTPError, asyncio.CancelledError) as exc:
        status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else "-"
        logger.warning(
            "School request failed operation=%s path=%s elapsed_ms=%.0f error=%s status=%s",
            operation, url.path, (perf_counter() - started) * 1000, type(exc).__name__, status,
        )
        raise

    logger.info(
        "School request completed operation=%s path=%s elapsed_ms=%.0f status=%d",
        operation, url.path, (perf_counter() - started) * 1000, response.status_code,
    )
    return response


async def send_telegram_msg(text: str) -> None:
    url = f"https://api.telegram.org/bot{config.NOTIFIER_TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": config.CHAT_ID, "text": text}
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        if response.json().get("ok") is not True:
            raise RuntimeError("텔레그램이 알림 발송을 확인하지 않았습니다.")
