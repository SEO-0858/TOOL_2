import streamlit as st
import streamlit.components.v1 as components
from pymongo import MongoClient
import datetime  # 기존 코드에서 datetime.datetime.utcnow() 등을 썼다면 필요합니다.
from datetime import datetime as dt, timedelta
import pandas as pd
import re
import time
import base64
import json
from io import BytesIO
from urllib import error as urlerror
from urllib import parse as urlparse
from urllib import request as urlrequest
import qrcode
dt_class = dt
import pytz



@st.dialog("⚠️ 툴 폐기 처리")
def waste_dialog(serial, data):
    if serial is None:
        serial = st.session_state.get('temp_serial')
    
    st.write(f"시리얼 번호: **{serial}**")
    
    # 1. 입력 UI 정의
    reason_options = ["1. 다이아팁 전면 2mm 이하", "2. 툴 현상변화", "3. 툴파이 진원도 불량", "4. 지정 수량 초과", "5. 파손(툴찍힘)", "6. 기타사유(직접기입)"]
    selected_reason = st.selectbox("폐기 사유 선택:", reason_options)
    
    detail_reason = ""
    if selected_reason == "6. 기타사유(직접기입)":
        detail_reason = st.text_input("상세 사유 입력:")

    current_mach = data.get('machine_no', '')
    machine_input = st.text_input("기계 번호 (또는 보관/이동):", value=current_mach)
    machine_val = machine_input.strip()
    
    # 기계번호 로직
   
    numbers = re.findall(r'\d+', machine_val)
    machine_final = f"{int(numbers[0]):02d}호기" if numbers else machine_val

    waste_qty = st.number_input("(!!가공수량이 없으면 0을 넣으세요!!) (개)", min_value=0, value=0, step=1)
    waste_qty_confirmed = st.checkbox(f"가공수량 {waste_qty}개 맞습니다.", key=f"confirm_waste_qty_{serial}")
    lot_info = render_lot_lookup_box(f"waste_{serial}")
    current_worker = data.get('worker', '')
    worker_input = st.text_input("작업자 이름:", value=current_worker)

    # 2. 버튼 및 저장 로직 (이곳에 기존 로직 모두 포함)
    col1, col2 = st.columns(2)
    if col1.button("✅ 최종 폐기 저장", key="final_save_btn"):
        if not selected_reason:
            st.error("사유를 선택해주세요.")
        elif not worker_input:
            st.error("작업자 이름을 입력해주세요.")
        elif not waste_qty_confirmed:
            st.error(f"가공수량 {waste_qty}개가 맞는지 확인 체크를 해주세요.")
        elif not ensure_lot_lookup_ready(lot_info):
            st.stop()
        else:
            try:
                # 기존 로직 (로그 생성 및 DB 업데이트)
                latest_doc = db_collection.database['tools_management'].find_one({"serial_no": serial})
                current_note = latest_doc.get('note', '') if latest_doc else ""
                quantities = re.findall(r'(?:수량|가공갯수):\s*(\d+)개', current_note)
                total_accumulated_qty = sum(int(q) for q in quantities) + waste_qty
                
                log_data = {
                    "serial_no": serial, "machine_no": machine_final, "disposal_reason": selected_reason,
                    "detail_reason": detail_reason, "worker": worker_input, "waste_qty": total_accumulated_qty,
                    "spec_detail": data.get('spec_detail', ''), "disposal_date": get_now_kst().strftime('%Y-%m-%d %H:%M:%S'),
                }
                log_data.update(disposal_lot_db_fields(lot_info, serial, latest_doc, data))
                db_collection.database['disposal_logs'].insert_one(log_data)
                
                # DB 업데이트
                combined_reason = f"{selected_reason}: {detail_reason}" if selected_reason == "6. 기타사유(직접기입)" else selected_reason
                new_log = f"\n[{get_now_kst().strftime('%Y-%m-%d %H:%M:%S')}] 상태:폐기, 스펙:{data.get('spec_detail', '스펙없음')}, 사유:{combined_reason}, 작업자:{worker_input}, 기계:{machine_final}, 최종수량:{total_accumulated_qty}개{format_lot_log(lot_info)}"
                db_collection.database['tools_management'].update_one({"serial_no": serial}, {"$set": {"status": "폐기", "disposal_reason": selected_reason, "detail_reason": combined_reason, "note": current_note + new_log, "worker": worker_input, "machine_no": machine_final, **lot_db_fields(lot_info)}, "$unset": lot_db_unset_fields(lot_info)})
                

                # 72라인 근처 수정
                result = db_collection.database['tools_management'].update_one(
                    {"serial_no": serial}, 
                    {"$set": {"status": "폐기", "disposal_reason": selected_reason, "detail_reason": combined_reason, "note": current_note + new_log, "worker": worker_input, "machine_no": machine_final, **lot_db_fields(lot_info)}, "$unset": lot_db_unset_fields(lot_info)}
                )
                
                # 업데이트된 개수를 확인하는 디버깅 코드 추가
                if result.matched_count == 0:
                    st.error(f"오류: 시리얼 번호 {serial}을(를) DB에서 찾을 수 없습니다!")
                    st.stop()
                
                # ... 그 다음 update_inventory_count 실행 ...
                update_inventory_count(data.get('spec_detail', ''), data.get('make', ''), data.get('status', ''), '폐기')
                time.sleep(2)
                st.session_state['show_waste_dialog'] = False # 다이얼로그 닫기
                st.session_state['show_success_msg'] = True  # 성공 메시지 예약
                st.rerun()

            except Exception as e:  
                st.error(f"오류 발생: {e}") 

    
    if col2.button("❌ 취소", key="cancel_btn"):
        # 1. 창을 닫습니다.
        st.session_state['show_waste_dialog'] = False
        
        # 2. [핵심] 성공 메시지 신호는 확실히 끕니다!
        st.session_state['show_success_msg'] = False 
        
        # 3. 데이터 복구 로직 (기존에 작성하신 복구 코드 유지)
        if 'last_valid_status' in st.session_state:
            st.session_state['reset_u_status_to'] = st.session_state['last_valid_status']
        else:
            st.session_state['reset_u_status_to'] = data.get('status', '사용전')
            
        st.rerun()
        

#폐기관련 전용함수-------------------------------------------------------------------------------------------------------------

def disposal_can_do(serial, data):
    st.session_state['temp_serial'] = serial
    st.session_state['temp_data'] = data
    st.session_state['show_waste_dialog'] = True




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
        tool_doc = db_collection.find_one({"serial_no": serial_no})
        log_data = {
            "serial_no": serial_no,
            "spec_detail": spec_detail,
            "reason": reason,
            "worker": worker,
            "disposal_date": get_now_kst().strftime('%Y-%m-%d %H:%M:%S')
        }
        log_data.update(disposal_lot_db_fields({}, serial_no, tool_doc, {}))
        db_collection.database['disposal_logs'].insert_one(log_data)
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
        col.update_one(
                {**query, field: {"$gt": 0}}, 
                {"$inc": {field: -1}}
            )
        

        
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
            update_inventory_count(existing_data.get("spec_detail"),existing_data.get("make"), current_status, "폐기") 
            # 신규 스펙에 더하기 (폐기/사용중을 거쳐 다시 상태가 돌아가는 개념으로 처리)
            update_inventory_count(new_spec,existing_data.get("make"), "폐기", current_status)
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
    active_tools = list(db_collection.find({"status": {"$in": ["사용중", "재사용"]}}))
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


    machine_tool_map = {}
    for t in active_tools:
        m_no_match = re.findall(r'\d+', str(t.get('machine_no', '')))
        if not m_no_match:
            continue
        m_no = int(m_no_match[0])
        # 해당 기계 번호 키가 없으면 리스트를 만들고, 있으면 기존 리스트에 툴을 추가(append)
        if m_no not in machine_tool_map:
            machine_tool_map[m_no] = []
        machine_tool_map[m_no].append(t)



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
                
                if st.form_submit_button("💾 기본 정보 저장"):
                    old_machine = target_tool.get('machine_no', '')
                    old_worker = target_tool.get('worker', '')
                    
                    # 로그 기록
                    timestamp = get_now_kst().strftime('%Y-%m-%d %H:%M:%S')
                    log_msg = f"\n[{timestamp}] 기계:{old_machine}→{new_machine} / 작업자:{old_worker}→{new_worker}"
                    updated_note = (target_tool.get('note', '') + log_msg).strip()

                    db_collection.update_one(
                        {"serial_no": ctx_key},
                        {"$set": {
                            "machine_no": new_machine, 
                            "worker": new_worker, 
                            "note": updated_note
                        }}
                    )
                    st.success("기본 정보가 저장되었습니다!")
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
            return "#FF4B4B", "※정상 가동중 ※", f"🚧 현재 구현 중"
        elif total_seconds <= 3600:
            return "#FFAA00", "※ 주의(임박) ※", f"🚧 현재 구현 중"
        else:
            hours = int(total_seconds // 3600)
            mins = int((total_seconds % 3600) // 60)
            return "#008850", "※ 정상 가동 중 ※", f"⏱️ {hours}시간 {mins}분 남음"
    except Exception as e:
        return "#808080", "형식 오류", "-"




def get_remaining_time(target_time_str):
    # 1. 값이 없으면 바로 탈출
    if not target_time_str or str(target_time_str).strip() == "-":
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

    # 4. 장착 누적 시간 계산 (상태가 사용중/재사용일 때만)

    duration_text = ""
    start_time_raw = item.get('start_time')
    if item.get('status') in ["사용중", "재사용"] and start_time_raw and str(start_time_raw).strip() != "-":
        try:
            # 1. DB 시간을 datetime 객체로 변환
            start_dt = dt.strptime(str(start_time_raw).strip(), "%Y-%m-%d %H:%M:%S") 
            
            # 2. 현재 시간도 동일한 형식으로 변환 (KST 기준)
            now_str = get_now_kst().strftime("%Y-%m-%d %H:%M:%S")
            now_dt = dt.strptime(now_str, "%Y-%m-%d %H:%M:%S")
            
            # 3. 차이 계산
            delta = now_dt - start_dt
            
            # 4. 시간과 분 계산
            hours = delta.total_seconds() // 3600
            minutes = (delta.total_seconds() % 3600) // 60
            
            duration_text = f"⏳ 장착 누적 시간: {int(hours)}시간 {int(minutes)}분"
        except Exception as e:
            duration_text = f"⏳ 오류: {str(e)}"

    status_icon = "🟢" if color == "green" else "🟠" if color == "orange" else "🔴" if color == "red" else "⚪"
    card_lines = [
        f"**🆔 {item.get('serial_no')}**",
        f"**[{db_status}]** {status_icon} {status_label}",
        f"**[{tool_type}툴]**",
        f"👤 작업자: {worker_name}",
        f"🛠 {item.get('spec_detail', '-')}",
    ]
    if duration_text:
        card_lines.append(duration_text)

    st.markdown("\n\n".join(card_lines))


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
if db_collection is None:
    st.stop()
db_inventory = db_collection.database["tool_inventory"]

# --- [공정 흐름 제어 검문소] ---
def validate_process(current_status, next_status):
    allowed = {
        "사용전": ["사용중", "폐기"],
        "사용중": ["재사용대기", "폐기"],
        "재사용대기": ["재사용", "폐기"],
        "재사용": ["재사용대기", "폐기"],
        "폐기": []
    }
    if current_status in allowed and next_status not in allowed[current_status]:
        return False, f"⚠️ 공정 오류: {current_status} 상태에서는 {next_status}로 이동할 수 없습니다."
    return True, ""


QTY_REQUIRED_TRANSITIONS = {
    ("사용중", "재사용대기"),
    ("사용중", "폐기"),
    ("재사용", "재사용대기"),
    ("재사용", "폐기"),
    ("사용전", "폐기"),
    ("재사용대기", "폐기"),
}


def requires_qty_input(prev_status, next_status):
    return (prev_status, next_status) in QTY_REQUIRED_TRANSITIONS


def requires_waste_dialog(prev_status, next_status):
    return requires_qty_input(prev_status, next_status) and next_status == "폐기"


def normalize_lot_api_key(raw_key):
    key = str(raw_key or "").strip()
    if not key:
        return ""

    if "key=" in key or "?" in key:
        parsed = urlparse.urlparse(key)
        query_text = parsed.query if parsed.query else key.lstrip("?")
        query_values = urlparse.parse_qs(query_text)
        key_values = query_values.get("key")
        if key_values:
            return str(key_values[0]).strip()
        if key.lower().startswith("key="):
            return key.split("=", 1)[1].strip()

    return key


def add_query_param(raw_url, name, value):
    if not value:
        return raw_url

    parsed = urlparse.urlparse(raw_url)
    query_values = urlparse.parse_qsl(parsed.query, keep_blank_values=True)
    query_values.append((name, value))
    return urlparse.urlunparse(parsed._replace(query=urlparse.urlencode(query_values)))


def get_lot_api_config():
    try:
        config = st.secrets.get("ksi_lot_api", {})
    except Exception:
        config = {}
    return {
        "url": str(config.get("url", "")).strip(),
        "key": normalize_lot_api_key(config.get("key", "")),
    }


def render_lot_api_debug(context_key):
    api = get_lot_api_config()
    url = api.get("url", "")
    key = api.get("key", "")
    masked_key_tail = f"**{key[-2:]}" if len(key) >= 2 else "(empty)"
    with st.expander("LOT API 설정 확인", expanded=False):
        st.caption("실제 key 값은 보안 때문에 표시하지 않습니다.")
        st.write(f"URL 설정됨: {'예' if url else '아니오'}")
        st.write(f"URL 값: {url or '(비어 있음)'}")
        st.write(f"KEY 설정됨: {'예' if key else '아니오'}")
        st.write(f"KEY 글자 수: {len(key)}")
        st.write(f"KEY 끝 2자리: {masked_key_tail}")


def lot_api_debug_text():
    api = get_lot_api_config()
    url = api.get("url", "")
    key = api.get("key", "")
    masked_key_tail = f"**{key[-2:]}" if len(key) >= 2 else "(empty)"
    return (
        f" LOT API 확인: URL={'있음' if url else '없음'}"
        f", KEY={'있음' if key else '없음'}"
        f", KEY글자수={len(key)}"
        f", KEY끝2자리={masked_key_tail}"
    )


def summarize_lot_http_error(exc):
    body = ""
    try:
        body = exc.read().decode("utf-8", errors="replace")
    except Exception:
        body = ""

    one_line = re.sub(r"\s+", " ", body).strip()
    if len(one_line) > 220:
        one_line = one_line[:220] + "..."

    headers_text = ""
    server = ""
    try:
        headers_text = str(exc.headers)
        server = exc.headers.get("server", "") or exc.headers.get("Server", "")
    except Exception:
        headers_text = ""

    body_lower = one_line.lower()
    headers_lower = headers_text.lower()
    if "invalid api key" in body_lower:
        source = "bridge_key_rejected"
    elif "cloudflare" in body_lower or "cf-ray" in headers_lower:
        source = "cloudflare_block_or_challenge"
    else:
        source = "unknown_403"

    return f" 403상세: source={source}, server={server or '(none)'}, body={one_line or '(empty)'}"


def build_ksi_work_order_no(tail_or_full, prefix=None):
    value = str(tail_or_full or "").strip().upper()
    if not value:
        return ""
    if value.startswith("KK"):
        return value

    digits = re.sub(r"\D", "", value)
    if not digits:
        return ""

    if prefix is None:
        prefix = f"KK{get_now_kst().year}"
    return f"{prefix}{digits}"


def normalize_lot_response(data, requested_work_order_no):
    if isinstance(data, list):
        data = data[0] if data else {}
    if not isinstance(data, dict):
        data = {}

    rows = data.get("rows")
    first_row = rows[0] if isinstance(rows, list) and rows and isinstance(rows[0], dict) else {}

    def pick(*keys):
        for source in (data, first_row):
            for key in keys:
                value = source.get(key)
                if value is not None and str(value).strip():
                    return str(value).strip()
        return ""

    normalized = {
        "work_order_no": pick("work_order_no", "lot", "LOT", "작업지시번호") or requested_work_order_no,
        "product_name": pick("product_name", "item_name", "품명", "AssyName"),
        "spec": pick("spec", "item_spec", "품목규격", "규격", "AssyItemSpec"),
        "plan_qty": pick("plan_qty", "plan_quantity", "계획수량"),
    }
    normalized["lookup_ok"] = bool(normalized["spec"])
    return normalized


def lookup_ksi_lot_info(work_order_no):
    api = get_lot_api_config()
    if not api["url"]:
        return None, "K-System LOT 중계 API 주소가 아직 설정되지 않았습니다."

    base_url = api["url"]
    if "{work_order_no}" in base_url:
        lookup_url = base_url.replace("{work_order_no}", urlparse.quote(work_order_no))
    elif "{tail}" in base_url:
        tail = work_order_no[6:] if work_order_no.startswith("KK") else work_order_no
        lookup_url = base_url.replace("{tail}", urlparse.quote(tail))
    else:
        lookup_url = base_url.rstrip("/") + "/lot/" + urlparse.quote(work_order_no)

    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (KSI-LOT-Streamlit/1.0)",
    }
    if api["key"]:
        headers["X-API-Key"] = api["key"]
        lookup_url = add_query_param(lookup_url, "key", api["key"])

    req = urlrequest.Request(lookup_url, headers=headers, method="GET")
    try:
        with urlrequest.urlopen(req, timeout=5) as response:
            payload = response.read().decode("utf-8")
            data = json.loads(payload)
            if isinstance(data, dict) and data.get("ok") is False:
                return None, str(data.get("message") or "LOT 조회 결과가 없습니다.")
            info = normalize_lot_response(data, work_order_no)
            if not info.get("spec"):
                return None, "LOT 조회는 되었지만 ERP 규격(spec) 값이 없습니다."
            return info, ""
    except urlerror.HTTPError as exc:
        if exc.code == 403:
            return None, "LOT 조회 인증 실패(HTTP 403)." + lot_api_debug_text() + summarize_lot_http_error(exc)
            return None, "LOT 조회 인증 실패(HTTP 403): Streamlit Secrets의 ksi_lot_api.key 값을 중계 PC api_key와 똑같이 맞춰주세요." + lot_api_debug_text()
            return None, "LOT 조회 인증 실패(HTTP 403): Streamlit Secrets의 ksi_lot_api.key 값을 중계 PC api_key와 똑같이 맞춰주세요."
        return None, f"LOT 조회 서버 응답 오류: HTTP {exc.code}"
    except Exception as exc:
        return None, f"LOT 조회 실패: {exc}"


def render_lot_lookup_box(context_key):
    st.markdown("#### 🔎 K-System LOT 조회")

    prefix = f"KK{get_now_kst().year}"
    no_lot_key = f"lot_not_required_{context_key}"
    if st.checkbox("LOT 없음 / 수리품 등 ERP 품목 없이 저장", key=no_lot_key):
        st.info("LOT 정보 없이 저장합니다.")
        return {
            "items": [],
            "expected_count": 0,
            "work_order_no": "",
            "product_name": "",
            "spec": "",
            "plan_qty": "",
            "lookup_ok": True,
            "lookup_error": "",
            "tail_entered": False,
            "lot_not_required": True,
        }

    lot_info_key = f"lot_info_{context_key}"

    col_prefix, col_tail, col_btn = st.columns([1.1, 2.0, 0.9])
    col_prefix.text_input("앞번호", value=prefix, disabled=True, key=f"lot_prefix_{context_key}")
    tail = col_tail.text_input("뒤 번호만 입력", placeholder="예: 0616031", key=f"lot_tail_{context_key}")

    if col_btn.button("조회", key=f"lot_lookup_btn_{context_key}"):
        work_order_no = build_ksi_work_order_no(tail, prefix)
        if not work_order_no:
            st.warning("LOT 뒤 번호를 입력해 주세요.")
        else:
            info, message = lookup_ksi_lot_info(work_order_no)
            if info:
                info["lookup_ok"] = True
                info["lookup_error"] = ""
                st.session_state[lot_info_key] = info
                st.success("LOT 정보를 조회했습니다.")
            else:
                st.session_state[lot_info_key] = {
                    "work_order_no": work_order_no,
                    "product_name": "",
                    "spec": "",
                    "plan_qty": "",
                    "lookup_ok": False,
                    "lookup_error": message,
                }
                st.warning(message)

    lot_info = st.session_state.get(lot_info_key, {})
    work_order_no = lot_info.get("work_order_no") or build_ksi_work_order_no(tail, prefix)
    tail_entered = bool(str(tail or "").strip())
    display_spec = str(lot_info.get("spec", "") or "").strip()

    spec = st.text_input("ERP 규격(spec)", value=display_spec, disabled=True, key=f"lot_spec_{context_key}_{work_order_no}_{display_spec}")

    return {
        "work_order_no": work_order_no,
        "product_name": "",
        "spec": display_spec or spec.strip(),
        "plan_qty": "",
        "lookup_ok": bool(lot_info.get("lookup_ok")),
        "lookup_error": lot_info.get("lookup_error", ""),
        "tail_entered": tail_entered,
    }


def ensure_lot_lookup_ready(lot_info):
    if not lot_info or not lot_info.get("tail_entered"):
        return True
    if lot_info.get("lookup_ok") and lot_info.get("spec"):
        return True
    st.error("LOT 번호를 입력했다면 ERP 조회가 성공해야 저장할 수 있습니다.")
    return False


def format_lot_log(lot_info):
    if not lot_info or not lot_info.get("spec"):
        return ""
    lot_no = lot_info.get("work_order_no", "")
    if lot_no:
        return f", ERP LOT:{lot_no}, ERP규격:{lot_info['spec']}"
    return f", ERP규격:{lot_info['spec']}"


def lot_db_fields(lot_info):
    if not lot_info or not lot_info.get("spec"):
        return {}
    return {
        "last_erp_lot_no": lot_info.get("work_order_no", ""),
        "last_erp_spec": lot_info.get("spec", ""),
    }


def lot_db_unset_fields(lot_info=None):
    fields = {
        "last_lot_no": "",
        "last_work_order_no": "",
        "last_product_name": "",
        "last_plan_qty": "",
        "last_product_spec": "",
    }
    return fields

# 🕒 한국 시간(KST) 전역 강제 설정 함수
def render_lot_lookup_box(context_key):
    st.markdown("#### K-System LOT 조회")

    prefix = f"KK{get_now_kst().year}"
    count_key = f"lot_count_{context_key}"
    lot_count = st.number_input(
        "LOT 품목 수",
        min_value=1,
        max_value=10,
        value=int(st.session_state.get(count_key, 1) or 1),
        step=1,
        key=count_key,
    )

    items = []
    for idx in range(int(lot_count)):
        row_no = idx + 1
        lot_info_key = f"lot_info_{context_key}_{idx}"

        col_prefix, col_tail, col_btn = st.columns([1.1, 2.0, 0.9])
        col_prefix.text_input("앞번호", value=prefix, disabled=True, key=f"lot_prefix_{context_key}_{idx}")
        tail = col_tail.text_input(
            f"LOT 뒷번호 {row_no}",
            placeholder="예: 0616031",
            key=f"lot_tail_{context_key}_{idx}",
        )

        if col_btn.button("조회", key=f"lot_lookup_btn_{context_key}_{idx}"):
            work_order_no = build_ksi_work_order_no(tail, prefix)
            if not work_order_no:
                st.warning("LOT 뒷번호를 입력해 주세요.")
            else:
                info, message = lookup_ksi_lot_info(work_order_no)
                if info:
                    info["lookup_ok"] = True
                    info["lookup_error"] = ""
                    st.session_state[lot_info_key] = info
                    st.success(f"LOT {row_no} 조회 성공")
                else:
                    st.session_state[lot_info_key] = {
                        "work_order_no": work_order_no,
                        "product_name": "",
                        "spec": "",
                        "plan_qty": "",
                        "lookup_ok": False,
                        "lookup_error": message,
                    }
                    st.warning(message)

        lot_info = st.session_state.get(lot_info_key, {})
        work_order_no = lot_info.get("work_order_no") or build_ksi_work_order_no(tail, prefix)
        tail_entered = bool(str(tail or "").strip())
        display_spec = str(lot_info.get("spec", "") or "").strip()
        spec = st.text_input(
            f"ERP 규격(spec) {row_no}",
            value=display_spec,
            disabled=True,
            key=f"lot_spec_{context_key}_{idx}_{work_order_no}_{display_spec}",
        )

        items.append({
            "work_order_no": work_order_no,
            "product_name": "",
            "spec": display_spec or spec.strip(),
            "plan_qty": "",
            "lookup_ok": bool(lot_info.get("lookup_ok")),
            "lookup_error": lot_info.get("lookup_error", ""),
            "tail_entered": tail_entered,
        })

    valid_items = [item for item in items if item.get("lookup_ok") and item.get("spec")]
    first = valid_items[0] if valid_items else (items[0] if items else {})
    return {
        "items": items,
        "expected_count": int(lot_count),
        "work_order_no": first.get("work_order_no", ""),
        "product_name": "",
        "spec": first.get("spec", ""),
        "plan_qty": "",
        "lookup_ok": bool(valid_items) and len(valid_items) == int(lot_count),
        "lookup_error": first.get("lookup_error", ""),
        "tail_entered": any(item.get("tail_entered") for item in items),
        "lot_not_required": False,
    }


def lot_valid_items(lot_info):
    if not lot_info:
        return []
    source_items = lot_info.get("items")
    if source_items is None:
        source_items = [lot_info]
    return [
        {
            "lot_no": str(item.get("work_order_no", "")).strip(),
            "spec": str(item.get("spec", "")).strip(),
        }
        for item in source_items
        if item.get("lookup_ok") and str(item.get("spec", "")).strip()
    ]


def ensure_lot_lookup_ready(lot_info):
    if not lot_info:
        return True
    if lot_info.get("lot_not_required"):
        return True
    items = lot_info.get("items") or [lot_info]
    expected_count = int(lot_info.get("expected_count") or len(items) or 1)
    any_tail_entered = any(item.get("tail_entered") for item in items)
    if not any_tail_entered and expected_count == 1:
        return True
    if len(lot_valid_items(lot_info)) == expected_count:
        return True
    if expected_count > 1:
        st.error("LOT 품목 수를 2개 이상으로 선택했다면 각 LOT를 모두 입력하고 ERP 조회가 성공해야 저장할 수 있습니다.")
        return False
    st.error("LOT 번호를 입력했다면 ERP 조회가 성공해야 저장할 수 있습니다.")
    return False


def format_lot_log(lot_info):
    if lot_info and lot_info.get("lot_not_required"):
        return ", ERP LOT:없음"
    valid_items = lot_valid_items(lot_info)
    if not valid_items:
        return ""
    if len(valid_items) == 1:
        item = valid_items[0]
        if item["lot_no"]:
            return f", ERP LOT:{item['lot_no']}, ERP규격:{item['spec']}"
        return f", ERP규격:{item['spec']}"
    item_text = " / ".join(
        f"[{idx}] LOT:{item['lot_no']}, ERP규격:{item['spec']}"
        for idx, item in enumerate(valid_items, start=1)
    )
    return f", ERP LOT 품목:{item_text}"


def lot_db_fields(lot_info):
    valid_items = lot_valid_items(lot_info)
    if not valid_items:
        return {}
    first = valid_items[0]
    lot_list = [item["lot_no"] for item in valid_items if item.get("lot_no")]
    spec_list = [item["spec"] for item in valid_items if item.get("spec")]
    return {
        "last_erp_lot_no": first["lot_no"],
        "last_erp_spec": first["spec"],
        "last_erp_items": valid_items,
        "last_erp_lot_list": lot_list,
        "last_erp_spec_list": spec_list,
        "last_erp_lot_text": " / ".join(lot_list),
        "last_erp_spec_text": " / ".join(spec_list),
    }


def lot_db_unset_fields(lot_info=None):
    fields = {
        "last_lot_no": "",
        "last_work_order_no": "",
        "last_product_name": "",
        "last_plan_qty": "",
        "last_product_spec": "",
    }
    return fields


def render_lot_lookup_box(context_key):
    st.markdown("#### K-System LOT 조회")

    no_lot_key = f"lot_not_required_{context_key}"
    if st.checkbox("LOT 없음 / 수리품 등 ERP 품목 없이 저장", key=no_lot_key):
        st.info("LOT 정보 없이 저장합니다.")
        return {
            "items": [],
            "expected_count": 0,
            "work_order_no": "",
            "product_name": "",
            "spec": "",
            "plan_qty": "",
            "lookup_ok": True,
            "lookup_error": "",
            "tail_entered": False,
            "lot_not_required": True,
        }

    prefix = f"KK{get_now_kst().year}"
    count_key = f"lot_count_{context_key}"
    lot_count = st.number_input(
        "LOT 품목 수",
        min_value=1,
        max_value=10,
        value=int(st.session_state.get(count_key, 1) or 1),
        step=1,
        key=count_key,
    )

    items = []
    for idx in range(int(lot_count)):
        row_no = idx + 1
        lot_info_key = f"lot_info_{context_key}_{idx}"

        col_prefix, col_tail, col_btn = st.columns([1.1, 2.0, 0.9])
        col_prefix.text_input("앞번호", value=prefix, disabled=True, key=f"lot_prefix_{context_key}_{idx}")
        tail = col_tail.text_input(
            f"LOT 뒷번호 {row_no}",
            placeholder="예: 0616031",
            key=f"lot_tail_{context_key}_{idx}",
        )

        if col_btn.button("조회", key=f"lot_lookup_btn_{context_key}_{idx}"):
            work_order_no = build_ksi_work_order_no(tail, prefix)
            if not work_order_no:
                st.warning("LOT 뒷번호를 입력해 주세요.")
            else:
                info, message = lookup_ksi_lot_info(work_order_no)
                if info:
                    info["lookup_ok"] = True
                    info["lookup_error"] = ""
                    st.session_state[lot_info_key] = info
                    st.success(f"LOT {row_no} 조회 성공")
                else:
                    st.session_state[lot_info_key] = {
                        "work_order_no": work_order_no,
                        "product_name": "",
                        "spec": "",
                        "plan_qty": "",
                        "lookup_ok": False,
                        "lookup_error": message,
                    }
                    st.warning(message)

        lot_info = st.session_state.get(lot_info_key, {})
        work_order_no = lot_info.get("work_order_no") or build_ksi_work_order_no(tail, prefix)
        tail_entered = bool(str(tail or "").strip())
        display_spec = str(lot_info.get("spec", "") or "").strip()
        spec = st.text_input(
            f"ERP 규격(spec) {row_no}",
            value=display_spec,
            disabled=True,
            key=f"lot_spec_{context_key}_{idx}_{work_order_no}_{display_spec}",
        )

        items.append({
            "work_order_no": work_order_no,
            "product_name": "",
            "spec": display_spec or spec.strip(),
            "plan_qty": "",
            "lookup_ok": bool(lot_info.get("lookup_ok")),
            "lookup_error": lot_info.get("lookup_error", ""),
            "tail_entered": tail_entered,
        })

    valid_items = [item for item in items if item.get("lookup_ok") and item.get("spec")]
    first = valid_items[0] if valid_items else (items[0] if items else {})
    return {
        "items": items,
        "expected_count": int(lot_count),
        "work_order_no": first.get("work_order_no", ""),
        "product_name": "",
        "spec": first.get("spec", ""),
        "plan_qty": "",
        "lookup_ok": bool(valid_items) and len(valid_items) == int(lot_count),
        "lookup_error": first.get("lookup_error", ""),
        "tail_entered": any(item.get("tail_entered") for item in items),
        "lot_not_required": False,
    }


def lot_valid_items(lot_info):
    if not lot_info or lot_info.get("lot_not_required"):
        return []
    source_items = lot_info.get("items")
    if source_items is None:
        source_items = [lot_info]
    return [
        {
            "lot_no": str(item.get("work_order_no", "")).strip(),
            "spec": str(item.get("spec", "")).strip(),
        }
        for item in source_items
        if item.get("lookup_ok") and str(item.get("spec", "")).strip()
    ]


def ensure_lot_lookup_ready(lot_info):
    if not lot_info or lot_info.get("lot_not_required"):
        return True
    items = lot_info.get("items") or [lot_info]
    expected_count = int(lot_info.get("expected_count") or len(items) or 1)
    any_tail_entered = any(item.get("tail_entered") for item in items)
    if not any_tail_entered and expected_count == 1:
        return True
    if len(lot_valid_items(lot_info)) == expected_count:
        return True
    if expected_count > 1:
        st.error("LOT 품목 수를 2개 이상으로 선택했다면 각 LOT를 모두 입력하고 ERP 조회가 성공해야 저장할 수 있습니다.")
        return False
    st.error("LOT 번호를 입력했다면 ERP 조회가 성공해야 저장할 수 있습니다.")
    return False


def format_lot_log(lot_info):
    if lot_info and lot_info.get("lot_not_required"):
        return ", ERP LOT:없음"
    valid_items = lot_valid_items(lot_info)
    if not valid_items:
        return ""
    if len(valid_items) == 1:
        item = valid_items[0]
        if item["lot_no"]:
            return f", ERP LOT:{item['lot_no']}, ERP규격:{item['spec']}"
        return f", ERP규격:{item['spec']}"
    item_text = " / ".join(
        f"[{idx}] LOT:{item['lot_no']}, ERP규격:{item['spec']}"
        for idx, item in enumerate(valid_items, start=1)
    )
    return f", ERP LOT 목록:{item_text}"


def lot_db_fields(lot_info):
    valid_items = lot_valid_items(lot_info)
    if not valid_items:
        return {}
    first = valid_items[0]
    lot_list = [item["lot_no"] for item in valid_items if item.get("lot_no")]
    spec_list = [item["spec"] for item in valid_items if item.get("spec")]
    return {
        "last_erp_lot_no": first["lot_no"],
        "last_erp_spec": first["spec"],
        "last_erp_items": valid_items,
        "last_erp_lot_list": lot_list,
        "last_erp_spec_list": spec_list,
        "last_erp_lot_text": " / ".join(lot_list),
        "last_erp_spec_text": " / ".join(spec_list),
    }


def lot_db_unset_fields(lot_info=None):
    fields = {
        "last_lot_no": "",
        "last_work_order_no": "",
        "last_product_name": "",
        "last_plan_qty": "",
        "last_product_spec": "",
    }
    return fields


def disposal_lot_db_fields(lot_info, serial_no=None, tool_doc=None, form_data=None):
    valid_items = lot_valid_items(lot_info)
    if valid_items:
        first = valid_items[0]
        lot_list = [item["lot_no"] for item in valid_items if item.get("lot_no")]
        spec_list = [item["spec"] for item in valid_items if item.get("spec")]
        return {
            "erp_items": valid_items,
            "erp_lot_no": first.get("lot_no", ""),
            "erp_spec": first.get("spec", ""),
            "erp_lot_list": lot_list,
            "erp_spec_list": spec_list,
            "erp_lot_text": " / ".join(lot_list),
            "erp_spec_text": " / ".join(spec_list),
        }

    sources = []
    if serial_no:
        try:
            previous_log = db_collection.database['disposal_logs'].find_one(
                {
                    "serial_no": serial_no,
                    "$or": [
                        {"erp_lot_no": {"$nin": ["", None]}},
                        {"erp_spec": {"$nin": ["", None]}},
                        {"erp_lot_list": {"$exists": True, "$ne": []}},
                        {"erp_spec_list": {"$exists": True, "$ne": []}},
                    ],
                },
                sort=[("disposal_date", -1)],
            )
            if previous_log:
                sources.append(previous_log)
        except Exception:
            pass

    for source in (tool_doc, form_data):
        if source:
            sources.append(source)

    field_map = {
        "erp_items": ("erp_items", "last_erp_items"),
        "erp_lot_no": ("erp_lot_no", "last_erp_lot_no"),
        "erp_spec": ("erp_spec", "last_erp_spec"),
        "erp_lot_list": ("erp_lot_list", "last_erp_lot_list"),
        "erp_spec_list": ("erp_spec_list", "last_erp_spec_list"),
        "erp_lot_text": ("erp_lot_text", "last_erp_lot_text"),
        "erp_spec_text": ("erp_spec_text", "last_erp_spec_text"),
    }
    preserved = {}
    for source in sources:
        for target_key, source_keys in field_map.items():
            if target_key in preserved:
                continue
            for source_key in source_keys:
                value = source.get(source_key)
                if value not in (None, "", []):
                    preserved[target_key] = value
                    break
    return preserved


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


MATERIAL_MENU_LABEL = "📦 원자재 입고 정보"
MATERIAL_COLLECTION_NAME = "material_receiving_logs"

MATERIAL_RECEIVER_MAP = {
    "01": "서재욱",
    "02": "서동일",
    "03": "정광우",
    "04": "정우철",
    "05": "강영천",
    "06": "허진웅",
    "07": "김연용",
    "08": "이덕무",
    "09": "홍민기",
    "10": "이해근",
    "11": "노재학",
    "12": "변두학",
    "13": "이동주",
    "14": "이현준",
    "15": "최광식",
    "16": "한제훈",
    "17": "한건우",
    "18": "이승형",
    "19": "유관우",
    "20": "신재관",
    "21": "최인준",
    "22": "김성욱",
    "23": "김은호",
    "24": "문태수",
    "25": "엄현석",
    "26": "김영환",
    "27": "나윤호",
    "28": "권용수",
    "29": "노우석",
    "30": "박철환",
}


def get_material_collection():
    return db_collection.database[MATERIAL_COLLECTION_NAME]


def to_int_safe(value, default=0):
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def normalize_material_lot_text(raw_text):
    text = str(raw_text or "").strip().upper().replace(" ", "")
    if not text:
        return ""
    return build_ksi_work_order_no(text)


def normalize_material_receiver_no(value):
    digits = re.sub(r"\D", "", str(value or ""))
    if not digits:
        return ""
    if len(digits) <= 2:
        return digits.zfill(2)
    return digits


def get_material_received_total(lot_no):
    if not lot_no:
        return 0

    pipeline = [
        {"$match": {"lot_no": lot_no}},
        {"$group": {"_id": "$lot_no", "total": {"$sum": "$received_qty"}}},
    ]
    result = list(get_material_collection().aggregate(pipeline))
    return to_int_safe(result[0].get("total"), 0) if result else 0


def build_material_search_query(keyword):
    keyword = str(keyword or "").strip()
    if not keyword:
        return {}

    fields = ["lot_no", "product_name", "spec", "receiver_name", "memo"]
    tokens = [token for token in re.split(r"\s+", keyword) if token]
    token_queries = []
    for token in tokens:
        safe_token = re.escape(token)
        token_queries.append({
            "$or": [
                {field: {"$regex": safe_token, "$options": "i"}}
                for field in fields
            ]
        })

    return {"$and": token_queries} if len(token_queries) > 1 else token_queries[0]


def get_material_records(keyword="", limit=500):
    query = build_material_search_query(keyword)
    return list(get_material_collection().find(query).sort("created_at", -1).limit(limit))


def get_material_receiver_options():
    return [f"{no} - {name}" for no, name in MATERIAL_RECEIVER_MAP.items()]


def parse_material_receiver_option(option):
    text = str(option or "")
    receiver_no = text.split(" - ", 1)[0].strip()
    return receiver_no, MATERIAL_RECEIVER_MAP.get(receiver_no, "")


def rerun_app():
    if hasattr(st, "rerun"):
        st.rerun()
    st.experimental_rerun()


def material_query_param(name):
    try:
        value = st.query_params.get(name, "")
    except Exception:
        try:
            value = st.experimental_get_query_params().get(name, "")
        except Exception:
            return ""
    if isinstance(value, list):
        return str(value[0]) if value else ""
    return str(value or "")


def clear_material_query_params():
    try:
        for key in ("material_qr", "material_scan"):
            if key in st.query_params:
                del st.query_params[key]
    except Exception:
        pass


def reset_material_live_lookup_state():
    for key in (
        "material_live_lot",
        "material_live_lookup",
        "material_live_message",
        "material_received_qty_live",
        "material_memo_live",
        "material_receive_date_live",
        "material_product_name_live",
        "material_spec_live",
        "material_plan_qty_live",
    ):
        if key in st.session_state:
            del st.session_state[key]


def apply_material_lot_lookup(raw_lot, source_label="QR"):
    lot_no = normalize_material_lot_text(raw_lot)
    for key in (
        "material_received_qty_live",
        "material_memo_live",
        "material_receive_date_live",
        "material_product_name_live",
        "material_spec_live",
        "material_plan_qty_live",
    ):
        if key in st.session_state:
            del st.session_state[key]

    st.session_state.material_live_lot = lot_no
    st.session_state.material_live_lookup = {}

    if not lot_no:
        st.session_state.material_live_message = ("warning", "LOT 번호를 읽지 못했습니다.")
        return

    try:
        info, message = lookup_ksi_lot_info(lot_no)
    except Exception as exc:
        info, message = None, f"K-System LOT 조회 오류: {exc}"

    if info and info.get("lookup_ok"):
        st.session_state.material_live_lookup = info
        st.session_state.material_live_message = ("success", f"{source_label} 조회 성공: {lot_no}")
        return

    st.session_state.material_live_lookup = {
        "lookup_ok": False,
        "work_order_no": lot_no,
        "product_name": "",
        "spec": "",
        "plan_qty": 0,
    }
    st.session_state.material_live_message = (
        "warning",
        message or f"{lot_no} 조회 결과가 없습니다. 필요하면 수동 정보로 저장하세요.",
    )


def render_material_qr_scanner():
    components.html(
        """
        <div style="max-width:560px;margin:0 auto;">
          <div id="material-qr-reader" style="width:100%;min-height:320px;border:1px solid #d8dee9;border-radius:8px;overflow:hidden;"></div>
          <div id="material-qr-status" style="margin-top:10px;padding:10px 12px;border-radius:8px;background:#eef6ff;color:#174ea6;font-size:15px;">
            카메라를 준비 중입니다. 권한 요청이 나오면 허용을 눌러주세요.
          </div>
        </div>
        <script src="https://unpkg.com/html5-qrcode@2.3.8/html5-qrcode.min.js"></script>
        <script>
        (function () {
          const statusBox = document.getElementById("material-qr-status");
          function setStatus(text) {
            if (statusBox) statusBox.textContent = text;
          }
          function escapeHtml(text) {
            return String(text).replace(/[&<>"']/g, function (ch) {
              return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[ch];
            });
          }
          function buildResultUrl(decodedText) {
            let baseHref = window.location.href;
            try {
              if (window.parent && window.parent.location && window.parent.location.href) {
                baseHref = window.parent.location.href;
              }
            } catch (e) {}
            const url = new URL(baseHref);
            url.searchParams.set("material_qr", decodedText);
            url.searchParams.set("material_scan", String(Date.now()));
            return url.toString();
          }
          function showFallback(decodedText, nextUrl) {
            if (!statusBox) return;
            const safeUrl = String(nextUrl).replace(/"/g, "&quot;");
            statusBox.innerHTML =
              "QR 인식 완료: " + escapeHtml(decodedText) +
              "<br><a id='material-qr-go' href=\"" + safeUrl + "\" target=\"_top\" " +
              "style=\"display:inline-block;margin-top:8px;color:#174ea6;font-weight:700;text-decoration:underline;\">" +
              "자동 조회가 안 되면 여기를 누르세요</a>";
          }
          function sendResult(decodedText) {
            const nextUrl = buildResultUrl(decodedText);
            showFallback(decodedText, nextUrl);
            setTimeout(function () {
              const link = document.getElementById("material-qr-go");
              if (link) link.click();
            }, 150);
            try { window.open(nextUrl, "_top"); } catch (e) {}
            try { window.top.location.assign(nextUrl); } catch (e) {}
            try { window.parent.location.assign(nextUrl); } catch (e) {}
          }
          function startScanner() {
            if (!window.Html5Qrcode) {
              setTimeout(startScanner, 300);
              return;
            }
            const scanner = new Html5Qrcode("material-qr-reader");
            scanner.start(
              { facingMode: "environment" },
              { fps: 10, qrbox: { width: 260, height: 260 }, aspectRatio: 1.0 },
              function(decodedText) {
                setStatus("QR 인식 완료: " + decodedText);
                scanner.stop()
                  .then(function(){ sendResult(decodedText); })
                  .catch(function(){ sendResult(decodedText); });
              },
              function() {}
            ).then(function(){
              setStatus("카메라 실행 중입니다. 도면 QR을 화면 안에 맞춰주세요.");
            }).catch(function(){
              setStatus("카메라를 열지 못했습니다. 브라우저 카메라 권한을 허용하거나 수동 입력을 사용하세요.");
            });
          }
          startScanner();
        })();
        </script>
        """,
        height=520,
    )


def show_material_receiving_page_live_qr():
    st.title("📦 원자재 입고 정보")
    st.caption("작업자를 선택한 뒤 도면 QR을 스캔하면 K-System LOT 정보를 자동 조회합니다.")

    scanned_text = material_query_param("material_qr")
    scan_nonce = material_query_param("material_scan")
    if scanned_text and scan_nonce and scan_nonce != st.session_state.get("material_last_scan_nonce"):
        st.session_state.material_last_scan_nonce = scan_nonce
        apply_material_lot_lookup(scanned_text, "QR")
        clear_material_query_params()
        rerun_app()

    saved_message = st.session_state.get("material_live_saved_message", "")
    if saved_message:
        st.success(saved_message)
        st.session_state.material_live_saved_message = ""

    receiver_options = get_material_receiver_options()
    selected_receiver = st.selectbox("입고 작업자", receiver_options, key="material_live_receiver")
    receiver_no, receiver_name = parse_material_receiver_option(selected_receiver)

    input_tab, search_tab = st.tabs(["📷 QR 입고", "🔍 입고 검색"])

    with input_tab:
        st.info(f"현재 작업자: {receiver_no} {receiver_name}")
        render_material_qr_scanner()

        with st.expander("카메라가 안 될 때 수동 LOT 입력"):
            manual_lot = st.text_input(
                "LOT 번호",
                placeholder="예: KK20260703080 또는 0703080",
                key="material_manual_lot_live",
            )
            if st.button("수동 LOT 조회", key="material_manual_lookup_live"):
                apply_material_lot_lookup(manual_lot, "수동")
                rerun_app()

        message_type, message_text = st.session_state.get("material_live_message", ("info", ""))
        if message_text:
            getattr(st, message_type, st.info)(message_text)

        lot_no = st.session_state.get("material_live_lot", "")
        if not lot_no:
            st.info("도면 QR을 카메라에 비추면 자동 조회됩니다.")
        else:
            lookup_info = st.session_state.get("material_live_lookup", {})
            product_name_default = str(lookup_info.get("product_name", "") or "")
            spec_default = str(lookup_info.get("spec", "") or "")
            plan_qty_default = to_int_safe(lookup_info.get("plan_qty"), 0)
            received_total = get_material_received_total(lot_no)
            default_received_qty = max(plan_qty_default - received_total, 0) if plan_qty_default else 0

            st.markdown("#### 조회된 입고 정보")
            cols = st.columns(4)
            cols[0].metric("LOT", lot_no)
            cols[1].metric("K-System 수량", plan_qty_default)
            cols[2].metric("기존 입고 합계", received_total)
            cols[3].metric("남은 수량", max(plan_qty_default - received_total, 0) if plan_qty_default else 0)

            with st.form("material_live_receiving_form"):
                st.text_input("LOT", value=lot_no, disabled=True)
                product_name = st.text_input("품명", value=product_name_default, key="material_product_name_live")
                spec = st.text_input("규격", value=spec_default, key="material_spec_live")

                qty_cols = st.columns(3)
                with qty_cols[0]:
                    plan_qty = st.number_input(
                        "K-System 수량",
                        min_value=0,
                        value=plan_qty_default,
                        step=1,
                        key="material_plan_qty_live",
                    )
                with qty_cols[1]:
                    st.number_input(
                        "기존 입고 합계",
                        min_value=0,
                        value=received_total,
                        step=1,
                        disabled=True,
                        key="material_received_total_live",
                    )
                with qty_cols[2]:
                    received_qty = st.number_input(
                        "이번 입고 수량",
                        min_value=0,
                        value=default_received_qty,
                        step=1,
                        key="material_received_qty_live",
                    )

                receive_date = st.date_input(
                    "입고 날짜",
                    value=get_now_kst().date(),
                    key="material_receive_date_live",
                )
                memo = st.text_area(
                    "메모",
                    placeholder="부분 입고, 수량 차이, 특이사항",
                    key="material_memo_live",
                )
                submitted = st.form_submit_button("✅ 저장 후 다음 QR 스캔")

            if submitted:
                if not receiver_no or not receiver_name.strip():
                    st.error("작업자를 선택해 주세요.")
                elif not lot_no:
                    st.error("LOT 번호가 없습니다.")
                elif received_qty <= 0:
                    st.error("이번 입고 수량은 1개 이상이어야 합니다.")
                else:
                    now_kst = get_now_kst()
                    received_total_after = received_total + int(received_qty)
                    doc = {
                        "lot_no": lot_no,
                        "product_name": product_name.strip(),
                        "spec": spec.strip(),
                        "plan_qty": int(plan_qty),
                        "received_qty": int(received_qty),
                        "received_total_before": int(received_total),
                        "received_total_after": int(received_total_after),
                        "receive_date": str(receive_date),
                        "receiver_no": receiver_no,
                        "receiver_name": receiver_name,
                        "memo": memo.strip(),
                        "source": "qr_live" if lookup_info.get("lookup_ok") else "manual_or_not_found",
                        "created_at": now_kst.strftime("%Y-%m-%d %H:%M:%S"),
                    }
                    get_material_collection().insert_one(doc)
                    reset_material_live_lookup_state()
                    st.session_state.material_live_saved_message = (
                        f"{lot_no} 입고 {int(received_qty)}개 저장 완료. 다음 QR을 스캔하세요."
                    )
                    rerun_app()

    with search_tab:
        keyword = st.text_input(
            "검색어",
            placeholder="LOT, 품명 일부, 규격 일부, 인수자, 메모",
            key="material_search_keyword_live",
        )
        records = get_material_records(keyword)
        if not records:
            st.info("검색 결과가 없습니다.")
            return

        rows = []
        for item in records:
            rows.append(
                {
                    "입고일": item.get("receive_date", ""),
                    "LOT": item.get("lot_no", ""),
                    "품명": item.get("product_name", ""),
                    "규격": item.get("spec", ""),
                    "K-System수량": item.get("plan_qty", 0),
                    "입고수량": item.get("received_qty", 0),
                    "누적입고": item.get("received_total_after", 0),
                    "인수자": item.get("receiver_name", ""),
                    "메모": item.get("memo", ""),
                }
            )

        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.subheader("LOT별 입고 합계")
        summary = df.groupby(["LOT", "품명", "규격"], dropna=False)["입고수량"].sum().reset_index()
        st.dataframe(summary, use_container_width=True, hide_index=True)


def show_material_receiving_page():
    return show_material_receiving_page_live_qr()

    st.title("📦 원자재 입고 정보")
    st.caption("도면 QR의 LOT를 조회해서 원자재 입고 내역을 별도로 저장합니다. 툴 관리 기록과는 아직 연결하지 않습니다.")

    input_tab, search_tab = st.tabs(["📥 입고 등록", "🔍 입고 검색"])

    with input_tab:
        if "material_scan_mode" not in st.session_state:
            st.session_state.material_scan_mode = False
        if "material_scan_counter" not in st.session_state:
            st.session_state.material_scan_counter = 0

        saved_message = st.session_state.get("material_last_saved_message", "")
        if saved_message:
            st.success(saved_message)
            st.session_state.material_last_saved_message = ""

        st.subheader("1. 인수자 선택")
        c1, c2 = st.columns(2)
        with c1:
            receiver_no_raw = st.text_input("인수자 번호", placeholder="예: 02", key="material_receiver_no")
        receiver_no = normalize_material_receiver_no(receiver_no_raw)
        auto_receiver_name = MATERIAL_RECEIVER_MAP.get(receiver_no, "")
        with c2:
            if auto_receiver_name:
                st.text_input("인수자 이름", value=auto_receiver_name, disabled=True, key="material_receiver_name_auto")
                receiver_name = auto_receiver_name
            else:
                receiver_name = st.text_input("인수자 이름", placeholder="번호 미등록 시 직접 입력", key="material_receiver_name")

        if receiver_no_raw.strip() and not auto_receiver_name:
            st.warning("등록되지 않은 인수자 번호입니다. 번호를 확인하거나 이름을 직접 입력하세요.")

        st.subheader("2. QR 스캔")
        scan_cols = st.columns([1, 1, 3])
        with scan_cols[0]:
            if st.button("📷 스캔 모드 시작", key="material_scan_start"):
                if not receiver_name.strip():
                    st.warning("인수자를 먼저 선택하거나 입력하세요.")
                else:
                    st.session_state.material_scan_mode = True
                    st.session_state.material_scan_counter += 1
                    st.session_state.material_lookup_info = {}
                    st.session_state.material_lookup_lot = ""
                    st.session_state.material_auto_lookup_lot = ""
                    st.rerun()
        with scan_cols[1]:
            if st.button("⏹ 스캔 모드 종료", key="material_scan_stop"):
                st.session_state.material_scan_mode = False
                st.session_state.material_lookup_info = {}
                st.session_state.material_lookup_lot = ""
                st.session_state.material_auto_lookup_lot = ""
                st.rerun()

        if st.session_state.material_scan_mode:
            st.info(f"스캔 모드 실행 중: {receiver_name.strip() or '인수자 미지정'} / QR을 찍으면 LOT가 자동 조회됩니다.")
        else:
            st.info("인수자를 먼저 선택한 뒤 스캔 모드 시작을 누르세요.")

        lot_input_key = f"material_lot_input_{st.session_state.material_scan_counter}"
        lot_raw = st.text_input(
            "QR 또는 LOT 번호",
            placeholder="예: KK20260703080 또는 0703080",
            key=lot_input_key,
            disabled=not st.session_state.material_scan_mode,
        )
        lot_no = normalize_material_lot_text(lot_raw)

        if st.button("LOT 조회", key="material_lookup_button", disabled=not st.session_state.material_scan_mode):
            if not lot_no:
                st.warning("LOT 번호를 먼저 입력하거나 QR 값을 붙여넣어 주세요.")
            else:
                info, message = lookup_ksi_lot_info(lot_no)
                st.session_state.material_lookup_lot = lot_no
                if info and info.get("lookup_ok"):
                    st.session_state.material_lookup_info = info
                    st.success(f"{lot_no} 조회 성공")
                else:
                    st.session_state.material_lookup_info = {}
                    st.warning(message or "K-System에서 해당 LOT를 찾지 못했습니다. 필요하면 수동 저장을 사용하세요.")

        if not st.session_state.material_scan_mode:
            st.session_state.material_lookup_lot = ""
            st.session_state.material_lookup_info = {}
            st.session_state.material_auto_lookup_lot = ""
        elif not lot_no:
            st.session_state.material_lookup_lot = ""
            st.session_state.material_lookup_info = {}
            st.session_state.material_auto_lookup_lot = ""
        elif len(lot_no) >= 13 and lot_no != st.session_state.get("material_auto_lookup_lot", ""):
            info, message = lookup_ksi_lot_info(lot_no)
            st.session_state.material_auto_lookup_lot = lot_no
            st.session_state.material_lookup_lot = lot_no
            if info and info.get("lookup_ok"):
                st.session_state.material_lookup_info = info
                st.success(f"{lot_no} 자동 조회 성공")
            else:
                st.session_state.material_lookup_info = {}
                st.info(message or "K-System에서 해당 LOT를 찾지 못했습니다. 필요하면 수동 저장을 사용하세요.")

        lookup_info = st.session_state.get("material_lookup_info", {})
        lookup_lot = st.session_state.get("material_lookup_lot", "")
        if lot_no != lookup_lot:
            lookup_info = {}

        product_name_default = str(lookup_info.get("product_name", "") or "")
        spec_default = str(lookup_info.get("spec", "") or "")
        plan_qty_default = to_int_safe(lookup_info.get("plan_qty"), 0)
        received_total = get_material_received_total(lot_no)
        default_received_qty = max(plan_qty_default - received_total, 0) if plan_qty_default else 0

        if lot_no and received_total:
            st.info(f"현재 LOT 기존 입고 합계: {received_total}개")

        with st.form("material_receiving_form"):
            st.text_input("저장될 LOT", value=lot_no, disabled=True)
            product_name = st.text_input("품명", value=product_name_default)
            spec = st.text_input("규격", value=spec_default)

            qty_cols = st.columns(3)
            with qty_cols[0]:
                plan_qty = st.number_input("K-System 수량", min_value=0, value=plan_qty_default, step=1)
            with qty_cols[1]:
                st.number_input("기존 입고 합계", min_value=0, value=received_total, step=1, disabled=True)
            with qty_cols[2]:
                received_qty = st.number_input("이번 입고 수량", min_value=0, value=default_received_qty, step=1)

            receive_date = st.date_input("입고 날짜", value=get_now_kst().date())
            memo = st.text_area("메모", placeholder="부분 입고, 수량 차이, 특이사항 등을 적어두면 됩니다.")
            allow_manual = st.checkbox("K-System 조회 결과 없이 수동 정보로 저장합니다.")
            submitted = st.form_submit_button("✅ 원자재 입고 저장")

        if submitted:
            if not lot_no:
                st.error("LOT 번호는 반드시 필요합니다.")
                st.stop()
            if not receiver_name.strip():
                st.error("인수자를 먼저 선택하거나 입력하세요.")
                st.stop()
            if received_qty <= 0:
                st.error("이번 입고 수량은 1개 이상이어야 합니다.")
                st.stop()
            if not allow_manual and not lookup_info.get("lookup_ok"):
                st.error("먼저 LOT 조회에 성공하거나, 수동 저장 체크를 켜주세요.")
                st.stop()

            now_kst = get_now_kst()
            doc = {
                "lot_no": lot_no,
                "product_name": product_name.strip(),
                "spec": spec.strip(),
                "plan_qty": int(plan_qty),
                "received_qty": int(received_qty),
                "received_total_before": int(received_total),
                "received_total_after": int(received_total + received_qty),
                "receive_date": receive_date.strftime("%Y-%m-%d"),
                "receiver_no": receiver_no,
                "receiver_name": receiver_name.strip(),
                "memo": memo.strip(),
                "source": "k_system" if lookup_info.get("lookup_ok") else "manual",
                "created_at": now_kst,
            }
            get_material_collection().insert_one(doc)
            st.session_state.material_lookup_info = {}
            st.session_state.material_lookup_lot = ""
            st.session_state.material_auto_lookup_lot = ""
            st.session_state.material_scan_mode = True
            st.session_state.material_scan_counter += 1
            st.session_state.material_last_saved_message = f"{lot_no} 원자재 입고 {received_qty}개 저장 완료. 다음 LOT 스캔 대기 중입니다."
            st.rerun()

    with search_tab:
        keyword = st.text_input("LOT / 품명 / 규격 / 인수자 검색", key="material_search_keyword")
        records = get_material_records(keyword)
        if not records:
            st.info("검색된 원자재 입고 기록이 없습니다.")
            return

        rows = []
        for record in records:
            rows.append({
                "입고일": record.get("receive_date", ""),
                "LOT": record.get("lot_no", ""),
                "품명": record.get("product_name", ""),
                "규격": record.get("spec", ""),
                "K-System 수량": record.get("plan_qty", 0),
                "이번 입고": record.get("received_qty", 0),
                "누적 입고": record.get("received_total_after", ""),
                "인수자": record.get("receiver_name", ""),
                "메모": record.get("memo", ""),
            })

        df = pd.DataFrame(rows)
        st.dataframe(df, use_container_width=True, hide_index=True)

        summary = (
            df.groupby(["LOT", "품명", "규격", "K-System 수량"], dropna=False)["이번 입고"]
            .sum()
            .reset_index()
            .rename(columns={"이번 입고": "입고 합계"})
        )
        st.subheader("LOT별 입고 합계")
        st.dataframe(summary, use_container_width=True, hide_index=True)


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
    pop_count_confirmed = st.checkbox(f"가공수량 {pop_count}개 맞습니다.", key=f"confirm_pending_count_{s_no}")
    lot_info = render_lot_lookup_box(f"reuse_pending_{s_no}")
    
    if st.button("🚀 실적 기록 및 재사용대기 저장"):
        if not pop_count_confirmed:
            st.error(f"가공수량 {pop_count}개가 맞는지 확인 체크를 해주세요.")
            st.stop()
        if not ensure_lot_lookup_ready(lot_info):
            st.stop()

        log_now = get_now_kst()
        log_time_str = log_now.strftime("%Y-%m-%d %H:%M:%S")
        pop_mach_name = f"{pop_mach_num}호기"
        
        # [2단계 수정] 작업자 이름 부분에 pop_worker_name 사용
        auto_log_msg = f"\n[{log_time_str}] 상태: 재사용대기, (스펙: {ed_spec}), 작업자: {pop_worker_name}, 가공기계: {pop_mach_name}, 가공갯수: {pop_count}개{format_lot_log(lot_info)}"
        final_note_val = orig_note.strip() + auto_log_msg
        
        timestamp = log_now.strftime("%m/%d %H:%M")
        history_entry = f"{timestamp} - 상태변환:재사용대기 (작업자:{pop_worker_name}, {pop_mach_name}, {pop_count}개)"
        
        db_collection.update_one(
            {"serial_no": s_no},
            {"$set": {
                "status": "재사용대기",
                "worker": pop_worker_name,  # [2단계 추가] DB에도 작업자 저장
                "machine_no": pop_mach_name,
                "current_use": pop_count,
                "start_time": "-",
                "target_time": "-",
                "waste_date": "-",
                "note": final_note_val,
                "last_active_machine": pop_mach_name,
                "last_active_count": pop_count,
                "last_active_time": log_time_str,
                **lot_db_fields(lot_info)
            }, "$unset": lot_db_unset_fields(lot_info), "$push": {"history": history_entry}}
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
    pop_use_count_confirmed = st.checkbox(f"가공수량 {pop_use_count}개 맞습니다.", key=f"confirm_waste_count_{s_no}")
    lot_info = render_lot_lookup_box(f"waste_detail_{s_no}")


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
        if not pop_use_count_confirmed:
            add_error(f"⚠️ 가공수량 {pop_use_count}개가 맞는지 확인 체크를 해주세요.")
            st.stop()
        if not ensure_lot_lookup_ready(lot_info):
            st.stop()

        spec = db_collection.find_one({"serial_no": s_no}).get('spec_detail', '스펙없음')    
        log_now = get_now_kst()
        log_time_str = log_now.strftime("%Y-%m-%d %H:%M:%S")
        final_reason_text = detail_reason if chosen_reason == "5. 기타 (직접기입)" else chosen_reason
        
        
        auto_log_msg = f"\n[{log_time_str}] 상태: 폐기, 작업자: {pop_worker_name}, 스펙: {spec}, 가공기계: {pop_mach_name}, 사용갯수: {pop_use_count}개, 폐기사유: {final_reason_text}{format_lot_log(lot_info)}"
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
                "start_time": "-",
                "target_time": "-",
                "waste_date": log_time_str,
                "note": final_note_val,
                **lot_db_fields(lot_info)
            }, "$unset": lot_db_unset_fields(lot_info), "$push": {"history": history_entry}}
        )
        st.success("💥 툴 폐기 실적 처리가 안전하게 저장되었습니다.")
        time.sleep(1)
        st.rerun()



# --- 📱 [모바일/현장 QR 스캔 기입 모드] --------------------------------------------------------------------------------------------------------

# [최종 확인 팝업창 - 상태 대조 기능 포함]
@st.dialog("💾 데이터 최종 확인")
def confirm_and_save(serial, data):
    if not st.session_state.get('show_confirm_dialog', False):
        return
    same_status = data['status'] == data['prev_status']
    # 1. 상태 대조 및 강조 로직
    if not same_status:
        if data['status'] == "폐기":
            st.error(f"⚠️ 경고: [ {data['prev_status']} ] ➔ [ {data['status']} ] (으)로 변경합니다!")
        else:
            st.warning(f"🔄 알림: [ {data['prev_status']} ] ➔ [ {data['status']} ] (으)로 상태가 변경됩니다.")
    else:
        st.warning(f"선택한 상태가 현재 상태와 같습니다: [ {data['status']} ]")
        st.info("상태 변경 없이 작업자/기계/메모/LOT 정보만 저장할지 확인해주세요. 실수라면 아래 취소를 누르세요.")
    reason = data.get('disposal_reason', '사유 없음')
    st.markdown("---")
    # 2. 요약 정보
    st.write(f"- **작업자:** {data.get('worker', '정보 없음')}")
    st.write(f"- **기계 호기:** {data.get('machine_no', '정보 없음')}")
    st.write(f"- **세부 스펙:** {data.get('spec_detail', '스펙 정보 없음')}")


    if data['status'] == "폐기":
        reason = data.get('disposal_reason', '사유 없음')
        st.write(f"- **폐기 사유:** {reason}")
    
    qty = 0
    qty_confirmed = True
    qty_required = requires_qty_input(data['prev_status'], data['status'])
    lot_info = {}
    if qty_required:
        qty = st.number_input("📦 최종 가공 수량(개)", min_value=0, value=0, step=1)
        qty_confirmed = st.checkbox(f"최종 가공수량 {qty}개 맞습니다.", key=f"confirm_final_qty_{serial}")
        lot_info = render_lot_lookup_box(f"confirm_{serial}_{data['prev_status']}_{data['status']}")

    save_label = "✅ 상태 변경 없이 저장 진행" if same_status else "✅ 최종 확정 및 저장"
    if st.button(save_label):
        if not same_status:
            ok, msg = validate_process(data['prev_status'], data['status'])
            if not ok:
                st.error(msg)
                st.session_state['reset_u_status_to'] = data['prev_status']
                st.session_state['show_confirm_dialog'] = False
                st.stop()
        if not qty_confirmed:
            st.error(f"최종 가공수량 {qty}개가 맞는지 확인 체크를 해주세요.")
            st.stop()
        if qty_required and not ensure_lot_lookup_ready(lot_info):
            st.stop()

        final_note = data['note']
        if not same_status:
            now_str = get_now_kst().strftime("%Y-%m-%d %H:%M:%S")
            if data['status'] == "폐기":
                log = f"\n[{now_str}] 상태:폐기, 스펙:{data['spec_detail']}, 작업자:{data['worker']}, 기계:{data['machine_no']}"
                if qty > 0:
                    log += f", 최종수량:{qty}개" # 수량 이름을 '최종수량'으로 변경
                log += format_lot_log(lot_info)
            else:
                # 폐기가 아닐 때의 기본 로그
                log = f"\n[{now_str}] 상태:{data['status']}, 스펙:{data['spec_detail']}, 작업자:{data['worker']}, 기계:{data['machine_no']}"
                if qty > 0: log += f", 수량:{qty}개"
                log += format_lot_log(lot_info)
            
            final_note += log

        # 상태가 실제로 바뀔 때만 재고 수량을 계산합니다.
        if not same_status:
            update_inventory_count(data['spec_detail'], data.get('make', ''),data['prev_status'], data['status'])
            if data['status'] == "폐기":
                log_disposal(serial, data['spec_detail'], data.get('worker', ''), data.get('disposal_reason', '사유 없음'))

        db_collection.update_one(
            {"serial_no": serial},
            {"$set": {
                "status": data['status'],
                "worker": "" if data['status'] in ["사용전", "폐기"] else data['worker'],
                "machine_no": "" if data['status'] in ["사용전", "폐기"] else data['machine_no'],
                "note": final_note,
                "spec_detail": data['spec_detail'],
                "start_time": data['start_time'],
                "target_time": data['target_time'],
                **lot_db_fields(lot_info)
            }, "$unset": lot_db_unset_fields(lot_info)},
            upsert=True
        )
        st.success("✅ 저장 완료되었습니다!")
        time.sleep(1.0) 
        st.session_state['show_confirm_dialog'] = False
        st.rerun()

    if st.button("❌ 취소하고 전 상태로 돌아가기"):
        st.session_state['show_confirm_dialog'] = False
        st.session_state['reset_u_status_to'] = data['prev_status']
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
           
            unique_spec_names = sorted(list(set([s.get('spec_detail', '').strip() for s in specs if s.get('spec_detail')])))
            
            st.write(f"🔍 {target_type} 타입에 맞는 스펙 목록을 선택하세요:")

            # 4) 버튼 생성 루프 (760라인 근처)
      
            st.write("### 🛠 상세 스펙을 선택하세요")
            unique_spec_names = sorted(list(set([s.get('spec_detail', '').strip() for s in specs])))

            # 라디오 버튼은 값을 선택만 하고 저장을 수행하지 않습니다.
            selected_spec = st.radio("목록에서 스펙을 하나 선택하세요:", unique_spec_names, index=None, key="radio_spec")

            # 5) 선택된 경우에만 다음 단계 표시
            if selected_spec:
                st.success(f"✅ 선택된 스펙: {selected_spec}")
                st.session_state['selected_spec'] = selected_spec
                
                # 제조사 필터링
                matching_specs = [s for s in specs if s.get('spec_detail', '').strip() == selected_spec]
                available_makers = sorted(list(set([s.get('make') for s in matching_specs if s.get('make')])))
                
                selected_make = st.selectbox("🏭 제조사를 선택하세요", available_makers, key="maker_select")
                
                # '저장하기' 버튼을 여기서 명시적으로 누를 때만 동작
                if st.button("💾 이 내용으로 데이터 등록 저장"):
                    st.session_state['confirm_save'] = True
                    st.rerun()

            
            # [단계 3] 팝업 확인창 (최종 확정 단계)
            if st.session_state.get('confirm_save'):
                st.markdown("---")
                st.error("⚠️ 작업 내용을 최종 확인해주세요!")

                final_spec = st.session_state.get('selected_spec')
                final_make = st.session_state.get('maker_select')

                with st.container(border=True):
                    st.write("### 📝 등록 정보 확인")
                    
                    # 상세 스펙 강조
                    st.write("**상세 스펙**")
                    st.info(f"**{final_spec}**") # 배경색과 함께 볼드체로 강조
                    
                    # 제조사 강조
                    st.write(f"**제조사:** {final_make}")

                    # 저장 및 초기화 버튼을 가로로 배치 (선택의 명확화)
                    btn_col1, btn_col2 = st.columns(2)

                    # 1. 확정 및 저장 버튼 (DB 로직 실행)
                    if btn_col1.button("✅ 진짜 저장", type="primary"):
                        # DB 업데이트 로직 (기존 로직 유지)
                        update_inventory_count(final_spec, final_make, "none", "사용전")
                        
                        db_collection.update_one(
                            {"serial_no": qr_scanned_serial},
                            {"$set": {"spec_detail": final_spec, "make": final_make, "status": "사용전"}}
                        )
                    
                        st.success("성공적으로 저장되었습니다!")
                        time.sleep(2.5)
                        # 모든 세션 초기화 (다음 작업을 위해)
                        for k in ['confirm_save', 'selected_spec', 'maker_select', 'radio_spec']:
                            if k in st.session_state: del st.session_state[k]
                        st.rerun()


                    # 2. 내용 틀림 시 초기화 (데이터 반영 없이 처음 단계로)
                    if btn_col2.button("❌ 내용이 틀림 (초기화)"):
                        for k in ['confirm_save', 'selected_spec', 'maker_select', 'radio_spec']:
                            if k in st.session_state: del st.session_state[k]
                        st.rerun()
                        
                
    if not existing_data.get('spec_detail'):
        st.info("💡 상세 스펙을 선택하면 상세 정보가 나타납니다.")
        st.stop()    

    # 2. 상세 스펙이 채워져 있을 때만 실행되는 기입창 코드
    prev_status = existing_data.get("status", "사용전")
    
    # 1008라인 근처
    def trigger_waste():
        next_status = st.session_state.get("u_status")
        if requires_waste_dialog(prev_status, next_status):
            # 여기서 serial과 data를 확실하게 세션에 박아넣습니다.
            st.session_state['temp_serial'] = qr_scanned_serial # 현재 시리얼 변수명으로 변경하세요
            st.session_state['temp_data'] = existing_data     # 현재 데이터 변수명으로 변경하세요
            st.session_state['show_waste_dialog'] = True
        else:
            st.session_state['show_waste_dialog'] = False

    st.markdown("### 🛠 툴 현재 상태")
    status_options = ["사용전", "사용중", "재사용", "재사용대기", "폐기"]
    idx = status_options.index(prev_status) if prev_status in status_options else 0
    reset_status = st.session_state.pop('reset_u_status_to', None)
    if reset_status in status_options:
        st.session_state['u_status'] = reset_status
    elif st.session_state.get('u_status') not in status_options:
        st.session_state['u_status'] = prev_status

    u_status = st.radio(
        "상태를 선택하세요", status_options, index=idx, key="u_status",
        on_change=trigger_waste, horizontal=True
    )
   

    # [중요] 사용자가 라디오 버튼을 바꾸기 직전의 상태를 기억함
    if 'last_known_status' not in st.session_state:
        st.session_state['last_known_status'] = prev_status

    # 팝업 호출부  
  
    if st.session_state.get('show_waste_dialog', False):
        waste_dialog(
            st.session_state.get('temp_serial'), 
            st.session_state.get('temp_data', {})
        )

    # [여기 추가!] 팝업이 닫히고 나서 성공 메시지를 띄워주는 로직입니다.
    if st.session_state.get('show_success_msg', False):
        st.success("✅ 폐기 정보가 저장되었습니다.")
        st.session_state['show_success_msg'] = False # 메시지를 딱 한 번만 보여주고 끕니다.
           
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
 

    st.markdown("### 📝 현장 특이사항")
    u_note = st.text_area("📝 현장 특이사항", value=existing_data.get('note', ''))
       


    if st.button("데이터 확인 및 저장", key="main_save_button"):
        if u_status != prev_status:
            ok, msg = validate_process(prev_status, u_status)
            if not ok:
                st.error(msg)
                st.session_state['reset_u_status_to'] = prev_status
                st.stop()

        st.session_state['last_confirmed_status'] = u_status
        st.session_state['confirm_data'] = {
            'status': u_status,
            'prev_status': prev_status,
            'worker': u_worker,
            'machine_no': f'{int(u_machine):02d}호기', 
            'spec_detail': u_spec,
            'note': u_note,
            'start_time': "-",
            'make': existing_data.get('make', ''),
            'target_time': "-",
            'disposal_reason': st.session_state.get('waste_reason_data', '')
        }

        if requires_waste_dialog(prev_status, u_status):
            st.session_state['temp_serial'] = qr_scanned_serial
            st.session_state['temp_data'] = existing_data
            st.session_state['show_waste_dialog'] = True
            st.rerun()
        else:
            st.session_state['show_confirm_dialog'] = True
            st.rerun()
   

    # [추가된 부분] 팝업 호출 트리거
    if st.session_state.get('show_confirm_dialog'):
        confirm_and_save(qr_scanned_serial, st.session_state['confirm_data'])

    if st.button("🏠 메인으로 돌아가기"):
        st.query_params.clear(); st.rerun()




# --- 💻 [PC 관리자 모드] -----------------------------------------------------------------------------------------------------------------------------
else:
    st.session_state.sidebar_errors = []
    st.sidebar.markdown("## 📁 KKQ 통합 시스템")
    menu_options = ["📊 빈데이터 QR코드 대량 선발행", "📂 전체 데이터 현황판", "⚙️ 데이터 수정 / 삭제 / QR 재발행", "🖥️ 실시간 기계 정보창","🔧 툴 상세스펙 마스터 관리","🔍 툴 재고 검색 및 인쇄","📅 날짜별 툴 현황"]
    all_menu_options = menu_options + [MATERIAL_MENU_LABEL]
    if "sidebar_choice" not in st.session_state:
        st.session_state.sidebar_choice = menu_options[0]
    elif st.session_state.sidebar_choice not in all_menu_options:
        st.session_state.sidebar_choice = menu_options[0]

    def sync_tool_sidebar_choice():
        st.session_state.sidebar_choice = st.session_state.tool_sidebar_choice

    selected_tool_index = (
        menu_options.index(st.session_state.sidebar_choice)
        if st.session_state.sidebar_choice in menu_options
        else 0
    )

    st.sidebar.radio(
        "하위 목록",
        menu_options,
        index=selected_tool_index,
        key="tool_sidebar_choice",
        on_change=sync_tool_sidebar_choice,
    )

    st.sidebar.markdown(
        "<div style='height: 44px'></div>"
        "<hr style='margin: 0 0 18px 0; border: 0; border-top: 1px solid #d8dee9;'>",
        unsafe_allow_html=True,
    )
    st.sidebar.markdown("### 📦 원자재")
    if st.sidebar.button(MATERIAL_MENU_LABEL, key="material_menu_button", use_container_width=True):
        st.session_state.sidebar_choice = MATERIAL_MENU_LABEL
        st.rerun()

    tool_menu = st.session_state.sidebar_choice
    
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
                    "start_time": "-",
                    "target_time": "-",
                    "use_limit": 100,
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
            st.session_state.initial_blank_record = blank_records


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
                                #db_collection.delete_many({})
                                st.session_state.reset_message = "💥 전체 데이터베이스 항목 초기화 처리가 완벽하게 끝났습니다! 전체 리셋이 완료되었습니다."
                            else:
                                today_str = get_now_kst().strftime('%Y%m%d')
                                code_prefix = target_reset_code.split(" ")[0]
                                search_pattern = f"^{code_prefix}{today_str}"
                                current_db = db_collection.database
        
                                serials_to_delete = list(db_collection.find({"serial_no": {"$regex": search_pattern}}))
                                if not serials_to_delete:
                                    st.warning("오늘 발행된 해당 대분류 툴 데이터가 없습니다.")
                                else:    
                                    for item in serials_to_delete:
                                        # tools_management 데이터에서 제조사(make)와 상세스펙(spec_detail)을 가져옵니다.
                                        make_val = item.get("make")
                                        detail_val = item.get("spec_detail")
                                        if make_val and detail_val:
                                            target = current_db['tool_specs_master'].find_one({"make": make_val, "spec_detail": detail_val})
                                            
                                            field_to_decrement = {
                                                "사용전": "new_tool_count",
                                                "재사용대기": "used_tool_count",
                                                "폐기": "disposed_tool_count",
                                            }.get(item.get("status"))

                                            if target and field_to_decrement: # 👈 field_to_decrement가 None이 아닐 때만 실행!
                                                current_db['tool_specs_master'].update_one(
                                                    {"_id": target["_id"], field_to_decrement: {"$gt": 0}}, 
                                                    {"$inc": {field_to_decrement: -1}}
                                                )
                                            else:
                                                # 만약 차감할 필드가 없다면(status가 사용중 등) 건너뜁니다.
                                                print(f"재고 차감 대상 아님: {item.get('status')}")
                    

                                    delete_result = db_collection.delete_many({"serial_no": {"$regex": search_pattern}})
                                    st.session_state.reset_message = f"{target_reset_code} 오늘자 데이터 {delete_result.deleted_count}개 삭제 및 상세 재고(제조사/스펙 기준) 차감 완료!"

 
                            
                            st.session_state.show_qr_grid = False
                            st.session_state.current_view_serials = []
                            st.session_state.reset_success = True
                            time.sleep(2)
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
                                # [추가] 삭제 직전에 재고를 먼저 차감하는 로직
                                item_to_delete = db_collection.find_one({"serial_no": target_single_serial})
                                if item_to_delete:
                                    make_val = item_to_delete.get("make")
                                    detail_val = item_to_delete.get("spec_detail")
                                    status_val = item_to_delete.get("status")
                                    if make_val and detail_val:
                                        delete_count_field = {
                                            "사용전": "new_tool_count",
                                            "재사용대기": "used_tool_count",
                                            "폐기": "disposed_tool_count",
                                        }.get(status_val)

                                        if delete_count_field:
                                            db_collection.database['tool_specs_master'].update_one(
                                                {
                                                    "make": make_val,
                                                    "spec_detail": detail_val,
                                                    delete_count_field: {"$gt": 0},
                                                },
                                                {"$inc": {delete_count_field: -1}}
                                            )

                                db_collection.delete_one({"serial_no": target_single_serial})
                                st.session_state.reset_message = f"🎯 지정 시리얼 [`{target_single_serial}`] 데이터가 안전하게 영구 삭제되었습니다!"
                                st.session_state.reset_success = True
                                st.rerun()


    # 3) 📂 종합 현황판 창---------------------------------------------------------------------------------------------------------------------------~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
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
            # DB 연결 및 데이터 조회
            mongo_uri = st.secrets["database"]["MONGO_URI"]
            client = MongoClient(mongo_uri)
            db = client["dashboard_db"]
            
            all_data = list(db["tools_management"].find({}).sort("serial_no", -1))
            
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
                    
                    for item in filtered_data:
                        s_no = item["serial_no"]
                        current_spec = item.get("spec_detail")
                        status_badge = {"사용전":"🟢 [사용전]", "사용중":"🟡 [사용중]", "재사용":"🔵 [재사용]", "재사용대기":"🟣 [재사용대기]", "폐기":"🔴 [폐기]"}.get(item.get("status"), "🔴 [폐기]")
                        
                        # 마스터 컬렉션에서 상세 정보 조회
                        spec_info = db["tool_specs_master"].find_one({"spec_detail": current_spec}) if current_spec else None
                        
                        with st.expander(f"🆔 {s_no} | {item.get('tool_type', '툴')} | {status_badge}"):
                            col1, col2 = st.columns(2)
                            with col1:
                                st.write(f"• **상세 스펙:** {current_spec if current_spec else '미기입'}")
                                st.write(f"• **제조사:** {spec_info.get('make', '정보 없음') if spec_info else '-'}")
                            with col2:
                                st.write(f"• **기계 호기:** {item.get('machine_no', '-')}")
                                st.write(f"• **사용 한도:** {int(item.get('use_limit', 10000))} 회")
                            
                            st.info(f"📝 **현장 특이 사항:** {item.get('note', '기록 없음')}")
                            st.divider()
                            st.subheader("🛠 데이터 관리")
                            

                                
                          
                            # [스펙 오류 삭제 및 재고 보정]
                            if st.button(f"🗑 [스펙 오류 삭제 및 재고 보정]", key=f"reset_spec_{s_no}", type="primary"):
                                # 1. 유효성 검사 (기존 로직 유지)
                                if not current_spec or not spec_info:
                                    st.error(f"⚠️ 경고: [{current_spec if current_spec else '공란'}]은 등록되지 않은 스펙이거나 마스터에 존재하지 않습니다!")
                                else:
                                    st.session_state[f"confirm_spec_{s_no}"] = True
                                    st.rerun()

                            # [확인 창 및 실제 실행 로직]
                            if st.session_state.get(f"confirm_spec_{s_no}", False):
                              
                                
                               
                                # 기존 변수 충돌 방지를 위해 new_spec_input 변수 사용
                                all_specs = [s["spec_detail"] for s in db["tool_specs_master"].find()]
                               

                                # [확인 창]
                                if st.session_state.get(f"confirm_spec_{s_no}", False):
                                    st.warning(f"⚠️ [{current_spec}] 스펙 오류를 삭제하고 빈 시리얼로 되돌리시겠습니까?")

                                    # 1. 컬럼 분리
                                    col_a, col_b = st.columns(2)

                                    # 2. 작업이 아직 완료되지 않았을 때 (확인/닫기 버튼 표시)
                                    if not st.session_state.get(f"work_done_{s_no}", False):
                                        
                                        # 확인 버튼
                                        if col_a.button(f"✅ 확인 (삭제 및 원복)", key=f"confirm_del_{s_no}", type="primary"):
                                            # A. 백업 저장
                                            st.session_state[f"backup_{s_no}"] = db["tools_management"].find_one({"serial_no": s_no})
                                            
                                            # B. 현재 상태가 실제 재고 수량에 잡혀 있는 경우만 차감
                                            spec_reset_count_field = {
                                                "사용전": "new_tool_count",
                                                "재사용대기": "used_tool_count",
                                                "폐기": "disposed_tool_count",
                                            }.get(item.get("status"))

                                            if spec_reset_count_field:
                                                db["tool_specs_master"].update_one(
                                                    {
                                                        "spec_detail": current_spec,
                                                        spec_reset_count_field: {"$gt": 0},
                                                    },
                                                    {"$inc": {spec_reset_count_field: -1}}
                                                )

                                            # C. 2. 데이터 리셋 (현장 DB)
                                            db["tools_management"].update_one(
                                                {"serial_no": s_no},
                                                {
                                                    "$unset": {"spec_detail": "", "make": ""},
                                                    "$set": {
                                                        "status": "사용전",
                                                        "worker": "",
                                                        "machine_no": "",
                                                        "note": f"[{get_now_kst().strftime('%Y-%m-%d %H:%M')}] 발행 입고일 완료 (현장 기입 대기) - 이전 스펙('{current_spec}') 오기입 상세스펙 삭제 완료"
                                                    }
                                                }
                                            )
                                            # D. 작업 완료 표시
                                            st.session_state[f"work_done_{s_no}"] = True
                                            st.rerun()

                                        # 닫기 버튼 (작업 안 하고 그냥 닫기)
                                        if col_b.button("❌ 닫기", key=f"close_del_{s_no}"):
                                            st.session_state[f"confirm_spec_{s_no}"] = False
                                            st.rerun()

                                    # 3. 작업이 완료된 후 (실행 취소 버튼 표시)
                                    else:
                                        st.success("작업이 완료되었습니다.")
                                        if st.button("❌ 닫기 (메인 돌아가기)", key=f"close_after_done_{s_no}"):      
                                            st.session_state[f"work_done_{s_no}"] = False
                                            st.session_state[f"confirm_spec_{s_no}"] = False
                                            st.rerun()


        except Exception as e:
            st.error(f"데이터 로드 에러: {e}")
    


#############################################################################################################################################################################




    # 4) 데이터 수정 / 삭제 / QR 재발행 창
    elif tool_menu == "⚙️ 데이터 수정 / 삭제 / QR 재발행":
    

        st.title("⚙️ 툴 데이터 관리 및 누락 QR 재발행")
        st.write("<br>", unsafe_allow_html=True)

        # 세션 상태 초기화
        if 'qr_cart' not in st.session_state:
            st.session_state['qr_cart'] = []

        st.subheader("누락 / 분실 QR코드 타겟 재발행")
        target_serial = st.text_input("재발행할 12자리 시리얼 번호를 정확히 입력하세요").strip()
        
        # 1. 장바구니 추가 로직
        if st.button("🛒 장바구니에 담기"):
            if target_serial and len(target_serial) == 12:
                if target_serial not in st.session_state['qr_cart']:
                    st.session_state['qr_cart'].append(target_serial)
                    st.success(f"{target_serial} 번호가 장바구니에 추가되었습니다.")
                    st.rerun()
                else:
                    st.warning("이미 장바구니에 있는 번호입니다.")
            else:
                st.error("올바른 12자리 시리얼 번호를 먼저 입력하세요.")

        # 2. 장바구니 목록 관리
        st.write("---")
        st.subheader("🛒 QR 발행 대기 목록")
        if st.button("목록 비우기"):
            st.session_state['qr_cart'] = []
            st.rerun()
        st.write(st.session_state['qr_cart'])

        # 3. 누락 번호 검증 및 개별 생성 (기존 로직 유지)
        if target_serial:
            if len(target_serial) != 12:
                st.warning("⚠️ 시리얼 넘버는 정확히 12자리 규격이어야 합니다.")
            else:
                exist_item = db_collection.find_one({"serial_no": target_serial})
                if exist_item:
                    st.success(f"✅ 확인결과: 데이터베이스에 기존 데이터가 존재하는 툴입니다.")
                else:
                    st.error("❌ 확인결과: 데이터베이스에 존재하지 않는 완전히 누락된 새로운 번호입니다.")
                    if st.button(f"➕ 누락번호 {target_serial} 신규 생성 및 QR 발행"):
                        t_code = target_serial[3]
                        new_blank = {
                            "serial_no": target_serial,
                            "tool_type": "전착툴" if t_code=="1" else "레진툴" if t_code=="2" else "메탈툴" if t_code=="2" else "코어툴",
                            "status": "사용전",
                            "input_date": str(today),
                            "init_time": get_now_kst().strftime("%H:%M"),
                            "worker": "",
                            "machine_no": "",
                            "start_time": "-",
                            "target_time": "-",
                            "use_limit": 10000,
                            "current_use": 0,
                            "waste_date": "-",
                            "note": "누락 번호 관리자 재발행 완료"
                        }
                        db_collection.insert_one(new_blank)
                        st.success(f"✅ 누락된 번호 {target_serial} 가 DB에 생성되었습니다.")
                        st.rerun()

        # 4. 일괄 인쇄 로직 (분석한 인쇄 규격 적용)
        if st.session_state['qr_cart']:
            st.write("---")
            st.subheader("🖨️ 일괄 인쇄 준비")
            
            # HTML 컨텐츠 생성
            html_content = ""
            for s_no in st.session_state['qr_cart']:
                qr_bytes = generate_app_qr_bytes(s_no)
                base64_qr = base64.b64encode(qr_bytes).decode("utf-8")
                html_content += f"""
                <div class="qr-item">
                    <img src="data:image/png;base64,{base64_qr}">
                    <span>{s_no}</span>
                </div>
                """

            
            # 인쇄 스크립트 결합 부분 (수정본)
        if st.button("🖨️ 대기 목록 모두 인쇄하기"):
            # 인쇄를 위한 HTML 구조 생성
            # 인쇄 버튼 및 스크립트 (print-area ID 유지)
            full_html = f"""
            <html>
                <head>
                    <style>
                        @page {{ size: 29mm 90mm; margin: 0; }}
                        body {{ margin: 0; padding: 0; }}
                        .label-page {{ width: 29mm; height: 85mm; display: flex; flex-direction: column; align-items: center; justify-content: space-evenly; page-break-after: always; }}
                        .qr-item {{ display: flex; flex-direction: column; align-items: center; margin-bottom: 5px; }}
                        img {{ width: 20mm !important; height: 20mm !important; display: block; }}
                        span {{ font-size: 8px; font-family: monospace; margin-top: 1px; }}
                    </style>
                </head>
                <body>
                    <div id="print-area">
                        {''.join([f'<div class="qr-item"><img src="data:image/png;base64,{base64.b64encode(generate_app_qr_bytes(s_no)).decode("utf-8")}"/><span>{s_no}</span></div>' for s_no in st.session_state['qr_cart']])}
                    </div>
                    <script>
                        window.onload = function() {{
                            var container = document.getElementById('print-area');
                            var items = container.getElementsByClassName('qr-item');
                            for (var i = 0; i < items.length; i += 3) {{
                                var pageDiv = document.createElement('div');
                                pageDiv.className = 'label-page';
                                for (var j = i; j < i + 3 && j < items.length; j++) {{
                                    pageDiv.appendChild(items[j].cloneNode(true));
                                }}
                                document.body.appendChild(pageDiv);
                            }}
                            container.style.display = 'none';
                            window.print();
                        }}
                    </script>
                </body>
            </html>
            """
            
            st.download_button(
                label="🖨️ 대기 목록 모두 인쇄하기 (파일 다운로드)",
                data=full_html,
                file_name="print_qr.html",
                mime="text/html"
            )
    

            if st.button("✅ 인쇄 완료 - 목록 비우기"):
                st.session_state['qr_cart'] = []
                st.rerun()



  
    
    elif tool_menu == MATERIAL_MENU_LABEL:
        show_material_receiving_page()

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

             
      
        # 3. 리스트 조회 (다른 모든 코드 무시하고 이것만 실행)
        st.write("---")
        st.subheader("📋스펙 마스터 목록")
        
        # 1. DB에서 데이터 가져오기
        specs = list(db.find({}))
        
        # 2. 이전에 렌더링된 요소들을 강제로 삭제 (레이아웃 잔상 제거)
        placeholder = st.empty()
        
        # 3. 데이터 출력
        if specs:
            for s in specs:
                label = f"{s.get('main_type', '기타')} | {s.get('spec_detail', '상세없음')}"
                
                # 여기서 st.expander를 사용하면 화살표가 무조건 나옵니다.
                with st.expander(label):
                    st.write(f"제조사: {s.get('make', '정보없음')}")
                    st.write(f"상세스펙: {s.get('spec_detail', '내용없음')}")
                    
                    if st.button("🗑️ 삭제", key=f"del_{str(s.get('_id'))}"):
                        db.delete_one({"_id": s['_id']})
                        st.rerun()
        else:
            st.write("등록된 스펙이 없습니다.")



#####################################################################################################################################

    elif tool_menu == "🔍 툴 재고 검색 및 인쇄":
        # [🔥 1단계 방안: 인쇄 숨김 CSS 제어 코드를 최상단으로 전면 배치]
        st.markdown(
            """
            <style>
                @media print {
                    /* 🔍 대제목(no-print 클래스)을 인쇄 시 강제 숨김 */
                    .no-print, [data-testid="stMarkdown"] :has(.no-print) {
                        display: none !important;
                    }
                    /* 사이드바 영역 전체 숨김 */
                    [data-testid="stSidebar"], section[data-testid="stSidebar"] {
                        display: none !important;
                    }
                    /* 상단 헤더 및 여백 숨김 */
                    header, [data-testid="stHeader"] {
                        display: none !important;
                    }
                    /* 하단 버튼 및 기타 불필요 요소 숨김 */
                    .stButton, div.stButton, iframe, footer {
                        display: none !important;
                    }    
                    /* 하단 조작 버튼 및 안내 메시지 영역 숨김 */
                    .stButton, div.stButton, iframe, footer, .stAlert {
                        display: none !important;
                    }    
        
                    /* 인쇄 용지 여백 제로화 */
                    [data-testid="stAppViewContainer"] {
                        padding: 0px !important;
                        background: white !important;
                    }
                    .main .block-container {
                        padding-top: 10px !important;
                        padding-bottom: 10px !important;
                    }
                }
            </style>
            """,
            unsafe_allow_html=True
        )

        # [🔥 2단계 방안: 대제목에 'no-print' 클래스 이름표를 붙여 일반 텍스트로 출력]
        st.markdown("<h2 class='no-print'>🔍 툴 재고 검색 및 인쇄</h2>", unsafe_allow_html=True)
        st.write("<br>", unsafe_allow_html=True)

        # 2. 상단 필터 버튼
        col1, col2, col3, col4, col5 = st.columns(5)
        selected_cat = None
        if col1.button("전체 보기"): selected_cat = "전체"
        if col2.button("전착툴"): selected_cat = "전착"
        if col3.button("레진툴"): selected_cat = "레진"
        if col4.button("메탈툴"): selected_cat = "메탈"
        if col5.button("코어툴"): selected_cat = "코어"

        # 3. 데이터 조회 및 파싱 함수
        def get_tool_data(category):
            mongo_uri = st.secrets["database"]["MONGO_URI"]
            client = MongoClient(mongo_uri)
            db = client["dashboard_db"]
            master_data = list(db.tool_specs_master.find({}))
            
            refined_list = []
            for item in master_data:
                inv = db.tool_inventory.find_one({"make": item.get("make"), "spec_detail": item.get("spec_detail")})
                
                full_spec = item.get("spec_detail", "-")
                if "#" in full_spec:
                    parts = full_spec.split("#")
                    pure_spec = parts[0]
                    mesh_val = "#" + parts[1]
                else:
                    pure_spec = full_spec
                    mesh_val = "-"
                    
                main_code_str = str(inv.get("main_code", "")) if inv else ""
                code_num = main_code_str[0] if len(main_code_str) > 0 else "기타"
                cat_map = {"1": "전착", "2": "레진", "3": "메탈", "4": "코어"}
                cat_name = cat_map.get(code_num, "기타")
                
                if category == "전체" or category == cat_name:
                    refined_list.append({
                        "대분류": cat_name,
                        "규격": pure_spec,
                        "메쉬": mesh_val,
                        "현재 재고": item.get("new_tool_count", 0),
                        "중고 재고": item.get("used_tool_count", 0)
                    })
            
            # 순수 데이터프레임으로 만듭니다.
            df_result = pd.DataFrame(refined_list)
            
            # [🔥 대분류 정렬 기능 추가] 
            # 데이터가 존재하면 "대분류" 가나다순으로 깔끔하게 정렬하여 반환합니다.
            if not df_result.empty:
                df_result = df_result.sort_values(by="대분류", ascending=True)
                
            return df_result

        # 4. 결과 출력 및 인쇄 버튼
        if selected_cat:
            df = get_tool_data(selected_cat)
            
            # 인쇄용 서브 타이틀 (인쇄물에 포함됨)
            st.markdown(f"<h1 style='text-align: center;'>공구 - LIST</h1>", unsafe_allow_html=True)
            st.markdown(f"<h3 style='text-align: center;'>{selected_cat} 리스트</h3>", unsafe_allow_html=True)
            st.write("<br>", unsafe_allow_html=True)
            
            # 1) 표의 제목 헤더 영역 생성 (5개 칸 분할 및 정중앙 정렬)
            th1, th2, th3, th4, th5 = st.columns([1.5, 3, 1.5, 1.5, 1.5])
            with th1: st.markdown("<p style='text-align: center; font-weight: bold; background-color: #f0f2f6; padding: 8px; margin: 0; border: 1px solid #e6e9ef;'>대분류</p>", unsafe_allow_html=True)
            with th2: st.markdown("<p style='text-align: center; font-weight: bold; background-color: #f0f2f6; padding: 8px; margin: 0; border: 1px solid #e6e9ef;'>규격</p>", unsafe_allow_html=True)
            with th3: st.markdown("<p style='text-align: center; font-weight: bold; background-color: #f0f2f6; padding: 8px; margin: 0; border: 1px solid #e6e9ef;'>메쉬</p>", unsafe_allow_html=True)
            with th4: st.markdown("<p style='text-align: center; font-weight: bold; background-color: #f0f2f6; padding: 8px; margin: 0; border: 1px solid #e6e9ef;'>현재 재고</p>", unsafe_allow_html=True)
            with th5: st.markdown("<p style='text-align: center; font-weight: bold; background-color: #f0f2f6; padding: 8px; margin: 0; border: 1px solid #e6e9ef;'>중고 재고</p>", unsafe_allow_html=True)
            
            # 2) 데이터 본문 내용 영역 생성 (반복문으로 한 줄씩 정중앙 정렬하여 출력)
            for _, row in df.iterrows():
                td1, td2, td3, td4, td5 = st.columns([1.5, 3, 1.5, 1.5, 1.5])
                with td1: st.markdown(f"<p style='text-align: center; padding: 8px; margin: 0; border: 1px solid #e6e9ef;'>{row['대분류']}</p>", unsafe_allow_html=True)
                with td2: st.markdown(f"<p style='text-align: center; padding: 8px; margin: 0; border: 1px solid #e6e9ef;'>{row['규격']}</p>", unsafe_allow_html=True)
                with td3: st.markdown(f"<p style='text-align: center; padding: 8px; margin: 0; border: 1px solid #e6e9ef;'>{row['메쉬']}</p>", unsafe_allow_html=True)
                with td4: st.markdown(f"<p style='text-align: center; padding: 8px; margin: 0; border: 1px solid #e6e9ef;'>{row['현재 재고']}</p>", unsafe_allow_html=True)
                with td5: st.markdown(f"<p style='text-align: center; padding: 8px; margin: 0; border: 1px solid #e6e9ef;'>{row['중고 재고']}</p>", unsafe_allow_html=True)
                
            st.write("<br>", unsafe_allow_html=True)

            st.info("🖨️ 인쇄하려면 키보드의 <<Ctrl + P>> 누르세요.")


            if st.button("⬅️ 돌아가기"):
                st.rerun()




    elif tool_menu == "📅 날짜별 툴 현황":
        st.title("📅 날짜별 툴 상태 현황")
        from datetime import datetime, timedelta, timezone
        KST = timezone(timedelta(hours=9))
        today_kst = datetime.now(KST)
        
        # 1. 입력 필드 구성
        col1, col2, col3 = st.columns(3)
        with col1:
            search_date = st.date_input("날짜 선택", value=today_kst, key="date_input_today")
        with col2:
            status_option = st.selectbox("상태 선택", ["전체", "사용전", "사용중", "재사용", "재사용대기", "폐기"])
        with col3:
            # 시리얼 번호 부분 입력창 추가
            serial_input = st.text_input("시리얼 번호 (일부 가능)")
        
        if st.button("검색 실행"):
            date_str = search_date.strftime('%Y-%m-%d')
            
            # 2. 검색 쿼리 구성
            # 기본 쿼리: 날짜 필수 포함
            query = {"note": {"$regex": f"{date_str}"}}
            
            # 상태 조건 추가
            if status_option != "전체":
                query["note"]["$regex"] += f".*{status_option}"
                
            # 시리얼 번호 조건 추가 (시리얼 번호가 입력된 경우)
            if serial_input:
                query["serial_no"] = {"$regex": serial_input}
            
            # 3. DB 조회
            db = db_collection.database['tools_management']
            results = list(db.find(query))
            
            # 4. 결과 출력
            if results:
                st.success(f"총 {len(results)}건의 데이터를 찾았습니다.")
                import pandas as pd
                df = pd.DataFrame(results)
                # 깔끔하게 표로 출력
                st.dataframe(df[['serial_no', 'tool_type', 'note']])
            else:
                st.warning("해당 조건에 맞는 데이터가 없습니다.")           
