import streamlit as st

def render_search_menu():
    st.sidebar.write("### 검색 옵션")
    # 1. 사이드바 라디오 버튼으로 모드 선택
    mode = st.sidebar.radio(
    "작업을 선택하세요",
    ["재고 검색", "데이터베이스 BACK UP", "데이터베이스 RECOVER"],
    key="tool_management_radio" # 이 key가 중복을 막아줍니다
)

    # 2. 선택된 모드에 따라 오른쪽 메인 화면을 다르게 그리기
    if mode == "재고 검색":
        st.header("⚙️ 재고 검색 메뉴")
        st.write("검색 조건을 입력하세요.")
        # 여기에 재고 검색 관련 코드(UI)를 넣으세요

    elif mode == "데이터베이스 BACK UP":
        st.header("💾 데이터베이스 백업")
        st.write("백업을 수행하면 현재 DB 상태가 보안 드라이브로 저장됩니다.")
        if st.button("백업 실행"):
            # 여기서 backup.py 함수를 호출하거나 코드를 실행
            st.success("백업이 완료되었습니다!")

    elif mode == "데이터베이스 RECOVER":
        st.header("📦 데이터베이스 복구")
        st.write("복구할 컬렉션을 선택하고 실행하세요.")
        # 여기서 복구 관련 코드(UI)를 넣으세요
        target = st.selectbox("복구할 데이터 선택", ["tools_management", "tool_specs_master"])
        if st.button("복구 실행"):
            st.warning(f"{target} 데이터를 복구 중입니다...")

# 메인 실행부
render_search_menu()
