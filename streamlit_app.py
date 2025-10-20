import streamlit as st
import pandas as pd

import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta, timezone
import hmac, hashlib, json, base64

SPREADSHEET_ID = (st.secrets.get("gsheets", {}).get("spreadsheet_id", "") or "").strip()
WORKSHEET_NAME = st.secrets.get("gsheets", {}).get("worksheet_name", "Secondary")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets.readonly",  # read-only for safety
    "https://www.googleapis.com/auth/drive.readonly",
]

def get_gs_client():
    if "gcp_service_account" not in st.secrets:
        st.error("Missing [gcp_service_account] in secrets")
        st.stop()
    info = dict(st.secrets["gcp_service_account"])
    pk = info.get("private_key", "")
    if pk and ("\\n" in pk) and ("\n" not in pk):
        info["private_key"] = pk.replace("\\n", "\n")
    try:
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    except Exception as e:
        st.error(f"Failed to build credentials: {e}")
        st.stop()
    return gspread.authorize(creds)

def open_ws():
    if not SPREADSHEET_ID:
        st.error("Missing [gsheets].spreadsheet_id in secrets")
        st.stop()
    gc = get_gs_client()
    try:
        sh = gc.open_by_key(SPREADSHEET_ID)
        ws = sh.worksheet(WORKSHEET_NAME)
    except Exception as e:
        st.error(f"Open worksheet failed: {e}")
        st.stop()
    return ws

def col_letter_to_index(letter: str) -> int:
    letter = letter.upper()
    result = 0
    for ch in letter:
        result = result * 26 + (ord(ch) - ord('A') + 1)
    return result

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

# ------- Stateless signed token (HMAC) -------
def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

def b64url_json(obj) -> str:
    return b64url(json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))

def sign_token(payload: dict, secret: str) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    h = b64url_json(header)
    p = b64url_json(payload)
    signing_input = f"{h}.{p}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{h}.{p}.{b64url(sig)}"

def verify_token(token: str, secret: str) -> dict | None:
    try:
        h, p, s = token.split(".")
        signing_input = f"{h}.{p}".encode("utf-8")
        expected = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
        got = base64.urlsafe_b64decode(s + "==")
        if not hmac.compare_digest(expected, got):
            return None
        payload = json.loads(base64.urlsafe_b64decode(p + "==").decode("utf-8"))
        return payload
    except Exception:
        return None


st.set_page_config(page_title='Primary Triage', page_icon='⏱️', layout='centered')
st.markdown('### ⏱️ Primary Triage — Stateless Timer (no writes)')

# URL params
qp = st.query_params if hasattr(st, 'query_params') else st.experimental_get_query_params()
row_str = (qp.get('row') if isinstance(qp.get('row'), str) else (qp.get('row',[None])[0])) or '1'
try:
    display_row = max(1, int(row_str))
except:
    display_row = 1
sheet_row = display_row + 1

ws = open_ws()
headers, vals = get_header_and_row(ws, sheet_row)
df_AK = pd.DataFrame([slice_dict_by_cols(headers, vals, 'A', 'K')])
st.subheader('Patient')
s = df_AK.iloc[0]
for c in df_AK.columns:
    st.write(f'**{c}:** {"-" if pd.isna(s[c]) or s[c]=="" else s[c]}')

# Read per-row window seconds from AA (after Z)
AA_idx = col_letter_to_index('AA') - 1
raw_window = vals[AA_idx] if AA_idx < len(vals) else ''
try:
    window_sec = max(1, int(str(raw_window).strip())) if str(raw_window).strip() else 300
except:
    window_sec = 300

# Build a signed token WITHOUT writing to sheet
secret = (st.secrets.get('auth', {}).get('hmac_secret', '') or '').strip()
if not secret:
    st.error('Missing [auth].hmac_secret in secrets')
    st.stop()
import time
now_ts = int(time.time())
exp_ts = now_ts + window_sec
payload = {'row': display_row, 'sheet_row': sheet_row, 'exp': exp_ts}
token = sign_token(payload, secret)

st.markdown('#### Treatment window (client-side countdown)')
st.caption(f'เวลาที่กำหนดสำหรับเคสนี้: {window_sec} วินาที')

# Pure JS countdown (no Streamlit reruns)
st.markdown("""
<div id='timer' style='font-size:1.4rem;font-weight:700'></div>
<script>
  const exp = {exp};
  const el = document.getElementById('timer');
  function tick(){{
    const now = Math.floor(Date.now()/1000);
    let remain = Math.max(0, exp - now);
    const mm = String(Math.floor(remain/60)).padStart(2,'0');
    const ss = String(remain%60).padStart(2,'0');
    el.textContent = `Time left: ${mm}:${ss}`;
  }}
  tick();
  setInterval(tick, 1000);
</script>
""".format(exp=exp_ts), unsafe_allow_html=True)

st.info('ให้เข้าหน้า Secondary ผ่าน URL ของระบบคุณเองภายในเวลาที่กำหนด')
st.markdown('ตัวอย่างโครง URL (คัดลอกไปใช้ในระบบคุณ):')
secondary_base = st.secrets.get('apps', {}).get('secondary_base', 'https://eprj-mci-secondarytriage.streamlit.app/')
st.code(f"{secondary_base}?row={display_row}&mode=edit1&token={token}")
