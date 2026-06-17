import streamlit as st
from pymongo import MongoClient
import datetime  # 기존 코드에서 datetime.datetime.utcnow() 등을 썼다면 필요합니다.
from datetime import datetime as dt, timedelta
import pandas as pd
import re
import time
import base64
from io import BytesIO
import qrcode
dt_class = dt
import datetime  # 이렇게 불러와야 datetime.datetime 으로 접근 가능합니다.
from datetime import timedelta
import pytz
st.cache_data.clear()


# [2단계] 팝업창을 호출하는 함수 정의------------------------------------------------

@st.dialog("상세 스펙 변경 확인")
def confirm_mobile_spec_change(new_spec, serial_no):
    st.write(f"정말로 스펙을 **{new_spec}**(으)로 변경하시겠습니까?")
    
    if st.button("확정"):
        # 1. DB 업데이트
        db_collection.update_one(
            {"serial_no": serial_no},
            {"$set": {"spec_detail": new_spec}}
        )
        st.session_state['new_spec'] = new_spec
        # 2. [핵심] 토글 스위치 상태를 강제로 꺼짐(False)으로 변경
        st.session_state["mobile_edit_mode"] = False 
        
        st.success("스펙이 변경되었습니다!")
        st.rerun() # 새로고침하면 토글이 꺼진 상태로 나타남
        
    if st.button("취소"):
        st.rerun()




#실시간 기계정보창 호출부---------------------------------------------------------------------------------------------------------------
@st.fragment(run_every="60s")
def show_machine_dashboard():
    st.title("🖥 실시간 기계 배치 및 툴 상세 현황")
    if st.button("🔄 실시간 정보 즉시 갱신"):
        st.rerun()
    now_kst = get_now_kst()
    st.write(f"**현재 기준 시간:** {now_kst.strftime('%Y-%m-%d %H:%M')}")
    # 1. 레이아웃 및 데이터 매핑 (기존 기능 유지)
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

    active_tools = list(db_collection.find({"status": {"$in": ["사용중", "재사용"]}}))
    machine_tool_map = {int(re.findall(r'\d+', str(t.get('machine_no', '')))[0]): [t] 
                        for t in active_tools if re.findall(r'\d+', str(t.get('machine_no', '')))}

    for row in layout:
        cols = st.columns(len(row))
        for i, m_no in enumerate(row):
            with cols[i]:
                st.markdown(f"**{m_no}호기**")
                if m_no in machine_tool_map:
                    for item in machine_tool_map[m_no]:
                        color, label, text = get_status_info(item, now_kst)
                        db_status = item.get('status', '사용중') # DB에 있는 진짜 상태값을 가져옴
                        render_tool_ui(item, "none", "none", db_status)
                        if st.button("📝 상세/수정", key=f"btn_edit_{item['serial_no']}"):
                            st.session_state.edit_serial = item['serial_no']
                            st.rerun()
                else:
                    st.info("비어있음")

    # 2. 상세 수정창 (데이터 로딩 및 관리)
    if 'edit_serial' in st.session_state and st.session_state.edit_serial:
        ctx_key = st.session_state.edit_serial
        st.divider()
        
        # 닫기 버튼
        if st.button("❌ 닫기 (상세 창 닫기)", key=f"close_{ctx_key}"):
            st.session_state.edit_serial = None
            st.rerun()

        st.subheader(f"🛠 툴 정보 및 연혁 관리: {ctx_key}")
        target_tool = db_collection.find_one({"serial_no": ctx_key})
        
        if target_tool:
            with st.form("edit_basic_info"):
                col1, col2 = st.columns(2)
                new_machine = col1.text_input("기계 번호", value=target_tool.get('machine_no', ''))
                new_worker = col2.text_input("담당 작업자", value=target_tool.get('worker', ''))
                
                # [수정] 드레싱 주기 입력창
                col_h, col_m = st.columns(2)
                new_hours = col_h.number_input("드레싱 시간(Hour)", min_value=0, value=int(target_tool.get('dressing_hours', 0)))
                new_mins = col_m.number_input("드레싱 분(Minute)", min_value=0, max_value=59, value=int(target_tool.get('dressing_mins', 0)))
                
                if st.form_submit_button("💾 기본 정보 저장"):
                    old_machine = target_tool.get('machine_no', '')
                    old_worker = target_tool.get('worker', '')
                    
                    # 로그 기록
                    timestamp = dt.now().strftime('%Y-%m-%d %H:%M')
                    log_msg = f"\n[{timestamp}] 기계:{old_machine}→{new_machine} / 작업자:{old_worker}→{new_worker} / 주기:{new_hours}h {new_mins}m 변경(타이머 리셋)".format(timestamp)
                    updated_note = (target_tool.get('note', '') + log_msg).strip()
                    
                    # [핵심] 현재 시간 기준으로 마감 시간(target_time) 재계산
                    click_now = get_now_kst()
                    new_start = click_now.strftime("%Y-%m-%d %H:%M:%S")
                    new_target = (click_now + timedelta(hours=int(new_hours), minutes=int(new_mins))).strftime("%Y-%m-%d %H:%M:%S")
                    
                    db_collection.update_one(
                        {"serial_no": ctx_key},
                        {"$set": {
                            "machine_no": new_machine, 
                            "worker": new_worker, 
                            "dressing_hours": new_hours, 
                            "dressing_mins": new_mins,
                            "start_time": new_start,   # 시작 시간도 변경 시점으로 갱신
                            "target_time": new_target, # 마감 시간 재계산 반영
                            "note": updated_note
                        }}
                    )
                    st.success("정보가 저장되었으며, 타이머가 현재 시간 기준으로 리셋되었습니다!")
                    st.rerun()

            # 연혁 데이터 편집
            st.write("#### 📜 연혁 데이터 (기록 관리)")
            raw_note = target_tool.get("note", "")
            df = pd.DataFrame(raw_note.split('\n') if raw_note else ["기록 없음"], columns=["연혁 및 기록 내용"])
            edited_df = st.data_editor(df, use_container_width=True, num_rows="dynamic", key=f"ed_{ctx_key}")
            
            if st.button("💾 연혁 전체 저장", key=f"save_{ctx_key}"):
                db_collection.update_one(
                    {"serial_no": ctx_key},
                    {"$set": {"note": "\n".join(edited_df["연혁 및 기록 내용"].tolist())}}
                )
                st.success("연혁이 업데이트되었습니다!")
                st.rerun()





# 실시간 툴드레싱 알림판 show_live_dashboard() 호출부---------------------------------------------------------
@st.fragment(run_every="60s")
def show_live_dashboard():
    """60초마다 자동 새로고침되는 실시간 알림판 대시보드"""
    active_tools = list(db_collection.find({"status": {"$in": ["사용중", "재사용"]}, "target_time": {"$ne": "-"}}))
    
    if not active_tools:
        st.info("🟢 현재 실시간 드레싱 타이머가 작동 중인 활성 툴이 없습니다.")
        return

    st.markdown("### 📊 실시간 가동 현황 목록")
    current_now = get_now_kst()
    
    for item in active_tools:
        target_time_str = item.get("target_time")
        try:
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
            st.error(f"아이템 렌더링 오류: {e}")


# thr.py 파일 내부
def get_status_info(item, current_now):
    """툴 상태 정보를 계산하는 함수"""
    try:
        # DB의 target_time 값을 가져옵니다.
        target_time_str = item.get("target_time")
        
        # 값이 없거나 '-' 이면 바로 "상태 정보 없음" 반환
        if not target_time_str or target_time_str == "-":
            return "#808080", "상태 정보 없음", "-"
            
        # 시간 문자열을 datetime 객체로 변환
        target_dt = datetime.datetime.strptime(target_time_str, "%Y-%m-%d %H:%M:%S")
        
        # 시간 차이 계산
        time_diff = target_dt - current_now
        total_seconds = time_diff.total_seconds()

        # 상태 판단 로직
        if total_seconds < 0:
            return "#FF4B4B", "※ 드레싱/교체 필요 ※", f"⚠️ {int(abs(total_seconds)//3600)}시간 지남"
        elif total_seconds <= 3600:
            return "#FFAA00", "※ 주의(임박) ※", f"⏳ 약 {int(total_seconds // 60)}분 남음"
        else:
            hours = int(total_seconds // 3600)
            mins = int((total_seconds % 3600) // 60)
            return "#008850", "※ 정상 가동 중 ※", f"⏱️ {hours}시간 {mins}분 남음"
    except Exception as e:
        return "#808080", "형식 오류", "-"




def get_remaining_time(target_time_str):
    # 1. 값이 없으면 바로 탈출
    if not target_time_str:
        return "-"
    
    try:
        # 2. 데이터 형식 강제 변환 (시간대 정보가 있다면 제거)
        target_str = str(target_time_str).strip()
        target_dt = datetime.datetime.strptime(target_str, "%Y-%m-%d %H:%M:%S")
        
        # 3. 시간대 정보가 없는 순수 시간과 비교 (오프셋 에러 방지)
        now = datetime.datetime.now().replace(tzinfo=None)
        
        delta = target_dt - now
        
        # 4. 시간 계산
        if delta.total_seconds() <= 0:
            return "시간 초과"
        
        total_seconds = int(delta.total_seconds())
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        
        return f"{hours}시간 {minutes}분 {seconds}초 남음"
    except Exception as e:
        # 에러가 나도 죽지 않게 함
        return "형식 확인 필요"
    

def get_tool_type_name(serial_no):
    """시리얼 번호 첫 글자로 툴 타입을 반환하는 함수"""
    if not serial_no or len(serial_no) == 0: return "알수없음"
    mapping = {"1": "전착", "2": "레진", "3": "메탈", "4": "코어"}
    return mapping.get(serial_no[0], "기타")

def render_tool_ui(item, color_hex, status_label, db_status):
    """
    모든 화면에서 동일한 기준(KST)으로 시간과 상태를 계산하여 출력합니다.
    외부에서 인자를 넘겨줄 필요 없이, item(DB 데이터)을 바탕으로 직접 계산합니다.
    """
    # 1. 전역 한국 시간 기준으로 현재 시간 확보
    now = get_now_kst()
    
    # 2. 공통 계산 함수 호출 (색상, 상태라벨, 남은시간 텍스트를 한 번에 가져옴)
    color, status_label, time_text = get_status_info(item, now)
    
    # 3. 툴 기본 정보 가져오기
    tool_type = get_tool_type_name(item.get('serial_no', ''))
    worker_name = item.get('worker', '-')
    # db_status는 인자로 전달받은 값을 그대로 활용
    
    # 4. HTML 기반 UI 출력
    # (주의: 인자로 전달된 color_hex 대신, 위에서 계산된 color 변수를 사용해야 시간이 일치합니다.)
    st.markdown(f"""
    <div style="padding: 10px; border-radius: 8px; border-left: 6px solid {color}; background-color: #f9f9f9; margin-bottom: 5px;">
        <h4 style="margin: 0; font-size: 15px;">🆔 {item.get('serial_no')}</h4>
        <div style="font-size: 14px; font-weight: bold; color: #222; margin: 5px 0;">
            [{db_status}] | <span style="color: {color};">{status_label}</span>
        </div>
        <div style="font-size: 13px; font-weight: bold; color: #444;">
            [{tool_type}툴]
        </div>
        <div style="font-size: 13px; color: #333; margin-top: 2px;">
            👤 <b>작업자:</b> {worker_name}
        </div>
        <div style="font-size: 12px; color: #666; margin-top: 2px;">
            🛠 {item.get('detail_spec', '-')}
        </div>
        <hr style="margin: 5px 0;">
        <div style="font-size: 13px; font-weight: bold; color: #d9534f; text-align: center;">
            ⏳ {time_text}
        </div>
    </div>
    """, unsafe_allow_html=True)


def get_spec_master_collection():
    mongo_uri = st.secrets["database"]["MONGO_URI"]
    try:
        client = MongoClient(mongo_uri)
        return client["dashboard_db"]["tool_specs_master"] # <- 여기서 정확히 지정 중!
    except:
        return None
    
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
        if not start_time_val or start_time_val == "-":
            return ""
        
        start_dt = dt_class.strptime(str(start_time_val), "%Y-%m-%d %H:%M:%S")
        
        # [핵심 수정] 여기서 직접 계산하지 말고 위에서 정의한 함수를 호출하세요!
        now_kst = get_now_kst() 
        diff = now_kst - start_dt
        
        # ... 이하 동일 ...
        
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
db_inventory = db_collection.database["tool_inventory"]

# --- [공정 흐름 제어 검문소] ---
def validate_process(current_status, next_status):
    # 예외 허용: 사용전 상태라도 다음이 폐기이고, 나중에 사유가 들어올 것이라면 일단 통과
    if current_status == "사용전" and next_status == "폐기":
        return True, ""
        
    allowed = {
        "사용전": ["사용중"],
        "사용중": ["사용중","재사용대기", "폐기"],
        "재사용대기": ["재사용", "폐기"],
        "재사용": ["재사용대기", "폐기"],
        "폐기": []
    }
    if current_status in allowed and next_status not in allowed[current_status]:
        return False, f"⚠️ 공정 오류: {current_status} 상태에서는 {next_status}로 이동할 수 없습니다."
    return True, ""

# 🕒 한국 시간(KST) 전역 강제 설정 함수
def get_now_kst():
    
    return datetime.datetime.now(pytz.timezone('Asia/Seoul')).replace(tzinfo=None)

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
def show_reuse_pending_dialog(s_no, current_mach, orig_note, ed_worker, ed_machine_num, ed_hours, ed_mins,ed_spec):
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
        auto_log_msg = f"\n[{log_time_str}] 상태: 재사용대기, (스펙: {ed_spec}), 작업자: {pop_worker_name}, 가공기계: {pop_mach_name}, 가공갯수: {pop_count}개"
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
                "current_use": pop_count,
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
        
        
        auto_log_msg = f"\n[{log_time_str}] 상태: 폐기, 작업자: {pop_worker_name}, 스펙: {spec}, 가공기계: {pop_mach_name}, 사용갯수: {pop_use_count}개, 폐기사유: {final_reason_text}"
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
                "current_use": pop_use_count,
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



# --- 📱 [모바일/현장 QR 스캔 기입 모드] --------------------------------------------------------------------------------------------------------

# [최종 확인 팝업창 - 상태 대조 기능 포함]
@st.dialog("💾 데이터 최종 확인")
def confirm_and_save(serial, data):
    # 1. 상태 대조 및 강조 로직
    if data['status'] != data['prev_status']:
        if data['status'] == "폐기":
            st.error(f"⚠️ 경고: [ {data['prev_status']} ] ➔ [ {data['status']} ] (으)로 변경합니다!")
        else:
            st.warning(f"🔄 알림: [ {data['prev_status']} ] ➔ [ {data['status']} ] (으)로 상태가 변경됩니다.")
    else:
        st.info(f"현재 상태 유지: [ {data['status']} ]")

    st.markdown("---")
    # 2. 요약 정보
    st.write(f"- **작업자:** {data['worker']}")
    st.write(f"- **기계 호기:** {data['machine_no']}")
    st.write(f"- **세부 스펙:** {data['detail_spec']}")
    st.write(f"- **설정 주기:** {data['dressing_hours']}시간 {data['dressing_mins']}분")
    
    qty = 0
    if data['status'] in ["폐기", "재사용대기"]:
        qty = st.number_input("📦 최종 가공 수량(개)", min_value=0, value=0, step=1)
        
    if st.button("✅ 최종 확정 및 저장"):
        final_note = data['note']
        if data['status'] != data['prev_status']:
            now_str = get_now_kst().strftime("%Y-%m-%d %H:%M:%S")
            log = f"\n[{now_str}] 상태:{data['status']}, 스펙:{data['detail_spec']}, 작업자:{data['worker']}, 기계:{data['machine_no']}"
            if qty > 0: log += f", 최종수량:{qty}개"
            final_note += log
            
        db_collection.update_one(
            {"serial_no": serial},
            {"$set": {
                "status": data['status'],
                "worker": "" if data['status'] in ["사용전", "폐기"] else data['worker'],
                "machine_no": "" if data['status'] in ["사용전", "폐기"] else data['machine_no'],
                "dressing_hours": data['dressing_hours'],
                "dressing_mins": data['dressing_mins'],
                "note": final_note,
                "detail_spec": data['detail_spec'],
                "start_time": data['start_time'],
                "target_time": data['target_time']
            }},
            upsert=True
        )
        st.toast("✅ 저장 완료되었습니다!", icon="🎉")
        time.sleep(1.5)
        st.rerun()


# --- 📱 [모바일/현장 QR 스캔 기입 모드] ---
if qr_scanned_serial:
    st.title("📱 현장 툴 정보 즉시 기입창")
    st.subheader(f"🆔 시리얼 넘버: `{qr_scanned_serial}`")
    
    existing_data = db_collection.find_one({"serial_no": qr_scanned_serial}) or {}
    
    # 1. 상세 스펙 확인 방어막 (이 로직이 가장 먼저 실행되어야 합니다)
    if not existing_data.get('spec_detail'):
        st.warning("🚨 상세 스펙이 등록되지 않은 툴입니다. 아래에서 먼저 선택해주세요.")
        
        # 시리얼로 툴 타입 파싱
        prefix = qr_scanned_serial[0]
        type_map = {'1': 'JUN', '2': 'REJ', '3': 'MET', '4': 'COR'}
        tool_type = type_map.get(prefix)
        
        # inventory에서 스펙 가져오기
        specs = list(db_inventory.find({"tool_type": tool_type}))

                
        # 스펙 선택 버튼 루프 부분
        for s in specs:
            # 버튼 클릭 시 동작
            if st.button(f"🛠 선택: {s.get('spec_detail', '정보없음')}", key=f"btn_{s.get('spec_detail')}"):
                # 1. DB 업데이트 (필드명 'spec_detail' 확인!)
                db_collection.update_one(
                    {"serial_no": qr_scanned_serial},
                    {"$set": {"spec_detail": s.get('spec_detail')}}
                )
                # 2. 강제 새로고침
                st.toast("✅ 스펙이 저장되었습니다!", icon="🎉")
                time.sleep(0.5) # 잠시 대기
                st.rerun() # 새로고침되어 기입창으로 진입

        st.stop()        

    # 2. 상세 스펙이 채워져 있을 때만 실행되는 기입창 코드
    prev_status = existing_data.get("status", "사용전")
    
    st.markdown("### 🔄 툴 현재 상태")
    status_options = ["사용전", "사용중", "재사용", "재사용대기", "폐기"]
    idx = status_options.index(prev_status) if prev_status in status_options else 0
    u_status = st.radio("상태를 선택하세요", status_options, index=idx, horizontal=True)
    
    st.divider()
    
    st.markdown("### 📝 기본 정보")
    u_worker = st.text_input("👷 교체 작업자 이름", value=existing_data.get('worker', ''))
    
    orig_mach = existing_data.get('machine_no', '')
    default_mach = int(''.join(filter(str.isdigit, orig_mach))) if any(c.isdigit() for c in orig_mach) else 0
    u_machine = st.number_input("⚙️ 기계 가공 호기", value=default_mach)
    
    # 수정된 스펙 선택 UI (이제 이미 값이 채워져 있으므로 선택지 기본값으로 활용)
    spec_opts = [s['spec_name'] for s in list(get_spec_master_collection().find({}))] or ["스펙없음"]
    current_spec = existing_data.get('spec.detail')
   
    
    # [수정된 1단계] 시리얼 앞자리에 따라 분류 필터링
    st.markdown("### 🛠 상세 스펙 확인 및 수정")
    edit_mode = st.toggle("스펙 수정 모드 켜기", key="mobile_edit_mode")

    # 1. 시리얼 첫 글자로 분류 매칭 (전착=1, 레진=2, 메탈=3, 코어=4)
    type_map = {'1': 'JUN', '2': 'REJ', '3': 'MET', '4': 'COR'}
    first_char = qr_scanned_serial[0] if qr_scanned_serial else ''
    target_type = type_map.get(first_char)

    # 2. 분류에 맞는 스펙만 필터링해서 가져오기
    # tool_inventory 컬렉션에서 'tool_type' 필드가 target_type과 일치하는 것만 찾음
    query = {"tool_type": target_type} if target_type else {}
    spec_master_list = list(db_collection.database["tool_inventory"].find(query))
    spec_opts = [s.get('spec_detail') for s in spec_master_list if s.get('spec_detail')]

    # 중복 제거
    spec_opts = sorted(list(set(spec_opts)))

    # 3. 현재 저장된 값 불러오기
    current_spec = st.session_state.get('new_spec', existing_data.get('spec_detail', '스펙없음'))

    if not edit_mode:
        st.info(f"현재 등록된 스펙: **{current_spec}**")
        u_spec = current_spec 
    else:
        u_spec = st.selectbox("변경할 스펙 선택", spec_opts, index=idx)

    
    st.divider()
    
    st.markdown("### ⏳ 드레싱 및 특이사항")
    c1, c2 = st.columns(2)
    u_h = c1.number_input("시간(Hour)", value=existing_data.get('dressing_hours', 0))
    u_m = c2.number_input("분(Minute)", value=existing_data.get('dressing_mins', 0))
    u_note = st.text_area("📝 현장 특이사항", value=existing_data.get('note', ''))
    
    

    # 1. 수정 모드일 때: [스펙 교체하기] 버튼 따로 생성
    # [하단부: 3단계 버튼 로직]
    if edit_mode:
        # 수정 모드일 때는 교체 버튼만 보임
        if st.button("🔄 상세 스펙 교체하기"):
            confirm_mobile_spec_change(u_spec, qr_scanned_serial)
    else:
        # 수정 모드가 아닐 때는 일반 저장 버튼 보임
        if st.button("💾 데이터 확인 및 저장"):
            confirm_data = {
                'status': u_status, 'prev_status': prev_status, 'worker': u_worker,
                'machine_no': f'{u_machine}호기', 'detail_spec': u_spec,
                'dressing_hours': u_h, 'dressing_mins': u_m, 'note': u_note,
                'start_time': get_now_kst().strftime('%Y-%m-%d %H:%M:%S'),
                'target_time': (get_now_kst() + timedelta(minutes=-(u_h * 60) + u_m)).strftime('%Y-%m-%d %H:%M:%S')
            }
            confirm_and_save(qr_scanned_serial, confirm_data)
            st.success("데이터가 저장되었습니다!")
            st.rerun()
    if st.button("🏠 메인으로 돌아가기"):
        st.query_params.clear(); st.rerun()

# --- 💻 [PC 관리자 모드] -----------------------------------------------------------------------------------------------------------------------------
else:
    st.session_state.sidebar_errors = []
    st.sidebar.markdown("## 📁 KKQ 통합 시스템")
    menu_options = ["📊 빈데이터 QR코드 대량 선발행", "⚠️ 실시간 툴 드레싱 알림판", "📂 전체 데이터 현황판", "⚙️ 데이터 수정 / 삭제 / QR 재발행", "🖥️ 실시간 기계 정보창","🔧 툴 상세스펙 마스터 관리"]
    if "sidebar_choice" not in st.session_state:
        st.session_state.sidebar_choice = menu_options[0]
        
    tool_menu = st.sidebar.radio("하위 목록", menu_options, key="sidebar_choice")
    
    # 1) QR코드 대량 연속 선발행 창
    if tool_menu == "📊 빈데이터 QR코드 대량 선발행":
        st.title("🖨️ 현장 부착용 빈데이터 QR코드 대량 연속 발행 (5자리 순번 버전)")
        st.write("<br>", unsafe_allow_html=True)
        
        c1, c2 = st.columns(2)
        with c1:
            tool_code = st.text_input("🆔 고유넘버 앞 1자리 입력 (전착:1 / 레진:2 / 메탈:3 / 코어:4)", value="1", max_chars=3)
        with c2:
            quantity = st.number_input("📦 발행할 QR코드 갯수", min_value=1, max_value=100, value=50, step=1)
        yyyymmdd = today.strftime("%Y%m%d")    
        prefix = f"{tool_code}{yyyymmdd}"
        
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
            display_yyyymmdd_hhmm = fixed_now_kst.strftime("%Y-%m-%d %H:%M")
            
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
                    "note": f"[{display_yyyymmdd_hhmm} 발행] 현장 입고일 완료 (현장 기입 대기)"
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
            
            # 1. 인쇄용 HTML 데이터 준비
            serials_to_print = st.session_state.current_view_serials
            html_content = ""
            
            for s_no in serials_to_print:
                qr_bytes = generate_app_qr_bytes(s_no)
                base64_qr = base64.b64encode(qr_bytes).decode("utf-8")
                html_content += f"""
                <div class='qr-item'>
                    <img src="data:image/png;base64,{base64_qr}">
                    <span>{s_no}</span>
                </div>
                """

            # 2. 인쇄 버튼 스크립트
            print_script = f"""
            <button onclick="
                var printWindow = window.open('', '_blank');
                var style = `<style>
                    @page {{ size: 29mm 90mm; margin: 0; }} 
                    body {{ margin: 0; padding: 0; }}
                    .label-page {{ width: 29mm; height: 85mm; display: flex; flex-direction: column; align-items: center; justify-content: space-evenly; page-break-after: always; }}
                    .qr-item {{ display: flex; flex-direction: column; align-items: center; margin-bottom: 5px; }}
                    img {{ width: 20mm !important; height: 20mm !important; display: block; }}
                    span {{ font-size: 8px; font-family: monospace; margin-top: 1px; }}
                </style>`;
                printWindow.document.write('<html><head>' + style + '</head><body></body></html>');
                setTimeout(function() {{
                    var body = printWindow.document.body;
                    var items = document.getElementById('print-area').getElementsByClassName('qr-item');
                    for (var i = 0; i < items.length; i += 3) {{
                        var pageDiv = document.createElement('div');
                        pageDiv.className = 'label-page';
                        for (var j = i; j < i + 3 && j < items.length; j++) {{ pageDiv.appendChild(items[j].cloneNode(true)); }}
                        body.appendChild(pageDiv);
                    }}
                    printWindow.document.close();
                    printWindow.print();
                }}, 500);
            " style="padding: 15px; font-size: 16px; cursor: pointer; color: white; background-color: #000; border: none; border-radius: 8px; font-weight: bold;">
                🖨️ 해당 QR코드 인쇄하기
            </button>
            <div style='display:none;' id='print-area'>{html_content}</div>
            """
            
            # ★ 여기서 버튼 먼저 띄우기
            st.components.v1.html(print_script, height=70)
            
            # 3. 화면용 그리드 표시
            st.write("<br><h5>발행된 QR 목록:</h5>", unsafe_allow_html=True)
            grid_cols = st.columns(4)
            for idx, s_no in enumerate(serials_to_print):
                with grid_cols[idx % 4]:
                    st.image(generate_app_qr_bytes(s_no), width=80)
                    st.markdown(f"**🆔 {s_no}**")

            if st.button("❌ 인쇄 완료 - 화면에서 목록 지우기"):
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



    

    # 2) ⚠️ 실시간 툴 드레싱 알림판 메뉴 호출부 (이 부분만 교체하세요)
    elif tool_menu == "⚠️ 실시간 툴 드레싱 알림판":
        st.title("⏳ 실시간 툴 드레싱 및 교체 주기 모니터링")
        st.write("<br>", unsafe_allow_html=True)
        
        # 60초마다 자동 갱신되는 대시보드 함수 호출
        show_live_dashboard()



    # 3) 📂 종합 현황판 창---------------------------------------------------------------------------------------------------------------------------~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
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
                            
                        spec_info = item.get('spec_detail', '스펙없음') # DB에서 상세스펙을 가져옴
                        
                                                # [수정된 부분]
                        # 기입 대기 라벨을 붙이기 전에 상태가 '폐기'인지 먼저 체크합니다.
                        if db_current_status == "폐기":
                            expander_title = f"🔴 [폐기] | 🆔 {s_no} ({spec_info}) | 정보: 이 시리얼 넘버의 TOOL은 사용이 완료된 툴입니다..!"
                        elif not item.get('worker') or not item.get('machine_no'):
                            expander_title = f"⚪ 기입 대기 | 🆔 {s_no} ({spec_info}) | 상태: {status_badge}"
                        else:
                            expander_title = f"🆔 {s_no} ({spec_info}) | 장비: {item['machine_no']} | 작업자: {item['worker']} | 상태: {status_badge}"
                            
                        with st.expander(expander_title):
                            # --- 1. 수정 모드 키 생성 및 토글 (Expander 시작점) ---
                            edit_key = f"pc_edit_mode_{s_no}"
                            if edit_key not in st.session_state:
                                st.session_state[edit_key] = False
                            
                            st.session_state[edit_key] = st.toggle("스펙 수정 모드 켜기", key=f"toggle_{s_no}")

                            # --- 2. 읽기 모드 / 수정 모드 분기 ---
                            if not st.session_state[edit_key]:
                                # 평소: 세션 값 우선, 없으면 DB 값 표시
                                current_spec = st.session_state.get(f'temp_spec_{s_no}', item.get('spec_detail', '스펙없음'))
                                st.info(f"현재 등록된 스펙: **{current_spec}**")
                            
                            else:
                                if st.button("❌ 변경 취소하고 돌아가기", key=f"cancel_{s_no}"):
                                    st.session_state[edit_key] = False
                                    st.session_state.pop(f'temp_spec_{s_no}', None)
                                    st.rerun()

                                # 수정 중: 스펙 선택창
                                prefix = s_no[0]
                                type_map = {'1': 'JUN', '2': 'REJ', '3': 'MET', '4': 'COR'} # 실제 DB 값으로 확인 필요
                                target_type = type_map.get(prefix)
                                
                                spec_master_list = list(db_collection.database["tool_inventory"].find({"tool_type": target_type}))
                                spec_opts = sorted(list(set([s.get('spec_detail') for s in spec_master_list if s.get('spec_detail')])))
                                
                                u_spec = st.selectbox("변경할 스펙 선택", spec_opts, key=f"sel_{s_no}")
                                
                                if st.button("🔄 스펙 확정", key=f"btn_confirm_{s_no}"):
                                    db_collection.update_one({"serial_no": s_no}, {"$set": {"spec_detail": u_spec}})
                                    st.session_state[f'temp_spec_{s_no}'] = u_spec 
                                    st.session_state[edit_key] = False
                                    st.rerun()

                                # --- 3. 원래 있던 현황판 고유 기능들 (지우지 마세요!) ---
                                # 이 아래부터는 기존에 있던 폼(form)이나 마크다운 코드들이 이어집니다.
                                spec_info = item.get('spec_detail', '스펙없음')
                                st.markdown(f"### ✏️ 시리얼 {s_no} ({spec_info}) 정보 실시간 수정 폼")
                            
                            # 여기서부터 기존 장착 날짜 변경, 상태 폼 등이 이어짐...
                                
                                note_content = str(item.get('note', ''))
                                has_history_log = "상태:" in note_content or "호기" in note_content
                                has_pending_log = "상태: 재사용대기" in note_content
                                
                                # [수정 후: note 텍스트 대신 실제 DB 데이터를 직접 확인]
                                last_mach = item.get("last_active_machine")
                                last_count = item.get("last_active_count")

                                # 가동 이력이 하나라도 있으면 경고창을 띄움
                                if last_mach or (last_count and last_count > 0):
                                    st.warning(f"⚠️ **이 툴은 이전에 가동되었다가 보관 후 다시 사용하는 [재사용 대상] 툴입니다.** (직전 기계: {last_mach}, 실적갯수: {last_count}개)")
                                    
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
                                    ed_date = st.date_input("장착 날짜 변경", value=init_date, key=f"dt_{s_no}_{item['_id']}")
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
                                    st.markdown("⚒ **현재 적용 스펙**")

                                    # 위쪽 토글에서 수정한 값을 그대로 불러와서 보여줍니다.
                                    current_display_spec = st.session_state.get(f'temp_spec_{s_no}', item.get('spec_detail', '스펙없음'))

                                    # 읽기 전용으로 보여줍니다 (수정은 위쪽 토글에서 하니까요!)
                                    st.info(f"현재 이 툴의 스펙: **{current_display_spec}**")
                                    st.markdown("⏳ **드레싱 주기 커스텀 시간 재설정**")
                                    col_eh, col_em = st.columns(2)
                                    with col_eh:
                                        ed_hours = st.number_input("시간(Hour)", min_value=0, max_value=100, value=0, step=1, key=f"eh_{s_no}")
                                    with col_em:
                                        ed_mins = st.number_input("분(Minute)", min_value=0, max_value=59, value=0, step=5, key=f"em_{s_no}")
                                        
                                   
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
                                        show_reuse_pending_dialog(s_no, item.get('machine_no',''), ed_note, ed_worker, ed_machine_num, ed_hours, ed_mins,new_spec)
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

                                    # 1. 스펙 정보를 세션 혹은 DB에서 가져옵니다.
                                    old_spec = item.get('spec_detail', '')
                                    new_spec = st.session_state.get(f'temp_spec_{s_no}', old_spec)

                                    # 2. 상태나 스펙이 바뀌었는지 확인합니다.
                                    if ed_status == item.get('status', '사용전') and old_spec == new_spec:
                                        final_note_val = ed_note.strip()
                                    else:
                                        log_time_str = real_now_kst.strftime("%Y-%m-%d %H:%M:%S")
                                        change_msg = f" 상태: {ed_status}"
                                        
                                        # 스펙이 다르면 로그 메시지에 추가
                                        if old_spec != new_spec:
                                            change_msg += f", (스펙: {old_spec} -> {new_spec})"

                        
                                        auto_log_msg = f"\n[{log_time_str}]{change_msg}, 작업자: {ed_worker}, 기계: {full_mach_name}"
                                        final_note_val = ed_note.strip() + auto_log_msg
                                        st.write(f"--- [최종 점검] DB 저장 직전 ed_status 값: {ed_status} ---")
                                    db_collection.update_one(
                                        {"serial_no": s_no},
                                        {"$set": {
                                            "status": ed_status,
                                            "worker": "" if ed_status in ["사용전", "폐기"] else ed_worker, 
                                            "machine_no": "" if ed_status in ["사용전", "폐기"] else full_mach_name,
                                            "dressing_hours": ed_hours,
                                            "dressing_mins": ed_mins,
                                            "use_limit": 0,  
                                            "start_time": start_time_val,
                                            "target_time": target_time_val,
                                            "waste_date": waste_date_val,
                                            "note": final_note_val,
                                            "detail_spec": new_spec
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
                                                formatted_date = date_obj.strftime("%Y-%m-%d")
                                            except:
                                                formatted_date = raw_date
                                                
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


#############################################################################################################################################################################




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




  
    
    # [실시간 기계 정보창 로직 전체]-------------------------------------------------------------------------------------------------------------------------------------------------
    elif tool_menu == "🖥️ 실시간 기계 정보창":
        show_machine_dashboard()


       
    # ★ 6) 🔧 툴 상세스펙 마스터 관리 (신규 하위 메뉴 매립 파트)----------------------------------------------------------------------------------------------------  
    elif tool_menu == "🔧 툴 상세스펙 마스터 관리":
        st.title("🔧 툴 상세 스펙 마스터 관리")
        st.write("관리자가 사전에 툴 규격을 적어두는 마스터 노트 공간입니다. 이곳에 등록된 데이터가 현장 모바일과 PC 수정창에 리스트로 호출됩니다.")
        
        spec_master_col = get_spec_master_collection()
        
        if spec_master_col is None:
            st.error("데이터베이스와 통신할 수 없습니다.")
        else:
            with st.form("spec_input_form_master", clear_on_submit=True):
                st.subheader("➕ 하위 상세 스펙 신규 등록")
                ins_type = st.selectbox("1. 툴 대분류 선택", ["전착툴", "레진툴", "메탈툴", "코어툴"])
                ins_name = st.text_input("2. 세부 스펙 이름 기입", placeholder="예: 파이90-20-200메쉬").strip()
                ins_memo = st.text_input("3. 비고/메모 (입도, 제조사 등)", placeholder="예: A사 정품 / #400")
                
                if st.form_submit_button("💾 스펙 리스트에 최종 등록"):
                    if not ins_name:
                        st.error("⚠️ 스펙 이름을 기입해야 등록 처리가 가능합니다!")
                    else:
                        spec_master_col.insert_one({
                            "main_type": ins_type,
                            "spec_name": ins_name,
                            "memo": ins_memo
                        })
                        st.success(f"🎉 '{ins_name}' 스펙이 마스터 리스트에 성공적으로 안착되었습니다.")
                        time.sleep(0.5)
                        st.rerun()

        st.write("<br><hr>", unsafe_allow_html=True)
        
        # 💡 토글 스위치 삽입 (이거 하나로 리스트 전체를 제어합니다)
        show_list = st.toggle("📋 전체 스펙 명부 보기/숨기기", value=True)
        
        if show_list:
            all_specs_list = list(spec_master_col.find({}))
            
            if not all_specs_list:
                st.info("💡 아직 등록된 스펙이 없습니다.")
            else:
                for spec in all_specs_list:
                    # 각 항목은 개별적으로 열어볼 수 있는 expander 사용
                    with st.expander(f"[{spec['main_type']}] {spec['spec_name']}"):
                        col_sp1, col_sp2, col_sp3 = st.columns([4, 1, 1])
                        with col_sp1:
                            st.markdown(f"**상세 메모:** {spec.get('memo', '내용 없음')}")
                        with col_sp2:
                            if st.button("✏️ 수정", key=f"edit_mst_{spec['_id']}"):
                                st.session_state.edit_target = spec
                                st.rerun()
                        with col_sp3:
                            if st.button("🗑️ 삭제", key=f"del_mst_{spec['_id']}"):
                                spec_master_col.delete_one({"_id": spec["_id"]})
                                st.success("삭제되었습니다.")
                                time.sleep(0.5)
                                st.rerun()
        else:
            st.caption("🔒 스펙 명부가 숨겨져 있습니다.")
