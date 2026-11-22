# database.py

import httpx
import config as config

# =============================================================================
# [공지사항 DB] Firebase 저장소 관리
# =============================================================================
def load_notice_db() -> dict | None:
    """Firebase에서 최신 공지 번호 데이터를 불러옵니다."""
    try:
        url = f"{config.FIREBASE_DB_URL.rstrip('/')}/notices.json"
        resp = httpx.get(url, params={"auth": config.FIREBASE_SECRET}, timeout=5.0)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, dict):
            return data
        if data is None:
            return {}
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
