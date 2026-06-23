import streamlit as st
from back import run_backup
from recover import run_recover
import os

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

            # ... (상단 생략) ...

    elif mode == "데이터베이스 BACK UP":
        st.header("💾 데이터베이스 백업")
        
     # 1. 백업 실행 버튼
        if st.button("백업 시작"):
            with st.spinner("백업 중..."):
                run_backup() # 엑셀 파일 생성
                st.session_state['backup_done'] = True # 백업 완료 상태 저장
            st.success("백업이 완료되었습니다!")
            
        # 2. 백업 완료 상태일 때만 다운로드 버튼 표시
        if st.session_state.get('backup_done'):
            backup_path = "./backup_data"
            if os.path.exists(backup_path):
                files = os.listdir(backup_path)
                st.write("### 📥 생성된 백업 파일")
                for file in files:
                    file_path = os.path.join(backup_path, file)
                    with open(file_path, "rb") as f:
                        st.download_button(
                            label=f"다운로드: {file}",
                            data=f,
                            file_name=file,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )




    elif mode == "데이터베이스 RECOVER":
        st.header("📦 데이터베이스 복구 모드")
        if st.button("복구 실행"):
            # 여기서 아까 만든 run_recover() 함수를 호출합니다!
            run_recover()
            st.success("복구가 완료되었습니다!")

# 메인 실행부
render_search_menu()
