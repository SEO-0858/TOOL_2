import streamlit as st
from back import run_backup
from recover import run_recover

def render_search_menu():
    st.sidebar.write("### 검색 옵션")
    # 1. 사이드바 라디오 버튼으로 모드 선택
    mode = st.sidebar.radio(
    "작업을 선택하세요",
    ["재고 검색", "데이터베이스 BACK UP", "데이터베이스 RECOVER"],
    key="unique_radio_key" # 이 key가 중복을 막아줍니다
)

    # 2. 선택된 모드에 따라 오른쪽 메인 화면을 다르게 그리기
    if mode == "데이터베이스 BACK UP":
            st.header("💾 데이터베이스 백업 모드")
            if st.button("백업 실행"):
                # 여기서 아까 만든 run_backup() 함수를 호출합니다!
                run_backup()
                st.success("백업이 완료되었습니다!")

    elif mode == "데이터베이스 RECOVER":
        st.header("📦 데이터베이스 복구 모드")
        if st.button("복구 실행"):
            # 여기서 아까 만든 run_recover() 함수를 호출합니다!
            run_recover()
            st.success("복구가 완료되었습니다!")

# 메인 실행부
render_search_menu()
