import streamlit as st
import streamlit.components.v1 as components
from pymongo import MongoClient
from bson import ObjectId
import datetime
from datetime import datetime as dt, timedelta
import pandas as pd
import re, time, base64, json, qrcode, pytz
from io import BytesIO
from urllib import error as urlerror, parse as urlparse, request as urlrequest
try:
    from streamlit_qrcode_scanner import qrcode_scanner
except ImportError:
    qrcode_scanner = None

st.set_page_config(page_title="4PART 원자재 입고·3PART 인계", layout="wide")
dt_class = dt
@st.cache_resource
def get_database():
    uri = st.secrets["database"]["MONGO_URI"]
    client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    return client["dashboard_db"]["tools_management"]

db_collection = get_database()
now = datetime.datetime.now(pytz.timezone("Asia/Seoul")).replace(tzinfo=None)
today = now.date()
mmdd = today.strftime("%m%d")
query_params = st.query_params
qr_scanned_serial = query_params.get("serial", None)

def normalize_lot_api_key(raw_key):
    key = str(raw_key or "").strip()
    if not key:
        return ""

    if "key=" in key or "?" in key:
        parsed = urlparse.urlparse(key)
        query_text = parsed.query if parsed.query else key.lstrip("?")
        query_values = urlparse.parse_qs(query_text)
        key_values = query_values.get("key")
        if key_values:
            return str(key_values[0]).strip()
        if key.lower().startswith("key="):
            return key.split("=", 1)[1].strip()

    return key


def add_query_param(raw_url, name, value):
    if not value:
        return raw_url

    parsed = urlparse.urlparse(raw_url)
    query_values = urlparse.parse_qsl(parsed.query, keep_blank_values=True)
    query_values.append((name, value))
    return urlparse.urlunparse(parsed._replace(query=urlparse.urlencode(query_values)))


def get_lot_api_config():
    try:
        config = st.secrets.get("ksi_lot_api", {})
    except Exception:
        config = {}
    return {
        "url": str(config.get("url", "")).strip(),
        "key": normalize_lot_api_key(config.get("key", "")),
    }


def lot_api_debug_text():
    api = get_lot_api_config()
    url = api.get("url", "")
    key = api.get("key", "")
    masked_key_tail = f"**{key[-2:]}" if len(key) >= 2 else "(empty)"
    return (
        f" LOT API 확인: URL={'있음' if url else '없음'}"
        f", KEY={'있음' if key else '없음'}"
        f", KEY글자수={len(key)}"
        f", KEY끝2자리={masked_key_tail}"
    )


def summarize_lot_http_error(exc):
    body = ""
    try:
        body = exc.read().decode("utf-8", errors="replace")
    except Exception:
        body = ""

    one_line = re.sub(r"\s+", " ", body).strip()
    if len(one_line) > 220:
        one_line = one_line[:220] + "..."

    headers_text = ""
    server = ""
    try:
        headers_text = str(exc.headers)
        server = exc.headers.get("server", "") or exc.headers.get("Server", "")
    except Exception:
        headers_text = ""

    body_lower = one_line.lower()
    headers_lower = headers_text.lower()
    if "invalid api key" in body_lower:
        source = "bridge_key_rejected"
    elif "cloudflare" in body_lower or "cf-ray" in headers_lower:
        source = "cloudflare_block_or_challenge"
    else:
        source = "unknown_403"

    return f" 403상세: source={source}, server={server or '(none)'}, body={one_line or '(empty)'}"


def build_ksi_work_order_no(tail_or_full, prefix=None):
    value = str(tail_or_full or "").strip().upper()
    if not value:
        return ""
    if value.startswith("KK"):
        return value

    digits = re.sub(r"\D", "", value)
    if not digits:
        return ""

    if prefix is None:
        prefix = f"KK{get_now_kst().year}"
    return f"{prefix}{digits}"


def normalize_lot_response(data, requested_work_order_no):
    if isinstance(data, list):
        data = data[0] if data else {}
    if not isinstance(data, dict):
        data = {}

    rows = data.get("rows")
    first_row = rows[0] if isinstance(rows, list) and rows and isinstance(rows[0], dict) else {}

    def pick(*keys):
        for source in (data, first_row):
            for key in keys:
                value = source.get(key)
                if value is not None and str(value).strip():
                    return str(value).strip()
        return ""

    # K-System 조회 목록에서 생산부서가 "품질경영팀"인 행의 진행상태만 추출합니다.
    quality_management_status = ""
    if isinstance(rows, list):
        for row in rows:
            if not isinstance(row, dict):
                continue

            department = ""
            for key in (
                "생산부서", "production_department", "department",
                "dept_name", "department_name", "부서", "팀명",
            ):
                value = row.get(key)
                if value is not None and str(value).strip():
                    department = str(value).strip()
                    break

            if re.sub(r"\s+", "", department) != "품질경영팀":
                continue

            for key in (
                "진행상태", "progress_status", "process_status",
                "status", "work_status",
            ):
                value = row.get(key)
                if value is not None and str(value).strip():
                    quality_management_status = str(value).strip()
                    break
            break

    normalized = {
        "work_order_no": pick("work_order_no", "lot", "LOT", "작업지시번호") or requested_work_order_no,
        "product_name": pick("product_name", "item_name", "품명", "AssyName"),
        "spec": pick("spec", "item_spec", "품목규격", "규격", "AssyItemSpec"),
        "plan_qty": pick("plan_qty", "plan_quantity", "계획수량"),
        "quality_management_status": quality_management_status,
    }
    normalized["lookup_ok"] = bool(normalized["spec"])
    return normalized


def lookup_ksi_lot_info(work_order_no):
    api = get_lot_api_config()
    if not api["url"]:
        return None, "K-System LOT 중계 API 주소가 아직 설정되지 않았습니다."

    base_url = api["url"]
    if "{work_order_no}" in base_url:
        lookup_url = base_url.replace("{work_order_no}", urlparse.quote(work_order_no))
    elif "{tail}" in base_url:
        tail = work_order_no[6:] if work_order_no.startswith("KK") else work_order_no
        lookup_url = base_url.replace("{tail}", urlparse.quote(tail))
    else:
        lookup_url = base_url.rstrip("/") + "/lot/" + urlparse.quote(work_order_no)

    headers = {
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (KSI-LOT-Streamlit/1.0)",
    }
    if api["key"]:
        headers["X-API-Key"] = api["key"]
        lookup_url = add_query_param(lookup_url, "key", api["key"])

    req = urlrequest.Request(lookup_url, headers=headers, method="GET")
    try:
        with urlrequest.urlopen(req, timeout=5) as response:
            payload = response.read().decode("utf-8")
            data = json.loads(payload)
            if isinstance(data, dict) and data.get("ok") is False:
                return None, str(data.get("message") or "LOT 조회 결과가 없습니다.")
            info = normalize_lot_response(data, work_order_no)
            if not info.get("spec"):
                return None, "LOT 조회는 되었지만 ERP 규격(spec) 값이 없습니다."
            return info, ""
    except urlerror.HTTPError as exc:
        if exc.code == 403:
            return None, "LOT 조회 인증 실패(HTTP 403)." + lot_api_debug_text() + summarize_lot_http_error(exc)
            return None, "LOT 조회 인증 실패(HTTP 403): Streamlit Secrets의 ksi_lot_api.key 값을 중계 PC api_key와 똑같이 맞춰주세요." + lot_api_debug_text()
            return None, "LOT 조회 인증 실패(HTTP 403): Streamlit Secrets의 ksi_lot_api.key 값을 중계 PC api_key와 똑같이 맞춰주세요."
        return None, f"LOT 조회 서버 응답 오류: HTTP {exc.code}"
    except Exception as exc:
        return None, f"LOT 조회 실패: {exc}"


def get_now_kst():
    
    return datetime.datetime.now(pytz.timezone('Asia/Seoul')).replace(tzinfo=None)

MATERIAL_MENU_LABEL = "📦 원자재 입고 정보"
MATERIAL_COLLECTION_NAME = "material_receiving_logs"

HANDOVER_MENU_LABEL = "🚚 3PART 인계"
TOSS_COLLECTION_NAME = "toss_logs"

MACHINE_TOOL_HISTORY_MENU_LABEL = "🏭 장비별 툴 장착/폐기 이력"

MATERIAL_RECEIVER_MAP = {
    "01": "서재욱",
    "02": "서동일",
    "03": "정광우",
    "04": "정우철",
    "05": "강영천",
    "06": "허진웅",
    "07": "김연용",
    "08": "이덕무",
    "09": "홍민기",
    "10": "이해근",
    "11": "노재학",
    "12": "변두학",
    "13": "이동주",
    "14": "이현준",
    "15": "최광식",
    "16": "한제훈",
    "17": "한건우",
    "18": "이승형",
    "19": "유관우",
    "20": "신재관",
    "21": "최인준",
    "22": "김성욱",
    "23": "김은호",
    "24": "문태수",
    "25": "엄현석",
    "26": "김영환",
    "27": "나윤호",
    "28": "권용수",
    "29": "노우석",
    "30": "박철환",
}


def get_material_collection():
    return db_collection.database[MATERIAL_COLLECTION_NAME]


@st.dialog("⚠️ LOT 데이터 완전 삭제")
def confirm_material_lot_delete(lot_no):
    """선택 LOT의 입고·3PART 인계 기록을 두 컬렉션에서 모두 완전 삭제합니다."""
    lot_no = str(lot_no or "").strip().upper()
    if not lot_no:
        st.error("삭제할 LOT 번호가 없습니다.")
        return

    material_collection = get_material_collection()
    toss_collection = db_collection.database[TOSS_COLLECTION_NAME]
    material_count = material_collection.count_documents({"lot_no": lot_no})
    toss_count = toss_collection.count_documents({"lot_no": lot_no})
    expected_tail = lot_no[-7:] if len(lot_no) >= 7 else lot_no

    st.error("이 작업은 복구할 수 없는 완전 삭제입니다.")
    st.write(f"**선택 LOT:** `{lot_no}`")
    count_cols = st.columns(2)
    count_cols[0].metric("입고 기록", f"{material_count:,}건")
    count_cols[1].metric("3PART 인계 기록", f"{toss_count:,}건")
    st.info(f"삭제 확인을 위해 LOT의 마지막 숫자 7자리 **{expected_tail}**를 입력하세요.")

    confirm_tail = st.text_input(
        "LOT 마지막 숫자 7자리",
        max_chars=7,
        placeholder="예: 0630011",
        key=f"material_delete_confirm_tail_{lot_no}",
    ).strip()
    valid_tail = bool(
        len(confirm_tail) == 7
        and confirm_tail.isdigit()
        and confirm_tail == expected_tail
    )

    if confirm_tail and not valid_tail:
        st.warning("입력한 7자리 숫자가 선택 LOT와 일치하지 않습니다.")

    cancel_col, delete_col = st.columns(2)
    if cancel_col.button("❌ 취소", use_container_width=True):
        st.rerun()

    if delete_col.button(
        "🗑️ 두 컬렉션에서 완전 삭제",
        disabled=not valid_tail,
        type="primary",
        use_container_width=True,
    ):
        try:
            material_result = material_collection.delete_many({"lot_no": lot_no})
            toss_result = toss_collection.delete_many({"lot_no": lot_no})
        except Exception as exc:
            st.error(f"MongoDB 삭제 중 오류가 발생했습니다: {exc}")
            return

        st.session_state.material_lot_delete_saved_message = (
            f"LOT {lot_no} 삭제 완료 · "
            f"입고 {material_result.deleted_count}건 / "
            f"3PART 인계 {toss_result.deleted_count}건"
        )
        for key in (
            "material_search_results_live",
            "material_search_executed_live",
            "material_search_description_live",
            "material_memo_edit_selected_index",
        ):
            st.session_state.pop(key, None)
        st.session_state.pop(f"material_delete_confirm_tail_{lot_no}", None)
        st.rerun()


@st.dialog("📝 원자재 입고 메모 수정 최종 확인")
def confirm_material_memo_update():
    """입고 검색에서 선택한 한 건의 메모만 최종 확인 후 수정합니다."""
    record = st.session_state.get("material_memo_edit_record")
    new_memo = str(st.session_state.get("material_memo_edit_pending", ""))
    editor_no = str(st.session_state.get("material_memo_edit_editor_no", ""))
    editor_name = str(st.session_state.get("material_memo_edit_editor_name", ""))
    edit_datetime = str(
        st.session_state.get("material_memo_edit_timestamp", "")
        or get_now_kst().strftime("%Y-%m-%d %H:%M:%S")
    )

    if not record:
        st.error("수정할 입고 기록을 찾지 못했습니다. 창을 닫고 다시 선택해 주세요.")
        return

    old_memo = str(record.get("memo", "") or "")
    st.warning("아래 입고수량과 메모 내용을 다시 확인한 뒤 저장해 주세요.")

    info_cols = st.columns(2)
    info_cols[0].write(f"**LOT:** {record.get('lot_no', '-')}")
    info_cols[1].write(f"**입고일:** {record.get('receive_date', '-')}")
    info_cols[0].write(f"**품명:** {record.get('product_name', '-')}")
    info_cols[1].write(f"**규격:** {record.get('spec', '-')}")
    info_cols[0].write(
        f"**이번 입고수량:** {to_int_safe(record.get('received_qty'), 0):,}개"
    )
    info_cols[1].write(
        f"**누적 입고수량:** {to_int_safe(record.get('received_total_after'), 0):,}개"
    )
    st.write(f"**기존 인수자:** {record.get('receiver_name', '-')}")
    editor_display = f"{editor_no} {editor_name}".strip() or "작업자 정보 없음"
    st.write(f"**메모 수정 작업자:** {editor_display}")
    st.write(f"**메모 기입 일시:** {edit_datetime}")

    st.markdown("##### 변경 전 메모")
    st.code(old_memo if old_memo else "(메모 없음)", language=None)
    st.markdown("##### 변경 후 메모")
    st.code(new_memo if new_memo else "(메모를 비움)", language=None)

    confirmed = st.checkbox(
        "위 입고수량과 변경할 메모 내용이 정확합니다.",
        key="material_memo_edit_final_confirm",
    )

    cancel_col, save_col = st.columns(2)
    if cancel_col.button("❌ 취소", use_container_width=True):
        st.session_state.pop("material_memo_edit_pending", None)
        st.session_state.pop("material_memo_edit_record", None)
        st.session_state.pop("material_memo_edit_timestamp", None)
        st.session_state.pop("material_memo_edit_final_confirm", None)
        st.rerun()

    if save_col.button("✅ 확인 후 저장", use_container_width=True):
        if not confirmed:
            st.error("입고수량과 메모 내용을 확인했다는 체크가 필요합니다.")
            return
        if new_memo == old_memo:
            st.warning("메모 내용이 변경되지 않았습니다.")
            return

        record_id = record.get("_id")
        if not record_id:
            st.error("입고 기록의 고유 ID가 없어 저장할 수 없습니다.")
            return

        # 확인창에 표시한 시간과 MongoDB에 저장하는 시간을 동일하게 사용합니다.
        now_text = edit_datetime
        result = get_material_collection().update_one(
            {"_id": ObjectId(str(record_id))},
            {
                "$set": {
                    "memo": new_memo,
                    "memo_updated_at": now_text,
                    "memo_updated_by_no": editor_no,
                    "memo_updated_by": editor_name,
                }
            },
        )

        if result.matched_count != 1:
            st.error("수정할 입고 기록을 MongoDB에서 찾지 못했습니다.")
            return
        if result.modified_count != 1:
            st.error("MongoDB에서 메모가 변경되지 않았습니다. 내용을 다시 확인해 주세요.")
            return

        # 화면에 보관된 검색 결과도 새 메모로 갱신합니다.
        cached_records = st.session_state.get("material_search_results_live", [])
        for cached in cached_records:
            if str(cached.get("_id")) == str(record_id):
                cached["memo"] = new_memo
                cached["memo_updated_at"] = now_text
                cached["memo_updated_by_no"] = editor_no
                cached["memo_updated_by"] = editor_name
                break

        st.session_state.material_memo_edit_saved_message = (
            f"{record.get('lot_no', '')} 입고 기록의 메모가 수정되었습니다."
        )
        st.session_state.pop("material_memo_edit_pending", None)
        st.session_state.pop("material_memo_edit_record", None)
        st.session_state.pop("material_memo_edit_timestamp", None)
        st.session_state.pop("material_memo_edit_final_confirm", None)
        st.rerun()


def to_int_safe(value, default=0):
    try:
        if value in (None, ""):
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def normalize_material_lot_text(raw_text):
    """
    QR에 LOT 번호만 들어 있거나, URL 전체가 들어 있어도 LOT 번호만 추출합니다.
    예:
      KK20260703080
      0703080
      https://.../?serial=KK20260703080
      https://.../?lot=0703080
    """
    original = str(raw_text or "").strip()
    if not original:
        return ""

    # 1) QR 내용이 URL이면 쿼리 파라미터에서 LOT 후보를 먼저 찾습니다.
    try:
        parsed = urlparse.urlparse(original)
        query = urlparse.parse_qs(parsed.query)
        for key in ("material_qr", "lot", "lot_no", "work_order_no", "serial"):
            values = query.get(key)
            if values:
                candidate = str(values[0]).strip()
                if candidate and candidate != original:
                    return normalize_material_lot_text(candidate)
    except Exception:
        pass

    text = original.upper().replace(" ", "")

    # 2) 문자열 안에 완성형 작업지시번호(KK + 연도 + 숫자)가 있으면 그것만 추출합니다.
    full_match = re.search(r"KK20\d{6,}", text)
    if full_match:
        return full_match.group(0)

    # 3) URL 경로나 일반 문자열에 섞인 경우 숫자 덩어리 중 가장 긴 값을 사용합니다.
    digit_groups = re.findall(r"\d+", text)
    if digit_groups:
        candidate = max(digit_groups, key=len)
        # 7자리 이상인 값만 LOT 후보로 인정합니다.
        if len(candidate) >= 7:
            return build_ksi_work_order_no(candidate)

    # 4) 마지막 일반 처리
    return build_ksi_work_order_no(text)


def normalize_material_receiver_no(value):
    digits = re.sub(r"\D", "", str(value or ""))
    if not digits:
        return ""
    if len(digits) <= 2:
        return digits.zfill(2)
    return digits


def get_material_received_total(lot_no):
    if not lot_no:
        return 0

    pipeline = [
        {"$match": {"lot_no": lot_no}},
        {"$group": {"_id": "$lot_no", "total": {"$sum": "$received_qty"}}},
    ]
    result = list(get_material_collection().aggregate(pipeline))
    return to_int_safe(result[0].get("total"), 0) if result else 0


def get_material_latest_record(lot_no):
    """해당 LOT의 가장 최근 입고 이력을 반환합니다."""
    if not lot_no:
        return None
    return get_material_collection().find_one(
        {"lot_no": lot_no},
        sort=[("_id", -1)],
    )


def build_material_search_query(keyword):
    keyword = str(keyword or "").strip()
    if not keyword:
        return {}

    fields = ["lot_no", "product_name", "spec", "receiver_name", "memo"]
    tokens = [token for token in re.split(r"\s+", keyword) if token]
    token_queries = []
    for token in tokens:
        safe_token = re.escape(token)
        token_queries.append({
            "$or": [
                {field: {"$regex": safe_token, "$options": "i"}}
                for field in fields
            ]
        })

    return {"$and": token_queries} if len(token_queries) > 1 else token_queries[0]


def get_material_records(keyword="", limit=500):
    query = build_material_search_query(keyword)
    return list(get_material_collection().find(query).sort("created_at", -1).limit(limit))


def build_material_advanced_search_query(
    lot_no="",
    product_name="",
    spec="",
    receiver_name="",
    memo="",
    memo_exists_only=False,
    start_date=None,
    end_date=None,
):
    """입고 검색 화면의 조건별 MongoDB 조회 쿼리입니다.

    LOT·품명·규격은 인계등록/인계이력과 동일한 스마트 검색을 사용합니다.
    각 입력칸 안에서 공백으로 나뉜 모든 검색어가 해당 필드에 글자 순서대로
    포함되어야 하며, 대소문자와 -, _, / 등의 기호 차이는 무시합니다.
    인수자와 메모는 기존 부분 문자열 검색을 유지합니다.
    """
    conditions = []

    # LOT·품명·규격: 각 입력칸별 스마트 검색
    smart_field_values = {
        "lot_no": lot_no,
        "product_name": product_name,
        "spec": spec,
    }
    for field, value in smart_field_values.items():
        tokens = [token for token in re.split(r"\s+", str(value or "").strip()) if token]
        for token in tokens:
            smart_regex = build_smart_search_regex(token)
            if smart_regex:
                conditions.append(
                    {field: {"$regex": smart_regex, "$options": "i"}}
                )

    # 인수자·메모: 기존 부분 문자열 검색 유지
    normal_field_values = {
        "receiver_name": receiver_name,
        "memo": memo,
    }
    for field, value in normal_field_values.items():
        value = str(value or "").strip()
        if value:
            conditions.append(
                {field: {"$regex": re.escape(value), "$options": "i"}}
            )

    # 메모 필드에 공백이 아닌 실제 문자가 1개 이상 있는 입고 건만 조회합니다.
    # 이 조건은 메모 내용 검색어와 함께 사용할 수도 있습니다.
    if memo_exists_only:
        conditions.append({"memo": {"$regex": r"\S"}})

    if start_date and end_date:
        conditions.append(
            {
                "receive_date": {
                    "$gte": str(start_date),
                    "$lte": str(end_date),
                }
            }
        )
    elif start_date:
        conditions.append({"receive_date": {"$gte": str(start_date)}})
    elif end_date:
        conditions.append({"receive_date": {"$lte": str(end_date)}})

    if not conditions:
        return {}

    return {"$and": conditions} if len(conditions) > 1 else conditions[0]


def get_material_advanced_records(
    lot_no="",
    product_name="",
    spec="",
    receiver_name="",
    memo="",
    memo_exists_only=False,
    start_date=None,
    end_date=None,
    limit=500,
):
    query = build_material_advanced_search_query(
        lot_no=lot_no,
        product_name=product_name,
        spec=spec,
        receiver_name=receiver_name,
        memo=memo,
        memo_exists_only=memo_exists_only,
        start_date=start_date,
        end_date=end_date,
    )
    return list(
        get_material_collection()
        .find(query)
        .sort([("receive_date", -1), ("created_at", -1), ("_id", -1)])
        .limit(int(limit))
    )


def get_material_receiver_options():
    return [f"{no} - {name}" for no, name in MATERIAL_RECEIVER_MAP.items()]


def parse_material_receiver_option(option):
    text = str(option or "")
    receiver_no = text.split(" - ", 1)[0].strip()
    return receiver_no, MATERIAL_RECEIVER_MAP.get(receiver_no, "")


def rerun_app():
    if hasattr(st, "rerun"):
        st.rerun()
    st.experimental_rerun()


def material_query_param(name):
    try:
        value = st.query_params.get(name, "")
    except Exception:
        try:
            value = st.experimental_get_query_params().get(name, "")
        except Exception:
            return ""
    if isinstance(value, list):
        return str(value[0]) if value else ""
    return str(value or "")


def clear_material_query_params():
    try:
        for key in ("material_qr", "material_scan", "material_page"):
            if key in st.query_params:
                del st.query_params[key]
    except Exception:
        pass


def reset_material_live_lookup_state():
    for key in (
        "material_live_lot",
        "material_live_lookup",
        "material_live_message",
        "material_received_qty_live",
        "material_memo_live",
        "material_receive_date_live",
        "material_product_name_live",
        "material_spec_live",
        "material_plan_qty_live",
    ):
        if key in st.session_state:
            del st.session_state[key]


def apply_material_lot_lookup(raw_lot, source_label="QR"):
    lot_no = normalize_material_lot_text(raw_lot)
    for key in (
        "material_received_qty_live",
        "material_memo_live",
        "material_receive_date_live",
        "material_product_name_live",
        "material_spec_live",
        "material_plan_qty_live",
    ):
        if key in st.session_state:
            del st.session_state[key]

    st.session_state.material_live_lot = lot_no
    st.session_state.material_live_lookup = {}

    if not lot_no:
        st.session_state.material_live_message = (
            "warning",
            f"QR은 인식했지만 LOT 번호를 추출하지 못했습니다. 인식값: {str(raw_lot)[:120]}"
        )
        return

    try:
        info, message = lookup_ksi_lot_info(lot_no)
    except Exception as exc:
        info, message = None, f"K-System LOT 조회 오류: {exc}"

    if info and info.get("lookup_ok"):
        st.session_state.material_live_lookup = info
        st.session_state.material_live_message = ("success", f"{source_label} 조회 성공: {lot_no}")
        return

    st.session_state.material_live_lookup = {
        "lookup_ok": False,
        "work_order_no": lot_no,
        "product_name": "",
        "spec": "",
        "plan_qty": 0,
    }
    st.session_state.material_live_message = (
        "warning",
        message or f"{lot_no} 조회 결과가 없습니다. 필요하면 수동 정보로 저장하세요.",
    )




# Mobile-safe QR scanner override. Mobile browsers require a real tap/click before camera access.


# Final QR scanner override. Keep this closest to the page renderer so it wins over
# older scanner definitions above.
def render_material_qr_scanner():
    """
    QR 값을 URL 이동으로 전달하지 않고 Streamlit Python 코드에 직접 반환합니다.

    장점
    - 네이버 앱 브라우저의 자동 페이지 이동 차단 영향을 받지 않음
    - QR 인식 직후 LOT 조회 화면으로 자동 전환
    - 저장 후 컴포넌트를 새로 생성하여 다음 스캔 카메라를 다시 준비
    """
    if qrcode_scanner is None:
        st.error(
            "QR 스캐너 패키지가 설치되지 않았습니다. "
            "GitHub의 requirements.txt에 "
            "`streamlit-qrcode-scanner==0.1.2`를 추가한 뒤 재부팅해 주세요."
        )
        return None

    scanner_generation = int(
        st.session_state.get("material_scanner_generation", 0) or 0
    )

    st.caption("카메라 권한을 허용하면 후면 카메라로 QR을 인식합니다.")

    try:
        scanned_value = qrcode_scanner(
            key=f"material_qrcode_scanner_{scanner_generation}"
        )
    except Exception as exc:
        st.error(f"QR 스캐너 실행 오류: {exc}")
        return None

    if isinstance(scanned_value, bytes):
        try:
            scanned_value = scanned_value.decode("utf-8")
        except Exception:
            scanned_value = str(scanned_value)

    scanned_text = str(scanned_value or "").strip()
    return scanned_text or None

def reset_material_search_state():
    """입고 검색 조건·결과·선택·삭제 관련 상태를 최초 화면으로 초기화합니다."""
    # Streamlit은 이미 렌더링된 위젯 키를 같은 실행 중 단순 삭제해도
    # 브라우저의 이전 값이 다시 살아날 수 있습니다. 세대 번호를 올려
    # 완전히 새로운 위젯 키를 만들면 입력값이 확실하게 초기화됩니다.
    st.session_state["material_search_generation"] = int(
        st.session_state.get("material_search_generation", 0) or 0
    ) + 1

    exact_keys = (
        "material_search_lot_live",
        "material_search_product_live",
        "material_search_spec_live",
        "material_search_receiver_live",
        "material_search_memo_live",
        "material_search_memo_exists_only_live",
        "material_search_start_date_live",
        "material_search_end_date_live",
        "material_search_use_date_live",
        "material_search_limit_live",
        "material_search_results_live",
        "material_search_executed_live",
        "material_search_description_live",
        "material_memo_edit_selected_index",
        "material_memo_edit_pending",
        "material_memo_edit_record",
        "material_memo_edit_timestamp",
        "material_memo_edit_final_confirm",
        "material_delete_selected_lot",
    )
    for key in exact_keys:
        st.session_state.pop(key, None)

    # LOT별로 동적으로 생성되는 삭제 토글·확인입력·버튼 상태도 함께 제거합니다.
    dynamic_prefixes = (
        "material_delete_mode_",
        "material_delete_confirm_tail_",
        "material_delete_open_",
    )
    for key in list(st.session_state.keys()):
        key_text = str(key)
        if any(key_text.startswith(prefix) for prefix in dynamic_prefixes):
            st.session_state.pop(key, None)
        # 이전 세대의 입고 검색 위젯 값도 정리합니다.
        elif key_text.startswith("material_search_widget_"):
            st.session_state.pop(key, None)


def show_material_receiving_page_live_qr():
    st.title("📦 원자재 입고 정보")
    st.caption("작업자를 선택한 뒤 도면 QR을 스캔하면 K-System LOT 정보를 자동 조회합니다.")

    if "material_scanner_generation" not in st.session_state:
        st.session_state.material_scanner_generation = 0

    scanned_text = material_query_param("material_qr").strip()
    scan_nonce = material_query_param("material_scan").strip() or scanned_text
    scan_key = f"{scan_nonce}:{scanned_text}"
    if scanned_text and scan_key != st.session_state.get("material_last_scan_key"):
        st.session_state.material_last_scan_key = scan_key
        st.session_state.material_last_scan_nonce = scan_nonce
        apply_material_lot_lookup(scanned_text, "QR")
        clear_material_query_params()
        rerun_app()

    saved_message = st.session_state.get("material_live_saved_message", "")
    if saved_message:
        st.success(saved_message)
        st.session_state.material_live_saved_message = ""

    deleted_lot_message = st.session_state.pop(
        "material_lot_delete_saved_message", ""
    )
    if deleted_lot_message:
        st.success(deleted_lot_message)

    receiver_options = get_material_receiver_options()
    selected_receiver = st.selectbox("입고 작업자", receiver_options, key="material_live_receiver")
    receiver_no, receiver_name = parse_material_receiver_option(selected_receiver)

    input_tab, search_tab = st.tabs(["📷 QR 입고", "🔍 입고 검색"])

    with input_tab:
        st.info(f"현재 작업자: {receiver_no} {receiver_name}")

        scanned_value = render_material_qr_scanner()
        if scanned_value:
            component_scan_key = (
                f"{st.session_state.material_scanner_generation}:"
                f"{scanned_value}"
            )
            if component_scan_key != st.session_state.get(
                "material_last_component_scan_key"
            ):
                st.session_state.material_last_component_scan_key = component_scan_key
                apply_material_lot_lookup(scanned_value, "QR")
                st.rerun()

        with st.expander("카메라가 안 될 때 수동 LOT 입력"):
            manual_lot = st.text_input(
                "LOT 번호",
                placeholder="예: KK20260703080 또는 0703080",
                key="material_manual_lot_live",
            )
            if st.button("수동 LOT 조회", key="material_manual_lookup_live"):
                apply_material_lot_lookup(manual_lot, "수동")
                rerun_app()

        message_type, message_text = st.session_state.get("material_live_message", ("info", ""))
        if message_text:
            getattr(st, message_type, st.info)(message_text)

        lot_no = st.session_state.get("material_live_lot", "")
        if not lot_no:
            st.info("도면 QR을 카메라에 비추면 자동 조회됩니다.")
        else:
            lookup_info = st.session_state.get("material_live_lookup", {})
            product_name_default = str(lookup_info.get("product_name", "") or "")
            spec_default = str(lookup_info.get("spec", "") or "")
            plan_qty_default = to_int_safe(lookup_info.get("plan_qty"), 0)
            received_total = get_material_received_total(lot_no)
            latest_record = get_material_latest_record(lot_no)
            remaining_qty = max(plan_qty_default - received_total, 0) if plan_qty_default else 0
            is_duplicate_lot = received_total > 0
            is_fully_received = bool(plan_qty_default > 0 and received_total >= plan_qty_default)
            default_received_qty = remaining_qty

            st.markdown("#### 조회된 입고 정보")
            cols = st.columns(4)
            cols[0].metric("LOT", lot_no)
            cols[1].metric("K-System 수량", plan_qty_default)
            cols[2].metric("기존 입고 합계", received_total)
            cols[3].metric("남은 수량", remaining_qty)

            if is_fully_received:
                st.error(
                    f"🚫 이미 전량 입고 완료된 LOT입니다. "
                    f"K-System 수량 {plan_qty_default}개 / 기존 입고 합계 {received_total}개"
                )
                st.info(
                    "내용을 확인한 뒤 아래 버튼을 누르면 현재 LOT 화면을 닫고 "
                    "다음 QR을 바로 스캔할 수 있습니다."
                )
                if st.button(
                    "⬅️ 확인 완료 · 다음 QR 찍기",
                    key=f"material_duplicate_back_{lot_no}",
                    use_container_width=True,
                ):
                    reset_material_live_lookup_state()
                    st.session_state.material_scanner_generation = (
                        int(st.session_state.get("material_scanner_generation", 0) or 0) + 1
                    )
                    st.session_state.pop("material_last_component_scan_key", None)
                    st.session_state.pop("material_last_scan_key", None)
                    st.session_state.pop("material_last_scan_nonce", None)
                    st.session_state.material_live_message = (
                        "info",
                        "다음 원자재 QR을 스캔해 주세요.",
                    )
                    rerun_app()
            elif is_duplicate_lot:
                latest_date = str((latest_record or {}).get("receive_date", "-"))
                latest_name = str((latest_record or {}).get("receiver_name", "-"))
                latest_qty = to_int_safe((latest_record or {}).get("received_qty"), 0)
                st.warning(
                    "⚠️ 이미 입고 이력이 있는 LOT입니다.\n\n"
                    f"- 기존 입고 합계: **{received_total}개**\n"
                    f"- 남은 수량: **{remaining_qty}개**\n"
                    f"- 최근 입고: **{latest_date} / {latest_name} / {latest_qty}개**\n\n"
                    "부분 입고를 추가하는 경우에만 아래 확인란을 체크한 뒤 저장하세요."
                )

            with st.form("material_live_receiving_form"):
                st.text_input("LOT", value=lot_no, disabled=True)
                product_name = st.text_input("품명", value=product_name_default, key="material_product_name_live")
                spec = st.text_input("규격", value=spec_default, key="material_spec_live")

                qty_cols = st.columns(3)
                with qty_cols[0]:
                    plan_qty = st.number_input(
                        "K-System 수량",
                        min_value=0,
                        value=plan_qty_default,
                        step=1,
                        key="material_plan_qty_live",
                    )
                with qty_cols[1]:
                    st.number_input(
                        "기존 입고 합계",
                        min_value=0,
                        value=received_total,
                        step=1,
                        disabled=True,
                        key="material_received_total_live",
                    )
                with qty_cols[2]:
                    received_qty = st.number_input(
                        "이번 입고 수량",
                        min_value=0,
                        value=default_received_qty,
                        step=1,
                        key="material_received_qty_live",
                    )

                receive_date = st.date_input(
                    "입고 날짜",
                    value=get_now_kst().date(),
                    key="material_receive_date_live",
                )
                memo = st.text_area(
                    "메모",
                    placeholder="부분 입고, 수량 차이, 특이사항",
                    key="material_memo_live",
                )

                duplicate_confirmed = True
                if is_duplicate_lot and not is_fully_received:
                    duplicate_confirmed = st.checkbox(
                        f"⚠️ 기존 입고 합계 {received_total}개를 확인했으며, 남은 수량에 추가 입고합니다.",
                        key="material_duplicate_confirm_live",
                    )

                submitted = st.form_submit_button(
                    "🚫 전량 입고 완료" if is_fully_received else "✅ 저장 후 다음 QR 스캔",
                    disabled=is_fully_received,
                )

            if submitted:
                if not receiver_no or not receiver_name.strip():
                    st.error("작업자를 선택해 주세요.")
                elif not lot_no:
                    st.error("LOT 번호가 없습니다.")
                elif is_duplicate_lot and not duplicate_confirmed:
                    st.error("기존 입고 이력을 확인했다는 체크가 필요합니다.")
                elif received_qty <= 0:
                    st.error("이번 입고 수량은 1개 이상이어야 합니다.")
                elif plan_qty > 0 and int(received_qty) > max(int(plan_qty) - int(received_total), 0):
                    st.error(
                        f"이번 입고 수량이 남은 수량을 초과합니다. "
                        f"현재 남은 수량은 {max(int(plan_qty) - int(received_total), 0)}개입니다."
                    )
                else:
                    # 저장 버튼을 누른 순간 DB를 다시 확인하여 다른 사용자의 동시 저장도 방지합니다.
                    latest_total = get_material_received_total(lot_no)
                    latest_remaining = max(int(plan_qty) - int(latest_total), 0) if int(plan_qty) > 0 else 0

                    if int(plan_qty) > 0 and latest_total >= int(plan_qty):
                        st.error(
                            f"🚫 저장 직전에 확인한 결과 이미 전량 입고 완료되었습니다. "
                            f"K-System 수량 {int(plan_qty)}개 / 입고 합계 {latest_total}개"
                        )
                        st.stop()

                    if int(plan_qty) > 0 and int(received_qty) > latest_remaining:
                        st.error(
                            f"다른 작업자의 입고가 먼저 저장되어 남은 수량이 {latest_remaining}개로 변경되었습니다. "
                            "화면을 새로고침한 뒤 다시 확인해 주세요."
                        )
                        st.stop()

                    now_kst = get_now_kst()
                    received_total = latest_total
                    received_total_after = received_total + int(received_qty)
                    doc = {
                        "lot_no": lot_no,
                        "product_name": product_name.strip(),
                        "spec": spec.strip(),
                        "plan_qty": int(plan_qty),
                        "received_qty": int(received_qty),
                        "received_total_before": int(received_total),
                        "received_total_after": int(received_total_after),
                        "receive_date": str(receive_date),
                        "receiver_no": receiver_no,
                        "receiver_name": receiver_name,
                        "memo": memo.strip(),
                        "source": "qr_live" if lookup_info.get("lookup_ok") else "manual_or_not_found",
                        "created_at": now_kst.strftime("%Y-%m-%d %H:%M:%S"),
                    }
                    insert_result = get_material_collection().insert_one(doc)
                    if not insert_result.inserted_id:
                        st.error("MongoDB 저장 결과를 확인하지 못했습니다.")
                        st.stop()

                    reset_material_live_lookup_state()

                    # 다음 QR 스캔용으로 컴포넌트를 완전히 새로 생성합니다.
                    st.session_state.material_scanner_generation = (
                        int(st.session_state.get("material_scanner_generation", 0) or 0) + 1
                    )
                    st.session_state.pop("material_last_component_scan_key", None)

                    st.session_state.material_live_saved_message = (
                        f"{lot_no} 입고 {int(received_qty)}개 저장 완료. "
                        "다음 QR 카메라를 준비했습니다."
                    )
                    rerun_app()

    with search_tab:
        st.markdown("#### 🔍 입고 내역 조건 검색")
        st.caption(
            "검색 조건을 입력하고 조회 버튼을 눌러야 결과가 표시됩니다. "
            "빈 화면에서 전체 입고 내역은 자동으로 불러오지 않습니다."
        )

        today = get_now_kst().date()
        default_start = today.replace(day=1)
        search_generation = int(
            st.session_state.get("material_search_generation", 0) or 0
        )

        with st.form(
            f"material_advanced_search_form_{search_generation}",
            clear_on_submit=False,
        ):
            row1 = st.columns(2)
            with row1[0]:
                search_lot = st.text_input(
                    "LOT",
                    placeholder="예: KK20260511043 또는 11043",
                    key=f"material_search_widget_lot_{search_generation}",
                )
            with row1[1]:
                search_product = st.text_input(
                    "품명",
                    placeholder=" ",
                    key=f"material_search_widget_product_{search_generation}",
                )

            row2 = st.columns(2)
            with row2[0]:
                search_spec = st.text_input(
                    "규격",
                    placeholder=" ",
                    key=f"material_search_widget_spec_{search_generation}",
                )
            with row2[1]:
                search_receiver = st.text_input(
                    "인수자",
                    placeholder=" ",
                    key=f"material_search_widget_receiver_{search_generation}",
                )

            search_memo = st.text_input(
                "메모",
                placeholder="메모 내용 일부",
                key=f"material_search_widget_memo_{search_generation}",
            )
            memo_exists_only = st.checkbox(
                "📝 메모가 작성된 입고 건만 조회",
                value=False,
                help=(
                    "메모가 비어 있거나 공백만 입력된 입고 건은 제외하고, "
                    "실제 메모 내용이 있는 기록만 조회합니다."
                ),
                key=f"material_search_widget_memo_exists_{search_generation}",
            )

            st.markdown("##### 입고일 검색")
            date_cols = st.columns(2)
            with date_cols[0]:
                search_start_date = st.date_input(
                    "시작일",
                    value=default_start,
                    key=f"material_search_widget_start_date_{search_generation}",
                )
            with date_cols[1]:
                search_end_date = st.date_input(
                    "종료일",
                    value=today,
                    key=f"material_search_widget_end_date_{search_generation}",
                )

            option_cols = st.columns([2, 1])
            with option_cols[0]:
                use_date_filter = st.checkbox(
                    "날짜 조건 사용",
                    value=False,
                    help="체크하지 않으면 날짜와 관계없이 입력한 조건만 검색합니다.",
                    key=f"material_search_widget_use_date_{search_generation}",
                )
            with option_cols[1]:
                result_limit = st.selectbox(
                    "최대 표시 건수",
                    [10,100, 300, 500, 1000],
                    index=2,
                    key=f"material_search_widget_limit_{search_generation}",
                )

            search_submitted = st.form_submit_button(
                "🔍 조건으로 조회",
                use_container_width=True,
            )

        clear_col, info_col = st.columns([1, 3])
        with clear_col:
            st.button(
                "🔄 새 검색 · 전체 초기화",
                key=f"material_search_clear_live_{search_generation}",
                use_container_width=True,
                on_click=reset_material_search_state,
            )
        with info_col:
            st.caption(
                "스마트 검색: LOT `0511`·`1043`, 품명 `shie top`, "
                "규격 `kz84`·`K84`처럼 일부만 입력해도 검색됩니다."
            )

        if search_submitted:
            if use_date_filter and search_start_date > search_end_date:
                st.error("시작일은 종료일보다 늦을 수 없습니다.")
                st.session_state.pop("material_search_results_live", None)
                st.session_state.material_search_executed_live = False
            else:
                has_text_condition = any(
                    str(value or "").strip()
                    for value in (
                        search_lot,
                        search_product,
                        search_spec,
                        search_receiver,
                        search_memo,
                    )
                )

                if not has_text_condition and not use_date_filter and not memo_exists_only:
                    st.warning(
                        "검색 조건을 하나 이상 입력해 주세요. "
                        "전체 데이터가 한꺼번에 표시되는 것을 방지하기 위해 빈 조건 조회는 실행하지 않습니다."
                    )
                    st.session_state.pop("material_search_results_live", None)
                    st.session_state.material_search_executed_live = False
                else:
                    query_start_date = search_start_date if use_date_filter else None
                    query_end_date = search_end_date if use_date_filter else None

                    records = get_material_advanced_records(
                        lot_no=search_lot,
                        product_name=search_product,
                        spec=search_spec,
                        receiver_name=search_receiver,
                        memo=search_memo,
                        memo_exists_only=memo_exists_only,
                        start_date=query_start_date,
                        end_date=query_end_date,
                        limit=result_limit,
                    )

                    # 검색된 LOT별로 MongoDB의 입고/3PART 인계 수량을 계산합니다.
                    # K-System 진행상태는 더 이상 사용하지 않습니다.
                    handover_state_cache = {}
                    for record in records:
                        record_lot_no = str(record.get("lot_no", "") or "").strip()
                        if not record_lot_no:
                            record["_handover_status"] = ""
                            continue

                        if record_lot_no not in handover_state_cache:
                            received_total = get_material_received_total(record_lot_no)
                            handover_total = get_handover_total(record_lot_no)
                            state = calculate_handover_state(
                                record.get("plan_qty"), received_total, handover_total
                            )
                            handover_state_cache[record_lot_no] = state

                        record["_handover_status"] = handover_state_cache[record_lot_no]["status"]

                    st.session_state.material_search_results_live = records
                    st.session_state.material_search_executed_live = True

                    descriptions = []
                    if str(search_lot or "").strip():
                        descriptions.append(f"LOT: {search_lot.strip()}")
                    if str(search_product or "").strip():
                        descriptions.append(f"품명: {search_product.strip()}")
                    if str(search_spec or "").strip():
                        descriptions.append(f"규격: {search_spec.strip()}")
                    if str(search_receiver or "").strip():
                        descriptions.append(f"인수자: {search_receiver.strip()}")
                    if str(search_memo or "").strip():
                        descriptions.append(f"메모: {search_memo.strip()}")
                    if memo_exists_only:
                        descriptions.append("메모 작성 건만")
                    if use_date_filter:
                        descriptions.append(
                            f"입고일: {search_start_date} ~ {search_end_date}"
                        )
                    st.session_state.material_search_description_live = " / ".join(descriptions)

        search_executed = bool(
            st.session_state.get("material_search_executed_live", False)
        )

        if not search_executed:
            st.info(
                "LOT, 품명, 규격, 인수자, 날짜 조건을 입력하거나 "
                "'메모가 작성된 입고 건만 조회'를 선택한 뒤 조회 버튼을 눌러주세요."
            )
        else:
            records = st.session_state.get("material_search_results_live", [])
            description = st.session_state.get(
                "material_search_description_live", ""
            )

            if description:
                st.caption(f"현재 검색 조건: {description}")

            if not records:
                st.warning("조건에 맞는 입고 내역이 없습니다.")
            else:
                rows = []
                for item in records:
                    rows.append(
                        {
                            "입고일": item.get("receive_date", ""),
                            "LOT": item.get("lot_no", ""),
                            "품명": item.get("product_name", ""),
                            "규격": item.get("spec", ""),
                            "K-System수량": to_int_safe(item.get("plan_qty"), 0),
                            "입고수량": to_int_safe(item.get("received_qty"), 0),
                            "누적입고": to_int_safe(
                                item.get("received_total_after"), 0
                            ),
                            "3PART 인계정보": item.get(
                                "_handover_status", ""
                            ),
                            "인수자": item.get("receiver_name", ""),
                            "메모": item.get("memo", ""),
                        }
                    )

                df = pd.DataFrame(rows)

                metric_cols = st.columns(3)
                metric_cols[0].metric("검색 결과", f"{len(df):,}건")
                metric_cols[1].metric(
                    "검색된 입고수량 합계",
                    f"{int(df['입고수량'].sum()):,}개",
                )
                metric_cols[2].metric(
                    "검색된 LOT 수",
                    f"{int(df['LOT'].nunique()):,}개",
                )

                if len(records) >= int(result_limit):
                    st.warning(
                        f"최대 표시 건수 {int(result_limit):,}건까지만 표시했습니다. "
                        "검색 조건을 더 구체적으로 입력해 주세요."
                    )

                st.dataframe(
                    df,
                    use_container_width=True,
                    hide_index=True,
                )

                saved_memo_message = st.session_state.pop(
                    "material_memo_edit_saved_message", ""
                )
                if saved_memo_message:
                    st.success(saved_memo_message)

                st.divider()
                st.markdown("#### 📝 선택한 입고 기록 메모 수정")
                st.caption(
                    "입고수량과 다른 정보는 변경하지 않고, 선택한 입고 건의 메모만 수정합니다."
                )

                record_options = list(range(len(records)))

                def material_record_label(index):
                    item = records[index]
                    return (
                        f"{item.get('receive_date', '-')} | "
                        f"{item.get('lot_no', '-')} | "
                        f"입고 {to_int_safe(item.get('received_qty'), 0):,}개 | "
                        f"{item.get('receiver_name', '-')}"
                    )

                selected_record_index = st.selectbox(
                    "수정할 입고 기록",
                    options=record_options,
                    format_func=material_record_label,
                    key="material_memo_edit_selected_index",
                )
                selected_record = records[selected_record_index]
                selected_lot_no = str(selected_record.get("lot_no", "") or "").strip()
                selected_received_total = get_material_received_total(selected_lot_no)
                selected_handover_total = get_handover_total(selected_lot_no)
                selected_handover_state = calculate_handover_state(
                    selected_record.get("plan_qty"),
                    selected_received_total,
                    selected_handover_total,
                )

                st.divider()
                status_col, delete_toggle_col = st.columns([4, 1.2])
                with status_col:
                    st.markdown("#### 🚚 3PART 인계정보")
                    st.info(
                        f"현재 상태: **{selected_handover_state['status']}**  ·  "
                        f"입고 {selected_handover_state['received_total']:,}개  ·  "
                        f"인계 {selected_handover_state['handover_total']:,}개  ·  "
                        f"미인계 {selected_handover_state['available_qty']:,}개"
                    )
                with delete_toggle_col:
                    delete_mode = st.toggle(
                        "🗑️ 삭제 기능",
                        value=False,
                        key=f"material_delete_mode_{selected_lot_no}",
                        help="선택 LOT의 입고 기록과 3PART 인계 기록을 모두 완전 삭제할 때만 켜세요.",
                    )

                if delete_mode:
                    st.warning(
                        "선택한 LOT와 관련된 모든 기록을 "
                        "material_receiving_logs와 toss_logs 두 컬렉션에서 삭제합니다."
                    )
                    if st.button(
                        "⚠️ LOT 완전 삭제 확인창 열기",
                        key=f"material_delete_open_{selected_lot_no}",
                        use_container_width=True,
                    ):
                        confirm_material_lot_delete(selected_lot_no)

                detail_cols = st.columns(3)
                detail_cols[0].metric(
                    "K-System 수량",
                    f"{to_int_safe(selected_record.get('plan_qty'), 0):,}개",
                )
                detail_cols[1].metric(
                    "이번 입고수량",
                    f"{to_int_safe(selected_record.get('received_qty'), 0):,}개",
                )
                detail_cols[2].metric(
                    "누적 입고수량",
                    f"{to_int_safe(selected_record.get('received_total_after'), 0):,}개",
                )

                selected_record_id = str(selected_record.get("_id", ""))
                memo_widget_key = f"material_memo_edit_text_{selected_record_id}"
                edited_memo = st.text_area(
                    "메모 수정",
                    value=str(selected_record.get("memo", "") or ""),
                    height=140,
                    placeholder="예: 가공 중 원자재 3개 깨짐 발견, 업체 반품 예정",
                    key=memo_widget_key,
                )
                st.caption(
                    f"메모 수정 작업자: {receiver_name} · "
                    "메모 기입 일시는 확인창을 여는 순간 자동 기록됩니다."
                )

                if st.button(
                    "🔎 수량 및 메모 확인",
                    key=f"material_memo_edit_review_{selected_record_id}",
                    use_container_width=True,
                ):
                    if edited_memo == str(selected_record.get("memo", "") or ""):
                        st.warning("메모 내용이 변경되지 않았습니다.")
                    else:
                        st.session_state.material_memo_edit_record = dict(selected_record)
                        st.session_state.material_memo_edit_pending = edited_memo
                        # 화면 상단의 현재 입고 작업자를 메모 수정 작업자로 자동 적용합니다.
                        st.session_state.material_memo_edit_editor_no = receiver_no
                        st.session_state.material_memo_edit_editor_name = receiver_name
                        # 확인창에 표시한 일시를 그대로 MongoDB에도 저장합니다.
                        st.session_state.material_memo_edit_timestamp = (
                            get_now_kst().strftime("%Y-%m-%d %H:%M:%S")
                        )
                        st.session_state.pop("material_memo_edit_final_confirm", None)
                        confirm_material_memo_update()


# =================================================================================================
# 🚚 3PART 인수인계 관리
# - 원자재 입고 이력(material_receiving_logs)을 기준으로 LOT별 인계 가능 수량을 계산합니다.
# - 실제 인계/취소 이력은 toss_logs에 보존합니다.
# - 취소는 원본 삭제가 아니라 상태 변경 방식으로 처리합니다.
# =================================================================================================

def get_toss_collection():
    return db_collection.database[TOSS_COLLECTION_NAME]


@st.cache_resource
def ensure_toss_indexes():
    """조회 성능용 인덱스입니다. 인덱스 생성 권한이 없어도 앱은 계속 동작합니다."""
    try:
        collection = get_toss_collection()
        collection.create_index([("lot_no", 1), ("is_cancelled", 1)])
        collection.create_index([("lot_no", 1), ("handover_at", -1)])
        collection.create_index([("handover_date", -1)])
        collection.create_index([("record_type", 1), ("lot_no", 1), ("handover_at", -1)])
        return True
    except Exception:
        return False


def get_handover_total(lot_no):
    """취소되지 않은 정상 인계수량에서 부분 반품수량을 차감한 실제 인계수량입니다."""
    if not lot_no:
        return 0
    pipeline = [
        {
            "$match": {
                "lot_no": lot_no,
                "is_cancelled": {"$ne": True},
                "status": {"$ne": "cancelled"},
            }
        },
        {
            "$group": {
                "_id": "$lot_no",
                "total": {
                    "$sum": {
                        "$switch": {
                            "branches": [
                                {
                                    "case": {"$eq": ["$record_type", "machining_defect"]},
                                    "then": 0,
                                },
                                {
                                    "case": {"$eq": ["$record_type", "handover_return"]},
                                    "then": {"$multiply": [{"$ifNull": ["$return_qty", 0]}, -1]},
                                },
                            ],
                            "default": {"$ifNull": ["$handover_qty", 0]},
                        }
                    }
                },
            }
        },
    ]
    result = list(get_toss_collection().aggregate(pipeline))
    return max(to_int_safe(result[0].get("total"), 0), 0) if result else 0


def get_active_return_total(original_handover_id):
    """특정 원본 인계기록에 연결된 취소되지 않은 부분 반품수량 합계입니다."""
    if not original_handover_id:
        return 0
    original_id_text = str(original_handover_id)
    pipeline = [
        {
            "$match": {
                "record_type": "handover_return",
                "original_handover_id": original_id_text,
                "is_cancelled": {"$ne": True},
                "status": {"$ne": "cancelled"},
            }
        },
        {"$group": {"_id": "$original_handover_id", "total": {"$sum": "$return_qty"}}},
    ]
    result = list(get_toss_collection().aggregate(pipeline))
    return max(to_int_safe(result[0].get("total"), 0), 0) if result else 0


def get_net_handover_qty(record):
    """원본 인계기록 한 건의 현재 실제 인계수량(원인계 - 누적 부분반품)입니다."""
    if not record or record.get("record_type") in ("machining_defect", "handover_return"):
        return 0
    original_qty = max(to_int_safe(record.get("handover_qty"), 0), 0)
    returned_qty = get_active_return_total(record.get("_id"))
    return max(original_qty - returned_qty, 0)


def get_machining_defect_total(lot_no):
    """선택 LOT에 별도로 등록된 4PART 가공불량 수량을 합산합니다.

    가공불량은 추적용 기록이며 인계 가능 수량 계산에서는 차감하지 않습니다.
    """
    if not lot_no:
        return 0
    pipeline = [
        {
            "$match": {
                "lot_no": lot_no,
                "record_type": "machining_defect",
            }
        },
        {
            "$group": {
                "_id": "$lot_no",
                "total": {"$sum": "$machining_defect_qty"},
            }
        },
    ]
    result = list(get_toss_collection().aggregate(pipeline))
    return to_int_safe(result[0].get("total"), 0) if result else 0


def get_handover_history_bulk_totals(lot_numbers, original_ids):
    """검색 화면 전용 읽기 일괄 집계. 기존 수량 계산/저장 함수는 변경하지 않습니다."""
    lot_numbers = sorted(set(str(x) for x in lot_numbers if x))
    original_ids = sorted(set(str(x) for x in original_ids if x))
    toss = get_toss_collection()
    returns = {}
    if original_ids:
        pipeline = [
            {"$match": {"record_type": "handover_return", "original_handover_id": {"$in": original_ids},
                        "is_cancelled": {"$ne": True}, "status": {"$ne": "cancelled"}}},
            {"$group": {"_id": "$original_handover_id", "total": {"$sum": "$return_qty"}}},
        ]
        returns = {str(r["_id"]): max(to_int_safe(r.get("total"), 0), 0) for r in toss.aggregate(pipeline)}
    handovers, defects, latest = {}, {}, {}
    if lot_numbers:
        pipeline = [
            {"$match": {"lot_no": {"$in": lot_numbers}, "is_cancelled": {"$ne": True}, "status": {"$ne": "cancelled"}}},
            {"$group": {"_id": "$lot_no", "total": {"$sum": {"$switch": {"branches": [
                {"case": {"$eq": ["$record_type", "machining_defect"]}, "then": 0},
                {"case": {"$eq": ["$record_type", "handover_return"]}, "then": {"$multiply": [{"$ifNull": ["$return_qty", 0]}, -1]}}
            ], "default": {"$ifNull": ["$handover_qty", 0]}}}}}},
        ]
        handovers = {str(r["_id"]): max(to_int_safe(r.get("total"), 0), 0) for r in toss.aggregate(pipeline)}
        pipeline = [
            {"$match": {"lot_no": {"$in": lot_numbers}, "record_type": "machining_defect"}},
            {"$group": {"_id": "$lot_no", "total": {"$sum": "$machining_defect_qty"}}},
        ]
        defects = {str(r["_id"]): to_int_safe(r.get("total"), 0) for r in toss.aggregate(pipeline)}
        pipeline = [
            {"$match": {"lot_no": {"$in": lot_numbers}, "record_type": {"$ne": "machining_defect"},
                        "is_cancelled": {"$ne": True}, "status": {"$ne": "cancelled"}}},
            {"$sort": {"handover_at": -1, "_id": -1}},
            {"$group": {"_id": "$lot_no", "handover_at": {"$first": "$handover_at"}}},
        ]
        latest = {str(r["_id"]): str(r.get("handover_at", "") or "") for r in toss.aggregate(pipeline)}
    return returns, handovers, defects, latest


@st.dialog("⚠️ 인계 전 가공불량 확인")
def handover_defect_notice_dialog(lot_no, defect_qty):
    st.warning(f"LOT **{lot_no}**에 가공불량 **{defect_qty:,}개**가 등록되어 있습니다.")
    st.write("3PART로 인계하기 전에 등록된 불량수량을 확인해 주세요.")
    st.caption("가공불량은 기존 운영 규칙에 따라 인계 가능수량에서 자동 차감하지 않습니다.")
    if st.button("확인 · 닫기", key="handover_defect_notice_close", use_container_width=True):
        st.rerun()


def calculate_handover_state(plan_qty, received_total, handover_total):
    """LOT의 수량과 상태를 한 곳에서 계산하는 순수 함수입니다."""
    plan_qty = max(to_int_safe(plan_qty, 0), 0)
    received_total = max(to_int_safe(received_total, 0), 0)
    handover_total = max(to_int_safe(handover_total, 0), 0)

    missing_received = max(plan_qty - received_total, 0) if plan_qty > 0 else 0
    available_qty = max(received_total - handover_total, 0)
    overall_not_handed = (
        max(plan_qty - handover_total, 0)
        if plan_qty > 0
        else available_qty
    )

    is_complete = bool(
        plan_qty > 0
        and received_total >= plan_qty
        and handover_total >= plan_qty
    )

    if is_complete:
        status = "✅ 인수인계 완료"
    elif received_total <= 0:
        status = "입고대기"
    elif handover_total <= 0:
        status = "출고대기"
    elif available_qty > 0:
        status = "일부출고"
    elif plan_qty > 0 and received_total < plan_qty:
        status = "입고대기 · 현재 입고분 인계완료"
    else:
        status = "현재 입고분 인계완료"

    return {
        "plan_qty": plan_qty,
        "received_total": received_total,
        "missing_received": missing_received,
        "handover_total": handover_total,
        "available_qty": available_qty,
        "overall_not_handed": overall_not_handed,
        "is_complete": is_complete,
        "status": status,
        "has_quantity_error": handover_total > received_total,
    }


def build_smart_search_regex(token):
    """검색어 글자 순서만 유지해도 일치하도록 MongoDB 정규식을 만듭니다.

    예:
      K84   -> K.*8.*4      (KZ-846 검색 가능)
      kz84  -> k.*z.*8.*4   (KZ-846 검색 가능)
      shie  -> s.*h.*i.*e   (SHIELD 검색 가능)
      0511  -> 0.*5.*1.*1   (LOT 중간 번호 검색 가능)

    공백과 -, _, / 등의 기호는 검색어에서 제외하며 대소문자는 MongoDB의 i 옵션으로 무시합니다.
    """
    normalized = "".join(
        char for char in str(token or "").strip() if char.isalnum()
    )
    if not normalized:
        return ""
    return ".*".join(re.escape(char) for char in normalized)


def build_handover_material_query(keyword):
    """LOT·품명·규격을 단어별 스마트 부분검색합니다.

    여러 단어를 입력하면 각 단어가 LOT·품명·규격 중 어느 한 필드에서든
    글자 순서대로 발견되는 자료만 조회합니다.
    """
    keyword = str(keyword or "").strip()
    if not keyword:
        return {}

    tokens = [token for token in re.split(r"\s+", keyword) if token]
    token_conditions = []
    for token in tokens:
        smart_regex = build_smart_search_regex(token)
        if not smart_regex:
            continue
        token_conditions.append(
            {
                "$or": [
                    {"lot_no": {"$regex": smart_regex, "$options": "i"}},
                    {"product_name": {"$regex": smart_regex, "$options": "i"}},
                    {"spec": {"$regex": smart_regex, "$options": "i"}},
                ]
            }
        )

    if not token_conditions:
        return {}
    return {"$and": token_conditions} if len(token_conditions) > 1 else token_conditions[0]


def get_handover_lot_summaries(keyword, limit=200):
    """입고 로그를 LOT별로 합산하고 최신 품명/규격/계획수량을 함께 반환합니다."""
    query = build_handover_material_query(keyword)
    pipeline = []
    if query:
        pipeline.append({"$match": query})
    pipeline.extend(
        [
            {"$sort": {"_id": 1}},
            {
                "$group": {
                    "_id": "$lot_no",
                    "received_total": {"$sum": "$received_qty"},
                    "product_name": {"$last": "$product_name"},
                    "spec": {"$last": "$spec"},
                    "plan_qty": {"$last": "$plan_qty"},
                    "hold": {"$last": {"$ifNull": ["$hold", False]}},
                    "first_receive_date": {"$min": "$receive_date"},
                    "latest_receive_date": {"$max": "$receive_date"},
                }
            },
            {"$sort": {"latest_receive_date": -1, "_id": 1}},
            {"$limit": int(limit)},
        ]
    )
    rows = []
    for item in get_material_collection().aggregate(pipeline):
        lot_no = str(item.get("_id", "") or "").strip()
        if not lot_no:
            continue
        handover_total = get_handover_total(lot_no)
        machining_defect_total = get_machining_defect_total(lot_no)
        state = calculate_handover_state(
            item.get("plan_qty"), item.get("received_total"), handover_total
        )
        rows.append(
            {
                "lot_no": lot_no,
                "product_name": str(item.get("product_name", "") or ""),
                "spec": str(item.get("spec", "") or ""),
                "hold": bool(item.get("hold", False)),
                "first_receive_date": str(item.get("first_receive_date", "") or ""),
                "latest_receive_date": str(item.get("latest_receive_date", "") or ""),
                "machining_defect_total": int(machining_defect_total),
                **state,
            }
        )
    return rows


def set_material_lot_hold(lot_no, hold):
    """기존 material_receiving_logs 문서에 LOT 보류 여부만 저장합니다."""
    lot_no = str(lot_no or "").strip()
    if not lot_no:
        return 0
    result = get_material_collection().update_many(
        {"lot_no": lot_no},
        {"$set": {"hold": bool(hold)}},
    )
    return int(result.matched_count or 0)


def get_recommended_handover_lot(product_name, spec):
    """같은 품명·규격에서 보류가 아니며 인계 가능한 첫 LOT를 추천합니다.

    이미 일부 인계한 LOT가 있으면 그 LOT를 우선하고, 없으면 입고 순서가 빠른 LOT를 추천합니다.
    추천은 안내용이며 작업자는 다른 정상 LOT도 직접 선택할 수 있습니다.
    """
    product_name = str(product_name or "").strip()
    spec = str(spec or "").strip()
    if not product_name and not spec:
        return None

    conditions = []
    if product_name:
        conditions.append({"product_name": {"$regex": f"^{re.escape(product_name)}$", "$options": "i"}})
    if spec:
        conditions.append({"spec": {"$regex": f"^{re.escape(spec)}$", "$options": "i"}})
    query = {"$and": conditions} if len(conditions) > 1 else conditions[0]

    pipeline = [
        {"$match": query},
        {"$sort": {"_id": 1}},
        {"$group": {
            "_id": "$lot_no",
            "received_total": {"$sum": "$received_qty"},
            "product_name": {"$last": "$product_name"},
            "spec": {"$last": "$spec"},
            "plan_qty": {"$last": "$plan_qty"},
            "hold": {"$last": {"$ifNull": ["$hold", False]}},
            "first_receive_date": {"$first": "$receive_date"},
        }},
        {"$sort": {"first_receive_date": 1, "_id": 1}},
    ]

    candidates = []
    for item in get_material_collection().aggregate(pipeline):
        lot_no = str(item.get("_id", "") or "").strip()
        if not lot_no or bool(item.get("hold", False)):
            continue
        handover_total = get_handover_total(lot_no)
        state = calculate_handover_state(item.get("plan_qty"), item.get("received_total"), handover_total)
        if state.get("available_qty", 0) <= 0 or state.get("is_complete"):
            continue
        candidates.append({
            "lot_no": lot_no,
            "handover_total": state.get("handover_total", 0),
            "first_receive_date": str(item.get("first_receive_date", "") or ""),
        })

    continuing = next((item for item in candidates if item.get("handover_total", 0) > 0), None)
    return continuing or (candidates[0] if candidates else None)


def get_toss_records(lot_no, limit=300):
    if not lot_no:
        return []
    return list(
        get_toss_collection()
        .find({"lot_no": lot_no})
        .sort([("handover_at", -1), ("_id", -1)])
        .limit(int(limit))
    )


def clear_handover_selection():
    for key in (
        "handover_selected_lot",
        "handover_selected_snapshot",
        "handover_search_results",
        "handover_search_executed",
    ):
        st.session_state.pop(key, None)


@st.dialog("⚠️ 인수인계 취소")
def cancel_handover_dialog(record_id_text):
    try:
        record_id = ObjectId(str(record_id_text))
    except Exception:
        st.error("취소 대상 기록번호가 올바르지 않습니다.")
        return

    record = get_toss_collection().find_one({"_id": record_id})
    if not record:
        st.error("취소할 인계 기록을 찾지 못했습니다.")
        return

    if record.get("is_cancelled") is True or record.get("status") == "cancelled":
        st.warning("이미 취소된 인계 기록입니다.")
        return

    st.write(f"LOT: **{record.get('lot_no', '')}**")
    st.write(f"인계수량: **{to_int_safe(record.get('handover_qty'), 0):,}개**")
    st.write(f"인계자: **{record.get('handover_by', '')}**")
    st.write(f"인수자: **{record.get('received_by', '')}**")
    st.write(f"인계일시: **{record.get('handover_at', '')}**")
    st.warning("원본 이력은 삭제되지 않으며 취소 담당자·사유·시간이 영구 보관됩니다.")

    worker_options = get_material_receiver_options()
    cancel_worker_option = st.selectbox(
        "취소 담당자",
        worker_options,
        key=f"cancel_handover_worker_{record_id_text}",
    )
    cancel_worker_no, cancel_worker_name = parse_material_receiver_option(cancel_worker_option)
    cancel_reason = st.text_area(
        "취소 사유 (필수)",
        placeholder="예: 인계수량 오입력, 다른 LOT 선택",
        key=f"cancel_handover_reason_{record_id_text}",
    )
    confirmed = st.checkbox(
        "위 인계기록을 취소하며 취소 후 수량이 다시 계산되는 것을 확인했습니다.",
        key=f"cancel_handover_confirm_{record_id_text}",
    )

    col_confirm, col_close = st.columns(2)
    if col_confirm.button(
        "🚫 인계기록 취소 확정",
        key=f"cancel_handover_confirm_btn_{record_id_text}",
        use_container_width=True,
    ):
        if not cancel_worker_no or not cancel_worker_name:
            st.error("취소 담당자를 선택해 주세요.")
        elif not cancel_reason.strip():
            st.error("취소 사유를 입력해 주세요.")
        elif not confirmed:
            st.error("취소 확인란을 체크해 주세요.")
        else:
            now_kst = get_now_kst()
            result = get_toss_collection().update_one(
                {
                    "_id": record_id,
                    "is_cancelled": {"$ne": True},
                    "status": {"$ne": "cancelled"},
                },
                {
                    "$set": {
                        "status": "cancelled",
                        "is_cancelled": True,
                        "cancelled_at": now_kst.strftime("%Y-%m-%d %H:%M:%S"),
                        "cancelled_date": now_kst.strftime("%Y-%m-%d"),
                        "cancelled_by_no": cancel_worker_no,
                        "cancelled_by": cancel_worker_name,
                        "cancel_reason": cancel_reason.strip(),
                    }
                },
            )
            if result.modified_count != 1:
                st.error("다른 사용자가 이미 취소했거나 기록 상태가 변경되었습니다.")
                st.stop()

            # 원본 인계가 전부 취소되면 그 인계에 연결된 부분 반품도 계산에서 제외합니다.
            get_toss_collection().update_many(
                {
                    "record_type": "handover_return",
                    "original_handover_id": str(record_id),
                    "is_cancelled": {"$ne": True},
                },
                {
                    "$set": {
                        "status": "cancelled",
                        "is_cancelled": True,
                        "cancelled_at": now_kst.strftime("%Y-%m-%d %H:%M:%S"),
                        "cancelled_date": now_kst.strftime("%Y-%m-%d"),
                        "cancelled_by_no": cancel_worker_no,
                        "cancelled_by": cancel_worker_name,
                        "cancel_reason": "원본 인계기록 전체 취소에 따라 연결 반품이력도 계산 제외",
                    }
                },
            )
            st.session_state.handover_flash_message = (
                f"{record.get('lot_no', '')} 인계 {to_int_safe(record.get('handover_qty'), 0):,}개를 "
                f"취소했습니다. 현재 수량을 다시 계산했습니다."
            )
            time.sleep(0.4)
            st.rerun()

    if col_close.button(
        "닫기",
        key=f"cancel_handover_close_btn_{record_id_text}",
        use_container_width=True,
    ):
        st.rerun()



@st.dialog("↩ 3PART 일부 반품 처리")
def partial_handover_return_dialog(record_id_text):
    """3PART에서 일부 수량이 돌아온 경우 원본 인계는 유지하고 반품 이력을 추가합니다."""
    try:
        record_id = ObjectId(str(record_id_text))
    except Exception:
        st.error("반품 대상 인계기록 번호가 올바르지 않습니다.")
        return

    toss_collection = get_toss_collection()
    record = toss_collection.find_one({"_id": record_id})
    if not record:
        st.error("반품 대상 인계기록을 찾지 못했습니다.")
        return

    if record.get("record_type") in ("machining_defect", "handover_return"):
        st.error("정상 인계기록에서만 일부 반품을 처리할 수 있습니다.")
        return

    if record.get("is_cancelled") is True or record.get("status") == "cancelled":
        st.warning("취소된 인계기록은 일부 반품 처리할 수 없습니다.")
        return

    original_qty = max(to_int_safe(record.get("handover_qty"), 0), 0)
    already_returned = get_active_return_total(record_id)
    returnable_qty = max(original_qty - already_returned, 0)

    st.write(f"LOT: **{record.get('lot_no', '')}**")
    info_cols = st.columns(3)
    info_cols[0].metric("원래 인계수량", f"{original_qty:,}개")
    info_cols[1].metric("기존 반품합계", f"{already_returned:,}개")
    info_cols[2].metric("현재 실제 인계", f"{returnable_qty:,}개")

    if returnable_qty <= 0:
        st.warning("이 인계기록은 이미 전량 반품되어 추가 반품할 수 없습니다.")
        return

    return_qty = st.number_input(
        "이번 반품수량",
        min_value=1,
        max_value=int(returnable_qty),
        value=1,
        step=1,
        key=f"partial_return_qty_{record_id_text}",
    )
    after_qty = max(returnable_qty - int(return_qty), 0)
    st.info(
        f"이번에 {int(return_qty):,}개를 반품 처리하면 "
        f"이 인계기록의 실제 인계수량은 **{after_qty:,}개**가 됩니다."
    )

    worker_option = st.selectbox(
        "반품 처리 담당자",
        get_material_receiver_options(),
        key=f"partial_return_worker_{record_id_text}",
    )
    worker_no, worker_name = parse_material_receiver_option(worker_option)
    return_memo = st.text_area(
        "반품 메모",
        placeholder="예: 3PART 검사 후 제품 이상으로 5개 반품",
        key=f"partial_return_memo_{record_id_text}",
    )
    confirmed = st.checkbox(
        f"LOT {record.get('lot_no', '')} / 반품 {int(return_qty):,}개 / "
        f"처리 후 실제 인계 {after_qty:,}개를 확인했습니다.",
        key=f"partial_return_confirm_{record_id_text}",
    )

    save_col, close_col = st.columns(2)
    if save_col.button(
        "↩ 일부 반품 저장",
        key=f"partial_return_save_{record_id_text}",
        use_container_width=True,
        type="primary",
    ):
        # 저장 직전에 다시 합계를 조회하여 다른 사용자의 동시 입력을 방지합니다.
        latest_record = toss_collection.find_one({"_id": record_id})
        latest_returned = get_active_return_total(record_id)
        latest_returnable = max(
            to_int_safe(latest_record.get("handover_qty"), 0) - latest_returned,
            0,
        ) if latest_record else 0

        if not latest_record:
            st.error("원본 인계기록이 삭제되었거나 조회되지 않습니다.")
        elif latest_record.get("is_cancelled") is True or latest_record.get("status") == "cancelled":
            st.error("원본 인계기록이 이미 취소되어 반품할 수 없습니다.")
        elif int(return_qty) > latest_returnable:
            st.error(
                f"현재 반품 가능한 수량은 {latest_returnable:,}개입니다. "
                "다른 작업자가 먼저 반품 처리했을 수 있으니 창을 닫고 다시 확인해 주세요."
            )
        elif not worker_no or not worker_name:
            st.error("반품 처리 담당자를 선택해 주세요.")
        elif not confirmed:
            st.error("반품수량 확인란을 체크해 주세요.")
        else:
            now_kst = get_now_kst()
            latest_material = get_material_latest_record(record.get("lot_no", "")) or {}
            return_doc = {
                "record_type": "handover_return",
                "original_handover_id": str(record_id),
                "lot_no": record.get("lot_no", ""),
                "product_name": record.get("product_name", latest_material.get("product_name", "")),
                "spec": record.get("spec", latest_material.get("spec", "")),
                "plan_qty": to_int_safe(record.get("plan_qty"), latest_material.get("plan_qty", 0)),
                "original_handover_qty": int(original_qty),
                "returned_total_before": int(latest_returned),
                "return_qty": int(return_qty),
                "returned_total_after": int(latest_returned + int(return_qty)),
                "net_handover_qty_after": int(latest_returnable - int(return_qty)),
                "return_by_no": worker_no,
                "return_by": worker_name,
                "return_memo": return_memo.strip(),
                "return_at": now_kst.strftime("%Y-%m-%d %H:%M:%S"),
                "return_date": now_kst.strftime("%Y-%m-%d"),
                # 기존 정렬·날짜검색과 호환되도록 공통 필드도 저장합니다.
                "handover_at": now_kst.strftime("%Y-%m-%d %H:%M:%S"),
                "handover_date": now_kst.strftime("%Y-%m-%d"),
                "status": "returned",
                "is_cancelled": False,
                "created_at": now_kst.strftime("%Y-%m-%d %H:%M:%S"),
            }
            result = toss_collection.insert_one(return_doc)
            if not result.inserted_id:
                st.error("MongoDB 반품 저장 결과를 확인하지 못했습니다.")
                return

            st.session_state.handover_flash_message = (
                f"{record.get('lot_no', '')}에서 {int(return_qty):,}개를 일부 반품 처리했습니다. "
                f"현재 실제 인계수량은 {int(latest_returnable - int(return_qty)):,}개입니다."
            )
            st.session_state.pop("handover_search_results", None)
            st.session_state.handover_search_executed = False
            time.sleep(0.3)
            st.rerun()

    if close_col.button(
        "닫기",
        key=f"partial_return_close_{record_id_text}",
        use_container_width=True,
    ):
        st.rerun()



def reset_handover_search_state():
    """3PART 인계 검색 조건·결과·선택·입력 상태를 최초 화면으로 초기화합니다."""
    # Streamlit 위젯은 같은 key를 다시 사용하면 브라우저 입력값이 살아날 수 있으므로
    # 검색 세대 번호를 증가시켜 다음 rerun에서 완전히 새로운 위젯 key를 사용합니다.
    current_generation = int(st.session_state.get("handover_search_generation", 0) or 0)
    st.session_state["handover_search_generation"] = current_generation + 1

    keys_to_clear = (
        "handover_search_results",
        "handover_search_executed",
        "handover_selected_lot",
        "handover_selected_snapshot",
    )
    for key in keys_to_clear:
        st.session_state.pop(key, None)

    # 이전 세대 검색 위젯 및 선택 LOT별 등록 폼 입력값을 모두 제거합니다.
    dynamic_prefixes = (
        "handover_search_keyword_",
        "handover_lot_selectbox_",
        "handover_qty_",
        "handover_by_",
        "handover_received_by_",
        "handover_memo_",
        "handover_confirm_",
        "handover_manual_selection_confirm_",
        "handover_hold_toggle_",
        "handover_defect_qty_",
        "handover_defect_worker_",
        "handover_defect_confirm_",
        "handover_defect_submit_",
        "partial_return_qty_",
        "partial_return_worker_",
        "partial_return_memo_",
        "partial_return_confirm_",
        "partial_return_save_",
        "partial_return_close_",
    )
    for key in list(st.session_state.keys()):
        if any(str(key).startswith(prefix) for prefix in dynamic_prefixes):
            st.session_state.pop(key, None)


def reset_handover_history_search_state():
    """전체 인계이력 검색 조건과 결과를 완전히 초기화합니다."""
    current_generation = int(
        st.session_state.get("handover_history_generation", 0) or 0
    )
    st.session_state["handover_history_generation"] = current_generation + 1
    st.session_state.pop("handover_history_results", None)

    for key in list(st.session_state.keys()):
        if str(key).startswith("handover_history_widget_"):
            st.session_state.pop(key, None)


def show_3part_handover_page():
    ensure_toss_indexes()
    st.title("🚚 3PART 인수인계")
    st.caption(
        "원자재 입고 이력을 LOT별로 합산해 현재 인계 가능 수량을 계산합니다. "
        "인계 취소 시 원본 기록은 삭제하지 않습니다."
    )

    flash_message = st.session_state.pop("handover_flash_message", "")
    if flash_message:
        st.success(flash_message)

    search_tab, history_tab = st.tabs(["🚚 인계 등록", "📜 전체 인계이력 검색"])

    with search_tab:
        handover_generation = int(
            st.session_state.get("handover_search_generation", 0) or 0
        )
        handover_keyword_key = f"handover_search_keyword_{handover_generation}"
        handover_selectbox_key = f"handover_lot_selectbox_{handover_generation}"

        with st.form(
            f"handover_lot_search_form_{handover_generation}",
            clear_on_submit=False,
        ):
            keyword = st.text_input(
                "LOT · 품명 · 규격 검색",
                placeholder="예: 0511, shie top, kz84, k84",
                key=handover_keyword_key,
            )
            search_submitted = st.form_submit_button(
                "🔍 입고 LOT 조회",
                use_container_width=True,
            )

        reset_col, reset_info_col = st.columns([1, 3])
        with reset_col:
            st.button(
                "🔄 새 검색 · 전체 초기화",
                key=f"handover_search_reset_button_{handover_generation}",
                use_container_width=True,
                on_click=reset_handover_search_state,
            )
        with reset_info_col:
            st.caption("검색어·조회 결과·선택 LOT·현재 상태·인계 입력값을 모두 지웁니다.")

        if search_submitted:
            if not keyword.strip():
                st.warning("LOT, 품명 또는 규격을 입력해 주세요.")
                st.session_state.handover_search_executed = False
                st.session_state.pop("handover_search_results", None)
            else:
                try:
                    results = get_handover_lot_summaries(keyword.strip(), limit=200)
                    st.session_state.handover_search_results = results
                    st.session_state.handover_search_executed = True
                    if len(results) == 1:
                        st.session_state.handover_selected_lot = results[0]["lot_no"]
                except Exception as exc:
                    st.error(f"LOT 검색 중 오류가 발생했습니다: {exc}")
                    results = []

        results = st.session_state.get("handover_search_results", [])
        if st.session_state.get("handover_search_executed"):
            if not results:
                st.warning("조건에 맞는 입고 LOT가 없습니다.")
            else:
                option_map = {item["lot_no"]: item for item in results}
                option_lots = list(option_map.keys())
                current_lot = st.session_state.get("handover_selected_lot")
                default_index = option_lots.index(current_lot) if current_lot in option_lots else 0
                selected_lot = st.selectbox(
                    "인계할 LOT 선택",
                    option_lots,
                    index=default_index,
                    format_func=lambda lot: (
                        f"{'⏸ 보류 | ' if option_map[lot].get('hold') else ''}{lot} | "
                        f"{option_map[lot]['product_name']} | {option_map[lot]['spec']} | "
                        f"전체수량: {option_map[lot]['plan_qty']:,}개 | "
                        f"인계된 수량: {option_map[lot]['handover_total']:,}개 | "
                        f"남은 인계수량: {option_map[lot]['overall_not_handed']:,}개"
                    ),
                    key=handover_selectbox_key,
                )
                st.session_state.handover_selected_lot = selected_lot

                close_col, spacer_col = st.columns([1, 4])
                with close_col:
                    st.button(
                        "⬅️ 닫기 · 새 LOT 검색",
                        key=f"handover_close_and_reset_btn_{handover_generation}",
                        use_container_width=True,
                        on_click=reset_handover_search_state,
                    )

                # 선택 후 최신 DB값을 다시 읽어 오래된 검색 결과로 저장되는 것을 방지합니다.
                refreshed = get_handover_lot_summaries(selected_lot, limit=50)
                selected = next((x for x in refreshed if x["lot_no"] == selected_lot), option_map[selected_lot])

                recommended = get_recommended_handover_lot(
                    selected.get("product_name", ""), selected.get("spec", "")
                )
                recommended_lot = str((recommended or {}).get("lot_no", "") or "")
                is_nonrecommended_selection = bool(
                    recommended_lot and selected_lot != recommended_lot
                )

                if recommended_lot:
                    if selected_lot == recommended_lot:
                        st.success(f"⭐ 시스템 추천 인계 대상 LOT: **{recommended_lot}**")
                    else:
                        st.info(
                            f"⭐ 시스템 추천 LOT은 **{recommended_lot}**입니다. "
                            f"현재 작업자가 직접 선택한 LOT은 **{selected_lot}**입니다."
                        )
                else:
                    st.caption("현재 같은 품명·규격에서 자동 추천할 수 있는 정상 LOT가 없습니다.")

                hold_col, hold_info_col = st.columns([1, 3])
                with hold_col:
                    hold_button_label = "▶ 보류 해제" if selected.get("hold") else "⏸ 이 LOT 보류"
                    if st.button(
                        hold_button_label,
                        key=f"handover_hold_toggle_{selected_lot}_{handover_generation}",
                        use_container_width=True,
                    ):
                        matched = set_material_lot_hold(selected_lot, not selected.get("hold"))
                        if matched <= 0:
                            st.error("보류 상태를 변경할 입고 기록을 찾지 못했습니다.")
                            st.stop()
                        st.session_state.handover_flash_message = (
                            f"{selected_lot} LOT의 인계 보류를 "
                            f"{'설정' if not selected.get('hold') else '해제'}했습니다."
                        )
                        st.session_state.pop("handover_search_results", None)
                        st.session_state.handover_search_executed = False
                        st.rerun()
                with hold_info_col:
                    if selected.get("hold"):
                        st.warning("⏸ 현재 보류된 LOT입니다. 보류를 해제해야 인계 등록할 수 있습니다.")
                    else:
                        st.caption("보류하면 자동 추천 대상에서 제외되며, 보류 해제 후 다시 인계할 수 있습니다.")

                defect_notice_qty = to_int_safe(selected.get("machining_defect_total"), 0)
                notice_signature = f"{selected_lot}:{defect_notice_qty}"
                if defect_notice_qty > 0 and st.session_state.get("handover_defect_notice_seen") != notice_signature:
                    st.session_state["handover_defect_notice_seen"] = notice_signature
                    handover_defect_notice_dialog(selected_lot, defect_notice_qty)

                st.markdown("#### LOT 현재 상태")
                metric_cols = st.columns(7)
                metric_cols[0].metric("계획수량", f"{selected['plan_qty']:,}")
                metric_cols[1].metric("누적입고", f"{selected['received_total']:,}")
                metric_cols[2].metric("미입고", f"{selected['missing_received']:,}")
                metric_cols[3].metric("누적인계", f"{selected['handover_total']:,}")
                metric_cols[4].metric("가공불량", f"{selected.get('machining_defect_total', 0):,}")
                metric_cols[5].metric("현재 인계가능", f"{selected['available_qty']:,}")
                metric_cols[6].metric("전체 미인계", f"{selected['overall_not_handed']:,}")
                st.info(f"현재 상태: **{selected['status']}**")

                if selected.get("has_quantity_error"):
                    st.error(
                        "데이터 점검 필요: 정상 인계수량이 누적입고보다 큽니다. "
                        "추가 등록은 차단되며 기존 이력의 취소 여부를 확인해야 합니다."
                    )

                if selected["is_complete"]:
                    st.success("이 LOT은 계획수량 전부가 입고되고 인계되어 완료되었습니다.")
                elif selected["available_qty"] <= 0:
                    st.warning("현재 추가로 인계할 수 있는 수량이 없습니다.")

                # 가공불량은 인계와 별도로 발생 즉시 기록합니다.
                # 다른 LOT의 동일 제품으로 보충할 수 있으므로 인계 가능 수량에서는 차감하지 않습니다.
                with st.expander("⚠️ 4PART 가공불량 바로 등록", expanded=False):
                    st.caption(
                        "선택한 LOT에서 발생한 불량수량만 기록합니다. "
                        "이 수량은 인계 가능 수량에서 차감되지 않습니다."
                    )
                    defect_cols = st.columns(2)
                    defect_qty = defect_cols[0].number_input(
                        "가공불량 수량",
                        min_value=0,
                        value=0,
                        step=1,
                        key=f"handover_defect_qty_{selected_lot}",
                    )
                    defect_worker = defect_cols[1].text_input(
                        "불량 등록 작업자 (4PART)",
                        key=f"handover_defect_worker_{selected_lot}",
                    )
                    defect_confirmed = st.checkbox(
                        f"LOT {selected_lot} / 가공불량 {int(defect_qty):,}개를 확인했습니다.",
                        key=f"handover_defect_confirm_{selected_lot}",
                    )
                    defect_submitted = st.button(
                        "⚠️ 가공불량 저장",
                        key=f"handover_defect_submit_{selected_lot}",
                        use_container_width=True,
                    )

                if defect_submitted:
                    defect_worker = str(defect_worker or "").strip()
                    if int(defect_qty) <= 0:
                        st.error("가공불량 수량은 1개 이상이어야 합니다.")
                    elif not defect_worker:
                        st.error("불량 등록 작업자 이름을 입력해 주세요.")
                    elif not defect_confirmed:
                        st.error("LOT와 가공불량 수량 확인란을 체크해 주세요.")
                    else:
                        latest_material = get_material_latest_record(selected_lot) or {}
                        now_kst = get_now_kst()
                        defect_doc = {
                            "record_type": "machining_defect",
                            "lot_no": selected_lot,
                            "product_name": str(latest_material.get("product_name", selected.get("product_name", "")) or ""),
                            "spec": str(latest_material.get("spec", selected.get("spec", "")) or ""),
                            "plan_qty": to_int_safe(latest_material.get("plan_qty"), selected.get("plan_qty", 0)),
                            "machining_defect_qty": int(defect_qty),
                            "defect_worker": defect_worker,
                            "defect_at": now_kst.strftime("%Y-%m-%d %H:%M:%S"),
                            "handover_at": now_kst.strftime("%Y-%m-%d %H:%M:%S"),
                            "handover_date": now_kst.strftime("%Y-%m-%d"),
                            "status": "defect_record",
                            "is_cancelled": False,
                            "created_at": now_kst.strftime("%Y-%m-%d %H:%M:%S"),
                        }
                        result = get_toss_collection().insert_one(defect_doc)
                        if not result.inserted_id:
                            st.error("MongoDB 가공불량 저장 결과를 확인하지 못했습니다.")
                            st.stop()
                        st.session_state.handover_flash_message = (
                            f"{selected_lot} 가공불량 {int(defect_qty):,}개를 기록했습니다."
                        )
                        st.session_state.pop("handover_search_results", None)
                        st.session_state.handover_search_executed = False
                        st.rerun()

                # 일반 컨테이너를 사용해 수량 변경 시 화면이 즉시 다시 계산되도록 합니다.
                # 따라서 확인 체크박스 문구도 작업자가 입력한 현재 인계수량으로 바로 바뀝니다.
                with st.container(border=True):
                    handover_qty = st.number_input(
                        "이번 인계수량",
                        min_value=0,
                        value=int(selected["available_qty"]),
                        step=1,
                        disabled=(
                            selected["available_qty"] <= 0
                            or selected.get("has_quantity_error", False)
                            or selected.get("hold", False)
                        ),
                        key=f"handover_qty_{selected_lot}",
                    )
                    person_cols = st.columns(2)
                    with person_cols[0]:
                        handover_by = st.text_input("인계자 (4PART)", key=f"handover_by_{selected_lot}")
                    with person_cols[1]:
                        received_by = st.text_input("인수자 (3PART)", key=f"handover_received_by_{selected_lot}")
                    memo = st.text_area("메모", placeholder="부분 인계, 특이사항", key=f"handover_memo_{selected_lot}")
                    register_confirmed = st.checkbox(
                        f"LOT {selected_lot} / 인계수량 {int(handover_qty):,}개를 확인했습니다.",
                        key=f"handover_confirm_{selected_lot}",
                    )
                    manual_selection_confirmed = True
                    if is_nonrecommended_selection:
                        st.warning(
                            f"추천 LOT({recommended_lot})이 아닌 LOT({selected_lot})를 직접 선택했습니다."
                        )
                        manual_selection_confirmed = st.checkbox(
                            "K_SYSTEM의 원자재 납입 순서를 확인했으며, 선택한 LOT로 인계를 진행합니다.",
                            key=f"handover_manual_selection_confirm_{selected_lot}",
                        )
                    register_submitted = st.button(
                        "✅ 3PART 인수인계 등록",
                        key=f"handover_register_submit_{selected_lot}",
                        use_container_width=True,
                        disabled=(
                            selected["available_qty"] <= 0
                            or selected.get("has_quantity_error", False)
                            or selected.get("hold", False)
                        ),
                    )

                if register_submitted:
                    handover_by = str(handover_by or "").strip()
                    received_by = str(received_by or "").strip()
                    handover_by_no = ""
                    received_by_no = ""

                    if int(handover_qty) <= 0:
                        st.error("인계수량은 1개 이상이어야 합니다.")
                    elif not handover_by or not received_by:
                        st.error("인계자와 인수자를 모두 입력해 주세요.")
                    elif handover_by.casefold() == received_by.casefold():
                        st.error("인계자와 인수자는 서로 다른 이름을 입력해 주세요.")
                    elif not register_confirmed:
                        st.error("LOT와 인계수량 확인란을 체크해 주세요.")
                    elif is_nonrecommended_selection and not manual_selection_confirmed:
                        st.error("추천 LOT가 아닌 LOT를 선택한 경우 K_SYSTEM 납입 순서 확인란을 체크해 주세요.")
                    elif selected.get("hold", False):
                        st.error("보류된 LOT은 인계할 수 없습니다. 먼저 보류를 해제해 주세요.")
                    else:
                        # 저장 직전 입고수량과 정상 인계합계를 다시 조회합니다.
                        latest_received_total = get_material_received_total(selected_lot)
                        latest_handover_total = get_handover_total(selected_lot)
                        latest_available = max(latest_received_total - latest_handover_total, 0)

                        if int(handover_qty) > latest_available:
                            st.error(
                                f"다른 사용자의 저장으로 인계 가능 수량이 {latest_available:,}개로 변경되었습니다. "
                                "혹은 인계수량이 입고수량을 초과 하였습니다" "," "LOT을 다시 조회해 주세요."
                            )
                            st.stop()

                        latest_material = get_material_latest_record(selected_lot) or {}
                        now_kst = get_now_kst()
                        doc = {
                            "record_type": "handover",
                            "lot_no": selected_lot,
                            "product_name": str(latest_material.get("product_name", selected.get("product_name", "")) or ""),
                            "spec": str(latest_material.get("spec", selected.get("spec", "")) or ""),
                            "plan_qty": to_int_safe(latest_material.get("plan_qty"), selected.get("plan_qty", 0)),
                            "received_total_at_handover": int(latest_received_total),
                            "handover_total_before": int(latest_handover_total),
                            "handover_qty": int(handover_qty),
                            "handover_total_after": int(latest_handover_total + int(handover_qty)),
                            "handover_by_no": handover_by_no,
                            "handover_by": handover_by,
                            "received_by_no": received_by_no,
                            "received_by": received_by,
                            "handover_at": now_kst.strftime("%Y-%m-%d %H:%M:%S"),
                            "handover_date": now_kst.strftime("%Y-%m-%d"),
                            "memo": memo.strip(),
                            "recommended_lot_at_handover": recommended_lot or None,
                            "manual_lot_selection": bool(is_nonrecommended_selection),
                            "manual_selection_confirmed": bool(
                                is_nonrecommended_selection and manual_selection_confirmed
                            ),
                            "status": "active",
                            "is_cancelled": False,
                            "cancelled_at": None,
                            "cancelled_date": None,
                            "cancelled_by_no": None,
                            "cancelled_by": None,
                            "cancel_reason": None,
                            "created_at": now_kst.strftime("%Y-%m-%d %H:%M:%S"),
                        }
                        result = get_toss_collection().insert_one(doc)
                        if not result.inserted_id:
                            st.error("MongoDB 인계 저장 결과를 확인하지 못했습니다.")
                            st.stop()

                        st.session_state.handover_flash_message = (
                            f"{selected_lot} 인계 {int(handover_qty):,}개를 저장했습니다."
                        )
                        # 다음 화면에서 DB를 다시 조회하도록 이전 검색 결과를 제거합니다.
                        st.session_state.pop("handover_search_results", None)
                        st.session_state.handover_search_executed = False
                        st.rerun()

                st.markdown("#### LOT별 인계 이력")
                history = get_toss_records(selected_lot)
                if not history:
                    st.info("아직 등록된 인계 이력이 없습니다.")
                else:
                    for record in history:
                        record_type = record.get("record_type")
                        is_defect = record_type == "machining_defect"
                        is_return = record_type == "handover_return"
                        cancelled = bool(record.get("is_cancelled")) or record.get("status") == "cancelled"

                        if is_defect:
                            with st.container(border=True):
                                info_cols = st.columns([1.4, 1, 1.4, 1.2])
                                info_cols[0].write(f"**{record.get('defect_at') or record.get('handover_at', '')}**")
                                info_cols[1].write(
                                    f"**가공불량 {to_int_safe(record.get('machining_defect_qty'), 0):,}개**"
                                )
                                info_cols[2].write(f"등록 작업자: {record.get('defect_worker', '')}")
                                info_cols[3].write("⚠️ 불량기록")

                        elif is_return:
                            status_text = "❌ 계산 제외" if cancelled else "↩ 일부 반품"
                            with st.container(border=True):
                                info_cols = st.columns([1.25, 0.85, 1.1, 1.1, 1.1])
                                info_cols[0].write(f"**{record.get('return_at') or record.get('handover_at', '')}**")
                                info_cols[1].write(f"**반품 {to_int_safe(record.get('return_qty'), 0):,}개**")
                                info_cols[2].write(f"처리: {record.get('return_by', '')}")
                                info_cols[3].write(
                                    f"처리 후 {to_int_safe(record.get('net_handover_qty_after'), 0):,}개"
                                )
                                info_cols[4].write(status_text)
                                if record.get("return_memo"):
                                    st.caption(f"반품 메모: {record.get('return_memo')}")
                                if cancelled:
                                    st.caption(
                                        f"계산 제외: {record.get('cancelled_at', '')} / "
                                        f"{record.get('cancelled_by', '')} / {record.get('cancel_reason', '')}"
                                    )

                        else:
                            original_qty = to_int_safe(record.get("handover_qty"), 0)
                            returned_qty = get_active_return_total(record.get("_id"))
                            net_qty = max(original_qty - returned_qty, 0)
                            status_text = "❌ 취소" if cancelled else "✅ 정상"
                            with st.container(border=True):
                                info_cols = st.columns([1.2, 1.15, 1, 1, 1.0])
                                info_cols[0].write(f"**{record.get('handover_at', '')}**")
                                if returned_qty > 0 and not cancelled:
                                    info_cols[1].write(
                                        f"**현재 {net_qty:,}개**\n\n"
                                        f"원인계 {original_qty:,} / 반품 {returned_qty:,}"
                                    )
                                else:
                                    info_cols[1].write(f"**{original_qty:,}개**")
                                info_cols[2].write(f"인계: {record.get('handover_by', '')}")
                                info_cols[3].write(f"인수: {record.get('received_by', '')}")
                                info_cols[4].write(status_text)
                                if record.get("memo"):
                                    st.caption(f"메모: {record.get('memo')}")
                                if cancelled:
                                    st.caption(
                                        f"취소: {record.get('cancelled_at', '')} / "
                                        f"{record.get('cancelled_by', '')} / {record.get('cancel_reason', '')}"
                                    )
                                else:
                                    button_cols = st.columns(2)
                                    if net_qty > 0 and button_cols[0].button(
                                        "↩ 일부 반품",
                                        key=f"open_partial_return_{record['_id']}",
                                        use_container_width=True,
                                    ):
                                        partial_handover_return_dialog(str(record["_id"]))
                                    if button_cols[1].button(
                                        "⚠️ 이 인계기록 취소",
                                        key=f"open_cancel_handover_{record['_id']}",
                                        use_container_width=True,
                                    ):
                                        cancel_handover_dialog(str(record["_id"]))

    with history_tab:
        st.markdown("#### 전체 인계이력 조건 검색")

        history_generation = int(
            st.session_state.get("handover_history_generation", 0) or 0
        )
        key_prefix = f"handover_history_widget_{history_generation}"

        # 폼 밖에서 날짜 체크 변경 즉시 재실행되도록 처리합니다.
        use_date_filter = st.checkbox(
            "날짜 조건 사용",
            value=False,
            key=f"{key_prefix}_use_date",
            help="체크하지 않으면 날짜와 관계없이 전체 인계이력에서 검색합니다.",
        )
        row2 = st.columns(2)
        start_date = row2[0].date_input(
            "시작일",
            value=get_now_kst().date().replace(day=1),
            disabled=not use_date_filter,
            key=f"{key_prefix}_start_date",
        )
        end_date = row2[1].date_input(
            "종료일",
            value=get_now_kst().date(),
            disabled=not use_date_filter,
            key=f"{key_prefix}_end_date",
        )

        # 검색 필드도 폼 밖에 두어 날짜 토글 시 입력값을 보존합니다.
        row1 = st.columns([1.2, 1.6, 1.2, 0.9])
        lot_keyword = row1[0].text_input(
            "LOT",
            placeholder="예: 0511, 1043, kk051",
            key=f"{key_prefix}_lot",
        )
        product_spec_keyword = row1[1].text_input(
            "품명 / 규격",
            placeholder="예: shie top, ring flat, kz84, k84",
            key=f"{key_prefix}_product_spec",
        )
        person_keyword = row1[2].text_input(
            "인계자 / 인수자",
            placeholder="이름만 입력해도 전체 검색",
            key=f"{key_prefix}_person",
        )
        include_cancelled = row1[3].checkbox(
            "취소 이력 포함",
            value=True,
            key=f"{key_prefix}_include_cancelled",
        )

        history_submitted = st.button(
            "🔍 인계이력 조회",
            use_container_width=True,
        )

        close_col, close_info_col = st.columns([1.3, 3.7])
        with close_col:
            st.button(
                "❌ 검색 결과 닫기 · 초기화",
                key=f"handover_history_close_{history_generation}",
                use_container_width=True,
                on_click=reset_handover_history_search_state,
            )
        with close_info_col:
            st.caption(
                "LOT·품명/규격·인계자/인수자·날짜 조건과 조회 결과를 모두 지웁니다."
            )

        if history_submitted:
            if use_date_filter and start_date > end_date:
                st.error("시작일은 종료일보다 늦을 수 없습니다.")
            else:
                conditions = []

                # 날짜 조건은 사용자가 체크한 경우에만 적용합니다.
                # 이름이나 LOT만 입력했을 때 과거 전체 이력이 검색되도록 기본값은 날짜 미사용입니다.
                if use_date_filter:
                    conditions.append(
                        {
                            "handover_date": {
                                "$gte": str(start_date),
                                "$lte": str(end_date),
                            }
                        }
                    )

                # LOT는 대소문자와 기호를 무시하고 글자·숫자의 순서만 맞아도 검색합니다.
                # 예: KK20260511043 -> 0511, 1043, k051, kk1043 등으로 검색 가능
                lot_text = str(lot_keyword or "").strip()
                if lot_text:
                    lot_token_conditions = []
                    for token in re.split(r"\s+", lot_text):
                        smart_regex = build_smart_search_regex(token)
                        if smart_regex:
                            lot_token_conditions.append(
                                {
                                    "lot_no": {
                                        "$regex": smart_regex,
                                        "$options": "i",
                                    }
                                }
                            )
                    if lot_token_conditions:
                        conditions.append(
                            {"$and": lot_token_conditions}
                            if len(lot_token_conditions) > 1
                            else lot_token_conditions[0]
                        )

                if product_spec_keyword.strip():
                    # 여러 단어를 입력하면 각 단어가 품명 또는 규격 중 한 곳에서
                    # 글자 순서대로 발견되어야 합니다.
                    # 예: "shie top" -> RING SHIELD TOP, "k84" -> KZ-846
                    product_spec_tokens = [
                        token
                        for token in re.split(
                            r"\s+", product_spec_keyword.strip()
                        )
                        if token
                    ]
                    for token in product_spec_tokens:
                        smart_regex = build_smart_search_regex(token)
                        if not smart_regex:
                            continue
                        conditions.append(
                            {
                                "$or": [
                                    {
                                        "product_name": {
                                            "$regex": smart_regex,
                                            "$options": "i",
                                        }
                                    },
                                    {
                                        "spec": {
                                            "$regex": smart_regex,
                                            "$options": "i",
                                        }
                                    },
                                ]
                            }
                        )

                # 이름 하나만 입력해도 인계자·인수자·취소담당자 중 일치하는 모든 이력을 조회합니다.
                if person_keyword.strip():
                    person_tokens = [
                        token
                        for token in re.split(r"\s+", person_keyword.strip())
                        if token
                    ]
                    for token in person_tokens:
                        safe_person = re.escape(token)
                        conditions.append(
                            {
                                "$or": [
                                    {
                                        "handover_by": {
                                            "$regex": safe_person,
                                            "$options": "i",
                                        }
                                    },
                                    {
                                        "received_by": {
                                            "$regex": safe_person,
                                            "$options": "i",
                                        }
                                    },
                                    {
                                        "cancelled_by": {
                                            "$regex": safe_person,
                                            "$options": "i",
                                        }
                                    },
                                    {
                                        "defect_worker": {
                                            "$regex": safe_person,
                                            "$options": "i",
                                        }
                                    },
                                    {
                                        "return_by": {
                                            "$regex": safe_person,
                                            "$options": "i",
                                        }
                                    },
                                ]
                            }
                        )

                if not include_cancelled:
                    conditions.append({"is_cancelled": {"$ne": True}})

                query = (
                    {"$and": conditions}
                    if len(conditions) > 1
                    else (conditions[0] if conditions else {})
                )
                records = list(
                    get_toss_collection()
                    .find(query)
                    .sort([("handover_at", -1), ("_id", -1)])
                    .limit(1000)
                )
                st.session_state.handover_history_results = records

        history_records = st.session_state.get("handover_history_results")
        if history_records is None:
            st.info("조건을 입력하고 인계이력 조회 버튼을 눌러주세요.")
        elif not history_records:
            st.warning("조건에 맞는 인계 이력이 없습니다.")
        else:
            # -----------------------------------------------------------------
            # 1) 검색된 원본 인계 이력 표
            # -----------------------------------------------------------------
            history_return_totals, _, _, _ = get_handover_history_bulk_totals(
                [], [r.get("_id") for r in history_records
                     if r.get("record_type") not in ("machining_defect", "handover_return")]
            )
            rows = []
            for record in history_records:
                record_type = record.get("record_type")
                is_defect = record_type == "machining_defect"
                is_return = record_type == "handover_return"
                cancelled = (
                    bool(record.get("is_cancelled"))
                    or record.get("status") == "cancelled"
                )

                if is_defect:
                    state_text = "가공불량"
                    event_time = record.get("defect_at") or record.get("handover_at", "")
                    handover_qty_value = 0
                    return_qty_value = 0
                    actual_qty_value = 0
                    handover_person = record.get("defect_worker", "")
                    received_person = ""
                    memo_value = record.get("memo", "")
                elif is_return:
                    state_text = "반품취소" if cancelled else "일부반품"
                    event_time = record.get("return_at") or record.get("handover_at", "")
                    handover_qty_value = 0
                    return_qty_value = to_int_safe(record.get("return_qty"), 0)
                    actual_qty_value = 0
                    handover_person = record.get("return_by", "")
                    received_person = ""
                    memo_value = record.get("return_memo", "")
                else:
                    state_text = "취소" if cancelled else "정상"
                    event_time = record.get("handover_at", "")
                    original_qty = to_int_safe(record.get("handover_qty"), 0)
                    active_returned = 0 if cancelled else history_return_totals.get(str(record.get("_id")), 0)
                    handover_qty_value = original_qty
                    return_qty_value = active_returned
                    actual_qty_value = 0 if cancelled else max(original_qty - active_returned, 0)
                    handover_person = record.get("handover_by", "")
                    received_person = record.get("received_by", "")
                    memo_value = record.get("memo", "")

                rows.append(
                    {
                        "상태": state_text,
                        "인계일시": event_time,
                        "LOT": record.get("lot_no", ""),
                        "품명": record.get("product_name", ""),
                        "규격": record.get("spec", ""),
                        "전체수량": to_int_safe(record.get("plan_qty"), 0),
                        "원인계수량": handover_qty_value,
                        "반품수량": return_qty_value,
                        "현재실제인계": actual_qty_value,
                        "가공불량수량": to_int_safe(record.get("machining_defect_qty"), 0) if is_defect else 0,
                        "처리자/인계자": handover_person,
                        "인수자": received_person,
                        "메모": memo_value,
                        "취소일시": record.get("cancelled_at", ""),
                        "취소담당자": record.get("cancelled_by", ""),
                        "취소사유": record.get("cancel_reason", ""),
                    }
                )
            df = pd.DataFrame(rows)

            # 같은 LOT에 인계 이력이 여러 건 있어도 전체수량은 LOT별로 한 번만 합산합니다.
            lot_total_qty = {}
            for record in history_records:
                lot_no = str(record.get("lot_no", "") or "").strip()
                plan_qty = to_int_safe(record.get("plan_qty"), 0)
                if not lot_no:
                    continue
                lot_total_qty[lot_no] = max(lot_total_qty.get(lot_no, 0), plan_qty)
            total_plan_qty = sum(lot_total_qty.values())

            metric_cols = st.columns(6)
            metric_cols[0].metric("전체 수량", f"{total_plan_qty:,}개")
            metric_cols[1].metric("검색 결과", f"{len(df):,}건")
            metric_cols[2].metric(
                "현재 실제 인계",
                f"{int(df.loc[df['상태'] == '정상', '현재실제인계'].sum()):,}개",
            )
            metric_cols[3].metric(
                "부분 반품",
                f"{int(df.loc[df['상태'] == '일부반품', '반품수량'].sum()):,}개",
            )
            metric_cols[4].metric(
                "가공불량",
                f"{int(df['가공불량수량'].sum()):,}개",
            )
            metric_cols[5].metric(
                "취소 건수",
                f"{int((df['상태'] == '취소').sum()):,}건",
            )


            # -----------------------------------------------------------------
            # 2) 검색 결과와 같은 품명·규격의 모든 LOT를 찾아 LOT별 진행현황 표시
            #    작업자가 "어느 LOT에서 이어서 인계할지" 바로 판단할 수 있게 합니다.
            # -----------------------------------------------------------------
            product_spec_pairs = []
            for record in history_records:
                product_name = str(record.get("product_name", "") or "").strip()
                spec = str(record.get("spec", "") or "").strip()
                pair = (product_name, spec)
                if (product_name or spec) and pair not in product_spec_pairs:
                    product_spec_pairs.append(pair)

            related_conditions = []
            for product_name, spec in product_spec_pairs:
                pair_conditions = []
                if product_name:
                    pair_conditions.append(
                        {"product_name": {"$regex": f"^{re.escape(product_name)}$", "$options": "i"}}
                    )
                if spec:
                    pair_conditions.append(
                        {"spec": {"$regex": f"^{re.escape(spec)}$", "$options": "i"}}
                    )
                if pair_conditions:
                    related_conditions.append(
                        {"$and": pair_conditions} if len(pair_conditions) > 1 else pair_conditions[0]
                    )

            related_query = (
                {"$or": related_conditions}
                if len(related_conditions) > 1
                else (related_conditions[0] if related_conditions else {})
            )

            related_pipeline = []
            if related_query:
                related_pipeline.append({"$match": related_query})
            related_pipeline.extend(
                [
                    {"$sort": {"_id": 1}},
                    {
                        "$group": {
                            "_id": "$lot_no",
                            "received_total": {"$sum": "$received_qty"},
                            "product_name": {"$last": "$product_name"},
                            "spec": {"$last": "$spec"},
                            "plan_qty": {"$last": "$plan_qty"},
                            "hold": {"$last": {"$ifNull": ["$hold", False]}},
                            "first_receive_date": {"$first": "$receive_date"},
                            "latest_receive_date": {"$last": "$receive_date"},
                        }
                    },
                    {"$sort": {"latest_receive_date": 1, "_id": 1}},
                    {"$limit": 1000},
                ]
            )

            related_material_items = list(get_material_collection().aggregate(related_pipeline))
            _, bulk_handover_totals, bulk_defect_totals, bulk_latest = get_handover_history_bulk_totals(
                [item.get("_id") for item in related_material_items], []
            )
            lot_status_items = []
            for material_item in related_material_items:
                lot_no = str(material_item.get("_id", "") or "").strip()
                if not lot_no:
                    continue

                handover_total = bulk_handover_totals.get(lot_no, 0)
                machining_defect_total = bulk_defect_totals.get(lot_no, 0)
                state = calculate_handover_state(
                    material_item.get("plan_qty"),
                    material_item.get("received_total"),
                    handover_total,
                )
                latest_normal_handover_at = bulk_latest.get(lot_no, "")
                lot_status_items.append(
                    {
                        "lot_no": lot_no,
                        "product_name": str(material_item.get("product_name", "") or ""),
                        "spec": str(material_item.get("spec", "") or ""),
                        "hold": bool(material_item.get("hold", False)),
                        "first_receive_date": str(material_item.get("first_receive_date", "") or ""),
                        "latest_receive_date": str(material_item.get("latest_receive_date", "") or ""),
                        "last_handover_at": latest_normal_handover_at,
                        "machining_defect_total": int(machining_defect_total),
                        **state,
                    }
                )

            # 품명·규격별 FIFO 순서에서 먼저 이어서 넘길 LOT를 표시합니다.
            grouped_items = {}
            for item in lot_status_items:
                group_key = (item["product_name"], item["spec"])
                grouped_items.setdefault(group_key, []).append(item)

            lot_summary_rows = []
            for group_key, group_items in grouped_items.items():
                group_items.sort(
                    key=lambda item: (
                        item.get("latest_receive_date", ""),
                        item.get("lot_no", ""),
                    )
                )

                actionable_items = [
                    item
                    for item in group_items
                    if (
                        item.get("available_qty", 0) > 0
                        and not item.get("is_complete")
                        and not item.get("hold", False)
                    )
                ]
                continuing_item = next(
                    (item for item in actionable_items if item.get("handover_total", 0) > 0),
                    None,
                )
                recommended_item = continuing_item or (actionable_items[0] if actionable_items else None)

                for item in group_items:
                    if item.get("hold", False):
                        guide = "⏸ 보류"
                    elif item.get("is_complete"):
                        guide = "✅ 완료"
                    elif recommended_item is item and item.get("handover_total", 0) > 0:
                        guide = "▶ 이어서 인계"
                    elif recommended_item is item:
                        guide = "▶ 다음 인계"
                    elif item.get("available_qty", 0) <= 0 and item.get("overall_not_handed", 0) > 0:
                        guide = "⏳ 추가 입고 대기"
                    else:
                        guide = "대기"

                    lot_summary_rows.append(
                        {
                            "작업안내": guide,
                            "LOT": item["lot_no"],
                            "품명": item["product_name"],
                            "규격": item["spec"],
                            "전체수량": item["plan_qty"],
                            "인계완료": item["handover_total"],
                            "가공불량": item.get("machining_defect_total", 0),
                            "남은인계수량": item["overall_not_handed"],
                            "현재입고": item["received_total"],
                            "현재인계가능": item["available_qty"],
                            "보류여부": "보류" if item.get("hold", False) else "정상",
                            "LOT상태": item["status"],
                            "마지막인계일시": item["last_handover_at"] or "-",
                        }
                    )

            st.markdown("#### 📦 같은 제품 LOT별 인계 진행현황")
            st.caption(
                "같은 품명·규격의 LOT를 입고 순서대로 보여줍니다. "
                "`▶ 이어서 인계` 또는 `▶ 다음 인계` 표시가 다음 작업 대상입니다."
            )

            if lot_summary_rows:
                lot_summary_df = pd.DataFrame(lot_summary_rows)
                st.dataframe(
                    lot_summary_df,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "전체수량": st.column_config.NumberColumn(format="%d개"),
                        "인계완료": st.column_config.NumberColumn(format="%d개"),
                        "가공불량": st.column_config.NumberColumn(format="%d개"),
                        "남은인계수량": st.column_config.NumberColumn(format="%d개"),
                        "현재입고": st.column_config.NumberColumn(format="%d개"),
                        "현재인계가능": st.column_config.NumberColumn(format="%d개"),
                    },
                )
            else:
                st.warning("같은 품명·규격의 입고 LOT 현황을 찾지 못했습니다.")

            st.markdown("#### 📜 상세 인계·취소 이력")
            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "전체수량": st.column_config.NumberColumn(format="%d개"),
                    "인계수량": st.column_config.NumberColumn(format="%d개"),
                    "가공불량수량": st.column_config.NumberColumn(format="%d개"),
                },
            )





@st.cache_data(ttl=45, show_spinner=False)
def load_material_status():
    # 서버측 LOT 집계: 전체 이력을 내려받지 않고 LOT별 요약만 전송
    pipeline = [
        {"$sort": {"_id": 1}},
        {"$group": {"_id": "$lot_no", "received_total": {"$sum": {"$ifNull": ["$received_qty", 0]}},
                    # Preserve all historical values for read-only nonblank fallback.
                    # A later partial receipt may omit product_name/spec.
                    "product_name_history": {"$push": "$product_name"},
                    "spec_history": {"$push": "$spec"},
                    "plan_qty": {"$last": "$plan_qty"}, "first_receive_date": {"$min": "$receive_date"},
                    "latest_receive_date": {"$max": "$receive_date"}}},
    ]
    received = list(get_material_collection().aggregate(pipeline, allowDiskUse=True))
    # 전체 LOT의 인계 수량을 한 번에 집계: LOT당 쿼리 반복 방지
    toss_pipeline = [
        {"$match": {"is_cancelled": {"$ne": True}, "status": {"$ne": "cancelled"}}},
        {"$group": {"_id": "$lot_no", "total": {"$sum": {"$switch": {"branches": [
            {"case": {"$eq": ["$record_type", "machining_defect"]}, "then": 0},
            {"case": {"$eq": ["$record_type", "handover_return"]},
             "then": {"$multiply": [{"$ifNull": ["$return_qty", 0]}, -1]}}
        ], "default": {"$ifNull": ["$handover_qty", 0]}}}}}}
    ]
    handed = {str(r["_id"]): max(to_int_safe(r.get("total")), 0)
              for r in get_toss_collection().aggregate(toss_pipeline, allowDiskUse=True)}
    def latest_nonblank(values):
        # Read-only display fallback; never infer or write missing master data.
        for value in reversed(values or []):
            if value is not None and str(value).strip():
                return str(value).strip()
        return "정보 없음"

    result = []
    for item in received:
        lot = str(item.get("_id") or "").strip()
        if not lot: continue
        state = calculate_handover_state(item.get("plan_qty"), item.get("received_total"), handed.get(lot, 0))
        result.append({"LOT": lot, "품명": latest_nonblank(item.get("product_name_history")),
                       "규격": latest_nonblank(item.get("spec_history")), "계획수량": state["plan_qty"],
                       "입고일": str(item.get("first_receive_date") or ""),
                       "입고상황": f'{state["received_total"]:,} / {state["plan_qty"]:,}',
                       "인계상황": f'{state["handover_total"]:,} / {state["received_total"]:,}',
                       "입고수량": state["received_total"], "인계수량": state["handover_total"],
                       "잔여수량": state["available_qty"], "상태": state["status"],
                       "수량오류": state["has_quantity_error"]})
    return result

# Read-only display helpers: preserve stored MongoDB fields and values.
MATERIAL_DETAIL_LABELS = {
    "lot_no": "LOT 번호", "product_name": "품명", "spec": "규격",
    "plan_qty": "계획수량", "received_qty": "입고수량",
    "received_total_before": "입고 전 누적수량", "received_total_after": "입고 후 누적수량",
    "receive_date": "입고일", "receiver_no": "입고 담당자 번호",
    "receiver_name": "입고 담당자", "memo": "비고", "source": "등록경로",
    "created_at": "등록일시", "record_type": "기록구분",
    "received_total_at_handover": "인계 당시 입고누계",
    "handover_total_before": "인계 전 누계", "handover_qty": "인계수량",
    "handover_total_after": "인계 후 누계", "handover_by_no": "인계자 번호",
    "handover_by": "인계자", "received_by_no": "인수자 번호",
    "received_by": "인수자", "handover_at": "인계일시",
    "handover_date": "인계일", "recommended_lot_at_handover": "당시 추천 LOT",
    "manual_lot_selection": "수동 LOT 선택", "manual_selection_confirmed": "수동 선택 확인",
    "status": "기록상태", "is_cancelled": "취소여부",
    "cancelled_at": "취소일시", "cancelled_date": "취소일",
    "cancelled_by_no": "취소자 번호", "cancelled_by": "취소자",
    "cancel_reason": "취소사유", "return_qty": "반품수량",
    "return_at": "반품일시", "return_date": "반품일",
    "return_by": "반품자", "return_by_no": "반품자 번호",
    "net_handover_qty_after": "반품 후 실인계수량",
    "defect_qty": "불량수량", "defect_reason": "불량사유",
}
MATERIAL_DETAIL_VALUES = {
    "record_type": {"handover": "인계", "handover_return": "반품", "machining_defect": "가공불량"},
    "status": {"active": "정상", "cancelled": "취소"},
    "source": {"qr_live": "QR 등록", "manual_or_not_found": "수동 등록 또는 조회 실패"},
}

def material_detail_display(records):
    if not records:
        return pd.DataFrame()
    frame = pd.DataFrame(records).copy()
    for key, mapping in MATERIAL_DETAIL_VALUES.items():
        if key in frame.columns:
            frame[key] = frame[key].map(lambda v: mapping.get(v, v) if isinstance(v, str) else v)
    for key in ("is_cancelled", "manual_lot_selection", "manual_selection_confirmed"):
        if key in frame.columns:
            frame[key] = frame[key].map(lambda v: "예" if v is True else ("아니요" if v is False else v))
    frame.rename(columns=MATERIAL_DETAIL_LABELS, inplace=True)
    return frame


def material_handover_display(received, handed):
    received, handed = int(received), int(handed)
    remaining = max(received - handed, 0)
    if handed <= 0:
        return f"미인계 · 0/{received:,}개 · 잔량 {remaining:,}개"
    if received > 0 and handed >= received:
        return f"인계완료 · {handed:,}/{received:,}개 · 잔량 {remaining:,}개"
    return f"인계중 · {handed:,}/{received:,}개 · 잔량 {remaining:,}개"


def show_material_status_page():
    st.title("📋 원자재별 입고·인계 현황 · V1.4C")
    st.caption("화면 버전: V1.4C · 인계상황 한글 표시 / LOT 상세 이력 한글화 적용")
    st.caption("조회 전용 · 규격별 최초 입고일 순 · 45초 조회 캐시 (등록/수정은 기존 메뉴 이용)")
    if st.button("🔄 최신 기록 새로고침"):
        load_material_status.clear()
        st.rerun()
    with st.spinner("LOT별 입고·인계 수량 집계 중..."):
        rows = load_material_status()
    if not rows:
        st.info("조회할 원자재 입고 기록이 없습니다.")
        return
    df = pd.DataFrame(rows).sort_values(["규격", "입고일", "LOT"], kind="stable")
    a,b,c = st.columns(3)
    a.metric("LOT 수", f"{len(df):,}")
    b.metric("입고 합계", f"{int(df['입고수량'].sum()):,}")
    c.metric("인계 합계", f"{int(df['인계수량'].sum()):,}")
    if df["수량오류"].any():
        st.warning(f"인계수량이 입고수량보다 많은 LOT {int(df['수량오류'].sum())}건: 원본 기록 확인 필요")
    # 인계 상태는 입고수량 대비 실인계수량 기준이며 조회 화면에서만 계산한다.
    # 원본 MongoDB 문서는 수정하지 않는다.
    df["인계상태"] = df.apply(
        lambda r: "인계없음" if int(r["인계수량"]) <= 0
        else ("인계완료" if int(r["입고수량"]) > 0 and int(r["인계수량"]) >= int(r["입고수량"])
              else "인계중"), axis=1)
    # 필터는 화면 세션에만 보관하며 MongoDB에 어떠한 변경도 수행하지 않는다.
    columns = ["LOT", "품명", "규격", "계획수량", "입고일", "입고상황", "인계상황"]
    active_key = "material_status_applied_filters_v12"
    if active_key not in st.session_state:
        st.session_state[active_key] = {}
    applied = st.session_state[active_key]

    def filter_view(source, filters, exclude=None):
        view = source
        for field, chosen in filters.items():
            if field == exclude or not chosen:
                continue
            source_field = "인계상태" if field == "인계상황" else field
            view = view[view[source_field].astype(str).isin(chosen)]
        return view

    def filter_options(field):
        # 다른 열에 적용된 필터를 반영하되 현재 열 자체의 필터는 제외한다.
        # 따라서 기존에 선택한 항목도 재선택/해제할 수 있다.
        available = filter_view(df, applied, exclude=field)
        if field == "인계상황":
            return [v for v in ("인계없음", "인계중", "인계완료") if v in set(available["인계상태"])]
        return sorted(available[field].astype(str).unique().tolist(), key=lambda x: x.casefold())

    st.caption("열별 필터 ▼ 를 눌러 선택한 뒤 '적용'을 누르세요. 여러 열의 조건은 누적됩니다.")
    if st.button("🧹 전체 필터 초기화", key="material_filter_reset_all"):
        st.session_state[active_key] = {}
        st.rerun()

    # Streamlit 기본 dataframe 헤더는 사용자 지정 팝업을 지원하지 않아
    # 각 열 바로 위에 Excel 자동필터와 동일한 동작의 필터 팝업을 배치한다.
    header_cells = st.columns([1.5, 1.6, 2.4, 1.1, 1.3, 1.2, 1.2], gap="small")
    for field, cell in zip(columns, header_cells):
        with cell:
            marked = " ●" if applied.get(field) else ""
            with st.popover(f"{field} ▼{marked}", use_container_width=True):
                choices = filter_options(field)
                previous = applied.get(field, [])
                with st.form(f"material_filter_form_{field}", border=False):
                    st.caption(f"{field} 선택 · {len(choices):,}개")
                    # DB 집계에 실제 존재하는 값만 체크박스로 표시한다.
                    # 인계상황은 입고/인계 실제 수량에서 계산된 3가지 상태만 표시한다.
                    # 검색창/중첩 드롭다운 없이 여러 값을 직접 체크할 수 있다.
                    checked = []
                    with st.container(height=260, border=False):
                        for index, value in enumerate(choices):
                            if st.checkbox(str(value), value=value in previous,
                                           key=f"material_v12_{field}_{index}_{value}"):
                                checked.append(value)
                    submit = st.form_submit_button("적용", use_container_width=True)
                    if submit:
                        updated = dict(applied)
                        if checked:
                            updated[field] = checked
                        else:
                            updated.pop(field, None)
                        st.session_state[active_key] = updated
                        st.rerun()
                if st.button("✕ 닫기", key=f"material_filter_close_{field}", use_container_width=True):
                    st.rerun()
                if st.button("이 열 필터 해제", key=f"material_filter_clear_{field}", use_container_width=True):
                    updated = dict(applied)
                    updated.pop(field, None)
                    st.session_state[active_key] = updated
                    st.rerun()

    visible = filter_view(df, applied)
    # Keep raw quantity/status columns intact for the existing filters.
    display = visible[columns].copy()
    display["인계상황"] = visible.apply(
        lambda r: material_handover_display(r["입고수량"], r["인계수량"]), axis=1)
    st.info("인계상황: 미인계(0개 인계) / 인계중(일부 인계) / 인계완료(전량 인계) · 잔량은 아직 인계하지 않은 수량입니다.")
    st.dataframe(display, use_container_width=True, hide_index=True, height=520,
                 column_config={"인계상황": st.column_config.TextColumn("인계상황 · 인계/입고 · 잔량", width="large")})
    st.caption(f"전체 {len(df):,}건 / 표시 {len(visible):,}건 · 열 제목을 클릭하면 표시 결과를 정렬할 수 있습니다.")
    df = visible
    if df.empty: return
    lot = st.selectbox("상세 이력 조회 LOT", df["LOT"].tolist())
    with st.expander(f"📑 {lot} 입고·인계 상세 이력", expanded=False):
        receive = list(get_material_collection().find({"lot_no": lot}, {"_id": 0}).sort("_id", 1))
        toss = list(get_toss_collection().find({"lot_no": lot}, {"_id": 0}).sort("_id", 1))
        tab1,tab2 = st.tabs([f"입고 {len(receive)}건", f"인계·반품·취소 {len(toss)}건"])
        st.caption("상세 이력은 표 안에서 좌우로 스크롤해 확인하세요. 마우스 Shift+휠 또는 하단 가로 스크롤을 이용할 수 있습니다.")
        with tab1:
            if receive:
                st.dataframe(material_detail_display(receive), use_container_width=True,
                             hide_index=True, height=min(350, 70 + 36 * len(receive)),
                             column_config={"LOT 번호": st.column_config.TextColumn("LOT 번호")})
            else:
                st.info("입고 이력이 없습니다.")
        with tab2:
            if toss:
                st.dataframe(material_detail_display(toss), use_container_width=True,
                             hide_index=True, height=min(350, 70 + 36 * len(toss)),
                             column_config={"LOT 번호": st.column_config.TextColumn("LOT 번호")})
            else:
                st.info("인계·반품·취소 이력이 없습니다.")



def show_material_receiving_page():
    return show_material_receiving_page_live_qr()

st.sidebar.title("4PART 원자재 관리")
PAGES = [MATERIAL_MENU_LABEL, HANDOVER_MENU_LABEL, "📋 원자재별 입고·인계 현황"]
if "material_page_choice" not in st.session_state:
    st.session_state.material_page_choice = PAGES[0]
if any(material_query_param(name) for name in ("material_qr", "material_scan", "material_page")):
    st.session_state.material_page_choice = MATERIAL_MENU_LABEL
page = st.sidebar.radio("메뉴", PAGES, key="material_page_choice")
if page == MATERIAL_MENU_LABEL:
    show_material_receiving_page()
elif page == HANDOVER_MENU_LABEL:
    show_3part_handover_page()
else:
    show_material_status_page()
