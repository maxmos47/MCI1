import time
import json
import hmac
import hashlib
import base64
from datetime import datetime, timezone
from typing import Dict, Any

import streamlit as st
import pandas as pd
import requests
import streamlit.components.v1 as components

st.set_page_config(page_title="Patient Dashboard (Primary)", page_icon="🩺", layout="centered")

# =========================
# CONFIG
# =========================
# .streamlit/secrets.toml
# [gas]
# webapp_url = "https://script.google.com/macros/s/XXXXX/exec"
# token = "MY_SHARED_SECRET"
GAS_WEBAPP_URL = st.secrets.get("gas", {}).get("webapp_url", "")
TOKEN = st.secrets.get("gas", {}).get("token", "")

ALLOWED_L = ["Minor", "Delayed", "Immediate", "Decreased"]
SECONDARY_APP_BASE = "https://eprj-mci-secondarytriage.streamlit.app/"

# =========================
# Session flags
# =========================
if "locked" not in st.session_state:
    st.session_state["locked"] = False  # จะถูกตั้ง True ทันทีเมื่อกด Submit สำเร็จ
if "flash" not in st.session_state:
    st.session_state["flash"] = ""       # ใช้แสดงข้อความครั้งเดียวหลัง rerun

# =========================
# Helpers
# =========================
def get_query_params() -> Dict[str, str]:
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

def utc_now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())

def fmt_hms(secs: int) -> str:
    secs = max(0, int(secs))
    h, rem = divmod(secs, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def show_lock_overlay(message: str = "Triage เรียบร้อย"):
    st.markdown(
        f"""
        <style>
        .lock-overlay {{
          position: fixed; inset: 0;
          background: rgba(2,6,23,.65);
          z-index: 99999;
          display: flex; align-items: center; justify-content: center;
          backdrop-filter: blur(2px);
        }}
        .lock-card {{
          background: #fff; color:#111827;
          padding: 24px 28px; border-radius: 16px;
          box-shadow: 0 10px 30px rgba(0,0,0,.25);
          max-width: 90vw; text-align:center;
        }}
        .lock-card h2 {{ margin: 0 0 8px 0; font-size: 1.6rem; }}
        .lock-card p {{ margin: 0; font-size: 1rem; color:#4b5563; }}
        </style>
        <div class="lock-overlay">
          <div class="lock-card">
            <h2>✅ {message}</h2>
            <p>ฟอร์มถูกล็อกแล้ว ไม่สามารถแก้ไขได้</p>
          </div>
        </div>
        """,
        unsafe_allow_html=True
    )

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

def gas_start_timer(row: int) -> dict:
    payload = {"action": "start_timer", "row": str(row)}
    if TOKEN:
        payload["token"] = TOKEN
    r = requests.post(GAS_WEBAPP_URL, data=payload, timeout=20)
    r.raise_for_status()
    return r.json()

# =========================
# Styles
# =========================
st.markdown(
    """
<style>
.kv-card{border:1px solid #e5e7eb;padding:12px;border-radius:14px;margin-bottom:10px;
         box-shadow:0 1px 4px rgba(0,0,0,0.06);background:#fff;}
.kv-label{font-size:0.9rem;color:#6b7280;margin-bottom:2px;}
.kv-value{font-size:1.05rem;font-weight:600;word-break:break-word;}
.countdown{border:1px dashed #94a3b8;padding:12px;border-radius:12px;background:#f8fafc}
.badge{font-size:0.8rem;background:#e2e8f0;border-radius:999px;padding:4px 10px;color:#334155;margin-right:10px}
.digits{font-weight:800;letter-spacing:1px;line-height:1}
.digits.big{font-size:2.8rem}
@media (max-width: 640px){
  .kv-card{padding:12px;}
  .kv-value{font-size:1.06rem;}
  .digits.big{font-size:2.2rem}
}
</style>
""",
    unsafe_allow_html=True,
)

def _pairs_from_row(df_one_row: pd.DataFrame):
    s = df_one_row.iloc[0]
    items = []
    for col in df_one_row.columns:
        v = s[col]
        if pd.isna(v):
            v = ""
        items.append((str(col), str(v)))
    return items

def render_kv_grid(df_one_row: pd.DataFrame, title: str = "", cols: int = 2):
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
# Main
# =========================
st.markdown("### 🩺 Patient Information")

if not GAS_WEBAPP_URL:
    st.error(
        """Missing GAS web app URL. Add it to secrets as:

[gas]
webapp_url = "https://script.google.com/macros/s/XXX/exec"
token = "MY_SHARED_SECRET"
"""
    )
    st.stop()

qp = get_query_params()
row_str = qp.get("row", "1")
mode = qp.get("mode", "edit")  # "edit" or "view"

try:
    row = int(row_str)
    if row < 1:
        row = 1
except ValueError:
    row = 1

# ถ้าเปิดมาด้วย mode=view ให้ล็อกไว้ตั้งแต่เริ่ม
if mode == "view" and not st.session_state["locked"]:
    st.session_state["locked"] = True

# Fetch
try:
    data = gas_get_row(row=row)
except Exception as e:
    st.error(f"Failed to fetch row via GAS: {e}")
    st.stop()

if data.get("status") != "ok":
    st.error(f"GAS error: {data}")
    st.stop()

df_ak = pd.DataFrame([data.get("A_K", {})])
df_al = pd.DataFrame([data.get("A_L", {})])
current_L = data.get("current_L", "")

# ---------- Timer server-state ----------
origin_seconds = int(data.get("timer_seconds", 0) or 0)
t0_epoch = int(data.get("t0_epoch", 0) or 0)
end_epoch = int(data.get("end_epoch", 0) or 0)

# Start timer on server once if needed (idempotent)
if origin_seconds > 0 and end_epoch == 0:
    try:
        res = gas_start_timer(row=row)
        if res.get("status") == "ok":
            t0_epoch = int(res.get("t0_epoch", t0_epoch) or 0)
            end_epoch = int(res.get("end_epoch", end_epoch) or 0)
        else:
            st.warning(f"Cannot start timer on server: {res}")
    except Exception as e:
        st.warning(f"start_timer failed: {e}")

# Compute remaining from server end_epoch
now = utc_now_ts()
remaining = max(0, (end_epoch - now) if end_epoch else 0)

# ---------- Show patient + countdown ----------
render_kv_grid(df_ak, title="Patient", cols=2)

initial_digits = fmt_hms(remaining)
progress_value = max(0, (origin_seconds - remaining) if origin_seconds else 0)
progress_max = max(1, origin_seconds if origin_seconds > 0 else 1)

# ซ่อน countdown เมื่อถูกล็อกแล้ว
if not st.session_state["locked"]:
    components.html(
        f"""
        <div class="countdown">
          <span class="badge">⏳ คนไข้กำลังจะเสียชีวิตใน</span>
          <span id="digits" class="digits big">{initial_digits}</span>
          <div style="margin-top:10px">
            <progress id="pg" max="{progress_max}" value="{progress_value}" style="width:100%"></progress>
          </div>
        </div>
        <script>
          (function() {{
            let remaining = {remaining};
            const origin = {origin_seconds};
            const digits = document.getElementById('digits');
            const pg = document.getElementById('pg');
            function fmt(n) {{ return String(n).padStart(2, '0'); }}
            function render() {{
              let s = Math.max(0, Math.floor(remaining));
              let h = Math.floor(s/3600);
              let m = Math.floor((s%3600)/60);
              let ss = s%60;
              digits.textContent = `${{fmt(h)}}:${{fmt(m)}}:${{fmt(ss)}}`;
              if (origin > 0 && pg) {{
                pg.max = origin;
                pg.value = Math.min(origin, Math.max(0, origin - s));
              }}
            }}
            render();
            const intv = setInterval(() => {{
              remaining -= 1;
              if (remaining <= 0) {{ remaining = 0; render(); clearInterval(intv); return; }}
              render();
            }}, 1000);
          }})();
        </script>
        """,
        height=160,
    )

# ---------- Flash once if exists ----------
if st.session_state["flash"]:
    st.success(st.session_state["flash"])
    st.session_state["flash"] = ""  # แสดงครั้งเดียว

# ---------- Edit / View modes ----------
if st.session_state["locked"] or mode == "view":
    # โหมดล็อก: แสดงข้อมูล + ข้อความสำเร็จ + overlay
    render_kv_grid(df_al, title="Patient (A–L)", cols=2)
    st.success("Triage เรียบร้อย")
    show_lock_overlay("Triage เรียบร้อย")

else:
    # โหมดแก้ไข (ยังไม่ล็อก)
    idx = ALLOWED_L.index(current_L) if current_L in ALLOWED_L else 0
    with st.form("update_l_form", border=True):
        st.markdown("### Primary triage")
        new_L = st.selectbox("Select a value for triage", ALLOWED_L, index=idx)
        submitted = st.form_submit_button("Submit")
        if submitted:
            try:
                res = gas_update_L(row=row, value=new_L)
                if res.get("status") == "ok":
                    # ✅ ล็อกทันที + แจ้งความสำเร็จ
                    st.session_state["locked"] = True
                    st.session_state["flash"] = "Triage เรียบร้อย"
                    # ไปโหมด view เพื่อโหลดข้อมูล A–L ครบ และกัน user ที่ back/refresh
                    set_query_params(row=str(row), mode="view")
                    st.rerun()
                else:
                    st.error(f"Update failed: {res}")
            except Exception as e:
                st.error(f"Failed to update via GAS: {e}")

# ---------- Link to Secondary (no token needed) ----------
# st.link_button("➡️ Open Secondary triage", f"{SECONDARY_APP_BASE}?row={row}&lock=1", use_container_width=True)
