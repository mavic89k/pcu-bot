# bot_notice.py

import asyncio
import logging
import re
from copy import deepcopy
import httpx
from bs4 import BeautifulSoup
import hashlib
import config as config
from database import load_notice_db, save_notice_db
from utils import fetch_school_page, normalize_search_text, send_telegram_msg

logger = logging.getLogger("uvicorn.error")


def notice_link(site_url: str, article_id: int) -> str:
    board_url = site_url.split("?", 1)[0].rstrip("/")
    return f"{board_url}/{article_id}"


async def fetch_notices(site_url: str, limit: int = 10, *, keyword: str | None = None) -> list:
    """게시판의 최신 글 또는 학교 사이트가 제목으로 검색한 글을 읽습니다."""
    url = httpx.URL(site_url)
    if keyword is not None:
        url = url.copy_merge_params({
            "pageIndex": 1,
            "searchCondition": "1",
            "searchKeyword": keyword,
        })

    operation = "학교 공지 검색" if keyword is not None else "학교 공지 조회"
    response = await fetch_school_page(url, operation=operation, timeout=10.0, follow_redirects=True)
    response.encoding = 'utf-8'
    soup = BeautifulSoup(response.text, "html.parser")

    notices = []
    for row in soup.select("[class*='board'] li, [class*='list'] li"):
        if "thead" in row.get("class", []):
            continue

        no_tag = row.find(class_="no")
        a_tag = row.find("a")
        if not no_tag or not a_tag:
            continue

        num_text = no_tag.text.strip()
        title = a_tag.text.strip()

        # 상단 고정 공지는 번호 대신 "공지" 등의 텍스트가 들어갑니다.
        is_fixed = not num_text.isdigit() and "공지" in num_text

        # 번호도 없고 고정 공지도 아니면 일반 데이터 찌꺼기이므로 패스
        if not num_text.isdigit() and not is_fixed:
            continue

        # 자바스크립트 onclick에서 고유 article_id를 추출합니다.
        match = re.search(r"article\.(?:view|iframeView)\('(\d+)'\)", a_tag.get("onclick", ""))
        if match:
            article_id = int(match.group(1))

            link = notice_link(site_url, article_id)

            # 💡 조회수 변동으로 인한 오작동을 막기 위해, '제목(title)'만 해시로 만듭니다!
            # (만약 내용 수정 시 제목에 [수정]을 달지 않는다면, 추후에 작성일자(date) 크롤링 코드를 추가해 합치는 것이 좋습니다)
            row_hash = hashlib.sha256(title.encode('utf-8')).hexdigest()

            notices.append({
                "id": article_id,
                "title": title,
                "link": link,
                "is_fixed": is_fixed,
                "hash": row_hash  # 딕셔너리에 해시값 추가
            })

        if len(notices) >= limit:
            break

    return notices

async def search_notices(keyword: str) -> tuple[list[dict], bool, bool]:
    """등록된 학교 게시판의 제목 검색을 병렬로 실행합니다."""
    async def search_board(site: dict) -> list:
        async with asyncio.timeout(3.0):
            entries = await fetch_notices(site["url"], limit=30, keyword=keyword)
        logger.info("학교 공지 검색 결과 | 게시판 %s | %d건", site["name"], len(entries))
        return entries

    sites = config.TARGET_SITES
    results = await asyncio.gather(*(search_board(site) for site in sites), return_exceptions=True)
    key = normalize_search_text(keyword)
    found = {}
    available = 0
    for site, entries in zip(sites, results):
        if isinstance(entries, BaseException):
            continue
        available += 1
        for entry in entries:
            # 학교 게시판은 검색어와 무관한 상단 고정글도 함께 반환합니다.
            if entry["is_fixed"] and key not in normalize_search_text(entry["title"]):
                continue
            found[site["id"], entry["id"]] = {
                "title": entry["title"],
                "link": entry["link"],
                "site": site["name"],
            }

    ordered = sorted(found, key=lambda record: record[1], reverse=True)
    return [found[record] for record in ordered[:5]], available > 0, available < len(sites)


async def job_check_new_notices():
    """백그라운드에서 주기적으로 실행되며 새 글 및 해시 변경(수정)을 감시합니다."""
    db = load_notice_db()
    if db is None:
        return
    db_updated = False
    
    for site in config.TARGET_SITES:
        try:
            notices = await fetch_notices(site["url"], limit=15)
            if not notices: 
                continue
            
            site_id = site["id"]
            # 발송이 끝나기 전까지 저장할 DB 상태를 변경하지 않습니다.
            previous_state = db.get(site_id, {})
            site_state = deepcopy(previous_state)
            site_state.setdefault("latest_regular_id", 0)
            site_state.setdefault("fixed_ids", [])
            site_state.setdefault("saved_notices", {})

            current_fixed_ids = []
            new_regular_notices = []
            new_fixed_notices = []
            modified_notices = [] # 수정 감지용
            
            for notice in notices:
                notice_id_str = str(notice["id"])
                
                if notice["is_fixed"]:
                    current_fixed_ids.append(notice["id"])
                    # DB에 없는 새로운 고정 공지이면 목록에 추가
                    if site_state["fixed_ids"] and notice["id"] not in site_state["fixed_ids"]:
                        new_fixed_notices.append(notice)
                else:
                    # 기존 저장된 최신 번호보다 더 큰 번호면 새 글로 간주
                    if site_state["latest_regular_id"] != 0 and notice["id"] > site_state["latest_regular_id"]:
                        new_regular_notices.append(notice)
                
                # 💡 [핵심] 해시(Hash) 비교를 통한 완벽한 수정 감지
                old_data = site_state["saved_notices"].get(notice_id_str)
                if old_data:
                    # 저장된 과거 해시값과 새로 생성한 해시값이 다르다면 내용/제목/날짜 중 무언가 수정된 것!
                    if old_data.get("hash") != notice["hash"]:
                        modified_notices.append({
                            "old_title": old_data["title"],
                            "new_title": notice["title"], 
                            "link": notice["link"]
                        })
                
                # DB의 최신 제목과 해시값을 현재 상태로 덮어쓰기 업데이트
                if not old_data or old_data.get("hash") != notice["hash"]:
                    site_state["saved_notices"][notice_id_str] = {
                        "title": notice["title"],
                        "hash": notice["hash"]
                    }
            
            # 새 글 알림 발송 (오래된 글부터 쏘기 위해 reversed 적용)
            for notice in reversed(new_regular_notices): 
                await send_telegram_msg(f"🔔새 공지! [{site['name']}] \n\n제목: {notice['title']}\n링크: {notice['link']}")
            for notice in reversed(new_fixed_notices): 
                await send_telegram_msg(f"📌새 고정공지! [{site['name']}] \n\n제목: {notice['title']}\n링크: {notice['link']}")
                
            # 💡 [추가] 해시값 변경으로 감지된 수정 알림 발송
            for mod in reversed(modified_notices):
                msg = f"✏️공지 업데이트됨! [{site['name']}]\n"
                # 만약 제목 자체가 수정되었다면 전후 비교를 보여주고, 내용/날짜만 수정되었다면 제목만 보여줍니다.
                if mod['old_title'] != mod['new_title']:
                    msg += f"\n❌ 이전: {mod['old_title']}\n⭕ 현재: {mod['new_title']}"
                else:
                    msg += f"\n제목: {mod['new_title']}\n(내용 또는 첨부파일 변경 감지)"
                msg += f"\n🔗 링크: {mod['link']}"
                
                await send_telegram_msg(msg)
                
            # 일반 공지의 최대 ID 찾아서 갱신
            regular_ids = [n["id"] for n in notices if not n["is_fixed"]]
            if regular_ids and max(regular_ids) > site_state["latest_regular_id"]:
                site_state["latest_regular_id"] = max(regular_ids)
                    
            # 고정 공지 목록이 달라졌다면 갱신
            if set(current_fixed_ids) != set(site_state["fixed_ids"]):
                site_state["fixed_ids"] = current_fixed_ids

            if site_state != previous_state:
                db[site_id] = site_state
                db_updated = True
        except Exception:
            print(f"[{site['name']}] 공지 처리에 실패했습니다.")
            
    if db_updated: 
        save_notice_db(db)
