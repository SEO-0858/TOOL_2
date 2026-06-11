# --- 📱 [모바일/현장 QR 스캔 기입 모드] ---
if qr_scanned_serial:
    st.title("📱 현장 툴 정보 즉시 기입창")
    st.subheader(f"🆔 시리얼 넘버: `{qr_scanned_serial}`")
    
    # 1. 데이터 조회
    existing_data = db_collection.find_one({"serial_no": qr_scanned_serial}) or {}
    prev_status = existing_data.get("status", "사용전")
    
    # [수정] 특이사항 데이터를 확실하게 불러오기
    saved_note = existing_data.get("note", "")
    
    # 2. 상태 선택
    st.markdown("### 🔄 툴 현재 상태")
    status_options = ["사용전", "사용중", "재사용", "재사용대기", "폐기"]
    status_index = status_options.index(prev_status) if prev_status in status_options else 0
    u_status = st.radio("상태를 선택하세요", status_options, index=status_index, horizontal=True)
    
    st.divider()
    
    # 3. 입력 필드
    st.markdown("### 📝 기본 정보")
    u_worker = st.text_input("👷 교체 작업자 이름", value=existing_data.get('worker', '')).strip()
    
    orig_mach = existing_data.get('machine_no', '')
    default_mach = int(''.join(filter(str.isdigit, orig_mach))) if any(c.isdigit() for c in orig_mach) else 0
    u_machine_num = st.number_input("⚙️ 기계 가공 호기 (숫자만 입력)", min_value=0, max_value=200, value=default_mach, step=1)
    
    spec_master_col = get_spec_master_collection()
    spec_options = [s['spec_name'] for s in list(spec_master_col.find({}))] or ["스펙없음"]
    current_spec = existing_data.get('detail_spec', spec_options[0])
    spec_index = spec_options.index(current_spec) if current_spec in spec_options else 0
    u_spec = st.selectbox("🛠 툴 세부 스펙 선택", spec_options, index=spec_index)
    
    st.divider()
    
    # 4. 드레싱 주기 설정
    st.markdown("### ⏳ 드레싱 주기 설정")
    col_h, col_m = st.columns(2)
    with col_h:
        u_hours = st.number_input("시간(Hour)", min_value=0, max_value=72, value=existing_data.get('dressing_hours', 0))
    with col_m:
        u_mins = st.number_input("분(Minute)", min_value=0, max_value=59, value=existing_data.get('dressing_mins', 0))
        
    # [수정] saved_note를 그대로 입력창에 넣어줌
    u_note = st.text_area("📝 현장 특이사항 (이전 기록)", value=saved_note, height=150)
    
    # 5. 저장 로직
    if st.button("💾 데이터 저장 및 수정 완료"):
        if not u_worker:
            st.error("⚠️ 작업자 이름을 입력해주세요!")
        else:
            # 상태가 바뀔 때만 로그 추가
            final_note_val = u_note.strip()
            if u_status != prev_status:
                current_time_str = get_now_kst().strftime("%Y-%m-%d %H:%M:%S")
                log_msg = f"\n[{current_time_str}] 상태:{u_status}, 작업자:{u_worker}, 기계:{u_machine_num}호기"
                final_note_val = final_note_val + log_msg
            
            # PC 알림판용 시간 계산
            total_minutes = (u_hours * 60) + u_mins
            start_dt = get_now_kst()
            target_dt = start_dt + timedelta(minutes=total_minutes)
            
            # DB 업데이트
            db_collection.update_one(
                {"serial_no": qr_scanned_serial},
                {"$set": {
                    "status": u_status,
                    "worker": "" if u_status in ["사용전", "폐기"] else u_worker,
                    "machine_no": "" if u_status in ["사용전", "폐기"] else f"{u_machine_num}호기",
                    "dressing_hours": u_hours,
                    "dressing_mins": u_mins,
                    "note": final_note_val,
                    "detail_spec": u_spec,
                    "start_time": start_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "target_time": target_dt.strftime("%Y-%m-%d %H:%M:%S")
                }},
                upsert=True
            )
            st.toast("✅ 저장 완료!", icon="🎉")
            st.rerun()

    if st.button("🏠 메인으로 돌아가기"):
        st.query_params.clear()
        st.rerun()
