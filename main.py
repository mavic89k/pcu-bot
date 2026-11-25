# main.py

import logging
import os
import uvicorn
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler

import config as config
from utils import normalize_search_text
from bot_meal import get_pcu_diet, job_check_next_week_meal, send_daily_meal_telegram
from bot_notice import fetch_notices, job_check_new_notices, search_notices
from monitoring import router as monitoring_router, generate_debug_report
from web import router as web_router

# =============================================================================
# --- 백그라운드 스케줄러 세팅 ---
# =============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    config.validate_settings()

    # HTTP 클라이언트 로그에 인증정보가 포함된 요청 URL을 남기지 않습니다.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    scheduler = AsyncIOScheduler(timezone="Asia/Seoul")

    # 1. 공지사항 모니터링 스케줄 (매 10분마다 새 글 및 수정 감시)
    scheduler.add_job(
        job_check_new_notices, 
        'cron', 
        minute='*/10',
        second=0
    )
    
    # 2. 배재대 학식 텔레그램 자동 발송 (매일 10:00)
    scheduler.add_job(
        send_daily_meal_telegram,
        'cron',
        hour=10,
        minute=0,
        misfire_grace_time=600
    )

    scheduler.add_job(job_check_next_week_meal, 'cron', hour=10, minute=0, second=0)

    scheduler.start()
    yield
    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)
app.include_router(monitoring_router)
app.include_router(web_router)

# =============================================================================
# --- 헬스체크 라우터 ---
# =============================================================================
@app.get("/")
@app.head("/")
def health_check():
    return {"status": "OK", "message": "배재대 알리미 챗봇 서버가 정상 작동 중입니다!"}

# =============================================================================
# --- 배재대학교 카카오톡 봇 라우터 ---
# =============================================================================
def skill_response(output: dict) -> dict:
    return {"version": "2.0", "template": {"outputs": [output]}}


def skill_text(text: str) -> dict:
    return skill_response({"simpleText": {"text": text}})


async def notice_search_response(keyword: str) -> dict:
    response = await build_notice_search_response(keyword)
    response["template"]["quickReplies"] = [
        {"label": "다시 검색", "action": "message", "messageText": "검색"}
    ]
    return response


async def build_notice_search_response(keyword: str) -> dict:
    keyword = keyword.strip()
    if not normalize_search_text(keyword) or len(keyword) > 60:
        return skill_text("공지 검색어를 1~60자로 입력해 주세요. 예: 장학금")

    matches, available, partial = await search_notices(keyword)
    if not available:
        return skill_text("공지사항을 불러오지 못했습니다. 잠시 후 다시 검색해 주세요.")
    if not matches:
        message = f"'{keyword}' 검색 결과가 없습니다."
        if partial:
            message += " 일부 공지 자료를 불러오지 못했습니다."
        return skill_text(message)

    title = "공지 검색 결과 · 일부 자료 제외" if partial else "공지 검색 결과"
    items = [
        {"title": record["title"][:100], "description": record["site"], "link": {"web": record["link"]}}
        for record in matches
    ]
    return skill_response({"listCard": {"header": {"title": title}, "items": items}})


async def handle_search_request(payload: dict, utterance: str) -> dict | None:
    params = (payload.get("action") or {}).get("params") or {}
    query = params.get("search_query")
    has_query = isinstance(query, str) and bool(query.strip())
    text = query if has_query else utterance
    prefix, separator, keyword = text.replace("：", ":", 1).partition(":")
    if separator and normalize_search_text(prefix) == "공지":
        return await notice_search_response(keyword)
    if separator and normalize_search_text(prefix) == "식단":
        return skill_text("공지 제목을 검색할 수 있어요. 예: 공지:장학금")
    if has_query:
        return await notice_search_response(text)
    return None


@app.post("/search")
async def chatbot_search(payload: dict):
    utterance = payload.get("userRequest", {}).get("utterance", "").strip()
    result = await handle_search_request(payload, utterance)
    if result is not None:
        return result
    if utterance and utterance != "검색":
        return await notice_search_response(utterance)
    return skill_text("검색할 공지 키워드를 입력해 주세요. 예: 장학금")


@app.post("/meal")
async def chatbot_meal(request: Request):
    """카카오톡 배재대 학식 봇 스킬 연동"""
    req = await request.json()
    user_utterance = req.get('userRequest', {}).get('utterance', '').strip()
    search_result = await handle_search_request(req, user_utterance)
    if search_result is not None:
        return search_result

    
    if any(cmd in user_utterance.lower() for cmd in ["디버깅", "hc", "헬스체크"]):
        debug_txt = await generate_debug_report("세부" in user_utterance.lower(), "meal")
        return JSONResponse(content={"version": "2.0", "template": {"outputs": [{"simpleText": {"text": debug_txt}}]}})
    
    params = req.get('action', {}).get('params', {})
    detail_params = req.get('action', {}).get('detailParams', {})
    sys_date_str = detail_params.get('sys_date', {}).get('value', '') if params.get('sys_date') == "sys.date" else str(params.get('sys_date', ''))
    
    target_input = str(params.get('meal_date')).strip() if params.get('meal_date') else (sys_date_str if sys_date_str and any(c.isdigit() for c in sys_date_str) else user_utterance)
    
    result_txt = await get_pcu_diet(user_utterance, target_input)
    return JSONResponse(content={"version": "2.0", "template": {"outputs": [{"simpleText": {"text": result_txt}}]}})

@app.post("/notice") 
async def chatbot_notice(payload: dict):
    """카카오톡 배재대 공지사항 검색 스킬 연동"""
    user_msg = payload.get("userRequest", {}).get("utterance", "").strip()
    search_result = await handle_search_request(payload, user_msg)
    if search_result is not None:
        return search_result

    
    if any(cmd in user_msg.lower() for cmd in ["디버깅", "hc", "헬스체크"]):
        debug_txt = await generate_debug_report("세부" in user_msg.lower(), "notice")
        return {"version": "2.0", "template": {"outputs": [{"simpleText": {"text": debug_txt}}]}}
    
    board_name = normalize_search_text(user_msg)
    if board_name == "생활관공지":
        board_name = "생활관일반공지"
    target_site = next(
        (site for site in config.TARGET_SITES if board_name and board_name in normalize_search_text(site["name"])),
        None,
    )
    
    if not target_site: 
        return {"version": "2.0", "template": {"outputs": [{"simpleText": {"text": "어떤 공지사항을 확인하시겠어요? 하단의 메뉴 버튼을 선택해 주세요!"}}]}}
        
    notices = await fetch_notices(target_site["url"], limit=4)
    items = [{"title": f"[고정공지] {i['title']}" if i["is_fixed"] else i["title"], "link": {"web": i["link"]}} for i in notices]
    
    return {"version": "2.0", "template": {"outputs": [{"listCard": {"header": {"title": f"{target_site['name']} 최신글"}, "items": items}}]}}

# (참고) 입금 확인 기능(/webhook/sms, /deposit)도 완전히 필요 없으시다면 삭제하셔도 무방합니다.

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
