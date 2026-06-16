import streamlit as st
from datetime import datetime
from datetime import datetime as dt, timedelta

# 한국 시간 구하는 함수 (기존 thr.py에 있는 것과 동일하게)
def get_now_kst():
    # UTC 시간에 9시간을 더해 한국 시간으로 만듭니다
    return datetime.utcnow() + timedelta(hours=9)

def add_new_tool(barcode_input, db_collection):
    try:
        # 1. 데이터 분리
        parts = barcode_input.split('|')
        if len(parts) != 3:
            return False, "바코드 형식이 틀렸습니다."
        
        cat, spec, vendor = parts
        now = get_now_kst()
        
        # 2. 신규 데이터 생성
        new_tool = {
            "serial_no": f"{cat}{now.strftime('%Y%m%d%H%M%S')}",
            "tool_type": cat,
            "detail_spec": spec,
            "worker": vendor,
            "status": "사용전",
            "input_date": now.strftime('%Y-%m-%d'),
            "init_time": now.strftime('%H:%M'),
            "note": f"{now.strftime('%Y-%m-%d %H:%M')} 바코드 입고 업체: {vendor}"
        }
        
        # 3. DB 저장
        db_collection.insert_one(new_tool)
        return True, spec
    except Exception as e:
        return False, str(e)
