# crawler.py
import time
import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

URL = "https://www.tv-asahi.co.jp/yajiplus/uranai/#ousi"
BASE_URL = "https://www.tv-asahi.co.jp/yajiplus/uranai/"

# ---- 내부 유틸 ----
def _build_driver(headless: bool = True) -> webdriver.Chrome:
    chrome_options = webdriver.ChromeOptions()
    if headless:
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1280,800")
    return webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=chrome_options
    )

def _text_after_label(parent, label_cls: str) -> str:
    """
    <span class="label_cls">ラベル</span>：テキ스트
    같은 구조에서, 라벨 span 다음에 오는 텍스트 노드를 깔끔히 추출.
    """
    span = parent.find("span", class_=label_cls)
    if not span:
        return ""
    # 다음 형제들 중 문자열 텍스트만 모아서 첫 유의미 텍스트 선택
    for sib in span.next_siblings:
        s = str(getattr(sib, "string", sib)).strip()
        if s and s != ":" and s != "：" and s != "<br/>":
            return s.replace("：", "").replace(":", "").strip()
    return ""

def _count_star(score_box, li_cls: str) -> int:
    target = score_box.find("li", class_=li_cls)
    if not target:
        return 0
    lucky = target.find("p", class_="lucky-box")
    if not lucky:
        return 0
    return len(lucky.find_all("img"))

# ---- 공개 함수 ----
def fetch_html(url: str = URL, headless: bool = True) -> str:
    """Selenium으로 HTML 받아오기."""
    driver = _build_driver(headless=headless)
    try:
        driver.get(url)
        time.sleep(2)
        return driver.page_source
    finally:
        driver.quit()


def parse_zodiac(html: str) -> pd.DataFrame:
    soup = BeautifulSoup(html, "html.parser")
    rank_box = soup.find("ul", class_="rank-box")
    detail = soup.find("div", class_="seiza-area")

    if rank_box is None or detail is None:
        raise ValueError("페이지 구조가 예상과 다릅니다. rank-box 또는 seiza-area를 찾을 수 없습니다.")

    zodiak_kr_jp = {
        "양자리": "おひつじ座", "황소자리": "おうし座", "쌍둥이자리": "ふたご座",
        "게자리": "かに座", "사자자리": "しし座", "처녀자리": "おとめ座",
        "천칭자리": "てんびん座", "전갈자리": "さそり座", "궁수자리": "いて座",
        "염소자리": "やぎ座", "물병자리": "みずがめ座", "물고기자리": "うお座",
    }
    jp_to_kr = {v: k for k, v in zodiak_kr_jp.items()}
    zodiak_eng = {
        "ohitsuji": "양자리", "ousi": "황소자리", "futago": "쌍둥이자리",
        "kani": "게자리", "sisi": "사자자리", "otome": "처녀자리",
        "tenbin": "천칭자리", "sasori": "전갈자리", "ite": "궁수자리",
        "yagi": "염소자리", "mizugame": "물병자리", "uo": "물고기자리",
    }

    # 1) 랭킹
    ranking_rows = []
    for i, li in enumerate(rank_box.find_all("li")[:12], start=1):
        span = li.find("span")
        jp_name = span.get_text(strip=True) if span else None
        ranking_rows.append({"순위": i, "별자리_일본어": jp_name, "별자리_한국어": jp_to_kr.get(jp_name)})
    ranking_df = pd.DataFrame(ranking_rows)

    # 2) 상세 (여기서 링크 추가)
    detail_rows = []
    for box in detail.find_all("div", class_="seiza-box")[:12]:
        zid = box.get("id")                            # ex) "ousi"
        kr_name = zodiak_eng.get(zid)
        read_area = box.find("div", class_="read-area")

        read = ""
        if read_area:
            p = read_area.find("p", class_="read")
            read = p.get_text(strip=True) if p else ""

        lucky_color = _text_after_label(read_area, "lucky-color-txt") if read_area else ""
        key = _text_after_label(read_area, "key-txt") if read_area else ""

        score = box.find("div", class_="number-one-box")

        # ✅ 링크 구성
        link = f"{BASE_URL}#{zid}" if zid else ""

        detail_rows.append({
            "별자리": kr_name,
            "운세": read,
            "행운의 색": lucky_color,
            "행운의 물건": key,
            "금전": _count_star(score, "lucky-money") if score else 0,
            "애정": _count_star(score, "lucky-love") if score else 0,
            "업무": _count_star(score, "lucky-work") if score else 0,
            "건강": _count_star(score, "lucky-health") if score else 0,
            "링크": link,                        
        })
    detail_df = pd.DataFrame(detail_rows)

    # 3) 병합
    zodiak = pd.merge(
        ranking_df[["순위", "별자리_한국어"]],
        detail_df,
        left_on="별자리_한국어",
        right_on="별자리",
        how="left",
    )
    zodiak["별자리"] = zodiak["별자리_한국어"]
    zodiak = zodiak.drop(columns=["별자리_한국어"])

    # ✅ 컬럼 정렬에 '링크' 포함
    cols_order = ["순위", "별자리", "링크", "운세", "행운의 색", "행운의 물건", "금전", "애정", "업무", "건강"]
    zodiak = zodiak[[c for c in cols_order if c in zodiak.columns]]
    return zodiak


def get_zodiak_data(headless: bool = True) -> pd.DataFrame:
    """최종 오케스트레이션: HTML fetch → 파싱 → DataFrame 반환"""
    html = fetch_html(URL, headless=headless)
    return parse_zodiac(html)
