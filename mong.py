import streamlit as st

def render_search_menu():
    st.sidebar.write("### 검색 옵션")
    if st.sidebar.button("⚙️ 재고 검색"):
        st.session_state['search_mode'] = 'spec'
    if st.sidebar.button("🏭 데이터베이스 BACK UP"):
        st.session_state['search_mode'] = 'make'
    if st.sidebar.button("🏭 데이터베이스  RECOVER"):
        st.session_state['search_mode'] = 'make'
