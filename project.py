import streamlit as st
from pymongo import MongoClient
import datetime
from datetime import timedelta
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

# 🕒 [중요] 한국 시간(KST) 전역 강제 설정 함수 (서버 시차 9시간 완벽 보정)
def get_now_kst():
    # 서버의 기본 UTC 시간에 정확히 9시간을 더해 대한민국 표준시를 강제 생성합니다.
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
        st.success("✅ 이미 정보 기입이 완료된 툴입니다. 상태, 사용 횟수 및 드레싱 타이머를 변경할 수 있습니다.")
        current_status = existing_data.get("status", "사용중")
        status_index = ["사용전", "사용중", "폐기"].index(current_status) if current_status in ["사용전", "사용중", "폐기"] else 1
        
        with st.form(key="mobile_update_form"):
            st.markdown("### ⚡ 실시간 툴 상태 및 횟수 수정")
            u_status = st.radio("🔄 툴 현재 상태 선택", ["사용전", "사용중", "폐기"], index=status_index, horizontal=True)
            u_count = st.number_input("📊 현재까지의 실제 사용 횟수", value=int(existing_data.get('current_use', 0)), step=1)
            u_worker = st.text_input("👷 작업자 이름 수정", value=existing_data.get('worker', ''))
            u_machine = st.text_input("⚙️ 기계 가공 호기 수정", value=existing_data.get('machine_no', ''))
            
            st.markdown("---")
            st.markdown("⏳ **드레싱 주기 커스텀 시간 수정** (0시간 0분 설정 시 타이머 미작동)")
            col_uh, col_um = st.columns(2)
            with col_uh:
                u_hours = st.number_input("시간(Hour) 설정", min_value=0, max_value=72, value=int(existing_data.get('dressing_hours', 0)), step=1, key="uh")
            with col_um:
                u_mins = st.number_input("분(Minute) 설정", min_value=0, max_value=59, value=int(existing_data.get('dressing_mins', 0)), step=5, key="um")
                
            u_note = st.text_area("📝 특이사항 수정", value=existing_data.get('note', ''))
            submit_u_btn = st.form_submit_button("🔄 수정사항 저장하기")
            
        if submit_u_btn:
            waste_val = str(today) if u_status == "폐기" else existing_data.get("waste_date", "-")
            
            # 실시간 한국 시간 기준으로 타이머 재산출
            total_duration_mins = (u_hours * 60) + u_mins
            current_now = get_now_kst()
            if total_duration_mins > 0 and u_status == "사용중":
                start_time_val = current_now.strftime("%Y-%m-%d %H:%M:%S")
                target_time_val = (current_now + timedelta(minutes=total_duration_mins)).strftime("%Y-%m-%d %H:%M:%S")
            else:
                start_time_val = existing_data.get("start_time", "-")
                target_time_val = existing_data.get("target_time", "-")

            db_collection.update_one(
                {"serial_no": qr_scanned_serial},
                {"$set": {
                    "status": u_status,
                    "current_use": u_count,
                    "worker": u_worker,
                    "machine_no": u_machine,
                    "dressing_hours": u_hours,
                    "dressing_mins": u_mins,
                    "start_time": start_time_val,
                    "target_time": target_time_val,
                    "waste_date": waste_val,
                    "note": u_note
                }}
            )
            st.success("🎉 툴의 상태와 커스텀 드레싱 주기가 한국 시간 기준으로 정상 업데이트되었습니다!")
            st.rerun()
            
    else:
        st.warning("📝 아직 정보가 기입되지 않은 빈데이터 QR코드입니다. 초기 정보를 기입해 주세요.")
        with st.form(key="mobile_input_form"):
            m_status = st.radio("💎 툴 최초 상태 선택", ["사용전", "사용중", "폐기"], index=0, horizontal=True)
            m_worker = st.text_input("Worker 👷 교체 작업자 이름")
            m_machine = st.text_input("Machine ⚙️ 기계 가공 호기 (예: MCT 3호기)")
            
            st.markdown("---")
            st.markdown("⏳ **드레싱 주기 커스텀 설정** (작업자가 원하는 시간을 직접 입력하세요)")
            col_h, col_m = st.columns(2)
            with col_h:
                dressing_hours = st.number_input("시간(Hour) 설정", min_value=0, max_value=72, value=4, step=1)
            with col_m:
                dressing_mins = st.number_input("분(Minute) 설정", min_value=0, max_value=59, value=0, step=5)
                
            m_limit = st.number_input("Limit 사용 한도 횟수", value=10000, step=1000)
            m_note = st.text_area("Note 📝 특이사항")
            
            submit_m_btn = st.form_submit_button("💾 데이터 저장 및 등록 완료")
            
        if submit_m_btn:
            if not m_worker or not m_machine:
                st.error("⚠️ 작업자 이름과 가공 호기를 반드시 입력해 주세요!")
            else:
                tool_code = qr_scanned_serial[:2]
                waste_val = str(today) if m_status == "폐기" else "-"
                
                # 실시간 한국 시간 기준 매칭
                total_mins = (dressing_hours * 60) + dressing_mins
                current_now = get_now_kst()
                if total_mins > 0 and m_status == "사용중":
                    start_time_str = current_now.strftime("%Y-%m-%d %H:%M:%S")
                    target_time_str = (current_now + timedelta(minutes=total_mins)).strftime("%Y-%m-%d %H:%M:%S")
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
                        "machine_no": m_machine,
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
                st.success("🎉 한국 가공 시간 매칭 기준 데이터 저장이 완료되었습니다!")
                st.balloons()
                st.rerun()
                
    if st.button("🏠 메인 시스템으로 돌아가기"):
        st.query_params.clear()
        st.rerun()


# --- 💻 [PC 관리자 모드] ---
else:
    st.sidebar.markdown("## 📁 KKQ 통합 시스템")
    tool_menu = st.sidebar.radio("하위 목록", [
        "📊 빈데이터 QR코드 대량 선발행", 
        "⚠️ 실시간 툴 드레싱 알림판", 
        "📂 전체 데이터 현황판", 
        "⚙️ 데이터 수정 / 삭제 / QR 재발행"
    ])
    
    # 1) QR코드 대량 연속 선발행 창
    if tool_menu == "📊 빈데이터 QR코드 대량 선발행":
        st.title("🖨️ 현장 부착용 빈데이터 QR코드 대량 연속 발행 (5자리 순번 버전)")
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
                last_counter = int(last_tool["serial_no"][-5:])
            else:
                last_counter = 0
        except Exception:
            last_counter = 0
            
        st.info(f"🔍 마지막 발행 번호: **{last_counter}번** ➡️ 이번에 생성될 순번: **{last_counter+1}번 ~ {last_counter+quantity}번**")
        
        if "show_qr_grid" not in st.session_state:
            st.session_state.show_qr_grid = False
        if "current_view_serials" not in st.session_state:
            st.session_state.current_view_serials = []

        if st.button(f"🖨️ {quantity}개의 연속 QR코드 즉시 발행"):
            blank_records = []
            generated_serials = []
            
            for idx in range(1, quantity + 1):
                current_seq = last_counter + idx
                serial_no = f"{prefix}{current_seq:05d}"
                generated_serials.append(serial_no)
                
                blank_records.append({
                    "serial_no": serial_no,
                    "tool_type": "전착툴" if tool_code=="01" else "레진툴" if tool_code=="02" else "메탈툴",
                    "status": "사용전",
                    "input_date": str(today),
                    "worker": "",
                    "machine_no": "",
                    "dressing_hours": 0,
                    "dressing_mins": 0,
                    "start_time": "-",
                    "target_time": "-",
                    "use_limit": 10000,
                    "current_use": 0,
                    "waste_date": "-",
                    "note": "QR 선발행 완료 (현장 기입 대기)"
                })
                    
            try:
                db_collection.insert_many(blank_records)
                st.session_state.current_view_serials = generated_serials
                st.session_state.show_qr_grid = True
                st.success(f"🎉 {quantity}개의 순번 빈데이터가 안전하게 DB에 등록되었습니다! 아래에서 인쇄해 주세요.")
            except Exception as e:
                st.error(f"오류 발생: {e}")

        if st.session_state.show_qr_grid and st.session_state.current_view_serials:
            st.markdown("---")
            grid_cols = st.columns(4)
            for idx, s_no in enumerate(st.session_state.current_view_serials):
                with grid_cols[idx % 4]:
                    st.image(generate_app_qr_bytes(s_no), width=130)
                    st.markdown(f"**🆔 {s_no}**")
                    st.caption("◀ 스캔 시 기입창 열림")
            
            st.markdown("---")
            st.info(f"💡 총 {len(st.session_state.current_view_serials)}개의 QR코드가 인쇄 대기 중입니다.")
            
            if st.button("❌ 인쇄 완료 - 화면에서 이 QR코드 목록 지우기", type="secondary"):
                st.session_state.show_qr_grid = False
                st.session_state.current_view_serials = []
                st.success("✅ 인쇄 완료 확인! 데이터는 DB에 안전하게 보관되었으며, 화면 목록이 깔끔하게 정리되었습니다.")
                st.rerun()

        # 🚨 마스터 관리자 영역
        st.markdown("<br><br><br>---", unsafe_allow_html=True)
        st.subheader("🚨 시스템 마스터 관리자 영역")
        
        with st.expander("💥 데이터베이스 툴 종류별 선택 초기화 및 리셋", expanded=False):
            st.error("⚠️ [주의] 선택한 고유코드 유형의 모든 데이터가 영구 삭제되며, 해당 툴 종류의 다음 순번은 1번으로 리셋됩니다.")
            target_reset_code = st.selectbox(
                "🎯 데이터 삭제 및 순번을 초기화할 툴 종류(앞 2자리)를 선택하세요",
                ["01 (전착툴)", "02 (레진툴)", "03 (메탈툴)", "⚠️ 전체 모든 데이터 싹 다 삭제"]
            )
            understand_risk = st.checkbox("❗ 선택한 대상 데이터를 초기화하고 처음부터 연사를 시작하는 것에 동의합니다.")
            
            if st.button("🚨 선택한 대상 데이터 초기화 실행"):
                if not understand_risk:
                    st.warning("⚠️ 동의 체크박스에 먼저 체크를 해주셔야 초기화가 가능합니다.")
                else:
                    try:
                        if target_reset_code == "⚠️ 전체 모든 데이터 싹 다 삭제":
                            db_collection.delete_many({})
                            st.success("💥 완벽 초기화! 시스템 내 모든 기록이 삭제되었습니다.")
                        else:
                            code_prefix = target_reset_code.split(" ")[0]
                            db_collection.delete_many({"serial_no": {"$regex": f"^{code_prefix}"}})
                            st.success(f"💥 {target_reset_code} 초기화 완료!")
                        
                        st.session_state.show_qr_grid = False
                        st.session_state.current_view_serials = []
                        st.balloons()
                        st.rerun()
                    except Exception as e:
                        st.error(f"초기화 중 DB 통신 에러 발생: {e}")

    # 2) ⚠️ 실시간 툴 드레싱 알림판 (한국 시간 시차 완벽 매칭 연산 버전)
    elif tool_menu == "⚠️ 실시간 툴 드레싱 알림판":
        st.title("⏳ 실시간 툴 드레싱 및 교체 주기 모니터링 (모든 툴 대상)")
        st.markdown("작업자가 현장에서 설정한 **커스텀 시간 타이머**를 실시간으로 추적하는 상황판입니다.")
        st.markdown("---")
        
        try:
            active_tools = list(db_collection.find({"status": "사용중", "target_time": {"$ne": "-"}}))
            
            if not active_tools:
                st.info("🟢 현재 실시간 드레싱 타이머가 작동 중인 활성 툴이 없습니다.")
            else:
                st.markdown("### 📊 실시간 가동 현황 목록")
                current_now = get_now_kst() # 실시간 한국 시간 연산용 클럭 동기화
                
                for item in active_tools:
                    target_time_str = item.get("target_time")
                    target_dt = datetime.datetime.strptime(target_time_str, "%Y-%m-%d %H:%M:%S")
                    
                    # 남은 시간 계산 (KST 클럭 연동)
                    time_diff = target_dt - current_now
                    total_seconds = time_diff.total_seconds()
                    
                    if total_seconds <= 0:
                        status_label = "🚨 드레싱/교체 필요 (시간초과)"
                        color_hex = "#FF4B4B"
                        time_text = f"⚠️ 마감 시간이 {str(abs(time_diff)).split('.')[0]} 지났습니다."
                    elif total_seconds <= 3600:
                        status_label = "🟡 주의 (1시간 이내 임박)"
                        color_hex = "#FFAA00"
                        time_text = f"⏳ 약 {int(total_seconds // 60)}분 남음"
                    else:
                        status_label = "🟢 정상 가동 중"
                        color_hex = "#00B050"
                        hours_left = int(total_seconds // 3600)
                        mins_left = int((total_seconds % 3600) // 60)
                        time_text = f"⏱️ {hours_left}시간 {mins_left}분 남음"
                    
                    with st.container():
                        st.markdown(
                            f"""
                            <div style="border-left: 8px solid {color_hex}; padding: 15px; margin-bottom: 15px; background-color: #f9f9f9; border-radius: 4px;">
                                <h4 style="margin: 0; color: #333;">🆔 시리얼: <code style="font-size:18px;">{item['serial_no']}</code> ({item['tool_type']})</h4>
                                <p style="margin: 5px 0; font-size: 15px;">
                                    <b>⚙️ 현재 가공 장비:</b> {item['machine_no']} 기 | <b>👷 담당 작업자:</b> {item['worker']} <br>
                                    <b>📅 최초 장착 시간 (KST):</b> {item['start_time']} | <b>🎯 드레싱 마감 목표 (KST):</b> {target_time_str} <br>
                                    <span style="color: {color_hex}; font-weight: bold; font-size: 16px;">▶ 알림 현황: {status_label} — {time_text}</span>
                                </p>
                            </div>
                            """, 
                            unsafe_allow_html=True
                        )
                        
                        if st.button(f"🔄 시리얼 [{item['serial_no']}] 드레싱 완료 (시간 초기화 리셋)", key=f"reset_{item['serial_no']}"):
                            t_hours = int(item.get('dressing_hours', 4))
                            t_mins = int(item.get('dressing_mins', 0))
                            new_total_mins = (t_hours * 60) + t_mins
                            
                            click_now = get_now_kst()
                            new_start = click_now.strftime("%Y-%m-%d %H:%M:%S")
                            new_target = (click_now + timedelta(minutes=new_total_mins)).strftime("%Y-%m-%d %H:%M:%S")
                            
                            db_collection.update_one(
                                {"serial_no": item['serial_no']},
                                {"$set": {
                                    "start_time": new_start,
                                    "target_time": new_target,
                                    "note": item.get('note', '') + f"\n[{click_now.strftime('%m/%d %H:%M')} 드레싱 주기 완료 및 타이머 리셋]"
                                }}
                            )
                            st.success(f"🎉 {item['serial_no']}번 툴의 드레싱 타이머가 현재 한국 시간 기준으로 리셋되었습니다!")
                            st.rerun()
                            
        except Exception as e:
            st.error(f"알림판 연동 오류: {e}")

    # 3) 종합 현황판 창
    elif tool_menu == "📂 전체 데이터 현황판":
        st.title("📂 현장 기입 데이터 통합 현황판")
        st.markdown("---")
        
        try:
            all_data = list(db_collection.find({}).sort("serial_no", -1))
            if not all_data:
                st.info("조회할 데이터가 없습니다.")
            else:
                for item in all_data:
                    status = item.get("status", "사용전")
                    status_badge = "🟢 [사용전]" if status == "사용전" else "🟡 [사용중]" if status == "사용중" else "🔴 [폐기]"
                        
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
                            st.write(f"• **⏳ 설정된 드레싱 주기:** {item.get('dressing_hours', 0)}시간 {item.get('dressing_mins', 0)}분")
                            st.write(f"• **🎯 다음 마감 시간:** {item.get('target_time', '-')}")
                        st.write(f"• **📝 현장 특이 사항:** {item['note']}")
        except Exception as e:
            st.error(f"데이터 로드 실패: {e}")

    # 4) 데이터 수정 / 삭제 / QR 재발행 창
    elif tool_menu == "⚙️ 데이터 수정 / 삭제 / QR 재발행":
        st.title("⚙️ 툴 데이터 관리 및 누락 QR코드 재발행")
        st.markdown("---")
        
        st.subheader("🖨️ 누락 / 분실 QR코드 타겟 재발행")
        target_serial = st.text_input("🆔 재발행할 11자리 시리얼 번호를 정확히 입력하세요 (예: 01060200001)").strip()
        
        if target_serial:
            if len(target_serial) != 11:
                st.warning("⚠️ 시리얼 넘버는 정확히 11자리 규격이어야 합니다.")
            else:
                exist_item = db_collection.find_one({"serial_no": target_serial})
                
                if exist_item:
                    st.success(f"🔍 확인결과: 데이터베이스에 기존 데이터가 존재하는 툴입니다. [QR코드 즉시 재생성 완료]")
                    qr_res_bytes = generate_app_qr_bytes(target_serial)
                    st.image(qr_res_bytes, width=180, caption=f"재발행 넘버: {target_serial}")
                else:
                    st.error(f"❌ 확인결과: 데이터베이스에 존재하지 않는 완전히 누락된 새로운 번호입니다.")
                    if st.button(f"➕ 누락번호 `{target_serial}` 신규 생성 및 QR 발행"):
                        t_code = target_serial[:2]
                        new_blank = {
                            "serial_no": target_serial,
                            "tool_type": "전착툴" if t_code=="01" else "레진툴" if t_code=="02" else "메탈툴",
                            "status": "사용전",
                            "input_date": str(today),
                            "worker": "",
                            "machine_no": "",
                            "dressing_hours": 0,
                            "dressing_mins": 0,
                            "start_time": "-",
                            "target_time": "-",
                            "use_limit": 10000,
                            "current_use": 0,
                            "waste_date": "-",
                            "note": "누락 번호 관리자 강제 재발행 완료"
                        }
                        db_collection.insert_one(new_blank)
                        st.success(f"🎉 누락된 번호 `{target_serial}` 가 DB에 생성되었습니다.")
                        st.rerun()
