# config.py

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(
    Path(__file__).with_name(".env"),
    override=False,
    encoding="utf-8-sig",
    interpolate=False,
)

# --- 버전 관리 ---
APP_VERSION = "2.1.0"
LAST_UPDATED = "2026-11-09"

# --- Firebase Database 설정 ---
FIREBASE_DB_URL = os.getenv("FIREBASE_DB_URL", "").strip()
FIREBASE_SECRET = os.getenv("FIREBASE_SECRET", "").strip()

# --- 텔레그램 봇 토큰 및 채팅방 설정 ---
NOTIFIER_TELEGRAM_TOKEN = os.getenv("NOTIFIER_TELEGRAM_TOKEN", "").strip()
CHAT_ID = os.getenv("CHAT_ID", "").strip()

# --- 배재대 공지사항 감시 대상 사이트 ---
NOTICE_DB_FILE = "notices_db.json"
TARGET_SITES = [
    {"id": "haksa", "name": "배재대 학사공지", "url": "https://www.pcu.ac.kr/kor/article/Haksa_1"},
    {"id": "general", "name": "배재대 일반공지", "url": "https://www.pcu.ac.kr/kor/article/Notify_1"},
    {"id": "dorm_general", "name": "생활관 일반공지", "url": "https://www.pcu.ac.kr/article/pitel_notice/api"},
    {"id": "dorm_entrance", "name": "생활관 입퇴사공지", "url": "https://www.pcu.ac.kr/article/pitel_notice2/api"}
]


def validate_settings() -> None:
    required = {
        "FIREBASE_DB_URL": FIREBASE_DB_URL,
        "FIREBASE_SECRET": FIREBASE_SECRET,
        "NOTIFIER_TELEGRAM_TOKEN": NOTIFIER_TELEGRAM_TOKEN,
        "CHAT_ID": CHAT_ID,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        raise RuntimeError("필수 환경변수가 설정되지 않았습니다: " + ", ".join(missing))
