import streamlit as st
from pymongo import MongoClient
import datetime
import qrcode
from io import BytesIO
import os

# 🌟 1. 페이지 기본 설정
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

# 🗂️ 3. 왼쪽 사이드바 (트리 구조 메뉴판)
st.sidebar.markdown("## 📁 KKQ 통합 시스템")
with st.sidebar.expander("💎 툴 관리 메뉴", expanded=True):
    tool_menu = st.sidebar.radio(
        "하위 목록",
        ["📊 툴 관리 메인 대시보드", "📂 발행된 QR코드 보관함", "⚙️ 데이터 수정 / 삭제"],
        key="tool_menu_radio"
    )

if "search_query" not in st.session_state:
    st.session_state.search_query = ""

def generate_qr_bytes(serial_text):
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=6, border=1)
    qr.add_data(serial_text)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()

# --- 🟢 [메인 대시보드창] ---
if tool_menu == "📊 툴 관리 메인 대시보드":
    st.title("💎 KKQ 4파트 다이아몬드 툴관리 SYSTEM")
    st.markdown("---")
    
    main_col1, main_col2 = st.columns([1.2, 1], gap="large")
    
    # ----------------------------------------------------------------💡 [좌측: 시리얼 넘버 연속 대량 발행]
    with main_col1:
        st.subheader("📥 시리얼 넘버 대량 연속 발행 및 등록")
        
        # 1단계 조건 입력 받기
        with st.container(border=True):
            st.markdown("#### 1단계: 발행 조건 설정")
            c1, c2 = st.columns(2)
            with c1:
                tool_code = st.text_input("🆔 고유넘버 앞 2자리 입력", value="01", max_chars=2)
            with c2:
                quantity = st.number_input("📦 오늘 들어온 툴 갯수 (발행 수량)", min_value=1, max_value=100, value=20, step=1)
            
            # DB에서 이 고유번호+오늘날짜 조합의 마지막 시퀀스 번호 찾기
            prefix = f"{tool_code}{mmdd}"
            try:
                last_tool = db_collection.find_one({"serial_no": {"$regex": f"^{prefix}"}}, sort=[("serial_no", -1)])
                if last_tool:
                    last_counter = int(last_tool["serial_no"][-4:])
                else:
                    last_counter = 0
            except Exception:
                last_counter = 0
                
            st.warning(f"🔍 확인된 이전 마지막 시리얼 카운터: **{last_counter}** 번 (다음 번호인 **{last_counter + 1}** 번부터 연속 발행됩니다.)")

        # 임시 배치 데이터 생성 및 테이블 폼 작성
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("#### 2단계: 개별 툴 데이터 테이블 작성")
        st.info("💡 아래 테이블에서 각 시리얼 넘버별 정보를 입력하거나 일괄 적용할 수 있습니다.")

        # 일괄 입력 기능 편의성 제공
        with st.expander("⚡ 공통 정보 한 번에 채우기 (전체 동일 적용)"):
            common_worker = st.text_input("👷 공통 작업자 이름")
            common_machine = st.text_input("⚙️ 공통 기계 가공 호기")
            common_limit = st.number_input("공통 사용한도", value=10000, step=1000)

        # 폼 생성 시작
        with st.form(key="batch_register_form"):
            generated_serials = []
            row_data_list = []
            
            # 수량만큼 루프를 돌며 가상의 테이블 로우 생성
            for idx in range(1, quantity + 1):
                current_seq = last_counter + idx
                serial_no = f"{prefix}{current_seq:04d}"
                generated_serials.append(serial_no)
                
                st.markdown(f"**🔢 [툴 {idx}] 시리얼 넘버: `{serial_no}`**")
                rc1, rc2, rc3 = st.columns(3)
                
                with rc1:
                    worker = st.text_input(f"작업자_{idx}", value=common_worker if common_worker else "", placeholder="작업자 이름", key=f"w_{serial_no}")
                with rc2:
                    machine = st.text_input(f"장비_{idx}", value=common_machine if common_machine else "", placeholder="가공 호기", key=f"m_{serial_no}")
                with rc3:
                    limit = st.number_input(f"한도_{idx}", value=common_limit if common_limit else 10000, step=1000, key=f"l_{serial_no}")
                
                note = st.text_input(f"특이사항_{idx}", placeholder="특이사항 기입", key=f"n_{serial_no}")
                st.markdown("---")
                
                # 저장할 데이터 구조화
                row_data_list.append({
                    "serial_no": serial_no,
                    "tool_type": "전착툴" if tool_code=="01" else "레진툴" if tool_code=="02" else "메탈툴",
                    "input_date": str(today),
                    "worker": worker,
                    "machine_no": machine,
                    "use_limit": limit,
                    "current_use": 0,
                    "waste_date": "-",
                    "note": note
                })

            submit_batch_btn = st.form_submit_button(f"🚀 총 {quantity}개의 툴 및 QR코드 일괄 등록")

        if submit_batch_btn:
            # 유효성 검사
            incomplete = any(not d["worker"] or not d["machine_no"] for d in row_data_list)
            if incomplete:
                st.error("⚠️ 모든 툴의 작업자 이름과 기계 가공 호기를 작성해 주세요! (공통 기능을 쓰면 편합니다)")
            else:
                # DB에 멀티 인서트(bulk) 진행
                try:
                    db_collection.insert_many(row_data_list)
                    st.success(f"🎉 시리얼 넘버 {generated_serials[0]} 부터 {generated_serials[-1]} 까지 총 {quantity}건의 데이터가 성공적으로 일괄 등록되었습니다!")
                    st.balloons()
                    st.rerun()
                except Exception as e:
                    st.error(f"대량 등록 중 에러 발생: {e}")

    # ----------------------------------------------------------------💡 [우측: 다조건 필터링 및 검색창]
    with main_col2:
        st.subheader("🔍 툴 통합 검색 및 필터링 현황판")
        search_serial = st.text_input("🔍 시리얼 넘버로 검색", value=st.session_state.search_query)
        search_machine = st.text_input("⚙️ 장비(머신번호)로 검색")
        
        query = {}
        if search_serial: query["serial_no"] = {"$regex": search_serial, "$options": "i"}
        if search_machine: query["machine_no"] = {"$regex": search_machine, "$options": "i"}
            
        try:
            filtered_data = list(db_collection.find(query).sort("_id", -1))
            if not filtered_data:
                st.info("검색 조건과 일치하는 다이아몬드 툴 데이터가 없습니다.")
            else:
                st.write(f"📊 검색 결과: 총 **{len(filtered_data)}** 건이 조회되었습니다.")
                for item in filtered_data:
                    with st.expander(f"🆔 시리얼: {item['serial_no']} | 장비: {item['machine_no']} | 작업자: {item['worker']}"):
                        st.write(f"• **📅 입고 날짜:** {item['input_date']}")
                        st.write(f"• **📊 사용 한도:** {item['current_use']} / {item['use_limit']} 회")
                        st.write(f"• **📝 특이 사항:** {item['note']}")
        except Exception as e:
            st.error(f"데이터 조회 실패: {e}")

# --- 🔵 [📂 발행된 QR코드 보관함 창] ---
elif tool_menu == "📂 발행된 QR코드 보관함":
    st.title("📂 발행된 QR코드 온라인 보관함")
    st.markdown("---")
    try:
        all_tools = list(db_collection.find({}).sort("serial_no", -1))
        if not all_tools:
            st.info("보관함이 비어 있습니다.")
        else:
            st.write(f"🗃️ 현재 보관함에 총 **{len(all_tools)}개**의 툴 QR코드가 보관되어 있습니다.")
            chunk_size = 4
            for i in range(0, len(all_tools), chunk_size):
                chunk = all_tools[i:i+chunk_size]
                cols = st.columns(4)
                for idx, item in enumerate(chunk):
                    with cols[idx]:
                        s_no = item["serial_no"]
                        st.image(generate_qr_bytes(s_no), width=130)
                        st.markdown(f"**🆔 {s_no}**")
                        st.caption(f"⚙️ {item['machine_no']} | 👷 {item['worker']}")
                st.markdown("---")
    except Exception as e:
        st.error(f"보관함 로딩 실패: {e}")

# --- 🔴 [관리자 데이터 수정/삭제창] ---
elif tool_menu == "⚙️ 데이터 수정 / 삭제":
    st.title("⚙️ 관리자 데이터 편집실")
