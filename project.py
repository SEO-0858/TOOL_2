import streamlit as st
from pymongo import MongoClient
import datetime
from datetime import timedelta, datetime as dt_class
import qrcode
from io import BytesIO
import base64
import re
import time
from datetime import datetime as dt_datetime
def parse_serial_new(s):
    # s는 12자리 문자열
    t_type = s[0]      # 종류 (1자리)
    date_part = s[1:9] # 날짜 (8자리)
    seq = s[9:12]      # 순번 (3자리)
    return t_type, date_part, seq
if 'sidebar_errors' not in st.session_state:
    st.session_state.sidebar_errors = []

# 파일 최상단 import 아래에 이 함수를 추가하세요
def get_elapsed_time_str(start_time_val):
    try:
        # 데이터가 없으면 빈 문자열 반환
        if not start_time_val or start_time_val == "-":
            return ""
        
        # 문자열을 datetime 객체로 변환 (기존에 이미 dt_class를 사용 중이므로 안전합니다)
        # 만약 start_time_val이 이미 datetime 객체라면 바로 사용
        start_dt = dt_class.strptime(str(start_time_val), "%Y-%m-%d %H:%M:%S")
        
        # 현재 시간과 차이 계산 (UTC+9 적용)
        now_kst = dt_class.utcnow() + timedelta(hours=9)
        diff = now_kst - start_dt
        
        hours = int(diff.total_seconds() // 3600)
        minutes = int((diff.total_seconds() % 3600) // 60)
        
        return f'<br><span style="color:red; font-size:9px;">({hours}시간 {minutes}분 경과)</span>'
    except:
        return "" # 어떤 에러가 나도 조용히 빈 값 반환

def add_error(msg):
    st.session_state.sidebar_errors.append(msg)
# 🌟 1. 페이지 기본 설정 및 URL 파라미터 추적
st.set_page_config(page_title="KKQ 4파트 다이아몬드 툴관리", layout="wide")
# [2단계: 사이드바 오류 표시 영역]
with st.sidebar:
    st.subheader("⚠️ 시스템 통합 알림")
    
    # 1. 오류 표시 공간(Placeholder) 만들기
    error_area = st.empty()
    
    # 2. 리스트에 오류가 있을 때만 화면에 표시
    if st.session_state.sidebar_errors:
        with error_area.container():
            for err in st.session_state.sidebar_errors:
                st.error(err)
    
    # 3. 버튼 로직
    if st.button("🚫 모든 오류 확인 및 초기화"):
        # 리스트 비우기
        st.session_state.sidebar_errors = []
        # 즉시 화면의 알람 영역을 비워버림 (rerun 불필요!)
        error_area.empty()
            

# 🔒 2. 데이터베이스 연결
@st.cache_resource
def get_database():
    # 이제 secrets.toml 금고에서 비밀번호를 꺼냅니다. (이 줄만 있으면 됩니다!)
    mongo_uri = st.secrets["database"]["MONGO_URI"]
    try:
        client = MongoClient(mongo_uri)
        db = client["dashboard_db"]
        return db["tools_management"]
    except Exception as e:
        st.error(f"🌐 데이터베이스 통신 오류: {e}")
        return None

db_collection = get_database()

# --- [공정 흐름 제어 검문소] ---
def validate_process(current_status, next_status):
    # 예외 허용: 사용전 상태라도 다음이 폐기이고, 나중에 사유가 들어올 것이라면 일단 통과
    if current_status == "사용전" and next_status == "폐기":
        return True, ""
        
    allowed = {
        "사용전": ["사용중"],
        "사용중": ["재사용대기", "폐기"],
        "재사용대기": ["재사용", "폐기"],
        "재사용": ["재사용대기", "폐기"],
        "폐기": []
    }
    if current_status in allowed and next_status not in allowed[current_status]:
        return False, f"⚠️ 공정 오류: {current_status} 상태에서는 {next_status}로 이동할 수 없습니다."
    return True, ""

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


# 🟣 [재사용대기 팝업 대화창 정의]
@st.dialog("📋 재사용대기 전환 추가 정보 기입")
def show_reuse_pending_dialog(s_no, current_mach, orig_note, ed_worker, ed_machine_num, ed_hours, ed_mins):
    st.write("🛠️ 이 툴을 보관 후 다시 사용하기 위해 기계 가공 실적을 입력해 주세요.")
    
    pop_worker_name = st.text_input("👤 보관 처리 작업자 성명", value=ed_worker, key=f"pop_worker_reuse_{s_no}")
    
    orig_m_num = ''.join(filter(str.isdigit, str(current_mach)))
    try:
        def_m_val = int(orig_m_num) if orig_m_num else 0
    except:
        def_m_val = 0
        
    pop_mach_num = st.number_input("⚙️ 방금 마친 기계 가공 호기 (숫자만)", min_value=1, max_value=200, value=def_m_val if def_m_val > 0 else 1, key=f"pop_mach_pending_{s_no}")
    pop_count = st.number_input("📊 이번 공정에서의 가공 갯수 (개)", min_value=0, max_value=999999, value=100, step=10, key=f"pop_count_pending_{s_no}")
    
    if st.button("🚀 실적 기록 및 재사용대기 저장"):
        log_now = get_now_kst()
        log_time_str = log_now.strftime("%Y-%m-%d %H:%M:%S")
        pop_mach_name = f"{pop_mach_num}호기"
        
        # [2단계 수정] 작업자 이름 부분에 pop_worker_name 사용
        auto_log_msg = f"\n[{log_time_str}] 상태: 재사용대기, 작업자: {pop_worker_name}, 가공기계: {pop_mach_name}, 가공갯수: {pop_count}개"
        final_note_val = orig_note.strip() + auto_log_msg
        
        timestamp = log_now.strftime("%m/%d %H:%M")
        history_entry = f"{timestamp} - 상태변환:재사용대기 (작업자:{pop_worker_name}, {pop_mach_name}, {pop_count}개)"
        
        db_collection.update_one(
            {"serial_no": s_no},
            {"$set": {
                "status": "재사용대기",
                "worker": pop_worker_name,  # [2단계 추가] DB에도 작업자 저장
                "machine_no": pop_mach_name,
                "dressing_hours": 0,
                "dressing_mins": 0,
                "start_time": "-",
                "target_time": "-",
                "waste_date": "-",
                "note": final_note_val,
                "last_active_machine": pop_mach_name,
                "last_active_count": pop_count,
                "last_active_time": log_time_str
            }, "$push": {"history": history_entry}}
        )
        st.success("🎉 재사용대기 실적이 성공적으로 누적 저장되었습니다!")
        time.sleep(1)
        st.rerun()


# 🔴 [폐기 전환 팝업 대화창 정의]
@st.dialog("🚨 툴 폐기 정보 및 사유 입력")
def show_waste_dialog(s_no, current_mach, orig_note, ed_worker, from_status):
    st.markdown("### 🗑️ 이 툴을 현장 폐기 처리합니다. 아래 정보를 입력하세요.")
    
    is_stored_waste = (from_status == "재사용대기")
    
# [수정된 부분] 
    if from_status == "재사용대기":
        st.info("📦 이 툴은 현재 보관 중인 [재사용대기] 상태이므로 기계 가공 호기가 '보관'으로 자동 지정됩니다.")
        pop_mach_name = "보관"
        # 재사용대기는 기존 작업자를 사용
        final_worker = ed_worker
    elif from_status == "사용전":
        st.info("🆕 이 툴은 [사용전] 새 제품입니다. 작업자와 기계 번호를 직접 입력하세요.")
        pop_mach_name = "없음"
        # 사용전 툴은 작업자를 직접 입력받음
        final_worker = ed_worker
    else:
        # 기존 방식
        orig_m_num = ''.join(filter(str.isdigit, str(current_mach)))
        try:
            def_m_val = int(orig_m_num) if orig_m_num else 0
        except:
            def_m_val = 0
        pop_waste_mach = st.number_input("⚙️ 방금 마친 기계 가공 호기 (숫자만)", min_value=1, max_value=200, value=def_m_val if def_m_val > 0 else 1, key=f"pop_mach_waste_{s_no}")
        pop_mach_name = f"{pop_waste_mach}호기"
      
    
    # [1단계] 입력창 추가 (팝업이 뜨면 바로 보입니다)
    # 작업자 이름과 사용 갯수를 여기서 입력받습니다.
    pop_worker_name = st.text_input("👤 폐기 처리 작업자 성명", value=ed_worker, key=f"pop_worker_{s_no}")
    pop_use_count = st.number_input("🔢 폐기 시점까지의 사용 갯수", min_value=0, value=0, key=f"pop_use_count_{s_no}")


    waste_options = [
        "1. 한도수량 (팁2mm이하)",
        "2. 다이아팁 파손, 툴형상변화",
        "3. 제품 스크레치 치핑, 깨짐",
        "4. 공구 떨림 공구 형상 불량",
        "5. 기타 (직접기입)"
    ]
    chosen_reason = st.selectbox("🎯 폐기 사유 선택 (드래그 목록)", waste_options, key=f"pop_reason_select_{s_no}")
    
    detail_reason = ""
    if chosen_reason == "5. 기타 (직접기입)":
        detail_reason = st.text_input("📝 상세 폐기 사유 직접 입력", placeholder="예: 보관 보관함 이동 중 낙하 파손", key=f"pop_detail_reason_{s_no}").strip()
        
    if st.button("💾 실적 기록 및 폐기 저장", type="primary"):
        if chosen_reason == "5. 기타 (직접기입)" and not detail_reason:
            add_error("⚠️ '5. 기타 (직접기입)'를 선택한 경우, 상세 사유 내용을 반드시 입력하셔야 저장이 가능합니다!")
            st.stop()
            
        log_now = get_now_kst()
        log_time_str = log_now.strftime("%Y-%m-%d %H:%M:%S")
        final_reason_text = detail_reason if chosen_reason == "5. 기타 (직접기입)" else chosen_reason
        
        
        auto_log_msg = f"\n[{log_time_str}] 상태: 폐기, 작업자: {pop_worker_name}, 가공기계: {pop_mach_name}, 사용갯수: {pop_use_count}개, 폐기사유: {final_reason_text}"
        final_note_val = orig_note.strip() + auto_log_msg
        
        timestamp = log_now.strftime("%m/%d %H:%M")
        history_entry = f"{timestamp} - 상태변환:폐기 (작업자:{final_worker}, 기계:{pop_mach_name}, 사유:{final_reason_text})"
        
        db_collection.update_one(
            {"serial_no": s_no},
            {"$set": {
                "status": "폐기",
                "worker": pop_worker_name,
                "machine_no": pop_mach_name,
                "use_count": pop_use_count,
                "dressing_hours": 0,
                "dressing_mins": 0,
                "start_time": "-",
                "target_time": "-",
                "waste_date": log_time_str,
                "note": final_note_val
            }, "$push": {"history": history_entry}}
        )
        st.success("💥 툴 폐기 실적 처리가 안전하게 저장되었습니다.")
        time.sleep(1)
        st.rerun()


# --- 📱 [모바일/현장 QR 스캔 기입 모드] ---
if qr_scanned_serial:
    st.title("📱 현장 툴 정보 즉시 기입창")
    st.subheader(f"🆔 인식된 시리얼 넘버: `{qr_scanned_serial}`")
    st.write("<br>", unsafe_allow_html=True)
    
    existing_data = db_collection.find_one({"serial_no": qr_scanned_serial})
    
    if existing_data and existing_data.get("worker") and existing_data.get("machine_no"):
        st.success("✅ 이미 정보 기입이 완료된 툴입니다. 상태 및 정보를 수정할 수 있습니다.")
        db_status_mob = existing_data.get("status", "사용중")
        
        status_options = ["사용전", "사용중", "재사용", "재사용대기", "폐기"]
        status_index = status_options.index(db_status_mob) if db_status_mob in status_options else 1
        
        note_content = str(existing_data.get('note', ''))
        has_history_log = "상태:" in note_content or "호기" in note_content
        has_pending_log = "상태: 재사용대기" in note_content
        
        if db_status_mob == "재사용대기" or (existing_data.get("last_active_machine") and has_history_log):
            st.warning(f"""
            ⚠️ **이 툴은 이전에 가동되었다가 보관 후 다시 사용하는 [재사용 대상] 툴입니다.**
            * **직전 사용 장비**: {existing_data.get('last_active_machine', '기록없음')}
            * **재사용대기 전환 시점**: {existing_data.get('last_active_time', '기록없음')}
            * **이전 공정 가공 갯수**: {existing_data.get('last_active_count', 0)} 개
            """)
        
        orig_machine = existing_data.get('machine_no', '')
        orig_machine_num = ''.join(filter(str.isdigit, orig_machine))
        try:
            default_machine_int = 0
        except:
            default_machine_int = 0

        with st.form(key="mobile_update_form"):
            st.markdown("### ⚡ 실시간 툴 상태 및 횟수 수정")
            u_status = st.radio("🔄 툴 현재 상태 선택", status_options, index=status_index, horizontal=True)
            u_count = st.number_input("📊 현재까지의 실제 사용 횟수", value=int(existing_data.get('current_use', 0)), step=1)
            
            u_worker = st.text_input("👷 작업자 이름 기입", value="").strip()
            u_machine_num = st.number_input("⚙️ 기계 가공 호기 선택 (숫자만 입력)", min_value=0, max_value=200, value=default_machine_int, step=1)
            
            st.write("<br>", unsafe_allow_html=True)
            st.markdown("⏳ **드레싱 주기 커스텀 시간 수정**")
            col_uh, col_um = st.columns(2)
            with col_uh:
                u_hours = st.number_input("시간(Hour) 설정", min_value=0, max_value=72, value=0, step=1, key="uh")
            with col_um:
                u_mins = st.number_input("분(Minute) 설정", min_value=0, max_value=59, value=0, step=5, key="um")
                
            default_val = existing_data.get('note', '')
            display_note = default_val
            if "현장 입고일" in default_val or "QR 선발행" in default_val:
                match = re.search(r"(\[.*?\])", default_val)
                if match: display_note = match.group(1)
                else: display_note = ""
            
            u_note = st.text_area("📝 현장 특이사항", value=display_note)
            u_submit_form_btn = st.form_submit_button("🔄 수정사항 저장하기")
            
        # 📱 모바일 공정 흐름 실시간 검증 시스템 가동
        flow_error_msg = ""
        
        # [수정된 모바일 공정 흐름 실시간 검증 시스템]
        if u_submit_form_btn:
            # 1. 여기서부터 검사를 시작합니다 (버튼 누를 때만!)
            flow_error_msg = ""
            
            if db_status_mob == "폐기" and u_status != "폐기":
                flow_error_msg = "⚠️ [공정 보안 경고] 이 툴은 이미 최종 '폐기' 처리가 완료된 상태입니다. 폐기 공구를 다시 가동 공정으로 되돌리는 것은 안전 및 논리상 절대 불가능합니다!"
            elif db_status_mob == "재사용대기" and u_status in ["사용전", "사용중"]:
                flow_error_msg = "⚠️ [공정 보안 경고] 현재 보관('재사용대기') 중인 툴입니다. 다시 장착하여 재가동할 때는 '사용중'이 아닌 무조건 [재사용] 또는 [폐기] 라디오 버튼만 선택해야 합니다!"
            elif db_status_mob == "사용전" and u_status in ["재사용", "재사용대기", "폐기"]:
                flow_error_msg = f"⚠️ [공정 흐름 오류] 아직 가동된 적 없는 '사용전' 상태의 새 제품입니다. 이치에 맞지 않게 바로 '{u_status}' 상태로 건너뛸 수 없습니다!"
            elif db_status_mob == "사용중" and u_status == "재사용":
                flow_error_msg = "⚠️ [공정 흐름 오류] 현재 '사용중'인 툴은 바로 '재사용'으로 갈 수 없습니다! 반드시 먼저 '재사용대기'를 선택하여 실적갯수를 기록한 후 보관함에서 꺼낼 때 '재사용' 하는 것입니다."
            elif db_status_mob in ["사용중", "재사용", "재사용대기"] and u_status == "사용전":
                flow_error_msg = "⚠️ [공정 오류] 이미 사용 흔적이 기록된 가동 툴은 라디오 버튼으로 '사용전' 복구가 불가합니다! 이력을 파괴하려면 PC 대시보드 하단의 '완전 초기화' 기능을 이용하세요."
            elif u_status in ["사용중", "재사용", "재사용대기"] and (not u_worker or u_machine_num == 0):
                flow_error_msg = "⚠️ [데이터 누락] 가동/보관 단계 저장 시에는 [교체 작업자 이름] 및 [기계 가공 호기(0호기 불가)]를 반드시 입력해야 합니다!"
            elif u_status == "폐기" and not u_worker:
                flow_error_msg = "⚠️ [데이터 누락] 툴 폐기 처리를 하려면 [교체 작업자 이름]을 반드시 입력해야 합니다!"

            # 2. 검사 결과, 에러가 있다면 여기서 바로 알림을 띄우고 멈춥니다.
            if flow_error_msg:
                if flow_error_msg not in st.session_state.sidebar_errors:
                    add_error(flow_error_msg)
                st.stop()
        
        # flow_error_msg 체크가 끝난 바로 아래에 추가하세요
        # [2단계: 모바일 검문소 설치]
        is_valid, msg = validate_process(db_status_mob, u_status)
        
        # [수정] 사용전 툴 폐기는 모바일에서도 예외적으로 통과시킴
        if not is_valid:
            if db_status_mob == "사용전" and u_status == "폐기":
                is_valid = True
                
        if not is_valid:
            st.error(msg)
            st.stop()

            machine_full_name = f"{u_machine_num}호기"
            total_duration_mins = (u_hours * 60) + u_mins
            current_now = get_now_kst()
            
            if u_status == "재사용대기":
                show_reuse_pending_dialog(qr_scanned_serial, existing_data.get('machine_no', ''), u_note, u_worker, u_machine_num, u_hours, u_mins)
                st.stop()
            
            if u_status == "폐기":
                show_waste_dialog(qr_scanned_serial, existing_data.get('machine_no', ''), u_note, u_worker, db_status_mob)
                st.stop()

            current_time_str = current_now.strftime("%Y-%m-%d %H:%M:%S")
            waste_val = current_time_str if u_status == "폐기" else "-"
            
            if total_duration_mins > 0 and u_status in ["사용중", "재사용"]:
                start_time_val = existing_data.get("start_time") if existing_data.get("start_time") != "-" else current_now.strftime("%Y-%m-%d %H:%M:%S")
                try:
                    start_dt = dt_class.strptime(start_time_val, "%Y-%m-%d %H:%M:%S")
                except:
                    start_dt = current_now
                    start_time_val = current_now.strftime("%Y-%m-%d %H:%M:%S")
                target_time_val = (start_dt + timedelta(minutes=total_duration_mins)).strftime("%Y-%m-%d %H:%M:%S")
            else:
                start_time_val = existing_data.get("start_time", "-")
                target_time_val = existing_data.get("target_time", "-")

            timestamp = current_now.strftime("%m/%d %H:%M")
            history_entry = f"{timestamp} - 상태:{existing_data.get('status')}→{u_status}, 작업자:{u_worker}, 기계:{machine_full_name}"
            
            if u_status == db_status_mob:
                final_note_val = u_note.strip()  
            else:
                log_time_str = current_now.strftime("%Y-%m-%d %H:%M:%S")
                auto_log_msg = f"\n[{log_time_str}] 상태: {u_status}, 작업자: {u_worker}, 기계: {machine_full_name}"
                final_note_val = u_note.strip() + auto_log_msg

            db_collection.update_one(
                {"serial_no": qr_scanned_serial},
                {
                    "$set": {
                        "status": u_status,
                        "current_use": u_count,
                        "worker": "" if u_status in ["사용전", "폐기"] else u_worker, 
                        "machine_no": "" if u_status in ["사용전", "폐기"] else machine_full_name,
                        "waste_date": waste_val,
                        "note": final_note_val,
                        "start_time": start_time_val,
                        "target_time": target_time_val
                    },
                    "$push": {"history": history_entry} if u_status != db_status_mob else {"$each": []}
                }
            )
            st.success("✅ 수정사항이 저장되었습니다!")
            time.sleep(1)
            st.rerun()    
    else:
        st.warning("📝 아직 정보가 기입되지 않은 빈데이터 QR코드입니다. 초기 정보를 기입해 주세요.")
        
        st.markdown("### 📅 기계 장착 날짜 및 시간 선택")
        current_now = get_now_kst()
        
        col_date, col_time = st.columns(2)
        with col_date:
            chosen_date = st.date_input("장착 날짜 선택", value=current_now.date(), key="m_chosen_date")
        with col_time:
            chosen_time = st.time_input("장착 시간 선택", value=current_now.time(), step=300, key="m_chosen_time")
            
        combined_dt = dt_class.combine(chosen_date, chosen_time)
        
        with st.form(key="mobile_input_form"):
            m_status = st.radio("💎 툴 최초 상태 선택", ["사용전", "사용중", "재사용", "재사용대기", "폐기"], index=0, horizontal=True)
            m_worker = st.text_input("Worker 👷 교체 작업자 이름").strip()
            m_machine_num = st.number_input("Machine ⚙️ 기계 가공 호기 (숫자만 입력)", min_value=0, max_value=200, value=0, step=1)
            
            st.write("<br>", unsafe_allow_html=True)
            st.markdown("⏳ **드레싱 주기 커스텀 설정**")
            col_h, col_m = st.columns(2)
            with col_h:
                dressing_hours = st.number_input("시간(Hour) 설정", min_value=0, max_value=72, value=4, step=1)
            with col_m:
                dressing_mins = st.number_input("분(Minute) 설정", min_value=0, max_value=59, value=0, step=5)
                
            m_limit = st.number_input("Limit 사용 한도 횟수",min_value=0, value=10000, step=1000)
            
            init_display_note = existing_data.get('note', '') if existing_data else ""
            if "현장 입고일" in init_display_note or "QR 선발행" in init_display_note:
                match_init = re.search(r"(\[.*?\])", init_display_note)
                init_display_note = match_init.group(1) if match_init else ""

            m_note = st.text_area("Note 📝 특이사항", value=init_display_note)
            
            submit_m_btn = st.form_submit_button("💾 데이터 저장 및 등록 완료")
            
        if submit_m_btn:
            if not m_worker:
                add_error("⚠️ 작업자 이름을 반드시 입력해 주세요!")
            elif m_machine_num == 0:
                add_error("⚠️ 장착 가공할 정확한 기계 호기 번호를 기입해 주세요!")
            else:
                tool_code = qr_scanned_serial[:3]
                waste_val = str(today) if m_status == "폐기" else "-"
                machine_full_name = f"{m_machine_num}호기"
                
                total_mins = (dressing_hours * 60) + dressing_mins
                if total_mins > 0 and m_status in ["사용중", "재사용"]:
                    start_time_str = combined_dt.strftime("%Y-%m-%d %H:%M:%S")
                    target_time_str = (combined_dt + timedelta(minutes=total_mins)).strftime("%Y-%m-%d %H:%M:%S")
                else:
                    start_time_str = "-"
                    target_time_str = "-"
                
                init_time_only = chosen_time.strftime("%H:%M")
                
                log_time_str = combined_dt.strftime("%Y-%m-%d %H:%M:%S")
                auto_log_msg = f"\n[{log_time_str}] 상태: {m_status}, 작업자: {m_worker}, 기계: {machine_full_name}"
                final_m_note_val = m_note.strip() + auto_log_msg

                db_collection.update_one(
                    {"serial_no": qr_scanned_serial},
                    {"$set": {
                        "serial_no": qr_scanned_serial,
                        "tool_type": "전착툴" if tool_code=="1" else "레진툴" if tool_code=="2" else "메탈툴"if tool_code=="3" else "코어툴",
                        "status": m_status,
                        "input_date": str(chosen_date), 
                        "init_time": init_time_only,  
                        "worker": m_worker,
                        "machine_no": machine_full_name,
                        "dressing_hours": dressing_hours,
                        "dressing_mins": dressing_mins,
                        "start_time": start_time_str,
                        "target_time": target_time_str,
                        "use_limit": m_limit,
                        "current_use": 0,
                        "waste_date": waste_val,
                        "note": final_m_note_val
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
    st.session_state.sidebar_errors = []
    st.sidebar.markdown("## 📁 KKQ 통합 시스템")
    menu_options = ["📊 빈데이터 QR코드 대량 선발행", "⚠️ 실시간 툴 드레싱 알림판", "📂 전체 데이터 현황판", "⚙️ 데이터 수정 / 삭제 / QR 재발행", "🖥️ 실시간 기계 정보창"]
    if "sidebar_choice" not in st.session_state:
        st.session_state.sidebar_choice = menu_options[0]
        
    tool_menu = st.sidebar.radio("하위 목록", menu_options, key="sidebar_choice")
    
    # 1) QR코드 대량 연속 선발행 창
    if tool_menu == "📊 빈데이터 QR코드 대량 선발행":
        st.title("🖨️ 현장 부착용 빈데이터 QR코드 대량 연속 발행 (5자리 순번 버전)")
        st.write("<br>", unsafe_allow_html=True)
        
        c1, c2 = st.columns(2)
        with c1:
            tool_code = st.text_input("🆔 고유넘버 앞 3자리 입력 (전착:001 / 레진:002 / 메탈:003 / 코어:004)", value="001", max_chars=3)
        with c2:
            quantity = st.number_input("📦 발행할 QR코드 갯수", min_value=1, max_value=100, value=50, step=1)
            
        prefix = f"{tool_code}{mmdd}"
        
        try:
            last_tool = db_collection.find_one({"serial_no": {"$regex": f"^{prefix}"}}, sort=[("serial_no", -1)])
            if last_tool:
                last_counter = int(last_tool["serial_no"][-3:])
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
            
            fixed_now_kst = get_now_kst()
            fixed_date_str = fixed_now_kst.strftime("%Y-%m-%d")
            fixed_time_str = fixed_now_kst.strftime("%H:%M")
            display_mmdd_hhmm = fixed_now_kst.strftime("%m/%d %H:%M")
            
            for idx in range(1, quantity + 1):
                current_seq = last_counter + idx
                serial_no = f"{prefix}{current_seq:03d}"
                generated_serials.append(serial_no)
                
                blank_records.append({
                    "serial_no": serial_no,
                    "tool_type": "전착툴" if tool_code=="1" else "레진툴" if tool_code=="2" else "메탈툴" if tool_code=="3" else "코어툴",
                    "status": "사용전",
                    "input_date": fixed_date_str,
                    "init_time": fixed_time_str,
                    "worker": "",
                    "machine_no": "",
                    "dressing_hours": 0,
                    "dressing_mins": 0,
                    "start_time": "-",
                    "target_time": "-",
                    "use_limit": 10000,
                    "current_use": 0,
                    "waste_date": "-",
                    "note": f"[{display_mmdd_hhmm} 발행] 현장 입고일 완료 (현장 기입 대기)"
                })
                    
            try:
                db_collection.insert_many(blank_records)
                st.session_state.current_view_serials = generated_serials
                st.session_state.show_qr_grid = True
                st.success(f"🎉 {quantity}개의 순번 빈데이터가 안전하게 DB에 등록되었습니다!")
            except Exception as e:
                st.error(f"오류 발생: {e}")

        if st.session_state.show_qr_grid and st.session_state.current_view_serials:
            st.write("<br>", unsafe_allow_html=True)
            
            html_printable_content = "<div id='print-target-area' style='display: flex; flex-wrap: wrap; gap: 20px; justify-content: flex-start; padding: 10px;'>"
            
            grid_cols = st.columns(4)
            for idx, s_no in enumerate(st.session_state.current_view_serials):
                qr_bytes = generate_app_qr_bytes(s_no)
                base64_qr = base64.b64encode(qr_bytes).decode("utf-8")
                
                with grid_cols[idx % 4]:
                    st.image(qr_bytes, width=130)
                    st.markdown(f"**🆔 {s_no}**")
                
                html_printable_content += f"""
                <div style="width: 140px; text-align: center; border: 1px dashed #ccc; padding: 8px; background: white; margin-bottom:10px; page-break-inside: avoid;">
                    <img src="data:image/png;base64,{base64_qr}" style="width: 120px; height: 120px;" />
                    <div style="font-family: monospace; font-size: 11px; font-weight: bold; margin-top: 4px; color:#000;">ID: {s_no}</div>
                </div>
                """
            html_printable_content += "</div>"
            st.write("<br>", unsafe_allow_html=True)
            
            # [최종 수정] 팝업 없는 직접 인쇄 방식
            if st.button("🖨️ 생성된 QR코드 전체 프린터로 인쇄하기"):
                # 인쇄용 CSS를 포함한 HTML 구조
                print_style = """
                <style>
                    @media print {
                        .no-print { display: none; }
                        .print-only { display: block; }
                    }
                </style>
                """
                # 인쇄 내용을 감싸는 HTML
                print_body = f"<div class='print-only'>{html_printable_content}</div>"
                
                # HTML 렌더링 후 자동으로 브라우저 인쇄 함수를 호출
                st.components.v1.html(f"""
                    {print_style}
                    {print_body}
                    <script>
                        window.print();
                    </script>
                """, height=0)
            
            if st.button("❌ 인쇄 완료 - 화면에서 이 QR코드 목록 지우기", type="secondary"):
                st.session_state.show_qr_grid = False
                st.session_state.current_view_serials = []
                st.rerun()

        st.markdown("<br><br><br> ", unsafe_allow_html=True)
        st.subheader("🚨 시스템 마스터 관리자 영역")
        
        if "reset_success" not in st.session_state:
            st.session_state.reset_success = False
        if "reset_message" not in st.session_state:
            st.session_state.reset_message = ""

        if st.session_state.reset_success:
            st.success(st.session_state.reset_message)
            st.balloons()
            if st.button("🔄 관리자 영역 새로고침 (메뉴 다시 열기)"):
                st.session_state.reset_success = False
                st.session_state.reset_message = ""
                st.rerun()
        else:
            with st.expander("💥 데이터베이스 초기화 및 특정 시리얼 개별 삭제", expanded=False):
                delete_mode = st.radio("🗑️ 삭제 방식 선택", ["📂 종류별 묶음 초기화 및 리셋", "🆔 특정 개별 시리얼 코드 1개만 삭제"], horizontal=True)
                
                if delete_mode == "📂 종류별 묶음 초기화 및 리셋":
                    target_reset_code = st.selectbox("🎯 데이터 삭제 및 순번을 초기화할 툴 종류", ["1 (전착툴)", "2 (레진툴)", "3 (메탈툴)", "4 (코어툴)", "⚠️ 전체 모든 데이터 싹 다 삭제"])
                    understand_risk = st.checkbox("❗ 선택한 대상 데이터를 초기화하고 처음부터 연사를 시작하는 것에 동의합니다.", key="risk_group")
                    
                    if st.button("🚨 선택한 대상 데이터 초기화 실행", key="btn_group_del"):
                        if understand_risk:
                            if target_reset_code == "⚠️ 전체 모든 데이터 싹 다 삭제":
                                db_collection.delete_many({})
                                st.session_state.reset_message = "💥 전체 데이터베이스 항목 초기화 처리가 완벽하게 끝났습니다! 전체 리셋이 완료되었습니다."
                            else:
                                code_prefix = target_reset_code.split(" ")[0]
                                db_collection.delete_many({"serial_no": {"$regex": f"^{code_prefix}"}})
                                st.session_state.reset_message = f"💥 선택하신 {target_reset_code} 데이터 초기화 처리가 완벽하게 끝났습니다!"
                            
                            st.session_state.show_qr_grid = False
                            st.session_state.current_view_serials = []
                            st.session_state.reset_success = True
                            st.rerun()
                        else:
                            st.error("⚠️ 상단 '동의합니다' 체크박스를 반드시 체크해야 초기화가 수행됩니다.")
                            
                else:
                    target_single_serial = st.text_input("🆔 삭제 처리할 12자리 시리얼 번호를 정확히 기입하세요 (예: 001060200001)").strip()
                    understand_risk_single = st.checkbox("❗ 기입한 특정 시리얼 툴 데이터를 영구 삭제하는 것에 동의합니다.", key="risk_single")
                    
                    if st.button("❌ 해당 개별 시리얼 넘버 데이터 즉시 삭제", key="btn_single_del"):
                        if not target_single_serial:
                            st.error("⚠️ 시리얼 번호를 입력해 주세요.")
                        elif len(target_single_serial) != 12:
                            st.error("⚠️ 시리얼 번호는 정확히 12자리여야 합니다.")
                        elif not understand_risk_single:
                            st.error("⚠️ 영구 삭제 동의 체크박스를 체크해 주세요.")
                        else:
                            match_count = db_collection.count_documents({"serial_no": target_single_serial})
                            if match_count == 0:
                                st.error(f"❌ 데이터베이스에 `{target_single_serial}` 번호가 존재하지 않습니다. 번호를 다시 확인해 주세요.")
                            else:
                                db_collection.delete_one({"serial_no": target_single_serial})
                                st.session_state.reset_message = f"🎯 지정 시리얼 [`{target_single_serial}`] 데이터가 안전하게 영구 삭제되었습니다!"
                                st.session_state.reset_success = True
                                st.rerun()

    # 2) ⚠️ 실시간 툴 드레싱 알림판
    elif tool_menu == "⚠️ 실시간 툴 드레싱 알림판":
        st.title("⏳ 실시간 툴 드레싱 및 교체 주기 모니터링 (모든 툴 대상)")
        st.write("<br>", unsafe_allow_html=True)
        
        try:
            active_tools = list(db_collection.find({"status": {"$in": ["사용중", "재사용"]}, "target_time": {"$ne": "-"}}))
            if not active_tools:
                st.info("🟢 현재 실시간 드레싱 타이머가 작동 중인 활성 툴이 없습니다.")
            else:
                st.markdown("### 📊 실시간 가동 현황 목록")
                current_now = get_now_kst()
                
                for item in active_tools:
                    target_time_str = item.get("target_time")
                    target_dt = dt_class.strptime(target_time_str, "%Y-%m-%d %H:%M:%S")
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
                                <h4 style="margin: 0; color: #333;">🆔 시리얼: <code style="font-size:18px;">{item['serial_no']}</code> ({item['tool_type']}) — <span style="color:blue;">[{item.get('status', '사용중')}]</span></h4>
                                <p style="margin: 5px 0; font-size: 15px;">
                                    <b>⚙️ 현재 가공 장비:</b> {item['machine_no']} | <b>👷 담당 작업자:</b> {item['worker']} <br>
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
                            st.success(f"🎉 타이머가 현재 시간 기준으로 리셋되었습니다!")
                            st.rerun()
                            
        except Exception as e:
            st.error(f"알림판 연동 오류: {e}")

    # 3) 📂 종합 현황판 창
    elif tool_menu == "📂 전체 데이터 현황판":
        st.title("📂 현장 기입 데이터 통합 현황판")
        st.markdown("현황판에서 각 툴의 데이터를 펼친 뒤, **직접 편집 및 수정**을 진행할 수 있습니다.")
        st.write("<br>", unsafe_allow_html=True)
        
        search_col1, search_col2, search_col3, search_col4 = st.columns([1.5, 1, 1, 1])
        with search_col1:
            status_filter = st.selectbox(
                "🔍 툴 상태별 정렬 필터", 
                ["사용중 🟡 (기본값)", "전체 보기 📂", "사용전(기기대기) 🟢", "재사용 🔵", "재사용대기 🟣", "폐기 🔴"], 
                index=0
            )
        with search_col2:
            keyword_search = st.text_input("🆔 특정 시리얼 넘버 직접 검색", placeholder="예: 010602").strip()
        with search_col3:
            worker_search = st.text_input("👷 작업자 이름으로 검색", placeholder="예: 홍길동").strip()
        with search_col4:
            machine_search = st.text_input("⚙️ 기계 번호(호기)로 검색", placeholder="예: 4호기").strip()

        st.write("<br>", unsafe_allow_html=True)
        
        try:
            all_data = list(db_collection.find({}).sort("serial_no", -1))
            
            if not all_data:
                st.info("조회할 데이터가 없습니다.")
            else:
                filtered_data = []
                
                for item in all_data:
                    item_status = item.get("status", "사용전")
                    
                    if status_filter == "사용중 🟡 (기본값)" and item_status != "사용중":
                        continue
                    elif status_filter == "사용전(기기대기) 🟢" and item_status != "사용전":
                        continue
                    elif status_filter == "재사용 🔵" and item_status != "재사용":
                        continue
                    elif status_filter == "재사용대기 🟣" and item_status != "재사용대기":
                        continue
                    elif status_filter == "폐기 🔴" and item_status != "폐기":
                        continue
                        
                    if keyword_search and keyword_search not in item["serial_no"]:
                        continue
                    if worker_search and worker_search not in item.get("worker", ""):
                        continue
                    if machine_search and machine_search not in item.get("machine_no", ""):
                        continue
                        
                    filtered_data.append(item)

                if not filtered_data:
                    st.warning("🔍 지정하신 검색 조건 및 정렬 기준에 일치하는 툴 데이터가 없습니다.")
                else:
                    st.caption(f"📊 총 **{len(filtered_data)}** 개의 항목이 검색되었습니다.")
                    
                    for item in filtered_data:
                        s_no = item["serial_no"]
                        db_current_status = item.get("status", "사용전")
                        
                        if db_current_status == "사용전": status_badge = "🟢 [사용전]"
                        elif db_current_status == "사용중": status_badge = "🟡 [사용중]"
                        elif db_current_status == "재사용": status_badge = "🔵 [재사용]"
                        elif db_current_status == "재사용대기": status_badge = "🟣 [재사용대기]"
                        else: status_badge = "🔴 [폐기]"
                            
                        spec_info = item.get('detail_spec', '스펙없음') # DB에서 상세스펙을 가져옴
                        
                        if not item.get('worker') or not item.get('machine_no'):
                            expander_title = f"⚪ 기입 대기 | 🆔 {s_no} ({spec_info}) | 상태: {status_badge}"
                        else:
                            expander_title = f"🆔 {s_no} ({spec_info}) | 장비: {item['machine_no']} | 작업자: {item['worker']} | 상태: {status_badge}"
                            
                        with st.expander(expander_title):
                            edit_key = f"is_editing_{s_no}"
                            if edit_key not in st.session_state:
                                st.session_state[edit_key] = False
                                
                            if st.session_state[edit_key]:
                               
                                spec_info = item.get('detail_spec', '스펙없음')
                                st.markdown(f"### ✏️ 시리얼 {s_no} ({spec_info}) 정보 실시간 수정 폼")
                                
                                note_content = str(item.get('note', ''))
                                has_history_log = "상태:" in note_content or "호기" in note_content
                                has_pending_log = "상태: 재사용대기" in note_content
                                
                                if db_current_status == "재사용대기" or (item.get("last_active_machine") and has_history_log):
                                    st.warning(f"⚠️ **이 툴은 이전에 가동되었다가 보관 후 다시 사용하는 [재사용 대상] 툴입니다.** (직전 기계: {item.get('last_active_machine', '-')}, 실적갯수: {item.get('last_active_count', 0)}개)")

                                orig_m = item.get('machine_no', '')
                                orig_m_num = ''.join(filter(str.isdigit, orig_m))
                                
                                if db_current_status in ["사용중", "재사용", "재사용대기", "폐기"]:
                                    def_m_int = 0
                                else:
                                    try:
                                        def_m_int = int(orig_m_num) if orig_m_num else 0
                                    except:
                                        def_m_int = 0

                                db_start_time = item.get("start_time", "-")
                                board_now = get_now_kst()
                                if db_start_time != "-":
                                    try:
                                        parsed_dt = dt_class.strptime(db_start_time, "%Y-%m-%d %H:%M:%S")
                                        init_date = parsed_dt.date()
                                        init_time = parsed_dt.time()
                                    except:
                                        init_date = board_now.date()
                                        init_time = board_now.time()
                                else:
                                    init_date = board_now.date()
                                    init_time = board_now.time()

                                st.markdown("📅 **최초 기계 장착 일시 수정**")
                                col_be_d, col_be_t = st.columns(2)
                                with col_be_d:
                                    ed_date = st.date_input("장착 날짜 변경", value=init_date, key=f"dt_{s_no}")
                                with col_be_t:
                                    ed_time = st.time_input("장착 시간 변경", value=init_time, step=300, key=f"tm_{s_no}")

                                combined_ed_dt = dt_class.combine(ed_date, ed_time)

                                with st.form(key=f"board_edit_form_{s_no}"):
                                    ed_status = st.radio("🔄 툴 상태 변경", ["사용전", "사용중", "재사용", "재사용대기", "폐기"], index=["사용전", "사용중", "재사용", "재사용대기", "폐기"].index(db_current_status) if db_current_status in ["사용전", "사용중", "재사용", "재사용대기", "폐기"] else 0, horizontal=True)
                                    
                                    col_e1, col_e2 = st.columns(2)
                                    with col_e1:
                                        if db_current_status in ["사용중", "재사용", "재사용대기", "폐기"]:
                                            default_worker_view = ""
                                        else:
                                            default_worker_view = item.get('worker', '')
                                        ed_worker = st.text_input("👷 교체 작업자 이름 기입", value=default_worker_view).strip()
                                    with col_e2:
                                        ed_machine_num = st.number_input("⚙️ 기계 가공 호기 (숫자만)", min_value=0, max_value=200, value=def_m_int, key=f"mach_{s_no}")
                                    # 상세 스펙 선택창 추가
                                    st.markdown("🛠 **상세 스펙 선택**")
                                    spec_options = ["파이90-20-200메쉬", "파이100-30-300메쉬", "파이50-10-100메쉬"]
                                    # DB에 저장된 값이 있으면 불러오고, 없으면 리스트의 첫 번째 선택
                                    ed_spec = st.selectbox("상세 스펙을 선택하세요", spec_options, index=0, key=f"spec_{s_no}")     
                                    st.markdown("⏳ **드레싱 주기 커스텀 시간 재설정**")
                                    col_eh, col_em = st.columns(2)
                                    with col_eh:
                                        ed_hours = st.number_input("시간(Hour)", min_value=0, max_value=72, value=0, step=1, key=f"eh_{s_no}")
                                    with col_em:
                                        ed_mins = st.number_input("분(Minute)", min_value=0, max_value=59, value=0, step=5, key=f"em_{s_no}")
                                        
                                    ed_limit = st.number_input("⚙️ Limit 사용 한도 횟수 재설정",min_value=0 ,value=int(item.get('use_limit', 10000)), step=1000, key=f"lim_{s_no}")
                                    ed_note = st.text_area("📝 현장 특이사항", value=item.get('note', ''))
                                    
                                    b_submit = st.form_submit_button("💾 수정사항 최종 저장하기")

                                    # [사용중 툴 폐기 시 경고 및 사유 입력]
                                    if ed_status == "폐기" and db_current_status == "사용중":
                                        st.warning("⚠️ 경고: 현재 [사용중]인 툴을 폐기하려 합니다. 정말 진행하시겠습니까?")
                                        confirm_waste = st.checkbox("위 내용을 확인했으며, 사용 중인 툴을 폐기하겠습니다.", key=f"confirm_{s_no}")
                                        
                                        if confirm_waste:
                                            waste_reason = st.text_input("필수: 폐기 사유를 입력하세요", key=f"reason_{s_no}")
                                            st.session_state[f"temp_reason_{s_no}"] = waste_reason
                                        else:
                                            st.info("폐기를 진행하려면 위 확인란을 체크하세요.")
                                            st.stop()
                                    
                                # PC 종합 통제 엔진 방어막 및 차단기 가동
                                flow_error_msg = ""
                                
                                if db_current_status == "폐기" and ed_status != "폐기":
                                    flow_error_msg = "⚠️ [공정 보안 경고] 이 툴은 이미 최종 '폐기' 처리가 완료된 상태입니다. 폐기 공구를 다시 가동 공정으로 되돌려 재사용하는 것은 안전 및 논리상 절대 불가능합니다!"
                                elif db_current_status == "재사용대기" and ed_status in ["사용전", "사용중"]:
                                    flow_error_msg = "⚠️ [공정 보안 경고] 현재 보관('재사용대기') 중인 툴입니다. 다시 장착하여 재가동할 때는 '사용중'이 아닌 무조건 [재사용] 또는 [폐기] 라디오 버튼만 선택해야 합니다!"
                                elif db_current_status == "사용전" and ed_status in ["재사용", "재사용대기", "폐기"]:
                                    if not (ed_status == "폐기"):
                                        flow_error_msg = f"⚠️ [공정 흐름 오류] 아직 가동된 적 없는 '사용전' 상태의 새 제품입니다. 이치에 맞지 않게 바로 '{ed_status}' 상태로 건너뛸 수 없습니다!"
                                elif db_current_status == "사용중" and ed_status == "재사용":
                                    flow_error_msg = "⚠️ [공정 흐름 오류] 현재 '사용중'인 툴은 바로 '재사용'으로 갈 수 없습니다! 반드시 먼저 '재사용대기'를 선택하여 실적갯수를 기록한 후 보관함에서 꺼낼 때 '재사용' 하는 것입니다."
                                elif db_current_status in ["사용중", "재사용", "재사용대기"] and ed_status == "사용전":
                                    flow_error_msg = "⚠️ [공정 오류] 이미 사용 흔적이 기록된 가동 툴은 라디오 버튼으로 '사용전' 복구가 불가합니다! 이력을 파괴하고 리셋하려면 하단의 [위험 영역: 가동 중단 및 완전 초기화] 기능을 이용하세요."
                               
                                if flow_error_msg and flow_error_msg not in st.session_state.sidebar_errors:
                                    add_error(flow_error_msg)

                                # [최종 수정] 사용전에서 넘어온 '폐기'는 이 차단막을 아예 건드리지 않음
                                if ed_status in ["재사용", "재사용대기"]:
                                    if not has_history_log:
                                        add_error("⚠️ 경고: 특이사항에 과거 가동 이력이 없는 완전히 새 제품 상태의 툴입니다.")
                                        st.stop()
                                
                                    # '폐기'는 이 경고창 로직 자체를 아예 안 타도록 합니다.
                                elif ed_status == "재사용" and has_history_log and not has_pending_log:
                                    st.error("⚠️ 공정 흐름 오류: 특이사항 내역에 '재사용대기'로 전환 보관된 연혁이 발견되지 않았습니다. 대기 이력 없이 바로 '재사용' 상태로 가동할 수 없으니 라디오 버튼을 다시 확인해 주세요.")

                                if b_submit:
                                    # [3단계] 저장 버튼을 눌렀을 때만 폐기 사유 확인
                                    if ed_status == "폐기" and db_current_status in ["사용중", "사용전"]:
                                        if not st.session_state.get(f"temp_reason_{s_no}"):
                                           show_waste_dialog(s_no, item.get('machine_no', ''), ed_note, ed_worker, db_current_status)
                                           st.stop()
                                    
                                    # 새 제품(사용전)일 때 폐기는 경고 예외 처리
                                    if ed_status in ["재사용", "재사용대기", "폐기"] and not has_history_log:
                                        if not (ed_status == "폐기" and db_current_status == "사용전"):
                                            st.error("⚠️ 경고: 특이사항에 과거 가동 이력이 없는 완전히 새 제품 상태의 툴입니다.")
                                            st.stop()

                                    if ed_status == "재사용" and has_history_log and not has_pending_log:
                                        st.stop()

                                    # [2단계: PC 검문소 설치]
                                    is_valid, msg = validate_process(db_current_status, ed_status)
                                    # 사용전 툴 폐기는 검문소 통과
                                    if not is_valid and not (db_current_status == "사용전" and ed_status == "폐기"):
                                        st.error(msg)
                                        st.stop()

                                    if ed_status == "재사용대기":
                                        show_reuse_pending_dialog(s_no, item.get('machine_no',''), ed_note, ed_worker, ed_machine_num, ed_hours, ed_mins)
                                        st.stop()
                                    
                                    if ed_status == "폐기":
                                        if db_current_status in ["사용중", "사용전"]:
                                            reason = st.session_state.get(f"temp_reason_{s_no}")
                                            if db_current_status == "사용전":
                                                ed_note += f"\n[{get_now_kst().strftime('%Y-%m-%d %H:%M:%S')}] 🚨긴급 폐기 사유: {reason} | 장착 기계: 없음"
                                            else:
                                                ed_note += f"\n[{get_now_kst().strftime('%Y-%m-%d %H:%M:%S')}] 🚨긴급 폐기 사유: {reason}"
                                        show_waste_dialog(s_no, item.get('machine_no', ''), ed_note, ed_worker, db_current_status)
                                        st.stop()
                                        
                                    waste_date_val = str(today) if ed_status == "폐기" else item.get("waste_date", "-")
                                    full_mach_name = f"{ed_machine_num}호기"
                                    
                                    total_mins = (ed_hours * 60) + ed_mins
                                    if total_mins > 0 and ed_status in ["사용중", "재사용"]:
                                        start_time_val = combined_ed_dt.strftime("%Y-%m-%d %H:%M:%S")
                                        target_time_val = (combined_ed_dt + timedelta(minutes=total_mins)).strftime("%Y-%m-%d %H:%M:%S")
                                    else:
                                        start_time_val = "-" if ed_status in ["사용전", "재사용대기"] else item.get("start_time", "-")
                                        target_time_val = "-"
                                        
                                    real_now_kst = get_now_kst()
                                    log_time_str = real_now_kst.strftime("%Y-%m-%d %H:%M:%S")

                                    old_spec = item.get('detail_spec', ' ')
                                    if ed_status == item.get('status', '사용전') and old_spec == ed_spec:
                                        final_note_val = ed_note.strip()
                                    else:
                                        log_time_str = real_now_kst.strftime("%Y-%m-%d %H:%M:%S")
                                            # 상태나 스펙이 바뀌었을 때 로그 메시지 생성
                                        change_msg = f" 상태: {ed_status}"
                                        if old_spec != ed_spec:
                                            change_msg += f", (스펙:{old_spec}→{ed_spec})"
                        
                                        auto_log_msg = f"\n[{log_time_str}]{change_msg}, 작업자: {ed_worker}, 기계: {full_mach_name}"
                                        final_note_val = ed_note.strip() + auto_log_msg
                                    db_collection.update_one(
                                        {"serial_no": s_no},
                                        {"$set": {
                                            "status": ed_status,
                                            "worker": "" if ed_status in ["사용전", "폐기"] else ed_worker, 
                                            "machine_no": "" if ed_status in ["사용전", "폐기"] else full_mach_name,
                                            "dressing_hours": ed_hours,
                                            "dressing_mins": ed_mins,
                                            "use_limit": ed_limit,  
                                            "start_time": start_time_val,
                                            "target_time": target_time_val,
                                            "waste_date": waste_date_val,
                                            "note": final_note_val,
                                            "detail_spec": ed_spec
                                        }}
                                    )
                                    st.session_state[edit_key] = False
                                    st.success(f"🎉 데이터와 현장 특이사항 이력이 성공적으로 함께 저장되었습니다.")
                                    time.sleep(0.5)
                                    st.rerun()
                                    
                                # 사용전 완전 복구용 초기화 시스템 배치
                                st.write("<br>", unsafe_allow_html=True)
                                st.markdown("### 🧽 위험 영역: 가동 중단 및 완전 초기화")
                                st.caption("실수로 가동을 시작했거나 정보가 심하게 꼬였을 때, 모든 공정 조치 이력을 파괴하고 최초 큐알 발행 시간 마크만 남긴 채 완전 새 제품 대기 상태로 되돌립니다.")
                                
                                confirm_reset = st.checkbox(f"❗ [{s_no}] 번호의 가동 내역을 파괴하고 최초 발행 마크만 남긴 채 사용전으로 리셋하는 것에 절대 동의합니다.", key=f"risk_reset_{s_no}")
                                if st.button("🗑️ 툴 데이터 가동 내역 완전 초기화 실행", key=f"btn_reset_{s_no}", type="primary"):
                                    if not confirm_reset:
                                        st.error("⚠️ 잘못 누름 방지 승인을 위해 위 동의합니다 체크박스에 먼저 체크해 주세요.")
                                    else:
                                        fresh_data = db_collection.find_one({"serial_no": s_no})
                                        
                                        if fresh_data:
                                            raw_date = fresh_data.get('input_date', str(today))
                                            try:
                                                date_obj = dt_class.strptime(raw_date, "%Y-%m-%d")
                                                formatted_date = date_obj.strftime("%m/%d")
                                            except:
                                                formatted_date = raw_date[-5:].replace("-", "/")
                                                
                                            formatted_time = fresh_data.get('init_time', get_now_kst().strftime("%H:%M"))
                                        else:
                                            formatted_date = get_now_kst().strftime("%m/%d")
                                            formatted_time = get_now_kst().strftime("%H:%M")
                                            
                                        clean_note = f"[{formatted_date} {formatted_time} 발행] 현장 입고일 완료 (수동 강제 공정 초기화 리셋)"
                                            
                                        db_collection.update_one(
                                            {"serial_no": s_no},
                                            {"$set": {
                                                "status": "사용전",
                                                "worker": "",
                                                "machine_no": "",
                                                "dressing_hours": 0,
                                                "dressing_mins": 0,
                                                "start_time": "-",
                                                "target_time": "-",
                                                "waste_date": "-",
                                                "current_use": 0,
                                                "note": clean_note,
                                                "history": [],
                                                "last_active_machine": None,
                                                "last_active_count": None,
                                                "last_active_time": None
                                            }}
                                        )
                                        st.success("💥 최초 발행 년월일 및 시·분 정보까지 완벽하게 보존 리셋되었습니다!")
                                        time.sleep(1)
                                        st.rerun()

                                if st.button("❌ 변경 취소하고 돌아가기", key=f"cancel_{s_no}"):
                                    st.session_state[edit_key] = False
                                    st.rerun()
                                    
                            else:
                                col_x, col_y = st.columns(2)
                                with col_x:
                                    st.write(f"• **💎 툴 종류:** {item.get('tool_type', '-')}")
                                    st.write(f"• **📅 최초 발행일:** {item.get('input_date', '-')}")
                                    st.write(f"• **📅 최초 장착 시간:** {item.get('start_time', '-')}")
                                    st.write(f"• **👷 교체 작업자:** {item.get('worker') if item.get('worker') else '-'}")
                                    if item.get("status") == "폐기":
                                        st.write(f"• **🗑️ 폐기 일시:** {item.get('waste_date', '-')}")
                                with col_y:
                                    East_mach = item.get('machine_no') if item.get('machine_no') else '-'
                                    st.write(f"• **⚙️ 기계 가공 호기:** {East_mach}")
                                    st.write(f"• **⏳ 설정된 드레싱 주기:** {item.get('dressing_hours', 0)}시간 {item.get('dressing_mins', 0)}분")
                                    st.write(f"• **⚙️ 설정된 사용 한도 횟수 (Limit):** {int(item.get('use_limit', 10000))} 회")
                                    st.write(f"• **🎯 다음 마감 시간:** {item.get('target_time', '-')}")
                                st.write(f"• **📝 현장 특이 사항:** {item.get('note', '')}")
                                
                                if st.button("✏️ 이 툴 정보 직접 수정하기", key=f"btn_edit_{s_no}", type="secondary"):
                                    st.session_state[edit_key] = True
                                    st.rerun()
                                
        except Exception as e:
            st.error(f"데이터 로드 실패: {e}")

    # 4) 데이터 수정 / 삭제 / QR 재발행 창
    elif tool_menu == "⚙️ 데이터 수정 / 삭제 / QR 재발행":
        st.title("⚙️ 툴 데이터 관리 및 누락 QR코드 재발행")
        st.write("<br>", unsafe_allow_html=True)
        
        st.subheader("🖨️ 누락 / 분실 QR코드 타겟 재발행")
        target_serial = st.text_input("🆔 재발행할 12자리 시리얼 번호를 정확히 입력하세요").strip()
        
        if target_serial:
            if len(target_serial) != 12:
                st.warning("⚠️ 시리얼 넘버는 정확히 12자리 규격이어야 합니다.")
            else:
                exist_item = db_collection.find_one({"serial_no": target_serial})
                
                if exist_item:
                    st.success(f"🔍 확인결과: 데이터베이스에 기존 데이터가 존재하는 툴입니다.")
                    
                    qr_res_bytes = generate_app_qr_bytes(target_serial)
                    base64_qr = base64.b64encode(qr_res_bytes).decode("utf-8")
                    
                    st.image(qr_res_bytes, width=180, caption=f"재발행 넘버: {target_serial}")
                    
                    html_content = f"""
                    <div style="text-align: center; border: 1px dashed #ccc; padding: 20px; width: 200px;">
                        <img src="data:image/png;base64,{base64_qr}" style="width: 150px; height: 150px;" />
                        <div style="font-family: monospace; font-size: 14px; font-weight: bold; margin-top: 10px;">ID: {target_serial}</div>
                    </div>
                    """
                    
                    # [최종 수정] 팝업 없는 직접 인쇄 버튼
                    if st.button("🖨️ 이 QR코드 인쇄하기"):
                        print_body = f"""
                        <div id='print-area' style='text-align: center; border: 1px dashed #ccc; padding: 20px; width: 200px;'>
                            <img src="data:image/png;base64,{base64_qr}" style="width: 150px; height: 150px;" />
                            <div style="font-family: monospace; font-size: 14px; font-weight: bold; margin-top: 10px;">ID: {target_serial}</div>
                        </div>
                        <style>
                            @media print {{
                                body * {{ visibility: hidden; }}
                                #print-area, #print-area * {{ visibility: visible; }}
                                #print-area {{ position: absolute; left: 0; top: 0; }}
                            }}
                        </style>
                        """
                        st.components.v1.html(f"""
                            {print_body}
                            <script>
                                setTimeout(function() {{ window.print(); }}, 500);
                            </script>
                        """, height=0)

                else:
                    st.error(f"❌ 확인결과: 데이터베이스에 존재하지 않는 완전히 누락된 새로운 번호입니다.")
                    if st.button(f"➕ 누락번호 `{target_serial}` 신규 생성 및 QR 발행"):
                        t_code = target_serial[:3]
                        new_blank = {
                            "serial_no": target_serial,
                            "tool_type": "전착툴" if t_code=="1" else "레진툴" if t_code=="2" else "메탈툴" if t_code=="2"else "코어툴",
                            "status": "사용전",
                            "input_date": str(today),
                            "init_time": get_now_kst().strftime("%H:%M"),
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
                        st.success(f"🎉 누락된 번호 `{target_serial}` 가 DB에 생성되었습니다. 다시 입력하여 확인해 주세요.")
                        st.rerun()

    # 5) 🖥️ 실시간 기계 정보창 (Grid Layout)
    elif tool_menu == "🖥️ 실시간 기계 정보창":
            st.title("🖥️ 실시간 기계 배치 및 툴 상세 현황")
            now_kst = get_now_kst()
            st.write(f"⏰ **현재 기준 시간:** {now_kst.strftime('%Y-%m-%d %H:%M:%S')}")
            
            layout = [
                [27, 28, 29, 30, 31, 9, 8, 7],
                [16, 17, 26, 32, 57],
                [15, 18, 25, 33, 56],
                [14, 19, 24, 34, 55, 6],
                [13, 20, 35, 54, 5],
                [12, 21, 36, 53, 4],
                [11, 22, 37, 52, 3],
                [10, 23, 38, 43],
                [39, 40, 41, 42],
                [44, 45, 46, 47, 48, 49, 50, 51]
            ]
          



            # 1187번 줄부터 마지막까지 덮어쓰기
            active_tools = list(db_collection.find({"status": {"$in": ["사용중", "재사용"]}}))
            machine_tool_map = {}
            for t in active_tools:
                nums = re.findall(r'\d+', str(t.get('machine_no', '')))
                if nums:
                    m_no = int(nums[0])
                    if m_no not in machine_tool_map: machine_tool_map[m_no] = []
                    machine_tool_map[m_no].append(t)

            for row in layout:
                cols = st.columns(len(row))
                for i, m_no in enumerate(row):
                    with cols[i]:
                        tools = machine_tool_map.get(m_no, [])
                        
                        # 컨테이너 높이를 160으로 늘려 충분한 공간 확보
                        with st.container(border=True, height=160):
                            st.markdown(f"<div style='font-weight:bold; color:black;'>{m_no}호기</div>", unsafe_allow_html=True)
                            
                            if tools:
                                for t in tools:
                                    elapsed = get_elapsed_time_str(t.get('start_time'))
                                    # 모든 정보를 한 줄씩 깔끔하게 카드 내부에 배치
                                    st.markdown(f"""
                                    <div style='font-size:9px; color:black; line-height:1.2; margin-top:2px;'>
                                        <b>ID:</b> {t.get('serial_no', 'N/A')}<br>
                                        <b>작업자:</b> {t.get('worker', '미지정')}<br>
                                        <b>장착:</b> {str(t.get('start_time', '-'))[5:16]}<br>
                                        <span style='color:red;'>{elapsed}</span>
                                    </div>
                                    """, unsafe_allow_html=True)
                            else:
                                st.markdown("<div style='color:black; font-size:11px;'>대기중</div>", unsafe_allow_html=True)
