# mong.py
import streamlit as st

# 하위 종목(마스터) 리스트를 DB에서 가져오는 함수
def get_master_specs(db):
    # db는 project.py에서 연결된 mongo 클라이언트를 넘겨받습니다
    collection = db['master_tool_collection'] # 대표님 DB의 마스터 컬렉션 이름으로 수정하세요
    return list(collection.find())

# 바코드 스캔 시 처리될 함수 (핵심)
def process_barcode(barcode_data, db):
    # 1. 마스터 데이터 가져오기
    master_list = get_master_specs(db)
    
    # 2. 바코드가 마스터에 있는지 확인
    found_tool = next((item for item in master_list if item['spec'] == barcode_data), None)
    
    if found_tool:
        return {"status": "found", "data": found_tool}
    else:
        return {"status": "not_found", "message": "마스터에 없는 툴입니다."}
