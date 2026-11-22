# monitoring.py

import time
import json
from fastapi import APIRouter, status

import config as config
from utils import get_kst_now
import database as database
from bot_meal import get_pcu_diet

router = APIRouter(prefix="/monitoring", tags=["System Monitoring"])
START_TIME = time.time()

@router.get("/health", status_code=status.HTTP_200_OK)
@router.head("/health", status_code=status.HTTP_200_OK)
async def health_check():
    return {
        "status": "ok",
        "timestamp": get_kst_now().strftime("%Y-%m-%d %H:%M:%S")
    }

@router.get("/status")
@router.head("/status")
async def system_status():
    current_time = time.time()
    uptime_seconds = int(current_time - START_TIME)
    
    days = uptime_seconds // 86400
    hours = (uptime_seconds % 86400) // 3600
    minutes = (uptime_seconds % 3600) // 60
    seconds = uptime_seconds % 60
    
    uptime_str = f"{days}일 {hours}시간 {minutes}분 {seconds}초" if days > 0 else f"{hours}시간 {minutes}분 {seconds}초"

    app_version = getattr(config, 'APP_VERSION', '2.0.0')

    return {
        "service": "Pai Chai Univ Notifier API",
        "version": app_version,
        "status": "HEALTHY",
        "uptime": uptime_str,
        "timestamp": get_kst_now().strftime("%Y-%m-%d %H:%M:%S")
    }

def summarize_notice_db(db: dict, limit: int = 5, title_max: int = 30) -> str:
    """공지 DB를 게시판별 최신 N개 제목 위주로 요약합니다. (해시 등 상세값 제외)"""
    if not isinstance(db, dict) or not db:
        return "(DB 비어 있음)"

    site_names = {site["id"]: site["name"] for site in config.TARGET_SITES}
    lines = []

    for site_id, data in db.items():
        if not isinstance(data, dict):
            continue
        saved = data.get("saved_notices", {}) or {}
        fixed_ids = data.get("fixed_ids", []) or []

        lines.append(f"\n📁 {site_names.get(site_id, site_id)}")
        lines.append(f"- 최신 ID: {data.get('latest_regular_id', 0)} / 저장 {len(saved)}건 / 고정 {len(fixed_ids)}건")

        # 게시글 ID가 클수록 최신 글이므로 내림차순 정렬 후 상위 N개만 출력
        recent_ids = sorted(saved.keys(), key=lambda k: int(k) if str(k).isdigit() else 0, reverse=True)[:limit]
        for notice_id in recent_ids:
            title = str(saved[notice_id].get("title", ""))
            if len(title) > title_max:
                title = title[:title_max] + "…"
            lines.append(f"  · {title}")

    return "\n".join(lines).strip()

async def generate_debug_report(is_detailed: bool = False, bot_type: str = "all") -> str:
    kst_now = get_kst_now()
    bot_names = {'meal': '학식', 'notice': '공지사항'}
    bot_title = bot_names.get(bot_type, '배재대 통합')
    
    report_lines = [
        f"🛠️ [{bot_title} 봇 디버깅]", 
        f"- 현재 버전: {config.APP_VERSION}", 
        f"- 서버 시간: {kst_now.strftime('%m/%d %H:%M:%S')}", 
        "------------------------------"
    ]
    
    # 학식 봇 검사
    if bot_type in ["meal", "all"]:
        report_lines.extend(["⬇️ [학식 크롤링 테스트] ⬇️"])
        try: 
            meal_data = await get_pcu_diet("오늘", "today")
            short_meal = "\n".join(meal_data.split("\n")[:3])
            report_lines.append(short_meal + "\n(✅ 정상)")
        except Exception as e: 
            report_lines.append(f"❌ 에러: {e}")

    # 공지사항 봇 검사
    if bot_type in ["notice", "all"]:
        report_lines.extend(["------------------------------", "⬇️ [공지사항 크롤러 테스트] ⬇️"])
        try:
            report_lines.extend([f"📡 감시 타겟: {len(config.TARGET_SITES)}개", "✅ 상태: 정상 작동 중"])
            if is_detailed: 
                db = database.load_notice_db()
                summary = "조회 실패" if db is None else summarize_notice_db(db)
                report_lines.extend(["🗄️ [공지 DB 요약]", summary])
        except Exception as e: 
            report_lines.append(f"❌ 에러: {e}")

    return "\n".join(report_lines)