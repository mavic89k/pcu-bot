const dateLabel = new Intl.DateTimeFormat("ko-KR", {
  month: "long", day: "numeric", weekday: "long", timeZone: "Asia/Seoul",
});
const shortDate = new Intl.DateTimeFormat("ko-KR", {
  month: "numeric", day: "numeric", timeZone: "Asia/Seoul",
});
const dayLabel = new Intl.DateTimeFormat("ko-KR", {
  weekday: "short", timeZone: "Asia/Seoul",
});

const weekButtons = Array.from(document.querySelectorAll("[data-week]"));
const mealPeriod = document.querySelector("#meal-period");
const mealDays = document.querySelector("#meal-days");
const mealContent = document.querySelector("#meal-content");
const todayPreview = document.querySelector("#today-preview");
const boardTabs = document.querySelector("#board-tabs");
const noticeResults = document.querySelector("#notice-results");
const searchForm = document.querySelector("#notice-form");
const searchInput = document.querySelector("#notice-query");
const sectionLinks = document.querySelectorAll("[data-section-link]");
let mealRequest = 0;
let boardRequest = 0;
let boards = [];
let selectedBoard = null;
let boardPending = false;
let boardError = false;
let searchActive = false;

function node(tag, text, className) {
  const result = document.createElement(tag);
  if (text) result.textContent = text;
  if (className) result.className = className;
  return result;
}

function button(text, handler, className) {
  const control = node("button", text, className);
  control.type = "button";
  control.addEventListener("click", handler);
  return control;
}

function empty(text, retry) {
  const message = node("div", null, "empty");
  message.append(document.createTextNode(text));
  if (retry) message.append(button("다시 시도", retry, "retry"));
  return message;
}

function setSelected(buttons, active) {
  for (const control of buttons) control.setAttribute("aria-pressed", String(control === active));
}

function updateSectionLinks() {
  for (const link of sectionLinks) {
    if (link.hash === location.hash) {
      link.setAttribute("aria-current", "location");
    } else {
      link.removeAttribute("aria-current");
    }
  }
}

function asDate(value) {
  return new Date(value + "T00:00:00Z");
}

async function request(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) throw new Error(String(response.status));
  return response.json();
}

function renderToday(data) {
  const today = data.days.find((day) => day.date === data.today);
  const lunch = today?.menus.find((entry) => entry.corner.startsWith("중식"));
  const meal = lunch || today?.menus[0];
  if (!meal) {
    todayPreview.replaceChildren(node("p", "등록된 오늘 식단이 없어요.", "today-message"));
    return;
  }
  todayPreview.replaceChildren(
    node("p", meal.corner.replace("[", " · ").replace(/\/.*$/, ""), "today-title"),
    node("p", meal.items.slice(0, 3).join(" · "), "today-menu"),
  );
}

function renderDay(day) {
  if (!day?.menus.length) {
    mealContent.replaceChildren(empty("이 날짜에 등록된 식단이 없어요."));
    return;
  }
  const list = node("ul", null, "meal-items");
  for (const meal of day.menus) {
    const row = node("li", null, "meal-item");
    row.append(node("h3", meal.corner), node("p", meal.items.join(" · ")));
    list.append(row);
  }
  mealContent.replaceChildren(list);
}

async function loadMeals(week) {
  const generation = ++mealRequest;
  setSelected(weekButtons, weekButtons.find((control) => control.dataset.week === week));
  mealDays.replaceChildren();
  mealPeriod.textContent = "평일 식단 · 한국 시간 기준";
  mealContent.replaceChildren(empty("학교 홈페이지에서 식단을 불러오는 중입니다."));
  try {
    const data = await request("/web/meals?week=" + week);
    if (week === "current") renderToday(data);
    if (generation !== mealRequest) return;
    const buttons = data.days.map((day) => {
      const date = asDate(day.date);
      const control = button(dayLabel.format(date), () => {
        setSelected(buttons, control);
        renderDay(day);
      });
      control.append(node("small", shortDate.format(date)));
      control.setAttribute("aria-label", dateLabel.format(date));
      return control;
    });
    mealDays.replaceChildren(...buttons);
    const initial = Math.max(0, data.days.findIndex((day) => day.date === data.today));
    setSelected(buttons, buttons[initial]);
    renderDay(data.days[initial]);
  } catch {
    if (week === "current") {
      todayPreview.replaceChildren(node("p", "오늘 식단을 불러오지 못했어요.", "today-message"));
    }
    if (generation === mealRequest) {
      mealContent.replaceChildren(empty("학교 식단을 불러오지 못했어요.", () => loadMeals(week)));
    }
  }
}

function noticeList(items) {
  const list = node("ul", null, "notice-list");
  for (const item of items) {
    const url = new URL(item.link, location.origin);
    if (url.protocol !== "https:" || url.hostname !== "www.pcu.ac.kr") continue;
    const row = node("li");
    const link = node("a", null, "notice-link");
    link.href = url.href;
    const details = node("span");
    details.append(node("span", item.title, "notice-title"));
    if (item.site || item.pinned) details.append(node("small", item.site || "고정 공지"));
    const arrow = node("span", "↗");
    arrow.setAttribute("aria-hidden", "true");
    link.append(details, arrow);
    row.append(link);
    list.append(row);
  }
  return list.children.length ? list : empty("표시할 공지가 없어요.");
}

function showBoard(id) {
  searchActive = false;
  boardRequest++;
  selectedBoard = id;
  const controls = Array.from(boardTabs.querySelectorAll("button"));
  setSelected(controls, controls.find((control) => control.dataset.board === id));
  const board = boards.find((entry) => entry.id === id);
  if (boardPending) {
    noticeResults.replaceChildren(empty("학교 홈페이지에서 공지를 불러오는 중입니다."));
  } else if (boardError || board?.available === false) {
    noticeResults.replaceChildren(empty("공지사항을 불러오지 못했어요.", loadBoards));
  } else {
    noticeResults.replaceChildren(noticeList(board?.items || []));
  }
}

async function loadBoards() {
  boardPending = true;
  boardError = false;
  if (!searchActive) showBoard(selectedBoard);
  try {
    const data = await request("/web/notices");
    boards = data.boards;
    if (!boards.some((entry) => entry.id === selectedBoard)) {
      selectedBoard = boards.find((entry) => entry.available)?.id ?? boards[0]?.id;
    }
    boardTabs.replaceChildren(...boards.map((board) => {
      const control = button(board.label, () => showBoard(board.id));
      control.dataset.board = board.id;
      control.setAttribute("aria-pressed", "false");
      return control;
    }));
  } catch {
    boardError = true;
  } finally {
    boardPending = false;
    if (!searchActive) showBoard(selectedBoard);
  }
}

function searchHeading(keyword) {
  const heading = node("div", null, "results-heading");
  heading.append(
    node("strong", "‘" + keyword + "’ 검색 결과"),
    button("최신 공지", () => { searchInput.value = ""; showBoard(selectedBoard); }, "text-button"),
  );
  return heading;
}

async function runSearch(keyword) {
  const generation = ++boardRequest;
  searchActive = true;
  setSelected(boardTabs.querySelectorAll("button"), null);
  noticeResults.replaceChildren(searchHeading(keyword), empty("학교 게시판을 검색하는 중입니다."));
  try {
    const data = await request("/web/search", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({q: keyword}),
    });
    if (generation !== boardRequest) return;
    noticeResults.replaceChildren(searchHeading(keyword),
      data.items.length ? noticeList(data.items) : empty("검색 결과가 없어요."));
    if (data.partial) noticeResults.append(empty("일부 게시판에 연결하지 못했어요."));
  } catch (error) {
    if (generation !== boardRequest) return;
    const message = error.message === "429" ? "검색 요청이 많아요. 잠시 후 시도해 주세요." : "공지를 검색하지 못했어요.";
    noticeResults.replaceChildren(searchHeading(keyword), empty(message, () => runSearch(keyword)));
  }
}

document.querySelector("#hero-date").textContent = dateLabel.format(new Date());
window.addEventListener("hashchange", updateSectionLinks);
updateSectionLinks();
for (const control of weekButtons) control.addEventListener("click", () => loadMeals(control.dataset.week));
searchForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const keyword = searchInput.value.trim();
  if (keyword) runSearch(keyword);
});
loadMeals("current");
loadBoards();
