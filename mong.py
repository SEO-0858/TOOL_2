import streamlit as st

def render_search_menu():
    st.sidebar.write("### 검색 옵션")
    if st.sidebar.button("⚙️ 스펙 중심 검색"):
        st.session_state['search_mode'] = 'spec'
    if st.sidebar.button("🏭 제조사 중심 검색"):
        st.session_state['search_mode'] = 'make'
