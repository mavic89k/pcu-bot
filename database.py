# database.py

import httpx
import config as config

# =============================================================================
# [공지사항 DB] Firebase 저장소 관리
# =============================================================================
def _fetch_notice_db() -> tuple[int, dict | None]:
    url = f"{config.FIREBASE_DB_URL.rstrip('/')}/notices.json"
    response = httpx.get(url, params={"auth": config.FIREBASE_SECRET}, timeout=5.0)
    response.raise_for_status()
    data = response.json()
    if data is not None and not isinstance(data, dict):
        raise ValueError("Unexpected notice database response")
    return response.status_code, data


def load_notice_db() -> dict | None:
    """Firebase에서 최신 공지 번호 데이터를 불러옵니다."""
    try:
        _, data = _fetch_notice_db()
        return data or {}
    except (httpx.HTTPError, httpx.InvalidURL, ValueError):
        pass

    print("⚠️ [Firebase] 공지 DB를 불러오지 못했습니다.")
    return None

def save_notice_db(data: dict):
    """Firebase에 갱신된 공지 번호 데이터를 덮어씁니다."""
    try:
        url = f"{config.FIREBASE_DB_URL.rstrip('/')}/notices.json"
        resp = httpx.put(url, params={"auth": config.FIREBASE_SECRET}, json=data, timeout=5.0)
        resp.raise_for_status()
    except (httpx.HTTPError, httpx.InvalidURL):
        print("⚠️ [Firebase] 공지 DB를 저장하지 못했습니다.")

def load_next_meal_alert() -> tuple[bool, str | None]:
    """미발송 상태와 조회 실패를 구분합니다."""
    try:
        url = f"{config.FIREBASE_DB_URL.rstrip('/')}/next_meal_alert.json"
        response = httpx.get(url, params={"auth": config.FIREBASE_SECRET}, timeout=5.0)
        response.raise_for_status()
        data = response.json()
        if data is None or isinstance(data, str):
            return True, data
    except (httpx.HTTPError, httpx.InvalidURL, ValueError):
        pass
    print("⚠️ [Firebase] 다음 주 식단 알림 상태를 불러오지 못했습니다.")
    return False, None


def save_next_meal_alert(week: str) -> None:
    try:
        url = f"{config.FIREBASE_DB_URL.rstrip('/')}/next_meal_alert.json"
        response = httpx.put(url, params={"auth": config.FIREBASE_SECRET}, json=week, timeout=5.0)
        response.raise_for_status()
    except (httpx.HTTPError, httpx.InvalidURL):
        print("⚠️ [Firebase] 다음 주 식단 알림 상태를 저장하지 못했습니다.")


def check_notice_db() -> int:
    """Cloudtype 터미널에서 공지 DB 읽기 결과를 출력합니다."""
    missing = [
        name for name in ("FIREBASE_DB_URL", "FIREBASE_SECRET")
        if not getattr(config, name)
    ]
    if missing:
        print("필수 환경변수 누락: " + ", ".join(missing))
        return 1

    try:
        status, data = _fetch_notice_db()
    except httpx.HTTPStatusError as error:
        print(f"[Firebase] 공지 DB 읽기 실패 (HTTP {error.response.status_code})")
        return 1
    except (httpx.HTTPError, httpx.InvalidURL, ValueError) as error:
        print(f"[Firebase] 공지 DB 읽기 실패 ({type(error).__name__})")
        return 1

    print(f"[Firebase] 공지 DB 읽기 성공 (HTTP {status}, 게시판 {len(data or {})}개)")
    return 0


if __name__ == "__main__":
    raise SystemExit(check_notice_db())
