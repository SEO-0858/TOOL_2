import streamlit as st
from pymongo import MongoClient
from bson.objectid import ObjectId

st.set_page_config(page_title="MongoDB 연동 테스트", layout="centered")
st.title("🧪 스트림릿 🤝 몽고디비 CRUD 완벽 검증")

# 1. 데이터베이스 연결 (로컬 기본 설정)
MONGO_URI = "mongodb+srv://sspon1270_db_user:wXA7NGCMjjTiTG5w@cluster0.1ectnsv.mongodb.net/?appName=Cluster0"

@st.cache_resource
def get_database():
    client = MongoClient(MONGO_URI)
    # 'dashboard_db'라는 데이터베이스의 'memos' 컬렉션(테이블 역할)을 사용합니다.
    return client["dashboard_db"]["memos"]

db_collection = get_database()

# -------------------------------------------------------------
# [1단계] 데이터 저장 (Create)
# -------------------------------------------------------------
st.header("1. 데이터 저장하기 (Create)")
with st.form(key="insert_form", clear_on_submit=True):
    new_memo = st.text_input("대쉬보드에 기록할 내용을 적으세요:")
    submit_button = st.form_submit_button(label="몽고디비에 저장")
    
    if submit_button and new_memo:
        # 몽고디비에 딕셔너리 형태로 저장
        db_collection.insert_one({"content": new_memo})
        st.success(f"📌 '{new_memo}' 가 성공적으로 저장되었습니다!")

st.markdown("---")

# -------------------------------------------------------------
# [2단계] 데이터 조회, 수정, 삭제 (Read, Update, Delete)
# -------------------------------------------------------------
st.header("2. 데이터 조회 / 수정 / 삭제 (R·U·D)")

# DB에서 전체 데이터 가져오기
data_list = list(db_collection.find())

if not data_list:
    st.info("현재 저장된 데이터가 없습니다. 위의 폼에서 데이터를 먼저 입력해 보세요.")
else:
    st.write(f"현재 총 **{len(data_list)}개**의 데이터가 DB에 있습니다.")
    
    # 데이터를 하나씩 꺼내서 화면에 뿌리고, 수정/삭제 버튼 달기
    for item in data_list:
        # 몽고디비의 고유 ID와 텍스트 내용 추출
        doc_id = item["_id"]
        current_content = item["content"]
        
        # 시각적으로 구분하기 위해 박스(container) 안에 배치
        with st.container():
            col1, col2, col3 = st.columns([5, 2, 1.5])
            
            # 컬럼 1: 현재 내용 표시 및 수정 입력칸
            with col1:
                edit_text = st.text_input(
                    f"내용 (ID: {str(doc_id)[:6]}...)", 
                    value=current_content, 
                    key=f"edit_{doc_id}"
                )
            
            # 컬럼 2: 수정 반영 버튼
            with col2:
                st.write("") # 줄맞춤용 공백
                if st.button("✏️ 수정", key=f"btn_edit_{doc_id}"):
                    # 몽고디비의 해당 ID를 찾아 내용 업데이트
                    db_collection.update_one({"_id": doc_id}, {"$set": {"content": edit_text}})
                    st.toast("수정이 완료되었습니다!")
                    st.rerun() # 화면 새로고침
                    
            # 컬럼 3: 삭제 버튼
            with col3:
                st.write("") # 줄맞춤용 공백
                if st.button("❌ 삭제", key=f"btn_del_{doc_id}"):
                    # 몽고디비의 해당 ID를 가진 데이터 삭제
                    db_collection.delete_one({"_id": doc_id})
                    st.toast("데이터가 삭제되었습니다.")
                    st.rerun() # 화면 새로고침
        
        
st.markdown("<small>--------------------------------------------------</small>", unsafe_allow_html=True)