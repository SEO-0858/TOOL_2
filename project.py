elif tool_menu == "🖥️ 실시간 기계 정보창":
        st.title("🖥️ 실시간 기계 배치 현황")
        
        # 기계 번호 리스트 (이미지 기준)
        machine_layout = [
            [27, 28, 29, 30, 31, 9, 8, 7],
            [16, 17, 26, 32, 57],
            [15, 18, 25, 33, 56],
            [14, 19, 24, 34, 55, 6],
            [13, 20, 35, 54, 5],
            [12, 21, 36, 53, 4],
            [11, 22, 37, 52, 3],
            [10, 23, 38, 43],
            [39, 40, 41, 42, 43],
            [45, 46, 47, 48, 49, 50, 51]
        ]

        # 데이터베이스에서 현재 가동 중인 기계들 불러오기
        active_tools = list(db_collection.find({"status": "사용중"}))
        active_machines = [int(t['machine_no'].replace('호기', '')) for t in active_tools if '호기' in t.get('machine_no', '')]

        # 배치도 그리기
        for row in machine_layout:
            cols = st.columns(len(row))
            for i, m_no in enumerate(row):
                with cols[i]:
                    # 가동 중이면 초록색, 아니면 회색
                    color = "green" if m_no in active_machines else "gray"
                    st.button(f"{m_no}", key=f"btn_{m_no}", help=f"{m_no}호기 정보 확인")
                    st.caption("공실" if m_no not in active_machines else "가동중")
