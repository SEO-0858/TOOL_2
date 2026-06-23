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
        
        # 버튼을 누르면 '메모리(BytesIO)'에 엑셀 데이터를 만듭니다.
        if st.button("백업 데이터 생성"):
            import io
            # 1. 엑셀을 메모리에 저장하기 위한 버퍼 생성
            buffer = io.BytesIO()
            
            # 2. run_backup 함수가 메모리(buffer)에 파일을 쓰도록 수정해야 하지만, 
            # 일단은 간단히 현재 폴더의 파일을 읽어오는 방식으로 진행합니다.
            run_backup() # 기존처럼 파일을 생성함
            
            st.session_state['backup_files'] = os.listdir("./backup_data")
            st.success("백업 데이터 준비 완료!")

        # 3. 백업된 파일이 있으면 무조건 다운로드 버튼을 보여줍니다.
        if 'backup_files' in st.session_state:
            for file in st.session_state['backup_files']:
                file_path = os.path.join("./backup_data", file)
                if os.path.exists(file_path):
                    with open(file_path, "rb") as f:
                        st.download_button(
                            label=f"📥 {file} 다운로드",
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
