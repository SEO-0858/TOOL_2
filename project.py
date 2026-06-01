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

# 📱 [핵심 기능] QR코드를 스마트폰으로 찍었을 때 URL 뒤에 붙은 시리얼 넘버를 읽어옴
# 예: kkqpd4p.streamlit.app/?serial=0106010016
query_params = st.query_params
qr_scanned_serial = query_params.get("serial", None)

# QR코드 생성 헬퍼 함수 (현장 스마트폰 인식을 위해 내 앱 주소 URL을 QR에 심음)
def generate_app_qr_bytes(serial_text):
    # 실제 스트림릿 앱 주소와 시리얼 넘버 파라미터를 결합
    app_url = f"https://kkqpd4p.streamlit.app/?serial={serial_text}"
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=6, border=1)
    qr.add_data(app_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# --- 📱 [모바일/현장 QR 스캔 기입 모드] ---
# 만약 QR코드를 찍어서 들어온 경우, 메뉴판을 숨기고 바로 입력창만 띄워줍니다.
if qr_scanned_serial:
    st.title("📱 현장 툴 정보 즉시 기입창")
    st.subheader(f"🆔 인식된 시리얼 넘버: `{qr_scanned_serial}`")
    st.markdown("---")
    
    # 이미 등록된 데이터가 있는지 확인
    existing_data = db_collection.find_one({"serial_no": qr_scanned_serial})
    
    if existing_data and existing_data.get("worker") and existing_data.get("machine_no"):
        st.success("✅ 이미 정보 기입이 완료된 툴입니다!")
        st.write(f"• **👷 현재 작업자:** {existing_data['worker']}")
        st.write(f"• **⚙️ 가공 호기:** {existing_data['machine_no']}")
        st.write(f"• **📊 사용 한도:** {existing_data['current_use']} / {existing_data['use_limit']} 회")
        
        # 현장에서 사용횟수 누적 업데이트 기능 추가
        st.markdown("### ⚡ 사용 횟수 업데이트 (카운팅)")
        new_count = st.number_input("현재까지의 실제 사용 횟수 입력", value=int(existing_data['current_use']), step=1)
        if st.button("🔄 사용 횟수 저장"):
            db_collection.update_one({"serial_no": qr_scanned_serial}, {"$set": {"current_use": new_count}})
            st.success("사용 횟수가 수정되었습니다!")
            st.rerun()
    else:
        st.warning("📝 아직 정보가 기입되지 않은 공 QR코드입니다. 아래 내용을 입력해 주세요.")
        
        with st.form(key="mobile_input_form"):
            m_worker = st.text_input("Worker 👷 교체 작업자 이름")
            m_machine = st.text_input("Machine ⚙️ 기계 가공 호기 (예: MCT 3호기)")
            m_limit = st.number_input("Limit 사용 한도 횟수", value=10000, step=1000)
            m_note = st.text_area("Note 📝 특이사항")
            
            submit_m_btn = st.form_submit_button("💾 데이터 저장 및 등록 완료")
            
        if submit_m_btn:
            if not m_worker or not m_machine:
                st.error("⚠️ 작업자 이름과 가공 호기를 반드시 입력해 주세요!")
            else:
                # 껍데기만 있던 데이터에 실제 현장 정보를 덮어씌움(Upsert)
                tool_code = qr_scanned_serial[:2]
                db_collection.update_one(
                    {"serial_no": qr_scanned_serial},
                    {"$set": {
                        "serial_no": qr_scanned_serial,
                        "tool_type": "전착툴" if tool_code=="01" else "레진툴" if tool_code=="02" else "메탈툴",
                        "input_date": str(today),
                        "worker": m_worker,
                        "machine_no": m_machine,
                        "use_limit": m_limit,
                        "current_use": 0,
                        "waste_date": "-",
                        "note": m_note
                    }},
                    upsert=True
                )
                st.success("🎉 정보가 성공적으로 저장되었습니다! 이제 데이터베이스에서 조회 가능합니다.")
                st.balloons()
                st.rerun()
                
    if st.button("🏠 메인 시스템으로 돌아가기"):
        st.query_params.clear()
        st.rerun()

# --- 💻 [PC 관리자 모드: 대량 QR 선발행 및 모니터링] ---
else:
    # 🗂️ 왼쪽 사이드바 메뉴
    st.sidebar.markdown("## 📁 KKQ 통합 시스템")
    tool_menu = st.sidebar.radio("하위 목록", ["📊 껍데기 QR코드 대량 선발행", "📂 전체 데이터 현황판"])
    
    # [메뉴 1: QR코드만 다음 순번으로 대량 선발행]
    if tool_menu == "📊 껍데기 QR코드 대량 선발행":
        st.title("🖨️ 현장 부착용 공(Blank) QR코드 대량 연속 발행")
        st.markdown("데이터 기입은 현장에서 QR을 스캔하여 진행합니다. 여기서는 순번에 맞는 QR코드만 먼저 생성합니다.")
        st.markdown("---")
        
        c1, c2 = st.columns(2)
        with c1:
            tool_code = st.text_input("🆔 고유넘버 앞 2자리 입력 (전착:01 / 레진:02 / 메탈:03)", value="01", max_chars=2)
        with c2:
            quantity = st.number_input("📦 발행할 QR코드 갯수", min_value=1, max_value=50, value=20, step=1)
            
        prefix = f"{tool_code}{mmdd}"
        
        # 마지막 번호 알아서 추적하기
        try:
            last_tool = db_collection.find_one({"serial_no": {"$regex": f"^{prefix}"}}, sort=[("serial_no", -1)])
            if last_tool:
                last_counter = int(last_tool["serial_no"][-4:])
            else:
                last_counter = 0
        except Exception:
            last_counter = 0
            
        st.info(f"🔍 마지막 발행 번호: **{last_counter}번** ➡️ 이번에 발행될 번호: **{last_counter+1}번 ~ {last_counter+quantity}번**")
        
        if st.button(f"🖨️ {quantity}개의 연속 QR코드 즉시 인쇄/발행"):
            blank_records = []
            st.markdown("### 🖨️ 인쇄용 QR코드 리스트 (마우스 우클릭 저장 가능)")
            
            grid_cols = st.columns(4) # 4열로 이쁘게 배치
            
            for idx in range(1, quantity + 1):
                current_seq = last_counter + idx
                serial_no = f"{prefix}{current_seq:04d}"
                
                # 1. 몽고디비에 시리얼 넘버 껍데기(초기값) 먼저 확보
                blank_records.append({
                    "serial_no": serial_no,
                    "tool_type": "전착툴" if tool_code=="01" else "레진툴" if tool_code=="02" else "메탈툴",
                    "input_date": str(today),
                    "worker": "",  # 현장에서 채울 것이므로 비워둠
                    "machine_no": "",
                    "use_limit": 10000,
                    "current_use": 0,
                    "waste_date": "-",
                    "note": "QR 선발행 완료 (기입 대기)"
                })
                
                # 2. 화면에 인쇄할 수 있게 QR코드 표시
                with grid_cols[(idx-1) % 4]:
                    qr_bytes = generate_app_qr_bytes(serial_no)
                    st.image(qr_bytes, width=140)
                    st.markdown(f"**🆔 {serial_no}**")
                    st.caption("◀ 스캔 시 기입창 오픈")
                    
            # 데이터베이스에 시리얼 번호 선등록(중복 방지 및 순번 선점)
            try:
                db_collection.insert_many(blank_records)
                st.success(f"🎉 {quantity}개의 시리얼 넘버 껍데기가 DB에 선점되었으며 QR코드 발행이 완료되었습니다!")
            except Exception as e:
                st.error(f"순번 선점 중 오류 발생 (이미 발행 누르셨다면 새로고침 하세요): {e}")

    # [메뉴 2: 현장에서 기입한 데이터 모니터링 현황판]
    elif tool_menu == "📂 전체 데이터 현황판":
        st.title("📂 현장 기입 데이터 통합 현황판")
        st.markdown("현장 작업자들이 QR코드를 찍어 입력한 실시간 데이터 테이블입니다.")
        st.markdown("---")
        
        try:
            all_data = list(db_collection.find({}).sort("serial_no", -1))
            if not all_data:
                st.info("조회할 데이터가 없습니다.")
            else:
                for item in all_data:
                    # 미기입 상태와 기입 완료 상태 구분 표시
                    if not item['worker'] or not item['machine_no']:
                        status_str = "⚪ 기입 대기중"
                        expander_title = f"{status_str} | 🆔 시리얼: {item['serial_no']}"
                    else:
                        status_str = "🟢 기입 완료"
                        expander_title = f"{status_str} | 🆔 시리얼: {item['serial_no']} | 장비: {item['machine_no']} | 작업자: {item['worker']}"
                        
                    with st.expander(expander_title):
                        st.write(f"• **📅 발행 날짜:** {item['input_date']}")
                        st.write(f"• **📊 사용 횟수:** {item['current_use']} / {item['use_limit']} 회")
                        st.write(f"• **📝 특이 사항:** {item['note']}")
        except Exception as e:
            st.error(f"데이터 로드 실패: {e}")
