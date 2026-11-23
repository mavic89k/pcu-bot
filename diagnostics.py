import asyncio
from uuid import uuid4

import httpx

import config
from bot_notice import fetch_notices
from database import check_notice_db
from utils import get_kst_now, send_telegram_msg


async def run_diagnostics() -> int:
    try:
        config.validate_settings()
    except RuntimeError as error:
        print(error)
        return 1

    print("[1/4] 운영 공지 DB 읽기")
    if check_notice_db() != 0:
        return 1

    stage = "[2/4] 학교 공지 조회"
    print(stage)
    try:
        notices = {}
        for site in config.TARGET_SITES:
            entries = await fetch_notices(site["url"], limit=1)
            print(f"  {site['name']}: {len(entries)}건")
            if entries:
                notice = entries[0]
                notices[site["id"]] = {
                    field: notice[field] for field in ("id", "title", "link")
                }
        if not notices:
            print("실패: 저장할 공지를 찾지 못했습니다.")
            return 1

        stage = "[3/4] Firebase 테스트 기록 저장 및 재조회"
        print(stage)
        check_id = uuid4().hex
        path = f"diagnostics/{check_id}"
        url = f"{config.FIREBASE_DB_URL.rstrip('/')}/{path}.json"
        record = {"checked_at": get_kst_now().isoformat(), "notices": notices}
        params = {"auth": config.FIREBASE_SECRET}
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.put(url, params=params, json=record)
            response.raise_for_status()
            response = await client.get(url, params=params)
            response.raise_for_status()
            if response.json() != record:
                print(f"실패: {path}에서 다시 읽은 기록이 저장한 값과 다릅니다.")
                return 1
        print(f"  저장 및 재조회 성공 ({path})")

        stage = "[4/4] Telegram 테스트 알림 발송"
        print(stage)
        await send_telegram_msg(
            f"🧪 배재대 알리미 연동 테스트\n"
            f"Firebase 읽기·쓰기 및 학교 공지 {len(notices)}건 조회 성공\n"
            f"테스트 ID {check_id}"
        )
    except httpx.HTTPStatusError as error:
        print(f"{stage} 실패 (HTTP {error.response.status_code})")
        return 1
    except (httpx.HTTPError, httpx.InvalidURL, ValueError, RuntimeError) as error:
        print(f"{stage} 실패 ({type(error).__name__})")
        return 1

    print("전체 테스트 성공")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run_diagnostics()))
