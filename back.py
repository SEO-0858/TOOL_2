import pandas as pd
from pymongo import MongoClient
import os

def run_backup():
    mongo_uri = "mongodb+srv://sspon1270_db_user:wXA7NGCMjjTiTG5w@cluster0.1ectnsv.mongodb.net/?appName=Cluster0"
    client = MongoClient(mongo_uri)
    db = client['dashboard_db']

    # [여기에 4개 컬렉션 이름을 적어주세요]
    collections = ['disposal_logs', 'tool_inventory', 'tool_specs_master', 'tools_management'] 
    save_folder = r"\\192.168.0.221\제조2팀\4part\tool"

    # 2. 일괄 백업 시작
    for col_name in collections:
        print(f"[{col_name}] 백업을 시작합니다...")
        collection = db[col_name]
        data = list(collection.find())
        
        if not data:
            print(f"⚠️ [{col_name}] 데이터가 없어 건너뜁니다.")
            continue
            
        df = pd.DataFrame(data)
        if '_id' in df.columns:
            df = df.drop(columns=['_id'])

        # 중복 제거 (serial_no가 있다면 적용, 없으면 아래 줄 주석 처리)
        if 'serial_no' in df.columns:
            df = df.drop_duplicates(subset=['serial_no'], keep='last')
            df = df.sort_values('serial_no')

        # 엑셀 저장
        file_path = os.path.join(save_folder, f"{col_name}_backup.xlsx")
        writer = pd.ExcelWriter(file_path, engine='xlsxwriter')
        df.to_excel(writer, sheet_name=col_name, index=False)

        # 서식 적용 (중간 맞춤 & 자동 줄 맞춤)
        workbook = writer.book
        worksheet = writer.sheets[col_name]
        center_format = workbook.add_format({'align': 'center', 'valign': 'vcenter'})

        for i, col in enumerate(df.columns):
            column_len = max(df[col].astype(str).map(len).max(), len(col)) + 2
            worksheet.set_column(i, i, column_len, center_format)

        writer.close()
        print(f"✅ [{col_name}] 완료: {file_path}")

    print("\n🎉 모든 컬렉션 백업이 완료되었습니다!")

if __name__ == "__main__":
    run_backup()
