import streamlit as st
from pymongo import MongoClient
import sys

st.set_page_config(page_title="KKQ 몽고디비 접속 테스트", layout="wide")

st.title("🔍 KKQ 몽고디비(MongoDB) 연결 상태 점검")
st.markdown("현재 코드에 기입된 아이디와 비밀번호가 몽고디비 클라우드 서버와 정상적으로 통신하는지 검증합니다.")
st.markdown("---")

# 1. 현재 테스트할 연결 주소 (기존에 주셨던 주소 그대로 주입)
MONGO_URI = "mongodb+srv://sspon1270_db_user:wXA7NGCmjjTiTG5w@cluster0.1ectnsv.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"

st.subheader("📋 입력된 연결 정보 확인")
st.code(MONGO_URI, language="text")

st.markdown("<br>", unsafe_allow_html=True)
st.subheader("⚡ 접속 테스트 진행 결과")

# 2. 실제 통신 시도 및 행위 로직
try:
    # 제한 시간을 5초로 둔 타임아웃 설정 추가 (무한 로딩 방지)
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    
    # admin 데이터베이스에 'ping' 명령을 날려 실제 인증 및 통신 상태 확인 (핵심 검증)
    client.admin.command('ping')
    
    # 🟢 성공 시 작동할 로직
    st.success("🎉 [접속 성공] 아이디와 비밀번호가 완벽하게 일치하며, 방화벽도 정상적으로 열려 있습니다!")
    st.balloons()
    
    # 연결된 김에 내부 데이터베이스 목록 출력해서 눈으로 확인하기
    st.markdown("### 🗃️ 내 몽고디비 서버 내부의 DB 목록:")
    db_names = client.list_database_names()
    for db in db_names:
        st.write(f"• **{db}**")

except Exception as e:
    # 🔴 실패 시 작동할 로직
    st.error("❌ [접속 실패] 몽고디비 인증 또는 통신에 실패했습니다.")
    
    st.markdown("### 🔧 시스템이 뱉은 진짜 에러 메시지 (상세):")
    st.warning(f"Error Details: {e}")
    
    # 에러 유형별 친절한 원인 가이드 출력
    error_str = str(e)
    if "authentication failed" in error_str or "bad auth" in error_str:
        st.markdown("""> 💡 **조치 가이드:** 비밀번호나 아이디가 몽고디비 Atlas 서버에 등록된 것과 다릅니다. 아까 로컬 PC 환경(localhost)과 지금 스트림릿 클라우드가 바라보는 주소가 완벽히 일치하는지 확인해 보거나, 몽고디비 사이트의 `Database Access` 메뉴에서 비밀번호를 재설정해야 합니다.""")
    elif "timeout" in error_str:
        st.markdown("""> 💡 **조치 가이드:** 네트워크 연결이 거부되었습니다. 아까 설정한 몽고디비 `Network Access` 메뉴에 `0.0.0.0/0` 방화벽 해제가 정상적으로 `Active` 상태인지 다시 한번 점검이 필요합니다.""")
