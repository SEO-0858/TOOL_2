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
import mong



st.cache_data.clear()


@st.dialog("🛠 신규 툴 등록 최종 확인")
def confirm_new_tool_registration(serial, spec, make):
    st.write(f"### ⚠️ 아래 정보로 등록하시겠습니까?")
    st.write(f"- **시리얼:** `{serial}`")
    st.write(f"- **스펙:** {spec}")
    st.write(f"- **제조사:** {make}")
    
    if st.button("✅ 최종 확정 등록"):
        # 기존 저장 로직
        db_collection.update_one(
            {"serial_no": serial},
            {"$set": {"spec_detail": spec, "make": make}}
        )
        update_inventory_count(spec, make, "폐기", "사용전")
        
        st.success("🎉 등록 완료!")
        del st.session_state['selected_spec']
        st.session_state['show_reg_popup'] = False
        time.sleep(1)
        st.rerun()


#폐기된 툴의 정보 함수----------------------------------------------------------------------------
def log_disposal(serial_no, spec_detail, worker,reason):
    col = db_collection.database['disposal_logs']
    if col.find_one({"serial_no": serial_no}) is None:
        db_collection.database['disposal_logs'].insert_one({
            "serial_no": serial_no,
            "spec_detail": spec_detail,
            "reason": reason,
            "worker": worker,
            "disposal_date": get_now_kst().strftime('%Y-%m-%d %H:%M:%S')
        })
        print(f"✅ 폐기 로그 저장 완료: {serial_no}")
    else:
        # 이미 로그가 있는 경우 아무것도 안 함 (중복 방지)
        print(f"⚠️ 이미 폐기 로그가 존재합니다 (중복 무시): {serial_no}")
        

#재고 계산기 함수----------------------------------------------------------------------------------------------------------------

def update_inventory_count(spec_detail, make, old_status, new_status):
    # 재고 관리 컬렉션 연결 (db_collection이 정의된 곳에서 불러옵니다)
    col = db_collection.database['tool_specs_master']
    query = {"spec_detail": spec_detail, "make": make}
    
    if old_status in ["사용전", "재사용대기"]:
        field = "new_tool_count" if old_status == "사용전" else "used_tool_count"
        col.update_one(query, {"$inc": {field: -1}}, upsert=True)
        
    # 2. 새 상태가 '폐기'라면 폐기 수량 증가 (+1)
    if new_status == "폐기":
        col.update_one(query, {"$inc": {"disposed_tool_count": 1}}, upsert=True)
        
    # 3. 새 상태에서 재고 하나 더하기 (+1)
    elif new_status in ["사용전", "재사용대기"]:
        field = "new_tool_count" if new_status == "사용전" else "used_tool_count"
        col.update_one(query, {"$inc": {field: 1}}, upsert=True)

# [2단계] 팝업창을 호출하는 함수 정의------------------------------------------------

@st.dialog("상세 스펙 변경 확인")
def confirm_mobile_spec_change(new_spec, serial_no):
    st.write(f"정말로 스펙을 **{new_spec}**(으)로 변경하시겠습니까?")
    
    if st.button("확정"):
        # 1. 재고 갱신: 기존 스펙은 -1, 신규 스펙은 +1
        # 주의: 현재 상태가 '사용전'이나 '재사용대기'인 경우에만 재고로 카운트합니다.
        current_status = existing_data.get("status")
        if current_status in ["사용전", "재사용대기"]:
            # 기존 스펙에서 빼기
            update_inventory_count(existing_data.get("spec_detail"), current_status, "폐기") 
            # 신규 스펙에 더하기 (폐기/사용중을 거쳐 다시 상태가 돌아가는 개념으로 처리)
            update_inventory_count(new_spec, "폐기", current_status)
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
            🛠 {item.get('spec_detail', '-')}
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
    reason = data.get('disposal_reason', '사유 없음')
    st.markdown("---")
    # 2. 요약 정보
    st.write(f"- **작업자:** {data['worker']}")
    st.write(f"- **기계 호기:** {data['machine_no']}")
    st.write(f"- **세부 스펙:** {data.get('spec_detail', '스펙 정보 없음')}")
    st.write(f"- **설정 주기:** {data['dressing_hours']}시간 {data['dressing_mins']}분")


    if data['status'] == "폐기":
        reason = data.get('disposal_reason', '사유 없음')
        st.write(f"- **폐기 사유:** {reason}")
    
    qty = 0
    if data['status'] in ["폐기", "재사용대기"]:
        qty = st.number_input("📦 최종 가공 수량(개)", min_value=0, value=0, step=1)

    # 상태가 '폐기'로 변경될 때만 로그 남기기
        if data['status'] == "폐기":           
            log_disposal(serial, data['spec_detail'], data.get('worker', ''), data.get('disposal_reason', '사유 없음'))
    if st.button("✅ 최종 확정 및 저장"):
        final_note = data['note']
        if data['status'] != data['prev_status']:
            now_str = get_now_kst().strftime("%Y-%m-%d %H:%M:%S")
            log = f"\n[{now_str}] 상태:{data['status']}, 스펙:{data['spec_detail']}, 작업자:{data['worker']}, 기계:{data['machine_no']}"
            if qty > 0: log += f", 최종수량:{qty}개"
            final_note += log

        # 재고 계산 함수 호출
        update_inventory_count(data['spec_detail'], data.get('make', ''),data['prev_status'], data['status'])

        db_collection.update_one(
            {"serial_no": serial},
            {"$set": {
                "status": data['status'],
                "worker": "" if data['status'] in ["사용전", "폐기"] else data['worker'],
                "machine_no": "" if data['status'] in ["사용전", "폐기"] else data['machine_no'],
                "dressing_hours": data['dressing_hours'],
                "dressing_mins": data['dressing_mins'],
                "note": final_note,
                "spec_detail": data['spec_detail'],
                "start_time": data['start_time'],
                "target_time": data['target_time']
            }},
            upsert=True
        )
        st.success("✅ 저장 완료되었습니다!")
        time.sleep(1.0) 
        st.session_state['show_confirm_dialog'] = False
        st.rerun()


# --- 📱 [모바일/현장 QR 스캔 기입 모드] ---
if qr_scanned_serial:
    st.title("📱 현장 툴 정보 즉시 기입창")
    st.subheader(f"🆔 시리얼 넘버: `{qr_scanned_serial}`")
    
    existing_data = db_collection.find_one({"serial_no": qr_scanned_serial}) or {}
    specs = []
    # 1. 상세 스펙 확인 방어막 (이 로직이 가장 먼저 실행되어야 합니다)

    if not existing_data.get('spec_detail'):
        st.warning("🚨 상세 스펙이 등록되지 않은 툴입니다. 아래에서 먼저 선택해주세요.")
        
        # 1) 시리얼 타입 파싱
        prefix = qr_scanned_serial[0]
        type_map = {'1': 'JUN', '2': 'REJ', '3': 'MET', '4': 'COR'}
        target_type = type_map.get(prefix)
        
        # 2) 데이터 불러오기
        specs = list(db_inventory.find({"main_type": target_type}))
        
        if not specs:
            st.error(f"❌ '{target_type}' 타입에 해당하는 스펙 데이터가 없습니다.")
        else:
            # 3) 중복 제거된 스펙 리스트 만들기
            unique_spec_names = sorted(list(set([s.get('spec_detail') for s in specs if s.get('spec_detail')])))
            
            st.write(f"🔍 {target_type} 타입에 맞는 스펙 목록을 선택하세요:")

            # 4) 버튼 생성 루프
            for spec_detail in unique_spec_names:
                first_doc = next(s for s in specs if s.get('spec_detail') == spec_detail)
                btn_key = f"btn_{first_doc['_id']}"
                
                if st.button(f"🛠 선택: {spec_detail}", key=btn_key):
                    st.session_state['selected_spec'] = spec_detail
                    st.rerun()

            # 5) 선택 시 제조사 드롭다운 보여주기
            if 'selected_spec' in st.session_state:
                selected_spec = st.session_state['selected_spec']
                st.success(f"✅ 선택된 스펙: {selected_spec}")
                
                # 선택된 스펙에 맞는 제조사 목록 추출
                matching_specs = [s for s in specs if s.get('spec_detail') == selected_spec]
                available_makers = sorted(list(set([s.get('make') for s in matching_specs if s.get('make')])))
                
                st.markdown("### 🏭 제조사를 선택하세요")
                selected_make = st.selectbox("제조사 선택", available_makers, key="maker_select")
                
                # 6) 최종 등록 버튼

                if st.button("🚀 상세 스펙 및 제조사 확정 후 재고 등록"):
                    st.session_state['show_reg_popup'] = True
                    st.rerun()

                # 팝업 호출 트리거
                if st.session_state.get('show_reg_popup'):
                    confirm_new_tool_registration(qr_scanned_serial, selected_spec, selected_make)

                st.stop() # 데이터가 등록되기 전까지는 여기서 멈춤


                
        # 스펙 선택 버튼 루프 부분
        for s in specs:
            # 버튼 클릭 시 동작
            if st.button(f"🛠 선택: {s.get('spec_detail', '정보없음')}", key=f"btn_{s.get('spec_detail')}"):
                existing_spec = existing_data.get('spec_detail')
                if existing_spec and existing_spec != '정보없음':
                    # 기존에 설정된 상태가 있다면 그 상태에서 -1 (보통 '사용전')
                    update_inventory_count(existing_spec, existing_data.get('status', '사용전'), "폐기")

                # --- [여기 추가] 2단계: 새로 선택한 스펙에 +1 ---
                update_inventory_count(s.get('spec_detail'), "폐기", "사용전")

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
   
    u_disposal_reason = "" 
    if u_status == "폐기":
        u_disposal_reason = st.text_input("⚠️ 폐기 사유 입력")

    
    st.divider()
    
    st.markdown("### 📝 기본 정보")
    u_worker = st.text_input("👷 교체 작업자 이름", value=existing_data.get('worker', ''))
    
    
    orig_mach = existing_data.get('machine_no', '')
    default_mach = int(''.join(filter(str.isdigit, orig_mach))) if any(c.isdigit() for c in orig_mach) else 0
    u_machine = st.number_input("⚙️ 기계 가공 호기", value=default_mach)
    current_spec = existing_data.get('spec_detail', '스펙없음')
    u_spec = current_spec 
    st.markdown(f"""
    <div style="background-color: #f0f2f6; padding: 10px; border-radius: 5px;">
        <p style="font-size: 20px; font-weight: bold; color: #d63384; margin: 0;">
            세부 스펙: {u_spec}
        </p>
    </div>
    """, unsafe_allow_html=True)
 

    st.markdown("### ⏳ 드레싱 및 특이사항")
    c1, c2 = st.columns(2)
    u_h = c1.number_input("시간(Hour)", value=existing_data.get('dressing_hours', 0))
    u_m = c2.number_input("분(Minute)", value=existing_data.get('dressing_mins', 0))
    u_note = st.text_area("📝 현장 특이사항", value=existing_data.get('note', ''))
       


    if st.button("데이터 확인 및 저장"):
        st.session_state['confirm_data'] = {
            'status': u_status,
            'prev_status': prev_status,
            'worker': u_worker,
            'machine_no': f'{u_machine}호기', 
            'spec_detail': u_spec,
            'dressing_hours': u_h, 'dressing_mins': u_m, 
            'note': u_note,
            'start_time': get_now_kst().strftime('%Y-%m-%d %H:%M:%S'),
            'make': existing_data.get('make', ''),
            'target_time': (get_now_kst() + timedelta(minutes=(u_h * 60) + u_m)).strftime('%Y-%m-%d %H:%M:%S'),
            'disposal_reason': u_disposal_reason
        }
        st.session_state['show_confirm_dialog'] = True
        st.rerun() # 팝업을 띄우기 위해 화면 새로고침

    # [추가된 부분] 팝업 호출 트리거
    if st.session_state.get('show_confirm_dialog'):
        confirm_and_save(qr_scanned_serial, st.session_state['confirm_data'])
    if st.button("🏠 메인으로 돌아가기"):
        st.query_params.clear(); st.rerun()




# --- 💻 [PC 관리자 모드] -----------------------------------------------------------------------------------------------------------------------------
else:
    st.session_state.sidebar_errors = []
    st.sidebar.markdown("## 📁 KKQ 통합 시스템")
    menu_options = ["📊 빈데이터 QR코드 대량 선발행", "⚠️ 실시간 툴 드레싱 알림판", "📂 전체 데이터 현황판", "⚙️ 데이터 수정 / 삭제 / QR 재발행", "🖥️ 실시간 기계 정보창","🔧 툴 상세스펙 마스터 관리","🔍 툴 종합 검색"]
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

#---------------------전체 데이터 현황판--------------------------------------------------------------------


    elif tool_menu == "📂 전체 데이터 현황판":
        st.title("📂 현장 기입 데이터 통합 현황판")
        st.markdown("현황판에서 각 툴의 데이터를 펼친 뒤, **편집 및 초기화**를 진행할 수 있습니다.")
        st.write("<br>", unsafe_allow_html=True)
        
        # 1. 검색 필터
        search_col1, search_col2, search_col3, search_col4 = st.columns([1.5, 1, 1, 1])
        with search_col1:
            status_filter = st.selectbox("🔍 툴 상태별 정렬 필터", ["사용중 🟡 (기본값)", "전체 보기 📂", "사용전(기기대기) 🟢", "재사용 🔵", "재사용대기 🟣", "폐기 🔴"])
        with search_col2:
            keyword_search = st.text_input("🆔 특정 시리얼 넘버 검색", placeholder="예: 010602").strip()
        with search_col3:
            worker_search = st.text_input("👷 작업자 검색", placeholder="예: 홍길동").strip()
        with search_col4:
            machine_search = st.text_input("⚙️ 기계 번호 검색", placeholder="예: 4호기").strip()

        st.write("<br>", unsafe_allow_html=True)
        
        try:
            # 데이터 로드 (tools_management 컬렉션 사용)
            all_data = list(db.tools_management.find({}).sort("serial_no", -1))
            if not all_data:
                st.info("조회할 데이터가 없습니다.")
            else:
                # 필터링 로직
                filtered_data = []
                for item in all_data:
                    item_status = item.get("status", "사용전")
                    if status_filter == "사용중 🟡 (기본값)" and item_status != "사용중": continue
                    if status_filter == "사용전(기기대기) 🟢" and item_status != "사용전": continue
                    if status_filter == "재사용 🔵" and item_status != "재사용": continue
                    if status_filter == "재사용대기 🟣" and item_status != "재사용대기": continue
                    if status_filter == "폐기 🔴" and item_status != "폐기": continue
                    if keyword_search and keyword_search not in item.get("serial_no", ""): continue
                    if worker_search and worker_search not in item.get("worker", ""): continue
                    if machine_search and machine_search not in item.get("machine_no", ""): continue
                    filtered_data.append(item)

                if not filtered_data:
                    st.warning("🔍 검색 조건에 맞는 데이터가 없습니다.")
                else:
                    st.caption(f"📊 총 **{len(filtered_data)}** 개의 항목이 검색되었습니다.")
                    
                    # 리스트 출력
                    for item in filtered_data:
                        s_no = item["serial_no"]
                        status_badge = {"사용전":"🟢 [사용전]", "사용중":"🟡 [사용중]", "재사용":"🔵 [재사용]", "재사용대기":"🟣 [재사용대기]", "폐기":"🔴 [폐기]"}.get(item.get("status"), "🔴 [폐기]")
                        
                        with st.expander(f"🆔 {s_no} | {item.get('tool_type', '툴')} | {status_badge}"):
                            col1, col2 = st.columns(2)
                            with col1:
                                st.write(f"• **상세 스펙:** {item.get('spec_detail', '-')}")
                                st.write(f"• **교체 작업자:** {item.get('worker', '-')}")
                            with col2:
                                st.write(f"• **기계 호기:** {item.get('machine_no', '-')}")
                                st.write(f"• **사용 한도:** {int(item.get('use_limit', 10000))} 회")
                            
                            input_date = item.get('input_date', '날짜 미기입')
                            init_time = item.get('init_time', '시간 미기입')
                            st.info(f"📝 **현장 특이 사항:** {item.get('note', '기록 없음')}\n\n🕒 **최초 발행:** {input_date} {init_time}")
                            
                            st.divider()
                            st.subheader("🛠 데이터 관리")
                            
                            # [버튼 1] 현장 작업 내용만 초기화 (재고 변동 없음)
                            if st.button(f"🔄 현장 작업 내용만 리셋", key=f"reset_work_{s_no}"):
                                db.tools_management.update_one({"serial_no": s_no}, {"$set": {
                                    "status": "사용전", "worker": "", "machine_no": "", "dressing_hours": 0, 
                                    "dressing_mins": 0, "start_time": "-", "target_time": "-", "note": "작업 내용 리셋"
                                }})
                                st.success("✅ 작업 이력이 초기화되었습니다.")
                                st.rerun()

                            # [버튼 2] 스펙 오류 삭제 및 재고 보정 (tool_inventory의 new_tool_count 보정)
                            if st.button(f"🗑️ [스펙 오류] 삭제 및 재고 보정", key=f"reset_spec_{s_no}", type="primary"):
                                st.session_state[f"confirm_spec_{s_no}"] = True
                            
                            if st.session_state.get(f"confirm_spec_{s_no}", False):
                                st.warning(f"⚠️ [{s_no}] 스펙 오류입니까? 선택한 스펙 재고가 -1 차감됩니다.")
                                c1, c2 = st.columns(2)
                                if c1.button("✅ 진짜 진행", key=f"do_spec_{s_no}"):
                                    current_spec = item.get("spec_detail")
                                    # 1. 재고 보정: tool_inventory의 new_tool_count 차감 (-1)
                                    if current_spec:
                                        db.tool_inventory.update_one(
                                            {"spec_detail": current_spec},
                                            {"$inc": {"new_tool_count": -1}}
                                        )
                                    # 2. 데이터 초기화: tools_management 수정
                                    db.tools_management.update_one({"serial_no": s_no}, {"$set": {
                                        "status": "사용전", "spec_detail": None, "worker": "", "machine_no": "", 
                                        "note": "스펙 오류로 삭제 및 재고 보정 완료"
                                    }})
                                    st.session_state[f"confirm_spec_{s_no}"] = False
                                    st.success("💥 삭제 완료! 재고가 보정되었습니다.")
                                    st.rerun()
                                if c2.button("취소", key=f"cancel_spec_{s_no}"):
                                    st.session_state[f"confirm_spec_{s_no}"] = False
                                    st.rerun()

        except Exception as e:
            st.error(f"데이터 로드 에러: {e}")

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
        db = db_collection.database['tool_inventory']
        # 1. 스펙 입력 (Form 제거 - 실시간 반영을 위해)
        st.subheader("🛠 상세 스펙 구성 (스펙 빌더)")
        
        cat_options = {"1": "1 (전착 - JUN)", "2": "2 (레진 - REJ)", "3": "3 (메탈 - MET)", "4": "4 (코어 - COR)"}
        main_cat_display = st.selectbox("툴 대분류 선택", list(cat_options.values()))
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            d_val = st.number_input("지름(D)", min_value=0.00, step=0.01, format="%.2f")
            t_val = st.number_input("두께(T)", min_value=0.00, step=0.01, format="%.2f")
        with col2:
            r_val = st.number_input("반경(R)", min_value=0.00, step=0.01, format="%.2f")
            a_val = st.number_input("각도(A)", min_value=0, step=1)
        with col3:
            free_input = st.text_input("기타 사양(자유기입)")
            grit_val = st.text_input("입자도(#)")
        with col4:
            make_val = st.text_input("제조사 약자 (예: KI)")

        # 실시간 조합 및 미리보기 (이제 즉시 바뀝니다!)
        main_code = main_cat_display.split(" ")[0] 
        main_type_eng = main_cat_display.split("- ")[1].replace(")", "").strip()
        parts = []
        parts.append(f"D{float(d_val)}")
        parts.append(f"{float(t_val)}T")
        
        # R값이 0보다 클 때만 목록에 추가
        if r_val > 0:
            parts.append(f"{r_val}R")
        # A값이 0보다 클 때만 목록에 추가
        if a_val > 0:
            parts.append(f"{int(a_val)}A")
            
        # 자유기입란에 내용이 있을 때만 추가
        if free_input:
            parts.append(free_input)
        
        # 입자도와 제조사는 항상 추가
        parts.append(f"#{grit_val}")
        parts.append(make_val.upper())

        # 리스트에 담긴 것들만 언더바로 연결
        spec_parts = [p for p in parts if p != make_val.upper()]
        final_spec = "_".join(spec_parts)
        
        st.info(f"생성된 상세 스펙(규격): **{final_spec}** | 제조사: **{make_val.upper()}**")

        # 2. 저장 버튼 (별도 처리)
        if st.button("마스터 리스트 등록"):
            if make_val:
                db.insert_one({
                    "main_code": main_code,
                    "main_type": main_type_eng,
                    "spec_detail": final_spec,
                    "make": make_val.upper()
                })
                st.success("등록 완료")
                time.sleep(1.5)
                st.rerun()
            else:
                st.warning("제조사 약자를 입력해주세요.")

        # 3. 리스트 조회
        st.write("---")
        st.subheader("📋 등록된 스펙 마스터 목록")
        specs = list(db.find({}))
        for s in specs:
            with st.expander(f"{s.get('main_type', 'N/A')} | {s.get('spec_detail', 'N/A')}"):
                if st.button("삭제", key=f"del_{s['_id']}"):
                    db.delete_one({"_id": s['_id']})
                    st.rerun()


    elif tool_menu == "🔍 툴 종합 검색":
        mong.render_search_menu()                
