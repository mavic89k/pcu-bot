import argparse
import asyncio
from uuid import uuid4

import httpx

import config
from bot_notice import fetch_notices
from database import check_notice_db
from utils import get_kst_now, send_telegram_msg


async def read_school_notices() -> dict:
    notices = {}
    for site in config.TARGET_SITES:
        entries = await fetch_notices(site["url"], limit=1)
        print(f"  {site['name']}: {len(entries)}건")
        if entries:
            notice = entries[0]
            notices[site["id"]] = {
                field: notice[field] for field in ("id", "title", "link")
            }
    return notices


async def verify_firebase_write(check_id: str, data: dict) -> bool:
    path = f"diagnostics/{check_id}"
    url = f"{config.FIREBASE_DB_URL.rstrip('/')}/{path}.json"
    record = {"checked_at": get_kst_now().isoformat(), **data}
    params = {"auth": config.FIREBASE_SECRET}
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.put(url, params=params, json=record)
        response.raise_for_status()
        response = await client.get(url, params=params)
        response.raise_for_status()
        if response.json() != record:
            print(f"실패: {path}에서 다시 읽은 기록이 저장한 값과 다릅니다.")
            return False
    print(f"  저장 및 재조회 성공 ({path})")
    return True


async def run_diagnostics(mode: str = "all") -> int:
    if mode == "db":
        return check_notice_db()

    required = {
        "all": ("FIREBASE_DB_URL", "FIREBASE_SECRET", "NOTIFIER_TELEGRAM_TOKEN", "CHAT_ID"),
        "notices": (),
        "write": ("FIREBASE_DB_URL", "FIREBASE_SECRET"),
        "telegram": ("NOTIFIER_TELEGRAM_TOKEN", "CHAT_ID"),
    }
    missing = [name for name in required[mode] if not getattr(config, name)]
    if missing:
        print("필수 환경변수 누락: " + ", ".join(missing))
        return 1

    check_id = uuid4().hex
    notices = {}
    if mode == "all":
        print("[1/4] 운영 공지 DB 읽기")
        if check_notice_db() != 0:
            return 1

    try:
        if mode in ("all", "notices"):
            stage = "학교 공지 조회"
            print(f"[2/4] {stage}" if mode == "all" else stage)
            notices = await read_school_notices()
            if not notices:
                print("실패: 공지를 찾지 못했습니다.")
                return 1

        if mode in ("all", "write"):
            stage = "Firebase 테스트 기록 저장 및 재조회"
            print(f"[3/4] {stage}" if mode == "all" else stage)
            data = {"notices": notices} if mode == "all" else {"kind": "write_test"}
            if not await verify_firebase_write(check_id, data):
                return 1

        if mode in ("all", "telegram"):
            stage = "Telegram 테스트 알림 발송"
            print(f"[4/4] {stage}" if mode == "all" else stage)
            message = "🧪 배재대 알리미 Telegram 발송 테스트"
            if mode == "all":
                message = f"🧪 배재대 알리미 연동 테스트\nFirebase 읽기·쓰기 및 학교 공지 {len(notices)}건 조회 성공"
            await send_telegram_msg(f"{message}\n테스트 ID {check_id}")
    except httpx.HTTPStatusError as error:
        print(f"{stage} 실패 (HTTP {error.response.status_code})")
        return 1
    except (httpx.HTTPError, httpx.InvalidURL, ValueError, RuntimeError) as error:
        print(f"{stage} 실패 ({type(error).__name__})")
        return 1

    print("전체 테스트 성공" if mode == "all" else f"{stage} 성공")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="배재대 알리미 연동 진단")
    parser.add_argument(
        "mode", nargs="?", default="all",
        choices=("all", "db", "notices", "write", "telegram"),
    )
    raise SystemExit(asyncio.run(run_diagnostics(parser.parse_args().mode)))
