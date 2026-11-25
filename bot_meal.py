# bot_meal.py

import asyncio
import datetime
import re
from bs4 import BeautifulSoup
from typing import Tuple
from database import load_next_meal_alert, save_next_meal_alert
from utils import fetch_school_page, get_kst_now, normalize_search_text, send_telegram_msg


def get_pcu_diet_sync(target_input: str = None) -> Tuple[str, int, str, datetime.date]:
    """사용자의 입력을 분석하여 이번 주 학식 URL과 요일 정보를 구합니다."""
    today = get_kst_now().date()
    target_date = today
    this_monday = today - datetime.timedelta(days=today.weekday())
    
    if target_input:
        target_input = target_input.strip()
        
        # 상대어 처리
        if target_input == "today" or "오늘" in target_input: 
            target_date = today
        elif target_input == "tomorrow" or "내일" in target_input: 
            target_date = today + datetime.timedelta(days=1)
        elif "어제" in target_input: 
            target_date = today - datetime.timedelta(days=1)
        elif "모레" in target_input: 
            target_date = today + datetime.timedelta(days=2)
            
        # 영문 요일 지정
        elif target_input == "mon": target_date = this_monday
        elif target_input == "tue": target_date = this_monday + datetime.timedelta(days=1)
        elif target_input == "wed": target_date = this_monday + datetime.timedelta(days=2)
        elif target_input == "thu": target_date = this_monday + datetime.timedelta(days=3)
        elif target_input == "fri": target_date = this_monday + datetime.timedelta(days=4)
            
        # 정확한 날짜 매칭 (ex. 2026-07-21, 7/21, 7월 21일)
        elif re.search(r'(\d{4}-\d{2}-\d{2})', target_input):
            try: 
                match = re.search(r'(\d{4}-\d{2}-\d{2})', target_input).group(1)
                target_date = datetime.datetime.strptime(match, "%Y-%m-%d").date()
            except ValueError: pass
        elif re.search(r'(\d+)\s*/\s*(\d+)', target_input) or re.search(r'(\d+)\s*월\s*(\d+)\s*일', target_input):
            match = re.search(r'(\d+)\s*/\s*(\d+)', target_input) or re.search(r'(\d+)\s*월\s*(\d+)\s*일', target_input)
            try: 
                target_date = datetime.date(today.year, int(match.group(1)), int(match.group(2)))
            except ValueError: pass
            
        # 한글 요일 지정 (ex. 다음주 월요일)
        elif any(d in target_input for d in ["월", "화", "수", "목", "금", "토", "일"]):
            day_map = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}
            for char_day, index in day_map.items():
                if char_day in target_input:
                    days_ahead = index - today.weekday()
                    if "지난" in target_input or "저번" in target_input: 
                        days_ahead -= 7
                    elif "다음" in target_input: 
                        days_ahead += 7
                    target_date = today + datetime.timedelta(days=days_ahead)
                    break
    
    # 목표 요일의 월요일 기준 주차 차이 계산
    target_monday = target_date - datetime.timedelta(days=target_date.weekday())
    week_diff = (target_monday - this_monday).days // 7
    url = meal_week_url(week_diff)
    
    weekday_labels = ["월", "화", "수", "목", "금", "토", "일"]
    return url, target_date.weekday(), weekday_labels[target_date.weekday()], target_date


MEAL_CORNERS = (
    "조식[한식/08:00~09:00]",
    "중식[한식/11:00~13:30]",
    "중식[일품/11:00~13:30]",
    "중식[분식/11:00~13:30]",
    "석식[한식/17:30~19:00]",
)
WEEKDAY_LABELS = "월화수목금"


def meal_week_url(offset: int) -> str:
    return f"https://www.pcu.ac.kr/kor/29/diet/?food={offset}"


async def fetch_meal_tables(url: str):
    response = await fetch_school_page(url, operation="meal", timeout=5.0)
    return BeautifulSoup(response.text, "html.parser").find_all("table")


def clean_meal_cell(raw_menu: str) -> str:
    def strip_annotations(line: str) -> str:
        is_ramen = "신라면" in line

        def keep_topping(match: re.Match[str]) -> str:
            annotation = match[1]
            if is_ramen and ":" not in annotation and re.search(r"[가-힣]", annotation):
                return match[0]
            return ""

        return re.sub(r"\(([^()]*)\)", keep_topping, line)

    cleaned = "\n".join(strip_annotations(line) for line in raw_menu.splitlines())
    cleaned = re.sub(r"\d+\.?\d*\s*kcal", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    return "\n".join(line.strip() for line in cleaned.splitlines() if line.strip())


async def fetch_week_menus(monday: datetime.date, offset: int, *, timeout: float = 3.0):
    """날짜 헤더가 요청한 주와 일치하는 실제 평일 식단을 반환합니다."""
    async with asyncio.timeout(timeout):
        tables = await fetch_meal_tables(meal_week_url(offset))
    days = [monday + datetime.timedelta(days=index) for index in range(5)]
    menus = {day: [] for day in days}
    for corner, table in zip(MEAL_CORNERS, tables):
        rows = table.find_all("tr")
        if len(rows) < 3:
            continue
        headers = rows[0].find_all(["th", "td"])
        cells = rows[2].find_all(["th", "td"])
        for day, header, cell in zip(days, headers, cells):
            match = re.search(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일", header.get_text(" ", strip=True))
            if match is None or tuple(map(int, match.groups())) != (day.month, day.day):
                continue
            menu = clean_meal_cell(cell.get_text())
            status = normalize_search_text(menu).strip(".-–—")
            if status and not any(word in status for word in ("준비중", "미등록", "없습니다", "미운영", "운영안함", "휴무")):
                menus[day].append((corner, menu))
    return menus


async def job_check_next_week_meal() -> None:
    today = get_kst_now().date()
    monday = today + datetime.timedelta(days=7 - today.weekday())
    week = monday.isoformat()
    loaded, last_alert = await asyncio.to_thread(load_next_meal_alert)
    if not loaded or last_alert == week:
        return

    try:
        menus = await fetch_week_menus(monday, 1, timeout=5.0)
        # 분식 코너에 상시 표시되는 라면만으로는 등록을 판단하지 않습니다.
        if not any(
            (corner != MEAL_CORNERS[3] or "라면" not in menu)
            for entries in menus.values() for corner, menu in entries
        ):
            return
        friday = monday + datetime.timedelta(days=4)
        await send_telegram_msg(
            f"🍽️ 다음 주 배재대 학식이 등록됐어요!\n"
            f"{monday:%m/%d}~{friday:%m/%d} 식단 확인\n{meal_week_url(1)}"
        )
    except Exception:
        print("⚠️ 다음 주 식단 확인 또는 알림 발송에 실패했습니다.")
        return

    await asyncio.to_thread(save_next_meal_alert, week)


async def get_pcu_diet(user_utterance: str, target_input: str = None) -> str:
    """학식 테이블 크롤링 및 텍스트 정제"""
    try:
        url, weekday, today_name, target_date = get_pcu_diet_sync(target_input)
        
        # 주말 예외 차단
        if weekday > 4: 
            return f"☀️ {target_date.strftime('%m/%d')}({today_name}요일)은 주말이라 학식 운영을 안 해요! 😎"
            
        tables = await fetch_meal_tables(url)

        # 💡 조식 필터링 변수를 제거하고, 중식/석식만 확인합니다.
        is_lunch = any(k in user_utterance for k in ["중식", "점심", "일품", "분식", "라면"])
        is_dinner = any(k in user_utterance for k in ["석식", "저녁", "야식"])
        filter_mode = is_lunch or is_dinner
        
        result_text = f"🌟 {target_date.strftime('%m/%d')}({today_name}요일) 배재대 학식 메뉴\n\n"
        has_menu = False
        
        # 💡 반복문을 1부터 시작하여 0번(조식) 코너를 아예 건너뜁니다!
        for idx in range(1, min(5, len(tables))):
            # 필터링 모드일 때 원하지 않는 코너 스킵
            if filter_mode:
                if (idx in [1, 2, 3] and not is_lunch): continue
                if (idx == 4 and not is_dinner): continue

            rows = tables[idx].find_all("tr")
            if len(rows) >= 3:
                # 3번째 행(메뉴가 들어있는 row)에서 텍스트 추출
                menus = [cell.text.strip() for cell in rows[2].find_all(["th", "td"])]
                
                if weekday < len(menus):
                    today_menu = clean_meal_cell(menus[weekday])

                    # 메뉴가 없거나 준비중인 경우 예외처리
                    if not today_menu or "준비중" in today_menu or today_menu == ".":
                        today_menu = "메뉴 준비중입니다. 🍳"
                else: 
                    today_menu = "메뉴 정보가 없습니다."
                    
                # 4번 분식 코너에 매일 중복되는 고정 "라면" 메뉴는 알람에서 제거하여 길이 단축
                if idx == 3 and "라면" in today_menu: 
                    continue 
                    
                result_text += f"▪️ {MEAL_CORNERS[idx]}\n{today_menu}\n\n"
                has_menu = True
                
        if has_menu:
            return result_text.strip()
        else:
            return f"📅 {target_date.strftime('%m/%d')} 식단 정보를 찾을 수 없거나 아직 준비중입니다."
            
    except Exception as e: 
        return f"학식 정보를 가져오지 못했습니다. 😢 (에러: {e})"


# =============================================================================
# [신규 추가] 학식 준비중 검사 및 텔레그램 발송 함수
# =============================================================================
def is_meal_available(meal_text: str) -> bool:
    """학식 결과 문자열을 분석해 실제 메뉴가 등록되어 있는지 판별합니다."""
    if "주말이라" in meal_text or "찾을 수 없거나" in meal_text or "에러" in meal_text:
        return False
        
    lines = meal_text.split("\n")
    valid_menu_count = 0
    
    for line in lines:
        line = line.strip()
        # 제목 및 코너 구분선 제외
        if not line or line.startswith("🌟") or line.startswith("▪️"):
            continue
        # "준비중"이나 "없습니다"가 아닌 실제 음식명 줄이 존재하는지 체크
        if "준비중" not in line and "없습니다" not in line:
            valid_menu_count += 1
            
    return valid_menu_count > 0


async def send_daily_meal_telegram():
    """매일 10:00에 실행될 텔레그램 학식 알림 스케줄러 작업"""
    meal_text = await get_pcu_diet("오늘", "today")
    
    # 식단이 준비 중이거나 주말이면 전송을 스킵합니다.
    if not is_meal_available(meal_text):
        print("ℹ️ [배재대 알리미] 오늘의 학식이 '준비중'이거나 주말이므로 텔레그램 발송을 스킵합니다.")
        return

    # 요청하신 타이틀 '배재대 알리미' 적용
    telegram_msg = f"📢 [배재대 알리미 - 오늘의 학식]\n\n{meal_text}"
    
    try:
        await send_telegram_msg(telegram_msg)
        print("✅ [배재대 알리미] 텔레그램 학식 알림 발송 완료!")
    except Exception:
        print("❌ [배재대 알리미] 텔레그램 학식 알림 발송 실패")
