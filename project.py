import streamlit as st
from pymongo import MongoClient
import datetime
from datetime import timedelta, datetime as dt_class
import qrcode
from io import BytesIO
import base64
import re
import time

# 🌟 1. 페이지 기본 설정 및 URL 파라미터 추적
st.set_page_config(page_title="KKQ 4파트 다이아몬드 툴관리", layout="wide")

# 🔒 2. 데이터베이스 연결
@st.cache_resource
def get_database():
    # ⚠️ 보안 주의: 실제 운영 환경에서는 st.secrets 등을 활용하여 관리하는 것을 권장합니다.
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
serial_from_url = query_params.get("serial", None)

# --- 헬퍼 함수 정의 ---
def generate_qr_base64(serial_no):
    """시리얼 번호를 기반으로 QR코드를 생성하고 Base64 문자열로 반환"""
    # 2026년 기준 도메인 및 포트 가치 반영 (필요시 도메인 변경 가능)
    qr_url = f"http://localhost:8501/?serial={serial_no}"
    qr = qrcode.QRCode(version=1, box_size=3, border=1)
    qr.add_data(qr_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    
    buffered = BytesIO()
    img.save(buffered, format="PNG")
    return base64.b64encode(buffered.getvalue()).decode()

def get_machine_display_num(m_str):
    """기계 번호 문자열에서 숫자만 추출하여 정렬용 정수 반환"""
    if not m_str:
        return 9999
    nums = re.findall(r'\d+', str(m_str))
    return int(nums[0]) if nums else 9999


# ==========================================
# 📱 [모드 1] 현장 QR 코드 스캔 모드 (URL 파라미터 존재 시)
# ==========================================
if serial_from_url:
    st.title(f"📱 현장 툴 작업 프로세스 ({serial_from_url})")
    
    if db_collection is None:
        st.error("데이터베이스가 연결되지 않았습니다.")
        st.stop()
        
    # 1. 기존 등록 여부 확인
    tool_data = db_collection.find_one({"serial_no": serial_from_url})
    
    if not tool_data:
        st.warning("⚠️ 아직 세부 정보가 등록되지 않은 QR 코드입니다. 최초 등록을 진행해 주세요.")
        
        # 기본 정보 파싱 시도 (예: 전착툴_0604_00001)
        parsed_type = "전착툴"
        if "_" in serial_from_url:
            prefix = serial_from_url.split("_")[0]
            if "레진" in prefix: parsed_type = "레진툴"
            elif "메탈" in prefix: parsed_type = "메탈툴"
            
        with st.form("init_form"):
            st.subheader("🆕 신규 툴 최초 등록")
            tool_type = st.selectbox("툴 종류", ["전착툴", "레진툴", "메탈툴"], index=["전착툴", "레진툴", "메탈툴"].index(parsed_type))
            worker = st.text_input("작업자 성명 *", placeholder="홍길동")
            machine_no = st.text_input("장착 기계 번호 (호기) *", placeholder="12호기")
            
            col1, col2 = st.columns(2)
            with col1:
                target_hours = st.number_input("드레싱 주기 (시간)", min_value=0, max_value=500, value=12, step=1)
            with col2:
                target_minutes = st.number_input("드레싱 주기 (분)", min_value=0, max_value=59, value=0, step=5)
                
            limit_cnt = st.number_input("최대 사용 한도 횟수 (드레싱 제한)", min_value=1, max_value=100, value=5, step=1)
            memo = st.text_area("특이사항 및 메모", placeholder="초기 특이사항 기입")
            
            submit_init = st.form_submit_button("🚀 최초 장착 및 가동 시작")
            
            if submit_init:
                if not worker.strip() or not machine_no.strip():
                    st.error("❌ 작업자 성명과 장착 기계 번호는 필수 입력 항목입니다.")
                else:
                    start_time = get_now_kst()
                    total_dur_minutes = (target_hours * 60) + target_minutes
                    target_time = start_time + timedelta(minutes=total_dur_minutes)
                    
                    new_doc = {
                        "serial_no": serial_from_url,
                        "tool_type": tool_type,
                        "status": "사용중",
                        "worker": worker.strip(),
                        "machine_no": machine_no.strip(),
                        "start_time": start_time,
                        "target_time": target_time,
                        "dressing_period_minutes": total_dur_minutes,
                        "limit_cnt": limit_cnt,
                        "current_cnt": 0,
                        "memo": memo.strip(),
                        "waste_date": None,
                        "history": [{
                            "timestamp": start_time,
                            "action": "최초 등록 및 장착 가동",
                            "worker": worker.strip(),
                            "machine_no": machine_no.strip(),
                            "status": "사용중"
                        }]
                    }
                    db_collection.insert_one(new_doc)
                    st.success(f"🎉 [{serial_from_url}] 툴이 성공적으로 가동 리스트에 등록되었습니다!")
                    time.sleep(1)
                    st.rerun()
    else:
        # 이미 등록된 툴인 경우 -> 상태 수정 및 카운트 관리 화면
        st.success("✅ 조회 성공: 정상 등록되어 운영 중인 툴입니다.")
        
        # 현재 상태 서머리 카드
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("툴 종류", tool_data.get("tool_type"))
        c2.metric("현재 상태", tool_data.get("status"))
        c3.metric("현재 기계", tool_data.get("machine_no"))
        c4.metric("드레싱 횟수", f"{tool_data.get('current_cnt') or 0} / {tool_data.get('limit_cnt') or 5} 회")
        
        st.write("---")
        
        # 현장 상태 업데이트 폼
        with st.form("update_form"):
            st.subheader("🔄 실시간 상태 조치 및 변경")
            status_opt = ["사용전", "사용중", "폐기"]
            curr_status = tool_data.get("status", "사용중")
            status_idx = status_opt.index(curr_status) if curr_status in status_opt else 1
            
            new_status = st.selectbox("변경할 상태", status_opt, index=status_idx)
            new_worker = st.text_input("담당 작업자 수정/확인", value=tool_data.get("worker", ""))
            new_machine = st.text_input("장착 기계 수정/확인", value=tool_data.get("machine_no", ""))
            new_cnt = st.number_input("현재까지 진행된 드레싱 누적 횟수", min_value=0, max_value=200, value=int(tool_data.get("current_cnt") or 0))
            new_memo = st.text_area("현장 작업 메모 갱신", value=tool_data.get("memo", ""))
            
            submit_update = st.form_submit_button("💾 현장 정보 업데이트 저장")
            
            if submit_update:
                up_time = get_now_kst()
                w_date = up_time if new_status == "폐기" else tool_data.get("waste_date")
                
                # 타겟 시간 재계산 방어 로직 (사용중으로 바뀔 때 주기 정보 보존)
                p_min = tool_data.get("dressing_period_minutes", 720)
                t_time = tool_data.get("target_time")
                if curr_status != "사용중" and new_status == "사용중":
                    t_time = up_time + timedelta(minutes=p_min)
                    
                update_fields = {
                    "status": new_status,
                    "worker": new_worker.strip(),
                    "machine_no": new_machine.strip(),
                    "current_cnt": new_cnt,
                    "memo": new_memo.strip(),
                    "waste_date": w_date,
                    "target_time": t_time
                }
                
                hist_entry = {
                    "timestamp": up_time,
                    "action": f"현장 모바일 수정 ({curr_status} -> {new_status})",
                    "worker": new_worker.strip(),
                    "machine_no": new_machine.strip(),
                    "status": new_status
                }
                
                db_collection.update_one(
                    {"serial_no": serial_from_url},
                    {"$set": update_fields, "$push": {"history": hist_entry}}
                )
                st.success("✅ 현장 상태가 성공적으로 DB에 반영되었습니다.")
                time.sleep(1)
                st.rerun()
                
        # 과거 이력 확인 (확장 섹션)
        with st.expander("📜 이 툴의 전체 변경 이력 보기"):
            for h in reversed(tool_data.get("history", [])):
                st.write(f"- **{str(h.get('timestamp'))[:19]}** | 작업자: {h.get('worker')} | 기계: {h.get('machine_no')} | 행동: {h.get('action')} -> `{h.get('status')}`")

    if st.button("🏠 전체 관리 시스템(PC모드)으로 전환"):
        st.query_params.clear()
        st.rerun()


# ==========================================
# 💻 [모드 2] PC 종합 모니터링 및 관리자 모드
# ==========================================
else:
    st.sidebar.title("🛠️ 툴 종합 관리 센터")
    menu = st.sidebar.radio(
        "메뉴 선택", 
        [
            "📊 빈데이터 QR코드 대량 선발행", 
            "⚠️ 실시간 툴 드레싱 알림판", 
            "📂 전체 데이터 현황판", 
            "⚙️ 데이터 수정 / 삭제 / QR 재발행",
            "🖥️ 실시간 기계 정보창"
        ]
    )
    
    # ------------------------------------------
    # 메뉴 1: 빈데이터 QR코드 대량 선발행
    # ------------------------------------------
    if menu == "📊 빈데이터 QR코드 대량 선발행":
        st.title("📊 빈데이터 QR코드 대량 선발행 시스템")
        st.write("현장에 미리 부착해 둘 공백 상태의 QR 라벨을 규칙 기반으로 일괄 생성합니다.")
        
        with st.form("bulk_form"):
            t_type = st.selectbox("선발행 툴 종류 선택", ["전착툴", "레진툴", "메탈툴"])
            qty = st.number_input("발행 수량 (개)", min_value=1, max_value=100, value=10)
            start_num = st.number_input("시작 순번 (당일 발행 기준)", min_value=1, max_value=99999, value=1)
            
            submit_bulk = st.form_submit_button("✨ 빈 데이터베이스 시리얼 및 QR 대량 생성")
            
            if submit_bulk:
                if db_collection is None:
                    st.error("데이터베이스 연결 실패")
                else:
                    success_cnt = 0
                    skip_cnt = 0
                    
                    type_code = "WJ" if t_type == "전착툴" else ("RJ" if t_type == "레진툴" else "MT")
                    
                    for i in range(qty):
                        seq = start_num + i
                        serial_str = f"{type_code}_{mmdd}_{seq:05d}"
                        
                        # 중복 검사
                        exist = db_collection.find_one({"serial_no": serial_str})
                        if exist:
                            skip_cnt += 1
                            continue
                            
                        blank_doc = {
                            "serial_no": serial_str,
                            "tool_type": t_type,
                            "status": "사용전",
                            "worker": "",
                            "machine_no": "",
                            "start_time": None,
                            "target_time": None,
                            "dressing_period_minutes": 720,
                            "limit_cnt": 5,
                            "current_cnt": 0,
                            "memo": "대량 선발행된 공백 데이터",
                            "waste_date": None,
                            "history": [{
                                "timestamp": get_now_kst(),
                                "action": "시스템 대량 선발행 생성",
                                "worker": "시스템",
                                "machine_no": "",
                                "status": "사용전"
                            }]
                        }
                        db_collection.insert_one(blank_doc)
                        success_cnt += 1
                        
                    st.success(f"✅ 일괄 생성 완료! (신규 생성: {success_cnt}건 / 중복 패스: {skip_cnt}건)")
                    
        # 인쇄를 위한 리스트 업 섹션
        st.write("---")
        st.subheader("🖨️ 인쇄할 발행대상 조건 검색 및 라벨 출력")
        
        p_type = st.selectbox("출력할 툴 종류", ["전착툴", "레진툴", "메탈툴"], key="print_type")
        p_date = st.text_input("출력 날짜 필터 (MMDD 형식)", value=mmdd)
        
        if st.button("🔍 인쇄 대상 조회하기"):
            t_code = "WJ" if p_type == "전착툴" else ("RJ" if p_type == "레진툴" else "MT")
            search_pattern = f"^{t_code}_{p_date}_"
            
            items = list(db_collection.find({"serial_no": {"$regex": search_pattern}}).sort("serial_no", 1))
            
            if not items:
                st.info("조건에 일치하는 선발행 데이터가 없습니다.")
            else:
                st.success(f"총 {len(items)}개의 라벨을 찾았습니다. 아래 인쇄 버튼을 누르세요.")
                
                # HTML+JS 프린트 레이아웃 구성
                html_cards = ""
                for idx, item in enumerate(items):
                    s_no = item["serial_no"]
                    b64_img = generate_qr_base64(s_no)
                    
                    html_cards += f"""
                    <div class="qr-card">
                        <div class="title">{p_type} 관리라벨</div>
                        <img src="data:image/png;base64,{b64_img}" />
                        <div class="serial">{s_no}</div>
                    </div>
                    """
                    if (idx + 1) % 4 == 0 and (idx + 1) < len(items):
                        html_cards += '<div class="page-break"></div>'
                        
                print_template = f"""
                <html>
                <head>
                <style>
                    body {{ font-family: 'Arial', sans-serif; margin: 0; padding: 10px; }}
                    .qr-grid {{ display: flex; flex-wrap: wrap; gap: 15px; justify-content: flex-start; }}
                    .qr-card {{ width: 160px; border: 1px dashed #333; padding: 8px; text-align: center; background: #fff; }}
                    .title {{ font-size: 13px; font-weight: bold; margin-bottom: 5px; color: #111; }}
                    .serial {{ font-size: 11px; font-weight: bold; margin-top: 3px; color: #444; }}
                    img {{ width: 120px; height: 120px; }}
                    .page-break {{ width: 100%; height: 0; page-break-after: always; }}
                    @media print {{
                        .no-print {{ display: none; }}
                        .qr-card {{ border: 1px solid #000; page-break-inside: avoid; }}
                    }}
                </style>
                </head>
                <body>
                    <div class="no-print" style="margin-bottom:20px;">
                        <button onclick="window.print()" style="padding:10px 20px; font-size:16px; background-color:#4CAF50; color:white; border:none; cursor:pointer; border-radius:5px;">
                            🖨️ 바코드 라벨프린터로 즉시 인쇄하기
                        </button>
                        <hr>
                    </div>
                    <div class="qr-grid">
                        {html_cards}
                    </div>
                </body>
                </html>
                """
                st.components.v1.html(print_template, height=500, scroller=True)
                
        # 마스터 수동 단일 발행 관리자 영역
        with st.sidebar.expander("🚨 [위험] 마스터 수동 단일 발행"):
            target_single_serial = st.text_input("수동 발행할 완벽한 시리얼넘버 입력", placeholder="WJ_0604_00001")
            single_type = st.selectbox("타겟 종류", ["전착툴", "레진툴", "메탈툴"], key="single_s")
            
            if st.button("수동 강제 생성 실행"):
                if not target_single_serial.strip():
                    st.error("시리얼 번호를 쓰세요.")
                # 🛠️ 버그 수정: 기존 len != 12 검사인데 문구는 11자리로 오 표기되었던 부분 수정 (12자리로 수정)
                elif len(target_single_serial) != 12:
                    st.error("⚠️ 시리얼 번호는 정확히 12자리여야 합니다. (예: WJ_0604_00001)")
                else:
                    dup = db_collection.find_one({"serial_no": target_single_serial.strip()})
                    if dup:
                        st.error("이미 존재하는 시리얼입니다.")
                    else:
                        db_collection.insert_one({
                            "serial_no": target_single_serial.strip(),
                            "tool_type": single_type,
                            "status": "사용전",
                            "worker": "", "machine_no": "", "start_time": None, "target_time": None,
                            "dressing_period_minutes": 720, "limit_cnt": 5, "current_cnt": 0,
                            "memo": "마스터 메뉴에서 수동 강제 단일 발행됨", "waste_date": None,
                            "history": [{"timestamp": get_now_kst(), "action": "마스터 수동 강제 발행", "worker": "마스터", "machine_no": "", "status": "사용전"}]
                        })
                        st.success("강제 생성 완료!")

    # ------------------------------------------
    # 메뉴 2: 실시간 툴 드레싱 알림판
    # ------------------------------------------
    elif menu == "⚠️ 실시간 툴 드레싱 알림판":
        st.title("⚠️ 실시간 가동 툴 드레싱 모니터링 전광판")
        st.write("현재 기계에 장착되어 작동 중인 툴들의 다음 드레싱 주기까지 남은 시간을 계산하여 실시간 알림을 보냅니다.")
        
        # 주기적 수동 동기화 유도
        if st.button("🔄 전광판 수동 새로고침"):
            st.rerun()
            
        # 가동중인 데이터 로드
        active_tools = list(db_collection.find({"status": "사용중"}))
        
        if not active_tools:
            st.info("🟢 현재 기계에 장착되어 가동 중인 툴이 없습니다. 모든 설비가 공실이거나 사용전/폐기 상태입니다.")
        else:
            # 상태 분류용 리스트
            danger_list = []   # 시간 초과 (빨강)
            warning_list = []  # 임박 1시간 미만 (노랑)
            normal_list = []   # 정상 (녹색)
            
            current_time_calc = get_now_kst()
            
            for tool in active_tools:
                t_time = tool.get("target_time")
                if not t_time:
                    # 타겟 타임이 실종된 예외 케이스 방어
                    p_min = tool.get("dressing_period_minutes", 720)
                    s_time = tool.get("start_time") or current_time_calc
                    t_time = s_time + timedelta(minutes=p_min)
                    db_collection.update_one({"_id": tool["_id"]}, {"$set": {"target_time": t_time}})
                
                # 남은 시간(분) 계산
                time_diff = t_time - current_time_calc
                diff_minutes = time_diff.total_seconds() / 60.0
                
                tool["diff_minutes"] = diff_minutes
                
                if diff_minutes < 0:
                    danger_list.append(tool)
                elif diff_minutes <= 60:
                    warning_list.append(tool)
                else:
                    normal_list.append(tool)
                    
            # 🎨 시각화 레이아웃 배치
            st.markdown(f"### 🕒 현재 기준 시간(KST): `{current_time_calc.strftime('%Y-%m-%d %H:%M:%S')}`")
            
            # 섹션 1: 🚨 알람 드레싱 시간 초과 (DANGER)
            st.markdown("#### 🔴 드레싱 주기 초과 (즉시 조치 필요)")
            if not danger_list:
                st.write("✅ 지연된 툴이 없습니다.")
            else:
                cols = st.columns(3)
                for idx, t in enumerate(danger_list):
                    with cols[idx % 3]:
                        over_min = abs(int(t['diff_minutes']))
                        st.markdown(f"""
                        <div style="background-color:#FFEBEE; padding:15px; border-radius:8px; border-left:8px solid #D32F2F; margin-bottom:10px;">
                            <b style="font-size:16px; color:#C62828;">🚨 {t['serial_no']} ({t['tool_type']})</b><br>
                            <b>📍 장착 설비:</b> {t['machine_no']} | <b>작업자:</b> {t['worker']}<br>
                            <span style="color:#B71C1C; font-weight:bold;">⚠️ {over_min}분 초과 근무 중!</span><br>
                            <small>목표시간: {str(t['target_time'])[11:16]} (누적: {t.get('current_cnt',0)}회)</small>
                        </div>
                        """, unsafe_allow_html=True)
                        if st.button(f"🧼 드레싱 완료 처리", key=f"btn_d_{t['serial_no']}"):
                            # 드레싱 리셋 로직
                            up_now = get_now_kst()
                            next_target = up_now + timedelta(minutes=t.get("dressing_period_minutes", 720))
                            next_cnt = int(t.get("current_cnt") or 0) + 1
                            
                            st.write(next_cnt, t.get("limit_cnt", 5))
                            
                            # 한도 도달 시 자동 폐기 제안 알림 처리 유연성 유도
                            status_action = "사용중"
                            action_msg = "드레싱 완료 (타이머 리셋)"
                            if next_cnt >= int(t.get("limit_cnt", 5)):
                                status_action = "사용중" # 현장에서 직접 폐기 전환하도록 유도하거나 경고문구 추가
                                action_msg = "드레싱 완료 [⚠️ 수명 한도 도달 경고]"
                                
                            db_collection.update_one(
                                {"_id": t["_id"]},
                                {
                                    "$set": {"start_time": up_now, "target_time": next_target, "current_cnt": next_cnt, "status": status_action},
                                    "$push": {"history": {"timestamp": up_now, "action": action_msg, "worker": t['worker'], "machine_no": t['machine_no'], "status": status_action}}
                                }
                            )
                            st.success("완료 반영 되었습니다!")
                            time.sleep(0.5)
                            st.rerun()

            # 섹션 2: 🟡 드레싱 주기 임박 (WARNING - 1시간 이내)
            st.markdown("#### 🟡 드레싱 임박 (1시간 이내)")
            if not warning_list:
                st.write("🟢 1시간 이내 임박한 툴이 없습니다.")
            else:
                cols = st.columns(4)
                for idx, t in enumerate(warning_list):
                    with cols[idx % 4]:
                        st.markdown(f"""
                        <div style="background-color:#FFFDE7; padding:12px; border-radius:8px; border-left:6px solid #FBC02D; margin-bottom:10px;">
                            <b style="color:#F57F17;">⚠️ {t['serial_no']}</b> [{t['machine_no']}]<br>
                            작업자: {t['worker']} | <b>⏱️ {int(t['diff_minutes'])}분 남음</b><br>
                            <small>목표시간: {str(t['target_time'])[11:16]} (누적: {t.get('current_cnt',0)}회)</small>
                        </div>
                        """, unsafe_allow_html=True)
                        if st.button(f"🧼 완료", key=f"btn_w_{t['serial_no']}"):
                            up_now = get_now_kst()
                            next_target = up_now + timedelta(minutes=t.get("dressing_period_minutes", 720))
                            db_collection.update_one(
                                {"_id": t["_id"]},
                                {
                                    "$set": {"start_time": up_now, "target_time": next_target, "current_cnt": int(t.get("current_cnt") or 0) + 1},
                                    "$push": {"history": {"timestamp": up_now, "action": "임박 전 사전 드레싱 완료", "worker": t['worker'], "machine_no": t['machine_no'], "status": "사용중"}}
                                }
                            )
                            st.success("반영 완료")
                            time.sleep(0.5)
                            st.rerun()

            # 섹션 3: 🟢 정상 가동 중 (NORMAL)
            st.markdown("#### 🟢 안정 가동 중")
            if not normal_list:
                st.write("가동 중인 정상 안정 상태의 툴이 없습니다.")
            else:
                cols = st.columns(4)
                for idx, t in enumerate(normal_list):
                    with cols[idx % 4]:
                        rem_hours = int(t['diff_minutes'] // 60)
                        rem_mins = int(t['diff_minutes'] % 60)
                        st.markdown(f"""
                        <div style="background-color:#E8F5E9; padding:10px; border-radius:6px; border-left:5px solid #388E3C; margin-bottom:8px; font-size:13px;">
                            <b style="color:#2E7D32;">{t['serial_no']}</b> ({t['machine_no']})<br>
                            남은시간: <b>{rem_hours}시간 {rem_mins}분</b><br>
                            <small>작업자: {t['worker']} | 누적 {t.get('current_cnt',0)}회</small>
                        </div>
                        """, unsafe_allow_html=True)

    # ------------------------------------------
    # 메뉴 3: 전체 데이터 현황판 (⭐ 복합 검색 기능 강화 및 추가)
    # ------------------------------------------
    elif menu == "📂 전체 데이터 현황판":
        st.title("📂 데이터 종합 조회 대시보드")
        st.write("데이터베이스에 등록된 전체 툴의 마스터 상태 일람표입니다.")
        
        # 탭 구조 분할 (상태별 필터링의 직관성 유도)
        tabs = st.tabs(["전체 테이블 보기", "사용중 툴", "사용전 대기조", "폐기 완료 이력"])
        
        # 공통 데이터 fetch
        all_raw = list(db_collection.find().sort("serial_no", -1))
        
        # 🔍 [기능 개선] 상단 복합 검색 창 추가 (시리얼, 작업자, 기계번호 공통 인터페이스)
        st.markdown("### 🔍 다중 조건 통합 검색 및 필터링")
        src_col1, src_col2, src_col3 = st.columns(3)
        
        with src_col1:
            search_serial = st.text_input("📦 시리얼 번호로 검색", placeholder="시리얼 번호 입력 (예: WJ_)").strip()
        with src_col2:
            search_worker = st.text_input("👤 작업자 성명으로 검색", placeholder="작업자 이름 입력 (예: 홍길동)").strip()
        with src_col3:
            search_machine = st.text_input("🖥️ 기계 번호(호기)로 검색", placeholder="기계 번호 입력 (예: 12호기)").strip()
            
        # 데이터 필터링 프론트엔드 파이프라인 엔진 구현
        filtered_data = all_raw
        
        if search_serial:
            filtered_data = [d for d in filtered_data if search_serial.lower() in str(d.get("serial_no", "")).lower()]
        if search_worker:
            filtered_data = [d for d in filtered_data if search_worker.lower() in str(d.get("worker", "")).lower()]
        if search_machine:
            filtered_data = [d for d in filtered_data if search_machine.lower() in str(d.get("machine_no", "")).lower()]
            
        def render_custom_table(data_list):
            """정렬 및 가독성을 높인 HTML 테이블 렌더러 함수"""
            if not data_list:
                st.info("검색 조건과 일치하는 데이터가 데이터베이스에 없습니다.")
                return
                
            table_rows = ""
            for item in data_list:
                s_time_str = str(item.get("start_time"))[:16] if item.get("start_time") else "-"
                t_time_str = str(item.get("target_time"))[:16] if item.get("target_time") else "-"
                w_time_str = str(item.get("waste_date"))[:10] if item.get("waste_date") else "-"
                
                # 상태별 배지 CSS 처리
                status = item.get("status", "사용전")
                badge_color = "#E0E0E0"
                text_color = "#333"
                if status == "사용중":
                    badge_color = "#C8E6C9"; text_color = "#2E7D32"
                elif status == "폐기":
                    badge_color = "#FFCDD2"; text_color = "#C62828"
                    
                table_rows += f"""
                <tr>
                    <td style="font-weight:bold; font-family:monospace;">{item.get('serial_no')}</td>
                    <td>{item.get('tool_type')}</td>
                    <td><span style="background-color:{badge_color}; color:{text_color}; padding:3px 8px; border-radius:4px; font-weight:bold; font-size:12px;">{status}</span></td>
                    <td style="font-weight:bold;">{item.get('worker') or '-'}</td>
                    <td style="color:#0D47A1; font-weight:bold;">{item.get('machine_no') or '-'}</td>
                    <td><small>{s_time_str}</small></td>
                    <td><small>{t_time_str}</small></td>
                    <td style="text-align:center; font-weight:bold;">{item.get('current_cnt',0)} / {item.get('limit_cnt',5)}</td>
                    <td><small style="color:red;">{w_time_str}</small></td>
                    <td style="max-width:180px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;"><small>{item.get('memo','')}</small></td>
                </tr>
                """
                
            html_table = f"""
            <table style="width:100%; border-collapse:collapse; margin-top:10px; font-size:13px; text-align:left;">
                <thead>
                    <tr style="background-color:#F5F5F5; border-bottom:2px solid #ddd; font-weight:bold;">
                        <th style="padding:10px;">시리얼 번호</th>
                        <th>툴 종류</th>
                        <th>상태</th>
                        <th>작업자</th>
                        <th>기계번호</th>
                        <th>장착일시</th>
                        <th>드레싱예정</th>
                        <th style="text-align:center;">드레싱 횟수</th>
                        <th>폐기일자</th>
                        <th>비고/메모</th>
                    </tr>
                </thead>
                <tbody>
                    {table_rows}
                </tbody>
            </table>
            """
            st.markdown(html_table, unsafe_allow_html=True)

        # 탭 1: 전체 데이터 테이블
        with tabs[0]:
            st.write(f"📊 현재 조건 검색 매칭 결과: 총 **{len(filtered_data)}** 건")
            render_custom_table(filtered_data)
            
        # 탭 2: 사용중인 데이터 필터링 테이블
        with tabs[1]:
            u_data = [d for d in filtered_data if d.get("status") == "사용중"]
            st.write(f"🔥 매칭된 사용중인 툴: 총 **{len(u_data)}** 건")
            render_custom_table(u_data)
            
        # 탭 3: 사용전 대기중 데이터 필터링 테이블
        with tabs[2]:
            b_data = [d for d in filtered_data if d.get("status") == "사용전"]
            st.write(f"📦 매칭된 준비 상태 대기 툴: 총 **{len(b_data)}** 건")
            render_custom_table(b_data)
            
        # 탭 4: 폐기된 데이터 필터링 테이블
        with tabs[3]:
            w_data = [d for d in filtered_data if d.get("status") == "폐기"]
            st.write(f"🪓 매칭된 수명 종료 폐기 툴: 총 **{len(w_data)}** 건")
            render_custom_table(w_data)

    # ------------------------------------------
    # 메뉴 4: 데이터 수정 / 삭제 / QR 재발행
    # ------------------------------------------
    elif menu == "⚙️ 데이터 수정 / 삭제 / QR 재발행":
        st.title("⚙️ 백엔드 마스터 마스터 데이터 관리 시스템")
        st.write("오타 수정, 강제 상태 변환, 기록 삭제 및 분실된 고유 QR 코드의 개별 재발행 처리를 수행합니다.")
        
        target_serial = st.text_input("🔍 대상 툴의 정확한 시리얼 번호 입력", placeholder="WJ_0604_00001").strip()
        
        if target_serial:
            doc = db_collection.find_one({"serial_no": target_serial})
            
            if not doc:
                st.error("❌ 입력한 시리얼 번호와 일치하는 데이터가 DB에 없습니다.")
            else:
                st.success("툴 정보를 성공적으로 조회했습니다. 수정 후 저장을 누르세요.")
                
                # 레이아웃 분할 배치
                m_col1, m_col2 = st.columns([2, 1])
                
                with m_col1:
                    with st.form("master_edit_form"):
                        st.subheader("📝 세부 필드 데이터 강제 보정")
                        e_type = st.selectbox("툴 종류 변경", ["전착툴", "레진툴", "메탈툴"], index=["전착툴", "레진툴", "메탈툴"].index(doc.get("tool_type", "전착툴")))
                        e_status = st.selectbox("상태 강제 변환", ["사용전", "사용중", "폐기"], index=["사용전", "사용중", "폐기"].index(doc.get("status", "사용전")))
                        e_worker = st.text_input("작업자 명의", value=doc.get("worker", ""))
                        e_machine = st.text_input("기계 장착 호기", value=doc.get("machine_no", ""))
                        
                        ec1, ec2 = st.columns(2)
                        with ec1:
                            e_cnt = st.number_input("현재 드레싱 카운트", min_value=0, value=int(doc.get("current_cnt") or 0))
                        with ec2:
                            e_limit = st.number_input("목표 한도 횟수 설정", min_value=1, value=int(doc.get("limit_cnt") or 5))
                            
                        e_period = st.number_input("드레싱 주기 규격 분(minutes) 단위", min_value=1, value=int(doc.get("dressing_period_minutes", 720)))
                        e_memo = st.text_area("마스터용 비고 메모 관리", value=doc.get("memo", ""))
                        
                        # 체크박스를 통한 강제 시간 초기화 트릭 제공
                        reset_timer_check = st.checkbox("🔄 저장 시 드레싱 타이머 주기를 현재 시간 기준으로 완전 리셋 재부팅")
                        
                        save_master = st.form_submit_button("💾 마스터 권한으로 수정사항 저장")
                        
                        if save_master:
                            m_now = get_now_kst()
                            target_t_calc = doc.get("target_time")
                            start_t_calc = doc.get("start_time")
                            
                            if reset_timer_check or (doc.get("status") != "사용중" and e_status == "사용중"):
                                start_t_calc = m_now
                                target_t_calc = m_now + timedelta(minutes=e_period)
                                
                            w_date_calc = doc.get("waste_date")
                            if e_status == "폐기" and doc.get("status") != "폐기":
                                w_date_calc = m_now
                            elif e_status != "폐기":
                                w_date_calc = None
                                
                            db_collection.update_one(
                                {"_id": doc["_id"]},
                                {"$set": {
                                    "tool_type": e_type,
                                    "status": e_status,
                                    "worker": e_worker.strip(),
                                    "machine_no": e_machine.strip(),
                                    "current_cnt": e_cnt,
                                    "limit_cnt": e_limit,
                                    "dressing_period_minutes": e_period,
                                    "memo": e_memo.strip(),
                                    "start_time": start_t_calc,
                                    "target_time": target_t_calc,
                                    "waste_date": w_date_calc
                                }, "$push": {"history": {"timestamp": m_now, "action": "마스터 관리자 강제 수동 정보 수정 보정 실행", "worker": "관리자", "machine_no": e_machine.strip(), "status": e_status}}}
                            )
                            st.success("데이터 수정 처리가 완료되었습니다.")
                            time.sleep(0.5)
                            st.rerun()
                            
                with m_col2:
                    st.subheader("🖨️ 고유 QR 라벨 재발행")
                    b64_img_single = generate_qr_base64(target_serial)
                    
                    st.markdown(f"""
                    <div style="border:1px solid #ccc; padding:15px; text-align:center; background:#fff; border-radius:8px;">
                        <b style="color:#333;">{doc.get('tool_type')} 라벨</b><br><br>
                        <img src="data:image/png;base64,{b64_img_single}" style="width:140px;" /><br>
                        <code style="font-weight:bold; color:#000;">{target_serial}</code>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    single_print_html = f"""
                    <html>
                    <body>
                    <button onclick="window.print()" style="width:100%; margin-top:10px; padding:8px; background-color:#0288D1; color:white; border:none; border-radius:4px; cursor:pointer;">
                        🖨️ 이 라벨만 한 장 인쇄하기
                    </button>
                    <div style="display:none; text-align:center;" class="print-area">
                        <h3>{doc.get('tool_type')} 재발행</h3>
                        <img src="data:image/png;base64,{b64_img_single}" style="width:150px;"/>
                        <p><b>{target_serial}</b></p>
                    </div>
                    <style>
                        @media print {{
                            body * {{ display:none; }}
                            .print-area, .print-area * {{ display:block; }}
                        }}
                    </style>
                    </body>
                    </html>
                    """
                    st.components.v1.html(single_print_html, height=80)
                    
                    # 데이터 영구 영멸 삭제 스위치 섹션
                    st.write("---")
                    st.subheader("💥 위험 영역")
                    confirm_delete = st.checkbox("이 데이터를 DB에서 영구 삭제하는 것에 절대 동의합니다.")
                    if st.button("🗑️ 영구 삭제 실행"):
                        if not confirm_delete:
                            st.error("체크박스에 동의 후 실행해 주세요.")
                        else:
                            db_collection.delete_one({"_id": doc["_id"]})
                            st.success("DB에서 해당 툴 로그가 완전 소멸 제거 되었습니다.")
                            time.sleep(1)
                            st.rerun()

    # ------------------------------------------
    # 메뉴 5: 실시간 기계 정보창
    # ------------------------------------------
    elif menu == "🖥️ 실시간 기계 정보창":
        st.title("🖥️ 가공 라인 기계별 배치 현황판 (Grid Layout)")
        st.write("공장 내부의 물리 기계 배치 맵입니다. 현재 설비 호기별 장착되어 가동 중인 다이아몬드 툴의 가동 대수를 표현합니다.")
        
        # 가동 데이터 로드
        all_active = list(db_collection.find({"status": "사용중"}))
        
        # 공장 기계 설비 맵 배열 레이아웃 구조체 선언 (예: 1호기 ~ 24호기)
        # 현장 라인 물리 구조에 맞춰 배치 배열 수정 가능
        machine_layout = [
            ["1호기", "2호기", "3호기", "4호기", "5호기", "6호기"],
            ["7호기", "8호기", "9호기", "10호기", "11호기", "12호기"],
            ["13호기", "14호기", "15호기", "16호기", "17호기", "18호기"],
            ["19호기", "20호기", "21호기", "22호기", "23호기", "24호기"]
        ]
        
        # 주기적 자동 리프레시 유도 기능 추가 (현장 대시보드 모니터용)
        st.sidebar.write("---")
        auto_refresh = st.sidebar.checkbox("🖥️ 대시보드 30초 자동 리프레시 기능 활성화", value=False)
        if auto_refresh:
            time.sleep(30)
            st.rerun()
            
        for row in machine_layout:
            cols = st.columns(6)
            for i, m_no in enumerate(row):
                with cols[i]:
                    # 해당 기기 호기에 걸려있는 툴 서칭 파싱 규칙 바인딩 정규식 매칭 처리
                    tools = [t for t in all_active if str(m_no).replace("호기","") in str(t.get("machine_no","")) or str(m_no) in str(t.get("machine_no",""))]
                    
                    if tools:
                        # 🔴 장착되어 가동중인 상태 (한 대의 기기에 여러개 연동도 배열 처리로 대응)
                        tool_cards = ""
                        for t in tools:
                            tool_cards += f"""
                            <div style="margin-bottom:5px; border-bottom:1px solid #c8e6c9; font-size:10px;">
                                <b>ID: {t.get('serial_no', 'N/A')}</b><br>
                                작업자: {t.get('worker', '미지정')}<br>
                                장착: {str(t.get('start_time', ''))[5:16]}
                            </div>
                            """
                        st.markdown(f"""
                            <div style="background-color:#E8F5E9; padding:5px; border-radius:6px; border:2px solid #2E7D32; height:150px; overflow-y:auto;">
                                <b style="color:#1b5e20; font-size:11px;">{m_no} ({len(tools)}개)</b>
                                {tool_cards}
                            </div>
                            """, unsafe_allow_html=True)
                    else:
                        # ⚪ 공실 상태 빈 기계 표현
                        st.markdown(f"""
                            <div style="background-color:#F5F5F5; padding:8px; border-radius:6px; border:1px solid #ccc; font-size:11px; height:150px; text-align:center; color:#777;">
                                <br><b>{m_no}</b><br><br><span style="color:#aaa; font-size:10px;">가동 툴 없음</span>
                            </div>
                            """, unsafe_allow_html=True)
