import streamlit as st
from pymongo import MongoClient
import datetime
import qrcode
from io import BytesIO

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

today = datetime.date.today()
mmdd = today.strftime("%m%d") 

# 📱 QR 스캔 시 URL 파라미터 읽기 (?serial=XXXX)
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
    
    # DB에서 기존 데이터 조회
    existing_data = db_collection.find_one({"serial_no": qr_scanned_serial})
    
    # 기존 데이터가 있고, 이미 최초 등록(작업자/장비)이 완료된 상태라면 '수정/조회 모드'
    if existing_data and existing_data.get("worker") and existing_data.get("machine_no"):
        st.success("✅ 이미 정보 기입이 완료된 툴입니다. 상태 및 사용 횟수를 변경할 수 있습니다.")
        
        # 현재 상태 읽어오기 (없으면 기본값 '사용중')
        current_status = existing_data.get("status", "사용중")
        status_index = ["사용전", "사용중", "폐기"].index(current_status) if current_status in ["사용전", "사용중", "폐기"] else 1
        
        with st.form(key="mobile_update_form"):
            st.markdown("### ⚡ 실시간 툴 상태 및 횟수 수정")
            
            # 💡 [요청 기능] 세 가지 항목 중 클릭해서 상태 변경
            u_status = st.radio("🔄 툴 현재 상태 선택", ["사용전", "사용중", "폐기"], index=status_index, horizontal=True)
            
            u_count = st.number_input("📊 현재까지의 실제 사용 횟수", value=int(existing_data.get('current_use', 0)), step=1)
            u_worker = st.text_input("👷 작업자 이름 수정", value=existing_data.get('worker', ''))
            u_machine = st.text_input("⚙️ 기계 가공 호기 수정", value=existing_data.get('machine_no', ''))
            u_note = st.text_area("📝 특이사항 수정", value=existing_data.get('note', ''))
            
            submit_u_btn = st.form_submit_button("🔄 수정사항 저장하기")
            
        if submit_u_btn:
            # 폐기를 선택하면 폐기 날짜를 오늘로 기록, 아니면 유지
            waste_val = str(today) if u_status == "폐기" else existing_data.get("waste_date", "-")
            
            db_collection.update_one(
                {"serial_no": qr_scanned_serial},
                {"$set": {
                    "status": u_status,
                    "current_use": u_count,
                    "worker": u_worker,
                    "machine_no": u_machine,
                    "waste_date": waste_val,
                    "note": u_note
                }}
            )
            st.success("🎉 툴의 현재 상태와 정보가 성공적으로 업데이트되었습니다!")
            st.rerun()
            
    # 껍데기만 발행된 상태라 처음 정보를 입력하는 경우
    else:
        st.warning("📝 아직 정보가 기입되지 않은 공 QR코드입니다. 초기 정보를 기입해 주세요.")
        
        with st.form(key="mobile_input_form"):
            # 💡 [요청 기능] 최초 기입 시에도 상태 지정 가능 (기본값: 사용전)
            m_status = st.radio("💎 툴 최초 상태 선택", ["사용전", "사용중", "폐기"], index=0, horizontal=True)
            
            m_worker = st.text_input("Worker 👷 교체 작업자 이름")
            m_machine = st.text_input("Machine ⚙️ 기계 가공 호기 (예: MCT 3호기)")
            m_limit = st.number_input("Limit 사용 한도 횟수", value=10000, step=1000)
            m_note = st.text_area("Note 📝 특이사항")
            
            submit_m_btn = st.form_submit_button("💾 데이터 저장 및 등록 완료")
            
        if submit_m_btn:
            if not m_worker or not m_machine:
                st.error("⚠️ 작업자 이름과 가공 호기를 반드시 입력해 주세요!")
            else:
                tool_code = qr_scanned_serial[:2]
                waste_val = str(today) if m_status == "폐기" else "-"
                
                db_collection.update_one(
                    {"serial_no": qr_scanned_serial},
                    {"$set": {
                        "serial_no": qr_scanned_serial,
                        "tool_type": "전착툴" if tool_code=="01" else "레진툴" if tool_code=="02" else "메탈툴",
                        "status": m_status,  # 상태 저장
                        "input_date": str(today),
                        "worker": m_worker,
                        "machine_no": m_machine,
                        "use_limit": m_limit,
                        "current_use": 0,
                        "waste_date": waste_val,
                        "note": m_note
                    }},
                    upsert=True
                )
                st.success("🎉 현장 데이터 정보가 성공적으로 첫 등록되었습니다!")
                st.balloons()
                st.rerun()
                
    if st.button("🏠 메인 시스템으로 돌아가기"):
        st.query_params.clear()
        st.rerun()


# --- 💻 [PC 관리자 모드: 대량 QR 선발행 및 모니터링 현황판] ---
else:
    st.sidebar.markdown("## 📁 KKQ 통합 시스템")
    tool_menu = st.sidebar.radio("하위 목록", ["📊 껍데기 QR코드 대량 선발행", "📂 전체 데이터 현황판"])
    
    # 1) QR코드만 대량 연속 선발행하는 창
    if tool_menu == "📊 껍데기 QR코드 대량 선발행":
        st.title("🖨️ 현장 부착용 공(Blank) QR코드 대량 연속 발행")
        st.markdown("데이터 기입 및 상태 설정은 현장에서 실물 QR을 스캔하여 진행합니다.")
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
                last_counter = int(last_tool["serial_no"][-4:])
            else:
                last_counter = 0
        except Exception:
            last_counter = 0
            
        st.info(f"🔍 마지막 발행 번호: **{last_counter}번** ➡️ 이번에 생성될 순번: **{last_counter+1}번 ~ {last_counter+quantity}번**")
        
        if st.button(f"🖨️ {quantity}개의 연속 QR코드 즉시 발행"):
            blank_records = []
            grid_cols = st.columns(4)
            
            for idx in range(1, quantity + 1):
                current_seq = last_counter + idx
                serial_no = f"{prefix}{current_seq:04d}"
                
                blank_records.append({
                    "serial_no": serial_no,
                    "tool_type": "전착툴" if tool_code=="01" else "레진툴" if tool_code=="02" else "메탈툴",
                    "status": "사용전",  # 초기값은 사용전으로 세팅
                    "input_date": str(today),
                    "worker": "",
                    "machine_no": "",
                    "use_limit": 10000,
                    "current_use": 0,
                    "waste_date": "-",
                    "note": "QR 선발행 완료 (현장 기입 대기)"
                })
                
                with grid_cols[(idx-1) % 4]:
                    st.image(generate_app_qr_bytes(serial_no), width=130)
                    st.markdown(f"**🆔 {serial_no}**")
                    st.caption("◀ 스캔 시 기입창 열림")
                    
            try:
                db_collection.insert_many(blank_records)
                st.success(f"🎉 {quantity}개의 순번 껍데기가 안전하게 DB에 선점되었습니다!")
            except Exception as e:
                st.error(f"오류 발생: {e}")

    # 2) 현장에서 작업자가 입력한 내역을 모니터링하는 종합 현황판
    elif tool_menu == "📂 전체 데이터 현황판":
        st.title("📂 현장 기입 데이터 통합 현황판")
        st.markdown("현장 작업자들이 QR코드를 찍어 실시간으로 변경한 툴 상태와 데이터 테이블입니다.")
        st.markdown("---")
        
        try:
            all_data = list(db_collection.find({}).sort("serial_no", -1))
            if not all_data:
                st.info("조회할 데이터가 없습니다.")
            else:
                for item in all_data:
                    # 💡 현황판 제목에 현재 툴의 상태([사용전], [사용중], [폐기])를 시각적으로 강조해 줍니다.
                    status = item.get("status", "사용전")
                    if status == "사용전":
                        status_badge = "🟢 [사용전]"
                    elif status == "사용중":
                        status_badge = "🟡 [사용중]"
                    else:
                        status_badge = "🔴 [폐기]"
                        
                    if not item['worker'] or not item['machine_no']:
                        expander_title = f"⚪ 기입 대기 | 🆔 {item['serial_no']} | 상태: {status_badge}"
                    else:
                        expander_title = f"🆔 {item['serial_no']} | 장비: {item['machine_no']} | 작업자: {item['worker']} | 상태: {status_badge}"
                        
                    with st.expander(expander_title):
                        col_x, col_y = st.columns(2)
                        with col_x:
                            st.write(f"• **💎 툴 종류:** {item['tool_type']}")
                            st.write(f"• **📅 최초 발행일:** {item['input_date']}")
                            st.write(f"• **👷 교체 작업자:** {item['worker'] if item['worker'] else '-'}")
                        with col_y:
                            st.write(f"• **⚙️ 기계 가공 호기:** {item['machine_no'] if item['machine_no'] else '-'}")
                            st.write(f"• **📊 현재 사용 횟수:** {item['current_use']} / {item['use_limit']} 회")
                            st.write(f"• **🗑️ 폐기 완료 날짜:** {item['waste_date']}")
                        st.write(f"• **📝 현장 특이 사항:** {item['note']}")
        except Exception as e:
            st.error(f"데이터 로드 실패: {e}")
