import streamlit as st
import pandas as pd
import secrets

import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone

SPREADSHEET_ID = (st.secrets.get("gsheets", {}).get("spreadsheet_id", "") or "").strip()
WORKSHEET_NAME = st.secrets.get("gsheets", {}).get("worksheet_name", "Secondary")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

def get_gs_client():
    if "gcp_service_account" not in st.secrets:
        st.error("Missing [gcp_service_account] in secrets.toml")
        st.stop()
    info = dict(st.secrets["gcp_service_account"])
    pk = info.get("private_key", "")
    if pk and ("\\n" in pk) and ("\n" not in pk):
        info["private_key"] = pk.replace("\\n", "\n")
    if "BEGIN PRIVATE KEY" not in info.get("private_key", ""):
        st.error("Invalid private_key format in secrets.toml")
        st.stop()
    try:
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    except Exception as e:
        st.error(f"Failed to build credentials: {e}")
        st.stop()
    return gspread.authorize(creds)

def open_ws():
    if not SPREADSHEET_ID:
        st.error("Missing [gsheets].spreadsheet_id in secrets.toml")
        st.stop()
    gc = get_gs_client()
    try:
        sh = gc.open_by_key(SPREADSHEET_ID)
    except Exception as e:
        st.error("เปิดสเปรดชีตไม่สำเร็จ (ตรวจสิทธิ์/Spreadsheet ID):\n" + str(e))
        st.stop()
    try:
        ws = sh.worksheet(WORKSHEET_NAME)
    except Exception as e:
        st.error(f"หา worksheet ชื่อ '{WORKSHEET_NAME}' ไม่เจอ: {e}")
        st.stop()
    return ws

def col_letter_to_index(letter: str) -> int:
    letter = letter.upper()
    result = 0
    for ch in letter:
        result = result * 26 + (ord(ch) - ord('A') + 1)
    return result

def index_to_col_letter(idx: int) -> str:
    letters = ""
    while idx > 0:
        idx, rem = divmod(idx - 1, 26)
        letters = chr(65 + rem) + letters
    return letters

def get_header_and_row(ws, row: int):
    headers = ws.row_values(1)
    vals = ws.row_values(row)
    if len(vals) < len(headers):
        vals = vals + [""] * (len(headers) - len(vals))
    return headers, vals

def slice_dict_by_cols(headers, vals, start_col: str, end_col: str):
    s = col_letter_to_index(start_col) - 1
    e = col_letter_to_index(end_col) - 1
    out = {}
    for i in range(s, e + 1):
        if i < len(headers):
            out[headers[i]] = vals[i] if i < len(vals) else ""
    return out

# Lock/timing helpers
DEFAULT_TREATMENT_WINDOW_SECONDS = 300  # fallback if AA is empty

def now_utc_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def parse_utc_iso(s: str|None):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception:
        return None

def read_lock_state(ws, sheet_row: int):
    headers = ws.row_values(1)
    vals = ws.row_values(sheet_row)
    if len(vals) < len(headers):
        vals += [""] * (len(headers) - len(vals))
    def get_col(col_letter: str):
        idx = col_letter_to_index(col_letter) - 1
        return vals[idx] if idx < len(vals) else ""
    return {
        "start":    get_col("W"),
        "deadline": get_col("X"),
        "token":    get_col("Y"),
        "started":  get_col("Z"),
        "window":   get_col("AA"),
    }

def write_lock_state(ws, sheet_row: int, start_iso: str, deadline_iso: str, token: str):
    ws.spreadsheet.values_batch_update(body={
        "valueInputOption": "RAW",
        "data": [
            {"range": f"{ws.title}!W{sheet_row}", "values": [[start_iso]]},
            {"range": f"{ws.title}!X{sheet_row}", "values": [[deadline_iso]]},
            {"range": f"{ws.title}!Y{sheet_row}", "values": [[token]]},
            {"range": f"{ws.title}!Z{sheet_row}", "values": [["0"]]},
        ]
    })

def mark_treatment_started(ws, sheet_row: int):
    ws.update_acell(f"Z{sheet_row}", "1")

def resolve_window_seconds(raw_window: str) -> int:
    try:
        s = int(str(raw_window).strip())
        return max(1, s)
    except Exception:
        return DEFAULT_TREATMENT_WINDOW_SECONDS


st.set_page_config(page_title='Primary Triage', page_icon='⏱️', layout='centered')
st.markdown('### ⏱️ Primary Triage — Treatment Window Controller')

# URL params
qp = st.query_params if hasattr(st, 'query_params') else st.experimental_get_query_params()
row_str = (qp.get('row') if isinstance(qp.get('row'), str) else (qp.get('row',[None])[0])) or '1'
try:
    display_row = max(1, int(row_str))
except:
    display_row = 1
sheet_row = display_row + 1

ws = open_ws()

# Show basic patient context (A–K)
headers, vals = get_header_and_row(ws, sheet_row)
df_AK = pd.DataFrame([slice_dict_by_cols(headers, vals, 'A', 'K')])
st.subheader('Patient')
def _pairs_from_row(df_one_row: pd.DataFrame):
    s = df_one_row.iloc[0]
    return [(str(c), '' if pd.isna(s[c]) else str(s[c])) for c in df_one_row.columns]
for label, value in _pairs_from_row(df_AK):
    st.write(f'**{label}:** {value if value!="" else "-"}')

# Create/refresh window & token if needed
state = read_lock_state(ws, sheet_row)
deadline_dt = parse_utc_iso(state['deadline'])
now = datetime.now(timezone.utc)
window_sec = resolve_window_seconds(state.get('window',''))

need_new_window = (deadline_dt is None) or (deadline_dt <= now)
if need_new_window:
    start_iso = now_utc_iso()
    new_deadline_iso = (now + timedelta(seconds=window_sec)).strftime('%Y-%m-%dT%H:%M:%SZ')
    token = secrets.token_urlsafe(16)
    write_lock_state(ws, sheet_row, start_iso, new_deadline_iso, token)
    deadline_dt = parse_utc_iso(new_deadline_iso)

st.markdown('#### Treatment window')
st.caption(f'เวลาที่กำหนดสำหรับเคสนี้: {window_sec} วินาที')
# Fallback autorefresh for Streamlit Cloud older versions
if hasattr(st, 'autorefresh'):
    st.autorefresh(interval=1000, key=f'primary_cd_row_{sheet_row}')
else:
    st.markdown("<meta http-equiv='refresh' content='1'>", unsafe_allow_html=True)
now2 = datetime.now(timezone.utc)
remaining_sec = 0 if (deadline_dt is None) else max(0, int((deadline_dt - now2).total_seconds()))
mm, ss = divmod(remaining_sec, 60)
if remaining_sec > 0:
    st.info(f'Time left: **{mm:02d}:{ss:02d}**\n\nให้เข้าแอป Secondary ผ่าน **URL ของระบบคุณ** ภายในเวลาที่กำหนด')
else:
    st.error('หมดเวลาแล้ว (จะไม่สามารถทำการรักษาในหน้าถัดไปได้)')