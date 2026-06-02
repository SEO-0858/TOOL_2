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


# --- 📱 [모바일/현장 QR 스캔 기입 모드] ---
if qr_scanned_serial:
    st.title("📱 현장 툴 정보 즉시 기입창")
    st.subheader(f"🆔 인식된 시리얼 넘버: `{qr_scanned_serial}`")
    st.markdown("---")
    
    existing_data = db_collection.find_one({"serial_no": qr_scanned_serial})
    
    if existing_data and existing_data.get("worker") and existing_data.get("machine_no"):
        st.success("✅ 이미 정보 기입이 완료된 툴입니다. 상태 및 정보를 수정할 수 있습니다.")
        current_status = existing_data.get("status", "사용중")
        status_index = ["사용전", "사용중", "폐기"].index(current_status) if current_status in ["사용전", "사용중", "폐기"] else 1
        
        orig_machine = existing_data.get('machine_no', '')
        orig_machine_num = ''.join(filter(str.isdigit, orig_machine))
        try:
            default_machine_int = int(orig_machine_num) if orig_machine_num else 1
        except:
            default_machine_int = 1

        with st.form(key="mobile_update_form"):
            st.markdown("### ⚡ 실시간 툴 상태 및 횟수 수정")
            u_status = st.radio("🔄 툴 현재 상태 선택", ["사용전", "사용중", "폐기"], index=status_index, horizontal=True)
            u_count = st.number_input("📊 현재까지의 실제 사용 횟수", value=int(existing_data.get('current_use', 0)), step=1)
            u_worker = st.text_input("👷 작업자 이름 수정", value=existing_data.get('worker', ''))
            u_machine_num = st.number_input("⚙️ 기계 가공 호기 선택 (숫자만 입력)", min_value=1, max_value=200, value=default_machine_int, step=1)
            
            st.markdown("---")
            st.markdown("⏳ **드레싱 주기 커스텀 시간 수정**")
            col_uh, col_um = st.columns(2)
            with col_uh:
                u_hours = st.number_input("시간(Hour) 설정", min_value=0, max_value=72, value=int(existing_data.get('dressing_hours', 0)), step=1, key="uh")
            with col_um:
                u_mins = st.number_input("분(Minute) 설정", min_value=0, max_value=59, value=int(existing_data.get('dressing_mins', 0)), step=5, key="um")
                
            u_note = st.text_area("📝 특이사항 수정", value=existing_data.get('note', ''))
            submit_u_btn = st.form_submit_button("🔄 수정사항 저장하기")
            
        if submit_u_btn:
            waste_val = str(today) if u_status == "폐기" else existing_data.get("waste_date", "-")
            machine_full_name = f"{u_machine_num}호기"
            
            total_duration_mins = (u_hours * 60) + u_mins
            current_now = get_now_kst()
            if total_duration_mins > 0 and u_status == "사용중":
                start_time_val = existing_data.get("start_time") if existing_data.get("start_time") != "-" else current_now.strftime("%Y-%m-%d %H:%M:%S")
                start_dt = dt_class.strptime(start_time_val, "%Y-%m-%d %H:%M:%S")
                target_time_val = (start_dt + timedelta(minutes=total_duration_mins)).strftime("%Y-%m-%d %H:%M:%S")
            else:
                start_time_val = existing_data.get("start_time", "-")
                target_time_val = existing_data.get("target_time", "-")

            db_collection.update_one(
                {"serial_no": qr_scanned_serial},
                {"$set": {
                    "status": u_status,
                    "current_use": u_count,
                    "worker": u_worker,
                    "machine_no": machine_full_name,
                    "dressing_hours": u_hours,
                    "dressing_mins": u_mins,
                    "start_time": start_time_val,
                    "target_time": target_time_val,
                    "waste_date": waste_val,
                    "note": u_note
                }}
            )
            st.success("🎉 정보가 정상 업데이트되었습니다!")
            st.rerun()
            
    else:
        st.warning("📝 아직 정보가 기입되지 않은 빈데이터 QR코드입니다. 초기 정보를 기입해 주세요.")
        
        st.markdown("### 📅 기계 장착 날짜 및 시간 선택")
        current_now = get_now_kst()
        
        col_date, col_time = st.columns(2)
        with col_date:
            chosen_date = st.date_input("장착 날짜 선택", value=current_now.date())
        with col_time:
            chosen_time = st.time_input("장착 시간 선택", value=current_now.time())
            
        combined_dt = dt_class.combine(chosen_date, chosen_time)
        
        with st.form(key="mobile_input_form"):
            m_status = st.radio("💎 툴 최초 상태 선택", ["사용전", "사용중", "폐기"], index=1, horizontal=True)
            m_worker = st.text_input("Worker 👷 교체 작업자 이름")
            m_machine_num = st.number_input("Machine ⚙️ 기계 가공 호기 (숫자만 입력)", min_value=1, max_value=200, value=4, step=1)
            
            st.markdown("---")
            st.markdown("⏳ **드레싱 주기 커스텀 설정**")
            col_h, col_m = st.columns(2)
            with col_h:
                dressing_hours = st.number_input("시간(Hour) 설정", min_value=0, max_value=72, value=4, step=1)
            with col_m:
                dressing_mins = st.number_input("분(Minute) 설정", min_value=0, max_value=59, value=0, step=5)
                
            m_limit = st.number_input("Limit 사용 한도 횟수", value=10000, step=1000)
            m_note = st.text_area("Note 📝 특이사항")
            
            submit_m_btn = st.form_submit_button("💾 데이터 저장 및 등록 완료")
            
        if submit_m_btn:
            if not m_worker:
                st.error("⚠️ 작업자 이름을 반드시 입력해 주세요!")
            else:
                tool_code = qr_scanned_serial[:2]
                waste_val = str(today) if m_status == "폐기" else "-"
                machine_full_name = f"{m_machine_num}호기"
                
                total_mins = (dressing_hours * 60) + dressing_mins
                if total_mins > 0 and m_status == "사용중":
                    start_time_str = combined_dt.strftime("%Y-%m-%d %H:%M:%S")
                    target_time_str = (combined_dt + timedelta(minutes=total_mins)).strftime("%Y-%m-%d %H:%M:%S")
                else:
                    start_time_str = "-"
                    target_time_str = "-"
                
                db_collection.update_one(
                    {"serial_no": qr_scanned_serial},
                    {"$set": {
                        "serial_no": qr_scanned_serial,
                        "tool_type": "전착툴" if tool_code=="01" else "레진툴" if tool_code=="02" else "메탈툴",
                        "status": m_status,
                        "input_date": str(today),
                        "worker": m_worker,
                        "machine_no": machine_full_name,
                        "dressing_hours": dressing_hours,
                        "dressing_mins": dressing_mins,
                        "start_time": start_time_str,
                        "target_time": target_time_str,
                        "use_limit": m_limit,
                        "current_use": 0,
                        "waste_date": waste_val,
                        "note": m_note
                    }},
                    upsert=True
                )
                st.success("🎉 지정하신 장착 시간 기준으로 저장이 완료되었습니다!")
                st.balloons()
                st.rerun()
                
    if st.button("🏠 메인 시스템으로 돌아가기"):
        st.query_params.clear()
        st.rerun()


# --- 💻 [PC 관리자 모드] ---
else:
    st.sidebar.markdown("## 📁 KKQ 통합 시스템")
    # 📝 [요청 반영] 왼쪽 하위 메뉴 이름을 '전체 데이터 현황판' -> '전체 툴 데이터 현황판'으로 변경
    tool_menu = st.sidebar.radio("하위 목록", [
        "📊 빈데이터 QR코드 대량 선발행", 
        "⚠️ 실시간 툴 드레싱 알림판", 
        "📂 전체 툴 데이터 현황판", 
        "⚙️ 데이터 수정 / 삭제 / QR 재발행"
    ])
    
    # 1) QR코드 대량 연속 선발행 창
    if tool_menu == "📊 빈데이터 QR코드 대량 선발행":
        st.title("🖨️ 현장 부착용 빈데이터 QR코드 대량 연속 발행 (5자리 순번 버전)")
        st.markdown("---")
        
        c1, c2 = st.columns(2)
        with c1:
            tool_code = st.text_input("🆔 고유넘버 앞 2자리 입력 (전착:01 / 레진:02 / 메탈:03)", value="01", max_chars=2)
        with c2:
            quantity = st.number_input("📦 발행할 QR코드 갯수", min_value=1, max_value=50, value=20, step=1)
            
        prefix = f"{tool_code}{mmdd}"
        
        try:
            last_tool = db_collection.find_one({"serial_no": {"$regex": f"^{prefix}"}}, sort=[("serial_no", -1)])
            if last_tool:
                last_counter = int(last_tool["serial_no"][-5:])
            else:
                last_counter = 0
        except Exception:
            last_counter = 0
            
        st.info(f"🔍 마지막 발행 번호: **{last_counter}번** ➡️ 이번에 생성
