def get_tool_type_name(serial_no):
    """시리얼 번호 첫 글자로 툴 타입을 반환하는 함수"""
    if not serial_no or len(serial_no) == 0: return "알수없음"
    mapping = {"1": "전착", "2": "레진", "3": "메탈", "4": "코어"}
    return mapping.get(serial_no[0], "기타")

def render_tool_ui(item, color_hex, status_label, time_text, db_status):
    """
    실시간 기계 정보창 UI
    - db_status: 툴의 현재 실제 상태 (사용중, 재사용 등)
    - status_label: 드레싱 알림 상태 (정상 가동 중, 주의 등)
    """
    tool_type = get_tool_type_name(item.get('serial_no', ''))
    worker_name = item.get('worker', '-')
    
    st.markdown(f"""
    <div style="padding: 10px; border-radius: 8px; border-left: 6px solid {color_hex}; background-color: #f9f9f9; margin-bottom: 5px;">
        <h4 style="margin: 0; font-size: 15px;">🆔 {item.get('serial_no')}</h4>
        
        <div style="font-size: 14px; font-weight: bold; color: #222; margin: 5px 0;">
            [{db_status}] | <span style="color: {color_hex};">{status_label}</span>
        </div>
        
        <div style="font-size: 13px; font-weight: bold; color: #444;">
            [{tool_type}툴]
        </div>
        
        <div style="font-size: 13px; color: #333; margin-top: 2px;">
            👤 <b>작업자:</b> {worker_name}
        </div>
        
        <div style="font-size: 12px; color: #666; margin-top: 2px;">
            🛠 {item.get('detail_spec', '-')} <br>
            ⏳ 주기: {item.get('dressing_hours', 0)}시간 {item.get('dressing_mins', 0)}분
        </div>
        
        <div style="font-size: 11px; color: #d9534f; margin-top: 3px;">
            {time_text}
        </div>
    </div>
    """, unsafe_allow_html=True)
