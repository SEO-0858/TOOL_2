import streamlit as st
from pymongo import MongoClient
import datetime
from datetime import timedelta, datetime as dt_class
import qrcode
from io import BytesIO
import base64
import re
import time

# 🌟 1. 페이지 기본 설정 및 상태 리스트 정의
st.set_page_config(page_title="KKQ 4파트 다이아몬드 툴관리", layout="wide")
STATUS_LIST = ["사용전", "사용중", "재사용", "폐기"]  # '재사용' 추가 완료

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

def get_now_kst():
    return datetime.datetime.utcnow() + timedelta(hours=9)

now = get_now_kst()
today = now.date()
mmdd = today.strftime("%m%d") 

query_params = st.query_params
qr_scanned_serial = query_params.get("serial", None)

def generate_app_qr_bytes(serial_text):
    app_url = f"https://kkqpd4p.streamlit.app/?serial={serial_text}"
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=6, border=1)
    qr.add_data(app_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

# --- 📱 모바일/현장 QR 스캔 기입 모드 ---
if qr_scanned_serial:
    st.title("📱 현장 툴 정보 즉시 기입창")
    existing_data = db_collection.find_one({"serial_no": qr_scanned_serial})
    
    if existing_data and existing_data.get("worker"):
        current_status = existing_data.get("status", "사용중")
        status_index = STATUS_LIST.index(current_status) if current_status in STATUS_LIST else 1

        with st.form(key="mobile_update_form"):
            u_status = st.radio("🔄 툴 현재 상태 선택", STATUS_LIST, index=status_index, horizontal=True)
            u_count = st.number_input("📊 사용 횟수", value=int(existing_data.get('current_use', 0)))
            u_worker = st.text_input("👷 작업자", value=existing_data.get('worker', ''))
            submit_u_btn = st.form_submit_button("🔄 저장")
            
        if submit_u_btn:
            db_collection.update_one({"serial_no": qr_scanned_serial}, {"$set": {"status": u_status, "current_use": u_count, "worker": u_worker}})
            st.success("업데이트 완료")
            st.rerun()
    else:
        with st.form(key="mobile_input_form"):
            m_status = st.radio("💎 상태", STATUS_LIST, index=1, horizontal=True)
            submit_m_btn = st.form_submit_button("💾 저장")
            if submit_m_btn:
                db_collection.update_one({"serial_no": qr_scanned_serial}, {"$set": {"status": m_status}}, upsert=True)
                st.rerun()

else:
    # --- 💻 PC 관리자 모드 ---
    tool_menu = st.sidebar.radio("하위 목록", [
        "📊 빈데이터 QR코드 대량 선발행", "⚠️ 실시간 툴 드레싱 알림판", 
        "📂 전체 데이터 현황판", "⚙️ 데이터 수정 / 삭제 / QR 재발행", "🖥️ 실시간 기계 정보창"
    ])
    
    # 📂 전체 데이터 현황판 (핵심 로직)
    if tool_menu == "📂 전체 데이터 현황판":
        st.title("📂 전체 데이터 현황판")
        all_data = list(db_collection.find({}).sort("serial_no", -1))
        
        for item in all_data:
            s_no = item["serial_no"]
            status = item.get("status", "사용전")
            with st.expander(f"🆔 {s_no} | 상태: {status}"):
                edit_key = f"is_editing_{s_no}"
                if edit_key not in st.session_state: st.session_state[edit_key] = False
                
                if st.session_state[edit_key]:
                    with st.form(key=f"edit_{s_no}"):
                        ed_status = st.radio("🔄 상태 변경", STATUS_LIST, index=STATUS_LIST.index(status) if status in STATUS_LIST else 0, horizontal=True)
                        if st.form_submit_button("💾 저장"):
                            db_collection.update_one({"serial_no": s_no}, {"$set": {"status": ed_status}})
                            st.session_state[edit_key] = False
                            st.rerun()
                else:
                    if st.button("✏️ 수정", key=f"btn_{s_no}"):
                        st.session_state[edit_key] = True
                        st.rerun()

    # 🖥️ 실시간 기계 정보창
    elif tool_menu == "🖥️ 실시간 기계 정보창":
        st.title("🖥️ 실시간 기계 정보창")
        layout = [[27, 28, 29, 30, 31, 9, 8, 7], [16, 17, 26, 32, 57], [15, 18, 25, 33, 56], [14, 19, 24, 34, 55, 6], [13, 20, 35, 54, 5], [12, 21, 36, 53, 4], [11, 22, 37, 52, 3], [10, 23, 38, 43], [39, 40, 41, 42], [44, 45, 46, 47, 48, 49, 50, 51]]
        active_tools = list(db_collection.find({"status": "사용중"}))
        tool_map = {int(re.findall(r'\d+', t.get('machine_no', ''))[0]): t for t in active_tools if re.findall(r'\d+', t.get('machine_no', ''))}
        
        for row in layout:
            cols = st.columns(len(row))
            for i, m_no in enumerate(row):
                with cols[i]:
                    t = tool_map.get(m_no)
                    if t:
                        st.markdown(f'<div style="background-color:#E8F5E9; padding:8px; border-radius:6px; font-size:11px; height:100px;">{m_no}호기<br>ID: {t.get("serial_no")}<br>작업자: {t.get("worker")}</div>', unsafe_allow_html=True)
                    else:
                        st.markdown(f'<div style="background-color:#F5F5F5; padding:8px; border-radius:6px; font-size:11px; height:100px; text-align:center;">{m_no}호기<br>공실</div>', unsafe_allow_html=True)              
