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
    if "mongo" in st.secrets:
        MONGO_URI = st.secrets["mongo"]["MONGO_URI"]
    else:
        MONGO_URI = "mongodb+srv://sspon1270_db_user:wXA7NGCMjjTiTG5w@cluster0.1ectnsv.mongodb.net/?appName=Cluster0"
    client = MongoClient(MONGO_URI)
    return client["dashboard_db"]["tools_management"]

db_collection = get_database()

# 📅 오늘 날짜 정보 추출 (시리얼 넘버용 MMDD 형식)
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

with st.sidebar.expander("📦 제품 관리 메뉴", expanded=False):
    st.sidebar.write("📝 4파트 제품 인수인계 내역서 (준비중)")

# 🛠️ QR 스캔/보관함 연동을 위한 세션 상태 세팅
if "search_query" not in st.session_state:
    st.session_state.search_query = ""

# 헬퍼 함수: 시리얼 넘버를 받아서 QR코드 이미지 바이트를 생성하는 함수
def generate_qr_bytes(serial_text):
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=6,
        border=1,
    )
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
    
    main_col1, main_col2 = st.columns([1, 1], gap="large")
    
    # ----------------------------------------------------------------💡 [좌측: 시리얼 넘버 발행 및 등록]
    with main_col1:
        st.subheader("📥 시리얼 넘버 발행 및 등록")
        
        tool_type = st.selectbox("💎 툴 종류 선택", ["전착툴 (코드: 01)", "레진툴 (코드: 02)", "메탈툴 (코드: 03)"])
        tool_code = "01" if "전착툴" in tool_type else "02" if "레진툴" in tool_type else "03"
        
        prefix = f"{tool_code}{mmdd}" 
        try:
            last_tool = db_collection.find_one({"serial_no": {"$regex": f"^{prefix}"}}, sort=[("serial_no", -1)])
            if last_tool:
                last_serial = last_tool["serial_no"]
                last_counter = int(last_serial[-4:]) 
                next_counter = last_counter + 1
            else:
                next_counter = 1
        except Exception:
            next_counter = 1
            
        auto_serial_no = f"{prefix}{next_counter:04d}" 
        
        with st.form(key="tool_register_form"):
            st.info(f"💡 시스템 추천 자동 넘버링 조합 완료")
            serial_no = st.text_input("🆔 생성된 시리얼 넘버", value=auto_serial_no)
            
            input_date = st.date_input("📅 입고 날짜", value=today)
            worker = st.text_input("👷 교체 작업자 이름")
            machine_no = st.text_input("⚙️ 기계 가공 호기 (예: MCT 3호기)")
            
            limit_col1, limit_col2 = st.columns(2)
            with limit_col1:
                use_count = st.number_input("사용한도", value=10000, step=1000)
            with limit_col2:
                current_count = st.number_input("현재 사용횟수", value=0, step=100)
                
            waste_date = st.date_input("🗑️ 폐기 날짜 (해당 시 선택)", value=None)
            note = st.text_area("📝 특이사항 (공정 내용 등)")
            
            submit_btn = st.form_submit_button("🚀 툴 등록 및 QR코드 발행")
            
        if submit_btn:
            if not worker or not machine_no:
                st.error("⚠️ 작업자 이름과 기계 가공 호기를 입력해 주세요!")
            else:
                existing = db_collection.find_one({"serial_no": serial_no})
                if existing:
                    st.error(f"❌ 중복 에러: 이미 등록된 시리얼 넘버({serial_no})입니다!")
                else:
                    new_data = {
                        "serial_no": serial_no,
                        "tool_type": tool_type.split(" ")[0],
                        "input_date": str(input_date),
                        "worker": worker,
                        "machine_no": machine_no,
                        "use_limit": use_count,
                        "current_use": current_count,
                        "waste_date": str(waste_date) if waste_date else "-",
                        "note": note
                    }
                    db_collection.insert_one(new_data)
                    
                    # 📁 로컬 PC 환경(D드라이브 존재시)에만 물리 파일 저장 (웹 서버 에러 방지 안전장치)
                    try:
                        img_to_save = qrcode.make(serial_no)
                        save_dir = r"D:\KKQ_PYTHON\QR"
                        if os.path.exists("D:\\") or os.path.splitdrive(os.getcwd())[0].upper() == "D:":
                            if not os.path.exists(save_dir):
                                os.makedirs(save_dir)
                            img_to_save.save(os.path.join(save_dir, f"QR_{serial_no}.png"))
                    except Exception:
                        pass
                    
                    st.success(f"🎉 [{serial_no}] 등록 성공!")
                    
                    # 화면 미리보기 출력
                    qr_bytes = generate_qr_bytes(serial_no)
                    st.image(qr_bytes, caption=f"발행 완료: {serial_no}", width=120)
                    
                    st.session_state.search_query = serial_no
                    st.balloons()
                    st.rerun()

    # ----------------------------------------------------------------💡 [우측: 다조건 필터링 및 검색창]
    with main_col2:
        st.subheader("🔍 툴 통합 검색 및 필터링 현황판")
        
        search_col1, search_col2 = st.columns(2)
        with search_col1:
            search_serial = st.text_input("🔍 시리얼 넘버로 검색", value=st.session_state.search_query)
            search_machine = st.text_input("⚙️ 장비(머신번호)로 검색")
        with search_col2:
            search_date = st.text_input("📅 날짜로 검색 (예: 2026-06-01)")
            search_worker = st.text_input("👷 사람이름으로 검색")
            
        st.markdown("---")
        
        query = {}
        if search_serial:
            query["serial_no"] = {"$regex": search_serial, "$options": "i"}
        if search_date:
            query["input_date"] = {"$regex": search_date, "$options": "i"}
        if search_machine:
            query["machine_no"] = {"$regex": search_machine, "$options": "i"}
        if search_worker:
            query["worker"] = {"$regex": search_worker, "$options": "i"}
            
        try:
            filtered_data = list(db_collection.find(query).sort("_id", -1))
            
            if not filtered_data:
                st.info("검색 조건과 일치하는 다이아몬드 툴 데이터가 없습니다.")
            else:
                st.write(f"📊 검색 결과: 총 **{len(filtered_data)}** 건이 조회되었습니다.")
                
                for item in filtered_data:
                    limit_ratio = (item['current_use'] / item['use_limit']) * 100 if item['use_limit'] > 0 else 0
                    color_style = "red" if limit_ratio >= 90 else "black"
                    
                    is_expanded = (search_serial == item['serial_no'])
                    with st.expander(f"🆔 시리얼: {item['serial_no']} | 종류: {item['tool_type']} | 장비: {item['machine_no']}", expanded=is_expanded):
                        st.markdown(f"### 📋 {item['serial_no']} 툴 정보 테이블")
                        
                        col_a, col_b = st.columns(2)
                        with col_a:
                            st.write(f"• **📅 입고 날짜:** {item['input_date']}")
                            st.write(f"• **👷 교체 작업자:** {item['worker']}")
                            st.write(f"• **⚙️ 기계 가공 호기:** {item['machine_no']}")
                        with col_b:
                            st.write(f"• **🗑️ 폐기 날짜:** {item['waste_date']}")
                            st.markdown(f"• **📊 사용 횟수:** <span style='color:{color_style}; font-weight:bold;'>{item['current_use']}</span> / {item['use_limit']} 회", unsafe_allow_html=True)
                            st.write(f"• **📝 특이 사항:** {item['note']}")
                            
        except Exception as e:
            st.error(f"데이터 조회 실패: {e}")


# --- 🔵 [📂 신규 추가 기능: 발행된 QR코드 보관함 창] ---
elif tool_menu == "📂 발행된 QR코드 보관함":
    st.title("📂 발행된 QR코드 온라인 보관함")
    st.markdown("현장에 라벨 프린터가 없을 때, 그동안 생성된 QR코드들을 모아서 확인하고 개별 인쇄/다운로드하는 가상 폴더 창입니다.")
    st.markdown("---")
    
    try:
        # 데이터베이스의 모든 툴 정보를 시리얼 번호 역순으로 가져옴
        all_tools = list(db_collection.find({}).sort("serial_no", -1))
        
        if not all_tools:
            st.info("아직 등록된 툴이 없어 보관함이 비어 있습니다. 메인 대시보드에서 툴을 먼저 등록해 주세요.")
        else:
            st.write(f"🗃️ 현재 보관함에 총 **{len(all_tools)}개**의 툴 QR코드가 보관되어 있습니다.")
            st.write("💡 *각 QR코드 아래의 버튼을 누르면 메인 대시보드 검색창으로 바로 이동합니다.*")
            st.markdown("<br>", unsafe_allow_html=True)
            
            # 한 줄에 4개씩 바둑판(갤러리) 모양으로 배치하기 위한 테이블 구조 모방
            # 스트림릿에서 flex/grid 대용으로 row-column 패턴 사용
            chunk_size = 4
            for i in range(0, len(all_tools), chunk_size):
                chunk = all_tools[i:i+chunk_size]
                cols = st.columns(4) # 4개 열 생성
                
                for idx, item in enumerate(chunk):
                    with cols[idx]:
                        # 각 툴의 QR 이미지 즉석 생성
                        s_no = item["serial_no"]
                        qr_img_bytes = generate_qr_bytes(s_no)
                        
                        # 카드 형태의 디자인으로 QR 출력
                        st.image(qr_img_bytes, width=140)
                        st.markdown(f"**🆔 {s_no}**")
                        st.caption(f"🔧 {item['tool_type']} | ⚙️ {item['machine_no']}")
                        
                        # [이 툴 조회하기] 버튼 클릭 시 세션에 심고 메인 화면으로 리다이렉트하는 행위 로직
                        if st.button("🔍 정보 조회", key=f"btn_{s_no}"):
                            st.session_state.search_query = s_no
                            st.success(f"{s_no} 선택됨! 메인 대시보드로 이동합니다.")
                            st.rerun()
                st.markdown("---")
                
    except Exception as e:
        st.error(f"보관함 로딩 실패: {e}")


# --- 🔴 [관리자 데이터 수정/삭제창] ---
elif tool_menu == "⚙️ 데이터 수정 / 삭제":
    st.title("⚙️ 관리자 데이터 편집실")
    st.info("여기는 나중에 잘못 기입된 시리얼 코드나 툴을 원격 수정/삭제하는 방입니다.")
