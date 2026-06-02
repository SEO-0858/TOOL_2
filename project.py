import streamlit as st
from pymongo import MongoClient
import datetime
from datetime import timedelta, datetime as dt_class
import qrcode
from io import BytesIO
import base64

# --- [상단 설정 및 DB 연결] ---
st.set_page_config(page_title="KKQ 4파트 다이아몬드 툴관리", layout="wide")

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

today = get_now_kst().date()

# --- [추가: 실시간 기계 정보창을 위한 함수] ---
def render_machine_box(m_id):
    info = db_collection.find_one({"machine_no": f"{m_id}호기", "status": "사용중"})
    worker = info['worker'] if info else "공실"
    serial = info['serial_no'][-5:] if info else "-"
    color = "#e6ffe6" if info else "#f9f9f9"
    st.markdown(f"""
    <div style="border:1px solid #999; padding:5px; border-radius:3px; text-align:center; height:65px; font-size:11px; background-color:{color};">
        <b style="font-size:14px;">{m_id}</b><br>{worker}<br>{serial}
    </div>
    """, unsafe_allow_html=True)

def draw_machine_layout():
    # 상단부
    c_top1, _, c_top2 = st.columns([5, 1, 3])
    with c_top1:
        cols = st.columns(5)
        for i, mid in enumerate([27, 28, 29, 30, 31]):
            with cols[i]: render_machine_box(mid)
    with c_top2:
        cols = st.columns(3)
        for i, mid in enumerate([9, 8, 7]):
            with cols[i]: render_machine_box(mid)
    
    st.write("<br>", unsafe_allow_html=True)
    # 나머지 중앙/하단은 동일한 방식으로 render_machine_box 호출...
    st.info("배치도 레이아웃이 활성화되었습니다.")

# --- [메인 로직] ---
query_params = st.query_params
qr_scanned_serial = query_params.get("serial", None)

if qr_scanned_serial:
    # (여기에 기존의 모바일 로직 코드를 그대로 붙여넣으세요)
    st.write("모바일 로직 수행 중...")
else:
    st.sidebar.markdown("## 📁 KKQ 통합 시스템")
    tool_menu = st.sidebar.radio("하위 목록", [
        "📊 빈데이터 QR코드 대량 선발행", 
        "⚠️ 실시간 툴 드레싱 알림판", 
        "📂 전체 데이터 현황판", 
        "⚙️ 데이터 수정 / 삭제 / QR 재발행",
        "🖥️ 실시간 기계 정보창" # 새 메뉴 추가
    ])

    if tool_menu == "🖥️ 실시간 기계 정보창":
        st.title("🖥️ 실시간 기계 정보창")
        draw_machine_layout()
    else:
        # 여기에 기존 파일의 'if tool_menu == "📊 ...":' 부터 끝까지 모든 코드를 복사해서 붙여넣으세요.
        st.write("기존 메뉴 기능을 불러오는 중...")
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
                st.success(f"🎉 {quantity}개의 순번 빈데이터가 안전하게 DB에 등록되었습니다!")
            except Exception as e:
                st.error(f"오류 발생: {e}")

        if st.session_state.show_qr_grid and st.session_state.current_view_serials:
            st.markdown("---")
            
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
            st.markdown("---")
            
            js_print_trigger = f"""
            <script>
            function executeQrPrint() {{
                var printWindow = window.open('', '_blank', 'width=900,height=700');
                printWindow.document.write('<html><head><title>KKQ 4파트 QR코드 라벨 인쇄</title>');
                printWindow.document.write('<style>body {{ margin: 10px; padding: 0; background: #fff; }} @page {{ size: auto; margin: 5mm; }}</style>');
                printWindow.document.write('</head><body>');
                printWindow.document.write(`{html_printable_content}`);
                printWindow.document.write('</body></html>');
                printWindow.document.close();
                printWindow.focus();
                setTimeout(function() {{
                    printWindow.print();
                    printWindow.close();
                }}, 600);
            }}
            </script>
            <button onclick="executeQrPrint()" style="
                width: 100%;
                background-color: #00B050;
                color: white;
                padding: 14px 20px;
                margin: 8px 0;
                border: none;
                border-radius: 6px;
                cursor: pointer;
                font-size: 16px;
                font-weight: bold;
                box-shadow: 0 4px 6px rgba(0,0,0,0.1);
                display: flex;
                align-items: center;
                justify-content: center;
                gap: 10px;
            ">
                🖨️ 생성된 QR코드 전체 프린터로 인쇄하기 (라벨 발행 연동)
            </button>
            """
            
            st.components.v1.html(js_print_trigger, height=75)
            
            if st.button("❌ 인쇄 완료 - 화면에서 이 QR코드 목록 지우기", type="secondary"):
                st.session_state.show_qr_grid = False
                st.session_state.current_view_serials = []
                st.rerun()

        st.markdown("<br><br><br>---", unsafe_allow_html=True)
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
                    target_reset_code = st.selectbox("🎯 데이터 삭제 및 순번을 초기화할 툴 종류", ["01 (전착툴)", "02 (레진툴)", "03 (메탈툴)", "⚠️ 전체 모든 데이터 싹 다 삭제"])
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
                    target_single_serial = st.text_input("🆔 삭제 처리할 11자리 시리얼 번호를 정확히 기입하세요 (예: 01060200001)").strip()
                    understand_risk_single = st.checkbox("❗ 기입한 특정 시리얼 툴 데이터를 영구 삭제하는 것에 동의합니다.", key="risk_single")
                    
                    if st.button("❌ 해당 개별 시리얼 넘버 데이터 즉시 삭제", key="btn_single_del"):
                        if not target_single_serial:
                            st.error("⚠️ 시리얼 번호를 입력해 주세요.")
                        elif len(target_single_serial) != 11:
                            st.error("⚠️ 시리얼 번호는 정확히 11자리여야 합니다.")
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
        st.markdown("---")
        
        try:
            active_tools = list(db_collection.find({"status": "사용중", "target_time": {"$ne": "-"}}))
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
                                <h4 style="margin: 0; color: #333;">🆔 시리얼: <code style="font-size:18px;">{item['serial_no']}</code> ({item['tool_type']})</h4>
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

    # 3) 📂 종합 현황판 창 (⭐ 상태 솔팅 및 시리얼 검색창 고도화 영역)
    elif tool_menu == "📂 전체 데이터 현황판":
        st.title("📂 현장 기입 데이터 통합 현황판")
        st.markdown("현황판에서 각 툴의 데이터를 펼친 뒤, **직접 편집 및 수정**을 진행할 수 있습니다.")
        st.markdown("---")
        
        # 🔍 [추가] 좌측 상단 실시간 검색 및 상태 정렬 컨트롤 보드 구조화
        search_col1, search_col2 = st.columns([1, 1])
        with search_col1:
            status_filter = st.selectbox(
                "🔍 툴 상태별 정렬 필터", 
                ["사용중 🟡 (기본값)", "전체 보기 📂", "사용전(기기대기) 🟢", "폐기 🔴"], 
                index=0
            )
        with search_col2:
            keyword_search = st.text_input("🆔 특정 시리얼 넘버 직접 검색 (번호 입력)", placeholder="예: 010602").strip()

        st.markdown("---")
        
        try:
            # 기본 정렬 조건: 시리얼 넘버 최신순
            all_data = list(db_collection.find({}).sort("serial_no", -1))
            
            if not all_data:
                st.info("조회할 데이터가 없습니다.")
            else:
                filtered_data = []
                
                # 🚀 메모리 단계적 하이브리드 필터링 파이프라인
                for item in all_data:
                    item_status = item.get("status", "사용전")
                    
                    # 1단계: 상태 셀렉트박스 매칭 검사
                    if status_filter == "사용중 🟡 (기본값)" and item_status != "사용중":
                        continue
                    elif status_filter == "사용전(기기대기) 🟢" and item_status != "사용전":
                        continue
                    elif status_filter == "폐기 🔴" and item_status != "폐기":
                        continue
                        
                    # 2단계: 키워드 검색어 매칭 검사 (입력값이 있을 때만 작동)
                    if keyword_search and keyword_search not in item["serial_no"]:
                        continue
                        
                    filtered_data.append(item)

                # 최종 결과물 화면 렌더링
                if not filtered_data:
                    st.warning("🔍 지정하신 검색 조건 및 정렬 기준에 일치하는 툴 데이터가 없습니다.")
                else:
                    st.caption(f"📊 총 **{len(filtered_data)}** 개의 항목이 검색되었습니다.")
                    
                    for item in filtered_data:
                        s_no = item["serial_no"]
                        status = item.get("status", "사용전")
                        status_badge = "🟢 [사용전]" if status == "사용전" else "🟡 [사용중]" if status == "사용중" else "🔴 [폐기]"
                            
                        if not item['worker'] or not item['machine_no']:
                            expander_title = f"⚪ 기입 대기 | 🆔 {s_no} | 상태: {status_badge}"
                        else:
                            expander_title = f"🆔 {s_no} | 장비: {item['machine_no']} | 작업자: {item['worker']} | 상태: {status_badge}"
                            
                        with st.expander(expander_title):
                            edit_key = f"is_editing_{s_no}"
                            if edit_key not in st.session_state:
                                st.session_state[edit_key] = False
                                
                            if st.session_state[edit_key]:
                                st.markdown(f"### ✏️ 시리얼 `{s_no}` 정보 실시간 수정 폼")
                                
                                orig_m = item.get('machine_no', '')
                                orig_m_num = ''.join(filter(str.isdigit, orig_m))
                                try:
                                    def_m_int = int(orig_m_num) if orig_m_num else 4
                                except:
                                    def_m_int = 4

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
                                    ed_time = st.time_input("장착 시간 변경", value=init_time, key=f"tm_{s_no}")

                                combined_ed_dt = dt_class.combine(ed_date, ed_time)

                                with st.form(key=f"board_edit_form_{s_no}"):
                                    ed_status = st.radio("🔄 툴 상태 변경", ["사용전", "사용중", "폐기"], index=["사용전", "사용중", "폐기"].index(status) if status in ["사용전", "사용중", "폐기"] else 0, horizontal=True)
                                    col_e1, col_e2 = st.columns(2)
                                    with col_e1:
                                        ed_worker = st.text_input("👷 교체 작업자 이름", value=item.get('worker', ''))
                                    with col_e2:
                                        ed_machine_num = st.number_input("⚙️ 기계 가공 호기 (숫자만)", min_value=1, max_value=200, value=def_m_int, key=f"mach_{s_no}")
                                        
                                    st.markdown("⏳ **드레싱 주기 커스텀 시간 재설정**")
                                    col_eh, col_em = st.columns(2)
                                    with col_eh:
                                        ed_hours = st.number_input("시간(Hour)", min_value=0, max_value=72, value=int(item.get('dressing_hours', 0)), step=1, key=f"eh_{s_no}")
                                    with col_em:
                                        ed_mins = st.number_input("분(Minute)", min_value=0, max_value=59, value=int(item.get('dressing_mins', 0)), step=5, key=f"em_{s_no}")
                                        
                                    ed_note = st.text_area("📝 현장 특이사항", value=item.get('note', ''))
                                    
                                    b_submit = st.form_submit_button("💾 수정사항 최종 저장하기")
                                    
                                if b_submit:
                                    waste_date_val = str(today) if ed_status == "폐기" else item.get("waste_date", "-")
                                    full_mach_name = f"{ed_machine_num}호기"
                                    
                                    total_mins = (ed_hours * 60) + ed_mins
                                    if total_mins > 0 and ed_status == "사용중":
                                        start_time_val = combined_ed_dt.strftime("%Y-%m-%d %H:%M:%S")
                                        target_time_val = (combined_ed_dt + timedelta(minutes=total_mins)).strftime("%Y-%m-%d %H:%M:%S")
                                    else:
                                        start_time_val = "-" if ed_status == "사용전" else item.get("start_time", "-")
                                        target_time_val = "-"
                                        
                                    db_collection.update_one(
                                        {"serial_no": s_no},
                                        {"$set": {
                                            "status": ed_status,
                                            "worker": ed_worker,
                                            "machine_no": full_mach_name,
                                            "dressing_hours": ed_hours,
                                            "dressing_mins": ed_mins,
                                            "start_time": start_time_val,
                                            "target_time": target_time_val,
                                            "waste_date": waste_date_val,
                                            "note": ed_note
                                        }}
                                    )
                                    st.session_state[edit_key] = False
                                    st.success(f"🎉 데이터가 성공적으로 업데이트되었습니다.")
                                    st.rerun()
                                    
                                if st.button("❌ 변경 취소하고 돌아가기", key=f"cancel_{s_no}"):
                                    st.session_state[edit_key] = False
                                    st.rerun()
                                    
                            else:
                                col_x, col_y = st.columns(2)
                                with col_x:
                                    st.write(f"• **💎 툴 종류:** {item['tool_type']}")
                                    st.write(f"• **📅 최초 발행일:** {item['input_date']}")
                                    st.write(f"• **📅 최초 장착 시간:** {item.get('start_time', '-')}")
                                    st.write(f"• **👷 교체 작업자:** {item['worker'] if item['worker'] else '-'}")
                                with col_y:
                                    East_mach = item['machine_no'] if item['machine_no'] else '-'
                                    st.write(f"• **⚙️ 기계 가공 호기:** {East_mach}")
                                    st.write(f"• **⏳ 설정된 드레싱 주기:** {item.get('dressing_hours', 0)}시간 {item.get('dressing_mins', 0)}분")
                                    st.write(f"• **🎯 다음 마감 시간:** {item.get('target_time', '-')}")
                                st.write(f"• **📝 현장 특이 사항:** {item['note']}")
                                
                                if st.button("✏️ 이 툴 정보 직접 수정하기", key=f"btn_edit_{s_no}", type="secondary"):
                                    st.session_state[edit_key] = True
                                    st.rerun()
                                
        except Exception as e:
            st.error(f"데이터 로드 실패: {e}")

    # 4) 데이터 수정 / 삭제 / QR 재발행 창
    elif tool_menu == "⚙️ 데이터 수정 / 삭제 / QR 재발행":
        st.title("⚙️ 툴 데이터 관리 및 누락 QR코드 재발행")
        st.markdown("---")
        
        st.subheader("🖨️ 누락 / 분실 QR코드 타겟 재발행")
        target_serial = st.text_input("🆔 재발행할 11자리 시리얼 번호를 정확히 입력하세요").strip()
        
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
