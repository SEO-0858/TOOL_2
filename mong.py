import streamlit as st
from pymongo import MongoClient

# 툴 상세 스펙 리스트 (나중에 관리 메뉴 만들어서 여기서 빼내시면 됩니다)
ALL_TOOLS = [
    {"tool_type": "COR", "spec_detail": "D90_5T_1.5T_#200"},
    {"tool_type": "COR", "spec_detail": "D90_5T_1.5T_#100"},
    {"tool_type": "MET", "spec_detail": "D100_3W_#325"},
    {"tool_type": "MET", "spec_detail": "D100_3W_#170"},
    {"tool_type": "MET", "spec_detail": "D80_40T_#325"},
    {"tool_type": "MET", "spec_detail": "D90_50T_#325"},
    {"tool_type": "MET", "spec_detail": "D80_40T_#600"},
    {"tool_type": "MET", "spec_detail": "D90_50T_#600"},
    {"tool_type": "MET", "spec_detail": "D100_20T_#80"},
    {"tool_type": "JUN", "spec_detail": "D90_10T_A45_#500"},
    {"tool_type": "JUN", "spec_detail": "D80_20T_1R_#200"},
    {"tool_type": "JUN", "spec_detail": "D90_17T_C2_#200"},
    {"tool_type": "JUN", "spec_detail": "D60_50T_#200"},
    {"tool_type": "JUN", "spec_detail": "D60_50T_#325"},
    {"tool_type": "JUN", "spec_detail": "D102.12_41.8T_6.35R_#400"},
    {"tool_type": "JUN", "spec_detail": "D80_45T_6.73R_#400"},
    {"tool_type": "JUN", "spec_detail": "D90_16T_V45_#200"},
    {"tool_type": "JUN", "spec_detail": "D90_16T_V45_#325"},
    {"tool_type": "JUN", "spec_detail": "D80_15T_0.3R_#200"},
    {"tool_type": "JUN", "spec_detail": "D80_15T_0.8R_#200"},
    {"tool_type": "JUN", "spec_detail": "D80_20T_0.3R_#200"},
    {"tool_type": "JUN", "spec_detail": "D80_20T_0.3R_#325"},
    {"tool_type": "JUN", "spec_detail": "D90_23T_0.3R_#200"},
    {"tool_type": "JUN", "spec_detail": "D100_25T_0.3R_#200"},
    {"tool_type": "JUN", "spec_detail": "D90_23T_0.3R_#325"},
    {"tool_type": "JUN", "spec_detail": "D90_23T_0.3R_#400"},
    {"tool_type": "JUN", "spec_detail": "D90_23T_1R_#200"},
    {"tool_type": "JUN", "spec_detail": "D100_25T_1R_#200"},
    {"tool_type": "JUN", "spec_detail": "D100_25T_1R_#400"},
    {"tool_type": "JUN", "spec_detail": "D90_17T_1R_#400"},
    {"tool_type": "JUN", "spec_detail": "D90_14T_2R_17V_#400"},
    {"tool_type": "REJ", "spec_detail": "D90_25T_#200"},
    {"tool_type": "REJ", "spec_detail": "D90_50T_#200"},
    {"tool_type": "REJ", "spec_detail": "D75_15V_#325"},
    {"tool_type": "REJ", "spec_detail": "D90_15T_#325"},
    {"tool_type": "REJ", "spec_detail": "D90_25T_#325"},
    {"tool_type": "REJ", "spec_detail": "D90_50T_#325"},
    {"tool_type": "REJ", "spec_detail": "D90_25T_#500"},
    {"tool_type": "REJ", "spec_detail": "D90_50T_#500"},
    {"tool_type": "REJ", "spec_detail": "D90_25T_#600"},
    {"tool_type": "REJ", "spec_detail": "D90_50T_#600"},
    {"tool_type": "REJ", "spec_detail": "D90_5T_#325"}
]

def get_collection():
    mongo_uri = st.secrets["database"]["MONGO_URI"]
    client = MongoClient(mongo_uri)
    db = client["dashboard_db"]
    return db["tool_inventory"]

def initialize_db():
    collection = get_collection()
    count = 0
    for tool in ALL_TOOLS:
        if not collection.find_one({"tool_type": tool["tool_type"], "spec_detail": tool["spec_detail"]}):
            tool["new_stock"] = 0
            tool["used_stock"] = 0
            collection.insert_one(tool)
            count += 1
    return count
