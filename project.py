# [수정된 부분] 
    if from_status == "재사용대기":
        st.info("📦 이 툴은 현재 보관 중인 [재사용대기] 상태이므로 기계 가공 호기가 '보관'으로 자동 지정됩니다.")
        pop_mach_name = "보관"
        # 재사용대기는 기존 작업자를 사용
        final_worker = ed_worker
    elif from_status == "사용전":
        st.info("🆕 이 툴은 [사용전] 새 제품입니다. 작업자와 기계 번호를 직접 입력하세요.")
        pop_mach_name = "없음"
        # 사용전 툴은 작업자를 직접 입력받음
        final_worker = st.text_input("👤 폐기 처리 작업자 성명", value="", placeholder="예: 홍길동")
    else:
        # 기존 방식
        orig_m_num = ''.join(filter(str.isdigit, str(current_mach)))
        try:
            def_m_val = int(orig_m_num) if orig_m_num else 0
        except:
            def_m_val = 0
        pop_waste_mach = st.number_input("⚙️ 방금 마친 기계 가공 호기 (숫자만)", min_value=1, max_value=200, value=def_m_val if def_m_val > 0 else 1, key=f"pop_mach_waste_{s_no}")
        pop_mach_name = f"{pop_waste_mach}호기"
        final_worker = ed_worker # 기존 방식
