import pandas as pd
from pymongo import MongoClient
import os


def run_recover():
    mongo_uri = "mongodb+srv://sspon1270_db_user:wXA7NGCMjjTiTG5w@cluster0.1ectnsv.mongodb.net/?appName=Cluster0"
    client = MongoClient(mongo_uri)
    db = client['dashboard_db']

    # [복구할 파일들이 있는 폴더]
    backup_folder = r"\\192.168.0.221\제조2팀\4part\tool"
    # 복구할 컬렉션 리스트
    collections = ['disposal_logs', 'tool_specs_master', 'tools_management'] 
    # 2. 일괄 복구 시작
    pk_map = {
        'tools_management': ['serial_no'],
        'disposal_logs': ['serial_no'],
        'tool_specs_master': ['spec_detail', 'make'] # 두 항목 조합
    }

    for col_name in collections:
        file_path = os.path.join(backup_folder, f"{col_name}_backup.xlsx")
        if not os.path.exists(file_path): continue
            
        print(f"[{col_name}] 복구 시작...")
        df = pd.read_excel(file_path)
        df = df.where(pd.notnull(df), None)
        
        collection = db[col_name]
        pk_fields = pk_map.get(col_name, ['serial_no'])
        
        count = 0
        for _, row in df.iterrows():
            data_dict = row.to_dict()
            
            # 복합 키 쿼리 생성
            query = {field: data_dict[field] for field in pk_fields}
                
            result = collection.update_one(query, {'$set': data_dict}, upsert=True)
            if result.upserted_id or result.modified_count > 0:
                count += 1
                
        print(f"✅ [{col_name}] 복구 완료: {count}건 처리됨.")

    print("\n🎉 모든 데이터 복구/업데이트가 완료되었습니다!")

if __name__ == "__main__":
    run_recover()   
