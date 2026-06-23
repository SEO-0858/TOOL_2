import streamlit as st
from back import run_backup
from recover import run_recover
import os

def render_search_menu():
    st.write("---")
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
        
        # 버튼을 누르면 '백업 상태'를 기록함
        if st.button("백업 시작"):
            with st.spinner("백업 중..."):
                run_backup()
            st.session_state['backup_complete'] = True # 백업 성공 기록
            st.rerun() # 화면을 새로고침

        # 백업이 성공한 상태라면 다운로드 버튼을 보여줌
        if st.session_state.get('backup_complete'):
            st.success("백업이 완료되었습니다!")
            
            # 여기서 파일을 찾아 다운로드 버튼을 생성
            backup_path = "./backup_data"
            if os.path.exists(backup_path):
                files = [f for f in os.listdir(backup_path) if f.endswith('.xlsx')]
                for file in files:
                    file_path = os.path.join(backup_path, file)
                    with open(file_path, "rb") as f:
                        st.download_button(
                            label=f"📥 {file} 다운로드",
                            data=f,
                            file_name=file,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
            
            # 다운로드 후에는 다시 백업 상태를 초기화하고 싶다면 이 아래 줄을 주석 해제하세요
            # if st.button("초기화"): st.session_state['backup_complete'] = False; st.rerun()
   




    elif mode == "데이터베이스 RECOVER":
        st.header("📦 데이터베이스 복구 모드")
        if st.button("복구 실행"):
            # 여기서 아까 만든 run_recover() 함수를 호출합니다!
            run_recover()
            st.success("복구가 완료되었습니다!")

# 메인 실행부
render_search_menu()
