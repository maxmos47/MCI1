import streamlit as st
import pandas as pd
import requests
import time
from datetime import timedelta

st.set_page_config(page_title="Patient Dashboard", page_icon="🩺", layout="centered")

# =========================
# CONFIG
# =========================
# ใส่ค่าใน .streamlit/secrets.toml ตอน deploy บน Streamlit Cloud:
# [gas]
# webapp_url = "https://script.google.com/macros/s/AKfycb.../exec"
# token = "MY_SHARED_SECRET"     # (optional, หากฝั่ง GAS ตั้งตรวจ token)
GAS_WEBAPP_URL = st.secrets.get("gas", {}).get("webapp_url", "")
TOKEN = st.secrets.get("gas", {}).get("token", "")  # optional shared secret

# ชอยส์ของคอลัมน์ L (Primary triage)
ALLOWED_L = ["Minor", "Delayed", "Immediate", "Decreased"]

# ชื่อหัวคอลัมน์ Q ในชีต (ต้องให้ฝั่ง GAS ส่งหัวคอลัมน์นี้กลับมา)
TIMER_COLUMN_NAME = "Timer"   # = คอลัมน์ Q


# =========================
# Helpers for query params
# =========================
def get_query_params():
    """รองรับทั้ง Streamlit เวอร์ชันใหม่ (st.query_params) และเก่า (experimental_get_query_params)."""
    try:
        q = st.query_params
        return {k: v for k, v in q.items()}
    except Exception:
        return {k: v[0] for k, v in st.experimental_get_query_params().items()}

def set_query_params(**kwargs):
    try:
        st.query_params.clear()
        st.query_params.update(kwargs)
    except Exception:
        st.experimental_set_query_params(**kwargs)


# =========================
# GAS calls
# =========================
def gas_get_row(row: int) -> dict:
    params = {"action": "get", "row": str(row)}
    if TOKEN:
        params["token"] = TOKEN
    r = requests.get(GAS_WEBAPP_URL, params=params, timeout=20)
    r.raise_for_status()
    return r.json()

def gas_update_L(row: int, value: str) -> dict:
    payload = {"action": "update", "row": str(row), "value": value}
    if TOKEN:
        payload["token"] = TOKEN
    r = requests.post(GAS_WEBAPP_URL, data=payload, timeout=20)
    r.raise_for_status()
    return r.json()


# =========================
# Card UI (mobile-friendly) — template style
# =========================
st.markdown("""
<style>
.kv-card{border:1px solid #e5e7eb;padding:12px;border-radius:14px;margin-bottom:10px;box-shadow:0 1px 4px rgba(0,0,0,0.06);background:#fff;}
.kv-label{font-size:0.9rem;color:#6b7280;margin-bottom:2px;}
.kv-value{font-size:1.05rem;font-weight:600;word-break:break-word;}
@media (max-width: 640px){
  .kv-card{padding:12px;}
  .kv-value{font-size:1.06rem;}
}
</style>
""", unsafe_allow_html=True)

def _pairs_from_row(df_one_row: pd.DataFrame):
    s = df_one_row.iloc[0]
    pairs = []
    for col in df_one_row.columns:
        val = s[col]
        if pd.isna(val):
            val = ""
        pairs.append((str(col), str(val)))
    return pairs

def render_kv_grid(df_one_row: pd.DataFrame, title: str = "", cols: int = 3):
    # เทมเพลตเดิม: card-grid 3 คอลัมน์ บนมือถือยังอ่านง่าย (Streamlit จะ wrap เอง)
    if title:
        st.subheader(title)
    items = _pairs_from_row(df_one_row)
    n = len(items)
    for i in range(0, n, cols):
        row_items = items[i:i+cols]
        col_objs = st.columns(len(row_items))
        for c, (label, value) in zip(col_objs, row_items):
            with c:
                st.markdown(
                    f"""
                    <div class="kv-card">
                      <div class="kv-label">{label}</div>
                      <div class="kv-value">{value if value!='' else '-'}</div>
                    </div>
                    """,
                    unsafe_allow_html=True
                )


# =========================
# Timer helpers
# =========================
def _parse_timer_to_seconds(v) -> int:
    """
    แปลงค่าที่อ่านมาจากคอลัมน์ Q ให้เป็นวินาที.
    รองรับ: 'HH:MM:SS', 'MM:SS', '10m', '10 min', '45s', 300 (วินาที),
           Excel time เช่น 0.0104 (ส่วนของ 1 วัน)
    """
    if v is None:
        return 0
    if isinstance(v, (int, float)):
        # ถ้าค่าน้อยกว่า 1 และมากกว่า 0 => อาจเป็น excel time (ส่วนของ 1 วัน)
        if isinstance(v, float) and 0 < v < 1:
            return int(round(v * 86400))
        return max(0, int(round(v)))

    s = str(v).strip().lower()

    # หน่วยแบบย่อ
    if s.endswith("s"):
        try:
            return max(0, int(float(s[:-1])))
        except:
            pass
    if s.endswith("sec"):
        try:
            return max(0, int(float(s[:-3])))
        except:
            pass
    if s.endswith("m") or "min" in s:
        num = s.replace("min", "").replace(" ", "").replace("m", "")
        try:
            return max(0, int(float(num) * 60))
        except:
            pass
    if s.endswith("h") or "hr" in s or "hour" in s or "hours" in s:
        num = (s.replace("hours", "")
                 .replace("hour", "")
                 .replace("hr", "")
                 .replace(" ", "")
                 .replace("h", ""))
        try:
            return max(0, int(float(num) * 3600))
        except:
            pass

    # รูปแบบมี ":" -> HH:MM:SS หรือ MM:SS
    if ":" in s:
        parts = [p for p in s.split(":") if p != ""]
        try:
            parts = [int(float(p)) for p in parts]
            if len(parts) == 3:  # HH:MM:SS
                h, m, sec = parts
                return max(0, h*3600 + m*60 + sec)
            if len(parts) == 2:  # MM:SS
                m, sec = parts
                return max(0, m*60 + sec)
        except:
            pass

    # อย่างสุดท้าย: ตีความเป็นวินาที
    try:
        return max(0, int(round(float(s))))
    except:
        return 0

def _format_hhmmss(seconds: int) -> str:
    return str(timedelta(seconds=max(0, int(seconds))))


# =========================
# Main UI (template-style)
# =========================
st.markdown("### 🩺 Patient Information")

if not GAS_WEBAPP_URL:
    st.error(
    "Missing GAS web app URL. Add it to secrets as:\n\n"
    "[gas]\nwebapp_url = \"https://script.google.com/macros/s/XXX/exec\""
)
    st.stop()

qp = get_query_params()
row_str = qp.get("row", "1")
mode = qp.get("mode", "edit")  # "edit" or "view"
lock = qp.get("lock", "0")     # รองรับพารามิเตอร์เทมเพลตเดิม ?lock=1 เพื่อเข้าสู่โหมดดู (ล็อก)

if lock == "1":
    mode = "view"

try:
    row = int(row_str)
    if row < 1:
        row = 1
except ValueError:
    row = 1

# เรียก GAS
try:
    data = gas_get_row(row=row)
except Exception as e:
    st.error(f"Failed to fetch row via GAS: {e}")
    st.stop()

if data.get("status") != "ok":
    st.error(f"GAS error: {data}")
    st.stop()

# สร้าง DataFrame จากผลลัพธ์ GAS
df_ak = pd.DataFrame([data.get("A_K", {})])   # A–K (ข้อมูลก่อนฟอร์ม)
df_al = pd.DataFrame([data.get("A_L", {})])   # A–L (ข้อมูลหลังอัปเดต)
max_row = data.get("max_rows", 1)
current_L = data.get("current_L", "")

# ----- อ่าน Timer (Column Q) -----
timer_raw = data.get("timer") or data.get("Timer")
if timer_raw is None:
    try:
        if TIMER_COLUMN_NAME in df_al.columns:
            timer_raw = df_al.iloc[0][TIMER_COLUMN_NAME]
    except Exception:
        pass
if timer_raw is None:
    q_dict = data.get("Q") or data.get("M_Q") or {}
    if isinstance(q_dict, dict):
        timer_raw = q_dict.get("value") or q_dict.get(TIMER_COLUMN_NAME)

timer_seconds = _parse_timer_to_seconds(timer_raw)

# โครงหน้าเป็นซ้าย-ขวา (ขวาแคบไว้สำหรับ Timer) — เทมเพลตเดิม
left_col, right_col = st.columns([3, 1])

with left_col:
    # --------- UI based on mode ---------
    if mode == "view":
        # โหมดหลัง Submit / lock=1 : แสดงข้อมูล A–L (หรือรวมทุกคอลัมน์ตาม GAS) แบบ card-grid 3 คอลัมน์
        render_kv_grid(df_al, title="Patient", cols=3)
        st.success("Triage เรียบร้อย")
        if st.button("Edit this row again"):
            # กลับสู่โหมดแก้ไข (ปลดล็อก)
            set_query_params(row=str(row), mode="edit", lock="0")
            st.rerun()
    else:
        # โหมดแก้ไข: โชว์ A–K ก่อน แล้วตามด้วยฟอร์มแก้ L
        render_kv_grid(df_ak, title="Patient", cols=3)

        idx = ALLOWED_L.index(current_L) if current_L in ALLOWED_L else 0
        with st.form("update_l_form", border=True):
            st.markdown("### Primary triage")
            new_L = st.selectbox(
                "Select a value for triage",
                ALLOWED_L,
                index=idx,
                help="Allowed: Minor, Delayed, Immediate, Decreased"
            )
            submitted = st.form_submit_button("Submit")
            if submitted:
                try:
                    res = gas_update_L(row=row, value=new_L)
                    if res.get("status") == "ok":
                        # หลัง Submit: เปิดโหมด lock=1 (เหมือนเทมเพลตเดิม ?lock=1)
                        set_query_params(row=str(row), mode="view", lock="1")
                        st.rerun()
                    else:
                        st.error(f"Update failed: {res}")
                except Exception as e:
                    st.error(f"Failed to update via GAS: {e}")

with right_col:
    # แถบ Timer ทางขวา (อ่านจากคอลัมน์ Q)
    st.markdown("#### ⏳ Timer")
    if timer_seconds <= 0:
        st.info("No timer (Q) or invalid value.")
    else:
        # ตั้ง deadline ไว้ใน session_state เพื่อให้นับต่อเนื่องแม้แอปรันซ้ำ
        key_id = f"deadline_row{row}_sec{timer_seconds}"
        now = time.time()
        if "countdown_deadline" not in st.session_state or st.session_state.get("countdown_key") != key_id:
            st.session_state["countdown_key"] = key_id
            st.session_state["countdown_deadline"] = now + timer_seconds

        deadline = st.session_state["countdown_deadline"]
        placeholder = st.empty()

        # เพื่อไม่บล็อกแอปนานเกินไป จำกัดการวิ่งสดสูงสุด 1 ชั่วโมงต่อครั้ง
        max_live_secs = min(60*60, timer_seconds)
        for _ in range(max_live_secs + 1):
            remaining = int(round(deadline - time.time()))
            if remaining <= 0:
                placeholder.error("00:00:00")
                break
            # ใช้ success เพื่อกรอบเขียวสไตล์เทมเพลตเดิม
            placeholder.success(_format_hhmmss(remaining))
            time.sleep(1)
