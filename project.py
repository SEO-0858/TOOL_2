import streamlit as st
from pymongo import MongoClient
import datetime
from datetime import timedelta, datetime as dt_class
import qrcode
from io import BytesIO
import base64

# 🌟 1. 페이지 기본 설정 및 URL 파라미터 추적
st.set_page_config(page_title="KKQ 4파트 다이아몬드 툴관리", layout="wide")

# 🔒 2. 데이터베이스 연결
@st.cache_resource
def get_database():
    MONGO_URI = "mongodb+srv://sspon1270_db_user:wXA7NGCMjjTiTG5w@cluster0.1ectnsv.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
    try:
        client = MongoClient(MONGO_URI)
        db = client["dashboard_db"]
        return db["tools_management"]
    except Exception as e:
        st.error(f"🌐 데이터베이스 통신 오류: {e}")
        return None

db_collection = get_database()

# 🕒 한국 시간(KST) 전역 강제 설정 함수
def get_now_kst():
    return datetime.datetime.utcnow() + timedelta(hours=9)

now = get_now_kst()
today = now.date()
mmdd = today.strftime("%m%d") 

# 📱 QR 스캔 시 URL 파라미터 읽기
query_params = st.query_params
qr_scanned_serial = query_params.get("serial", None)

# QR코드 생성 헬퍼 함수
def generate_app_qr_bytes(serial_text):
    app_url = f"https://kkqpd4p.streamlit.app/?serial={serial_text}"
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=6, border=1)
    qr.add_data(app_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

# --- [추가된 부분: 실시간 기계 정보창 전용 함수] ---
def render_machine_box(m_id):
    info = db_collection.find_one({"machine_no": f"{m_id}호기", "status": "사용중"})
    label = f"{m_id}"
    worker = info['worker'] if info else "공실"
    serial = info['serial_no'][-5:] if info else "-"
    color = "#e6ffe6" if info else "#f9f9f9"
    st.markdown(f"""
    <div style="border:1px solid #999; padding:5px; border-radius:3px; text-align:center; height:65px; font-size:11px; background-color:{color};">
        <b style="font-size:14px;">{label}</b><br>{worker}<br>{serial}
    </div>
    """, unsafe_allow_html=True)

def draw_machine_layout():
    c_top1, _, c_top2 = st.columns([5, 1, 3])
    with c_top1:
        cols = st.columns(5)
        for i, mid in enumerate([27, 28, 29, 30, 31]):
            with cols[i]: render_machine_box(mid)
    with c_top2:
        cols = st.columns(3)
        for i, mid in enumerate([9, 8, 7]):
            with cols[i]: render_machine_box(mid)
    st.write("<br>", unsafe_allow_html=True)
    c_left, c_mid, c_right_main, c_right_side = st.columns([2, 0.6, 2, 0.6])
    with c_left:
        for left, right in [(16,17), (15,18), (14,19), (13,20), (12,21), (11,22), (10,23)]:
            col1, col2 = st.columns(2)
            with col1: render_machine_box(left)
            with col2: render_machine_box(right)
    with c_mid:
        for mid in [26, 25, 24]: render_machine_box(mid)
    with c_right_main:
        for left, right in [(32,57), (33,56), (34,55), (35,54), (36,53), (37,52), (38,43)]:
            col1, col2 = st.columns(2)
            with col1: render_machine_box(left)
            with col2: render_machine_box(right)
    with c_right_side:
        for mid in [6, 5, 4, 3]: render_machine_box(mid)
    st.write("<br>", unsafe_allow_html=True)
    cols_h1 = st.columns(5)
    for i, mid in enumerate([39, 40, 41, 42, 43]):
        with cols_h1[i]: render_machine_box(mid)
    cols_h2 = st.columns(7)
    for i, mid in enumerate([45, 46, 47, 48, 49, 50, 51]):
        with cols_h2[i]: render_machine_box(mid)

# --- [기존 모바일/PC 로직 통합] ---
if qr_scanned_serial:
    # ... (기존 모바일 로직 생략 - 그대로 유지됨)
    pass
else:
    st.sidebar.markdown("## 📁 KKQ 통합 시스템")
    tool_menu = st.sidebar.radio("하위 목록", [
        "📊 빈데이터 QR코드 대량 선발행", 
        "⚠️ 실시간 툴 드레싱 알림판", 
        "📂 전체 데이터 현황판", 
        "⚙️ 데이터 수정 / 삭제 / QR 재발행",
        "🖥️ 실시간 기계 정보창" # 메뉴 추가
    ])

    if tool_menu == "🖥️ 실시간 기계 정보창":
        st.title("🖥️ 실시간 기계 정보창")
        draw_machine_layout()
    else:
        # 기존 코드의 나머지 부분을 여기에 붙여넣으세요.
        # (빈데이터 QR코드 대량 선발행, 알림판, 현황판 등 기존 기능)
        pass
