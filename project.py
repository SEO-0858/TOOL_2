import streamlit as st

# [경고 팝업 함수]
@st.dialog("⚠️ 상태 변경 규칙 위반")
def show_warning_dialog(message):
    st.error(message)
    if st.button("확인"):
        st.rerun()

if qr_scanned_serial:
    st.title("📱 현장 툴 정보 즉시 기입창")
    st.subheader(f"🆔 시리얼: `{qr_scanned_serial}`")
    
    # 1. DB 데이터 로드 (용어 통일: "사용전")
    existing_data = db_collection.find_one({"serial_no": qr_scanned_serial})
    db_status_mob = existing_data.get("status", "사용전") if existing_data else "사용전"
    
    # 2. 상태 전이 규칙 (사용전으로 통일)
    status_map = {
        "사용전": ["사용중", "폐기"],
        "사용중": ["재사용대기", "폐기"],
        "재사용대기": ["재사용", "폐기"],
        "재사용": ["재사용대기", "폐기"],
        "폐기": [] 
    }
    status_options = ["사용전", "사용중", "재사용", "재사용대기", "폐기"]
    
    # 3. 폼 영역
    with st.form(key="mobile_update_form"):
        st.markdown("### ⚡ 상태 및 수량 수정")
        
        # 전체 선택지 노출
        u_status = st.radio("🔄 툴 현재 상태 선택", status_options, index=status_options.index(db_status_mob) if db_status_mob in status_options else 0, horizontal=True)
        
        # [조건부 필수 입력]
        show_count_input = (db_status_mob == "사용중" and u_status in ["재사용대기", "폐기"])
        u_work_count = 0
        if show_count_input:
            u_work_count = st.number_input("🔢 이번 작업 가공 수량 (필수입력)", min_value=1, step=1)
        
        u_spec = st.selectbox("🛠 상세 스펙", ["파이90-20-200메쉬", "파이100-30-300메쉬", "파이50-10-100메쉬"], 
                             index=["파이90-20-200메쉬", "파이100-30-300메쉬", "파이50-10-100메쉬"].index(existing_data.get('detail_spec', "파이90-20-200메쉬")) if existing_data and existing_data.get('detail_spec') else 0)
        u_count = st.number_input("📊 누적 사용 횟수", value=int(existing_data.get('current_use', 0)) if existing_data else 0, step=1)
        u_worker = st.text_input("👷 작업자", value=existing_data.get('worker', '') if existing_data else "").strip()
        u_machine_num = st.number_input("⚙️ 기계 가공 호기", min_value=0, max_value=200, 
                                       value=int(''.join(filter(str.isdigit, existing_data.get('machine_no', '0'))) or 0) if existing_data else 0, step=1)
        u_note = st.text_area("📝 특이사항", value=existing_data.get('note', '') if existing_data else "")
        
        u_submit_form_btn = st.form_submit_button("🔄 수정사항 저장하기")

    # 4. 저장 로직 (검증 포함)
    if u_submit_form_btn:
        # 검증 1: 동일 상태 선택 방지
        if u_status == db_status_mob:
            st.warning("⚠️ 현재 상태와 동일합니다. 변경할 상태를 선택하세요.")
        
        # 검증 2: 규칙 위반 체크 (통일된 "사용전" 기반)
        elif u_status not in status_map.get(db_status_mob, []):
            show_warning_dialog(f"🚨 현재 '{db_status_mob}' 상태에서는 '{u_status}'로 이동할 수 없습니다.")
        
        # 검증 3: 필수 입력 체크
        elif show_count_input and u_work_count == 0:
            st.error("🚨 필수 항목: 이번 작업 가공 수량을 입력해주세요!")
        
        else:
            log_time_str = get_now_kst().strftime("%Y-%m-%d %H:%M:%S")
            new_log = f"\n[{log_time_str}] 상태:{db_status_mob}→{u_status}"
            if show_count_input: new_log += f", 가공수량:{u_work_count}개"
            new_log += f", 작업자:{u_worker}, 기계:{u_machine_num}호기"
            
            final_note_val = (existing_data.get('note', '') if existing_data else '') + new_log
            new_total_use = u_count + u_work_count
            
            db_collection.update_one(
                {"serial_no": qr_scanned_serial},
                {"$set": {
                    "status": u_status,
                    "detail_spec": u_spec,
                    "current_use": new_total_use,
                    "worker": u_worker,
                    "machine_no": f"{u_machine_num}호기",
                    "note": final_note_val
                }},
                upsert=True
            )
            st.success("✅ 저장 완료!")
            st.rerun()

    if st.button("🏠 메인으로 돌아가기"):
        st.query_params.clear()
        st.rerun()
