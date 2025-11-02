# send_taurus_horoscope_kakao.py
import os
import json
import requests
import pandas as pd
from datetime import datetime, timezone, timedelta
from typing import Optional

# 당신의 크롤러 모듈 (앱에서 쓰던 것과 동일)
from 오하아사_크롤링 import get_zodiak_data

# --- Kakao OAuth/Message endpoints ---
TOKEN_URL = "https://kauth.kakao.com/oauth/token"
MEMO_SEND_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"

# --- 환경변수 (GitHub Actions 등에서 Secrets로 설정 권장) ---
# 필수
KAKAO_CLIENT_ID = os.getenv("KAKAO_CLIENT_ID")            # 카카오 REST API 키
KAKAO_REFRESH_TOKEN = os.getenv("KAKAO_REFRESH_TOKEN")    # 사용자 Refresh Token
KAKAO_REDIRECT_URI = os.getenv("KAKAO_REDIRECT_URI")      # 관례상 보관(실사용하지 않음)

assert KAKAO_CLIENT_ID and KAKAO_REFRESH_TOKEN, "KAKAO_CLIENT_ID / KAKAO_REFRESH_TOKEN 환경변수 필수"


# --- 번역기 (deep-translator 사용, Python 3.13 호환) ---
from deep_translator import MyMemoryTranslator

def translate_text(text: str, target_language="korean") -> str:
    """MyMemory 무료 번역 (일본어→한국어)"""
    if not text or not isinstance(text, str):
        return text
    try:
        translated = MyMemoryTranslator(source="japanese", target=target_language).translate(text)
        return translated.strip()
    except Exception as e:
        print(f"[WARN] 번역 실패 ({text[:10]}...): {e}")
        return text


# -------------------------------
# Kakao API: 토큰 갱신/메시지 전송
# -------------------------------
def refresh_access_token() -> str:
    """Refresh Token으로 Access Token 갱신"""
    data = {
        "grant_type": "refresh_token",
        "client_id": KAKAO_CLIENT_ID,
        "refresh_token": KAKAO_REFRESH_TOKEN,
    }
    res = requests.post(TOKEN_URL, data=data, timeout=15)
    res.raise_for_status()
    js = res.json()
    access = js.get("access_token")
    if not access:
        raise RuntimeError(f"토큰 갱신 실패: {js}")
    return access

def send_kakao_memo(access_token: str, text: str, web_url: Optional[str] = None) -> dict:
    """카카오톡 '나에게 보내기' 메시지 전송"""
    headers = {"Authorization": f"Bearer {access_token}"}
    template_obj = {
        "object_type": "text",
        "text": text,
        "link": {"web_url": web_url or "https://www.kakao.com"},
    }
    payload = {"template_object": json.dumps(template_obj, ensure_ascii=False)}
    res = requests.post(MEMO_SEND_URL, headers=headers, data=payload, timeout=15)
    try:
        return res.json()
    except Exception:
        return {"status_code": res.status_code, "text": res.text}

# -------------------------------
# 메시지 빌드 유틸
# -------------------------------
def stars(n: int) -> str:
    """정수 점수를 문자 별(★)로 표기. 0 이하면 '-'"""
    try:
        n = int(n)
    except Exception:
        n = 0
    return "★" * n if n > 0 else "-"

def build_message_from_row(row: pd.Series) -> tuple[str, Optional[str]]:
    """크롤링 행으로부터 카카오 메시지 본문/링크 생성"""
    # 한국시간 날짜 표기
    kst = timezone(timedelta(hours=9))
    today = datetime.now(kst).strftime("%Y-%m-%d")

    title = f"[오늘의 운세] {today}\n"
    header = f"🏅 순위: {row.get('순위','?')}위 {row.get('별자리','')}\n\n"
    body = (row.get("운세") or "").strip()
    lucky = (
        f"\n\n🍀 행운의 색: {row.get('행운의 색','-')}\n"
        f"🍀 행운의 물건: {row.get('행운의 물건','-')}\n"
    )
    scores = (
        f"\n🏷️ 운세 지수\n"
        f"- 금전: {stars(row.get('금전',0))}\n"
        f"- 애정: {stars(row.get('애정',0))}\n"
        f"- 업무: {stars(row.get('업무',0))}\n"
        f"- 건강: {stars(row.get('건강',0))}\n"
    )
    link = row.get("링크") or None

    text = title + header + body + lucky + scores
    return text, link

# -------------------------------
# 메인
# -------------------------------
def main():
    # 1) 데이터 수집 (당신의 크롤러)
    df = get_zodiak_data(headless=True)

    # 2) 필요한 컬럼만 남기고 정렬(선택)
    cols_order = ["순위", "별자리", "운세", "행운의 색", "행운의 물건", "금전", "애정", "업무", "건강", "링크"]
    df = df[[c for c in cols_order if c in df.columns]].copy()

    # 3) 황소자리 선택 (별자리명은 크롤링 결과에 맞춰 정확히)
    target = "황소자리"
    sel = df.loc[df["별자리"] == target]
    if sel.empty:
        raise RuntimeError("크롤링 데이터에 '황소자리'가 없습니다.")

    # 4) 선택된 행(row)만 번역 (일본어 -> 한국어)
    row = sel.iloc[0].copy()
    for col in ["운세", "행운의 색", "행운의 물건"]:
        if col in row and pd.notna(row[col]):
            row[col] = translate_text(row[col])

    text, web_url = build_message_from_row(row)
    
    # 5) 카카오 Access Token 갱신 → 메시지 전송
    access = refresh_access_token()
    res = send_kakao_memo(access, text, web_url)

    # 6) 결과 로그 (result_code == 0 이면 성공)
    print("Kakao response:", res)

if __name__ == "__main__":
    import sys, traceback
    print("[0] 엔트리 진입")
    try:
        main()
        print("[10] 정상 종료")
    except Exception as e:
        print("[ERR] 예외 발생:", e)
        traceback.print_exc()
        sys.exit(1)
