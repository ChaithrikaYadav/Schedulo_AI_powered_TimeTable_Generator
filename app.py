"""
Streamlit UI for AI Timetable Generator
Save as: timetable_app.py
Place it in same folder as timetable_generator.py (which must expose build_timetable(department) function)
"""

import streamlit as st
import pandas as pd
import io
import base64
from pathlib import Path
from datetime import datetime

# Import your timetable generator (must be in same folder)
# It should expose build_timetable(department="...") returning dict {section_id: DataFrame}
try:
    from timetable_generator import build_timetable, DEPARTMENT_NAME
except Exception as e:
    # fallback - helpful message shown in UI
    build_timetable = None
    DEPARTMENT_NAME = "School of Computer Science & Engineering"
    import traceback
    build_timetable_error = traceback.format_exc()

# ---------------------------
# PAGE CONFIG
# ---------------------------
st.set_page_config(
    page_title="AI Timetable Generator",
    page_icon="📘",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------
# STYLES (animated background + card styles)
# ---------------------------
def local_css():
    bg_path = Path("bg.jpg")
    if bg_path.exists():
        # embed image as base64 to avoid external requests
        with open(bg_path, "rb") as f:
            data = f.read()
        b64 = base64.b64encode(data).decode()
        bg_style = f"background-image: url('data:image/jpg;base64,{b64}');"
    else:
        # fallback gradient
        bg_style = "background: linear-gradient(135deg, #0f172a 0%, #082032 50%, #0b3b53 100%);"

    css = f"""
    <style>
    :root {{
      --accent: #00c2ff;
      --card-bg: rgba(255,255,255,0.03);
      --glass: rgba(255,255,255,0.04);
      --muted: rgba(255,255,255,0.65);
    }}
    /* full page background */
    .stApp {{
      background-attachment: fixed;
      background-size: cover;
      {bg_style}
      color-scheme: dark;
      font-family: "Inter", system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial;
    }}

    /* top header */
    .header {{
      display:flex; align-items:center; gap:14px; padding:18px 10px;
      background: linear-gradient(90deg, rgba(255,255,255,0.03), rgba(255,255,255,0.01));
      border-radius: 12px;
      margin-bottom: 18px;
      box-shadow: 0 6px 20px rgba(2,6,23,0.6);
    }}

    .brand-title {{
      font-size:20px; font-weight:700; color: white;
      letter-spacing:0.2px;
    }}

    .brand-sub {{
      font-size:12px; color:var(--muted);
    }}

    /* animated icon */
    .logo {{
      width:56px;height:56px;border-radius:12px;
      display:flex;align-items:center;justify-content:center;
      background: linear-gradient(180deg,#062a3a, #013a56);
      box-shadow: 0 6px 18px rgba(0,0,0,0.6);
      transform-origin:center;
      animation: float 6s ease-in-out infinite;
    }}

    @keyframes float {{
      0% {{ transform: translateY(0px) rotate(0deg); }}
      50% {{ transform: translateY(-6px) rotate(4deg); }}
      100% {{ transform: translateY(0px) rotate(0deg); }}
    }}

    /* control card */
    .control-card {{
      background: var(--card-bg);
      border-radius:12px;
      padding:12px;
      box-shadow: 0 6px 20px rgba(2,6,23,0.5);
      color: white;
    }}

    /* timetable card */
    .tt-card {{
      background: linear-gradient(180deg, rgba(255,255,255,0.02), rgba(255,255,255,0.01));
      border-radius:10px;
      padding:10px;
      color: white;
      box-shadow: 0 8px 30px rgba(2,6,23,0.6);
    }}

    /* cell style inside html table */
    table.tt-table {{
      border-collapse: collapse;
      width:100%;
      table-layout: fixed;
      font-size: 13px;
    }}
    table.tt-table th {{
      background: rgba(255,255,255,0.04);
      padding:10px;
      text-align:center;
      font-weight:700;
    }}
    table.tt-table td {{
      padding:8px;
      vertical-align: top;
      border: 1px solid rgba(255,255,255,0.03);
      min-height:60px;
      max-width:180px;
      overflow:hidden;
      word-break:break-word;
    }}

    /* nice accents for lab/classroom */
    .lab {{ background: linear-gradient(90deg,#1b2b6b, #0f4d6f); color:white; border-left:4px solid #ffd166; }}
    .class {{ background: linear-gradient(90deg,#1b3b2f, #0b6450); color:white; border-left:4px solid #06d6a0; }}
    .free {{ color: rgba(255,255,255,0.7); font-style: italic; }}
    .lunch {{ text-align:center; font-weight:700; color: #ffb703; }}

    /* download / small btn */
    .small-btn {{
      background: linear-gradient(90deg,#06b6d4,#00c2ff); padding:8px 12px; border-radius:8px; color: #002; font-weight:700;
    }}

    /* responsive tweaks */
    @media (max-width: 900px) {{
      .brand-title {{ font-size:16px; }}
      table.tt-table th, table.tt-table td {{ font-size:11px; padding:6px; }}
    }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

# inject css
local_css()

# ---------------------------
# UI header
# ---------------------------
with st.container():
    cols = st.columns([0.12, 0.88])
    with cols[0]:
        # inline SVG icon (lightweight)
        st.markdown(
            """
            <div class="logo">
              <svg width="34" height="34" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <rect width="24" height="24" rx="5" fill="url(#g)"/>
                <defs>
                  <linearGradient id="g" x1="0" x2="1"><stop offset="0" stop-color="#00c2ff"/><stop offset="1" stop-color="#0066ff"/></linearGradient>
                </defs>
                <path d="M7 8h10v2H7zM7 11h10v2H7zM7 14h6v2H7z" fill="white" opacity="0.95"/>
              </svg>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with cols[1]:
        st.markdown('<div class="header"><div><div class="brand-title">AI Timetable Generator</div><div class="brand-sub">Smart, fast timetables — visualized</div></div></div>', unsafe_allow_html=True)

# ---------------------------
# Sidebar: controls
# ---------------------------
st.sidebar.title("Controls")
st.sidebar.write("Generate and view timetables")

# Dept selection (from timetable_generator if available)
dept = st.sidebar.text_input("Department", value=DEPARTMENT_NAME)

# Regenerate / cache control
regen = st.sidebar.button("Regenerate Timetables (force)")

# Section selector (populated after generation)
selected_section = None

# info / error if build_timetable not importable
if build_timetable is None:
    st.sidebar.error("Could not import timetable_generator.build_timetable()")
    st.sidebar.markdown("Traceback:")
    st.sidebar.text(build_timetable_error)
    st.stop()

# ---------------------------
# Generate timetables (cached)
# ---------------------------
@st.cache_data(ttl=300, show_spinner=False)
def cached_build(department, force=False):
    # force flag inclusion to ensure rerun if needed (button will call without caching)
    return build_timetable(department)

if regen:
    st.sidebar.info("Regenerating (forced) — this may take a moment...")
    tt = build_timetable(dept)
else:
    tt = cached_build(dept)

# Sections list
sections = sorted(list(tt.keys()))
if not sections:
    st.warning("No timetables generated. Make sure timetable_generator.build_timetable returns a non-empty dict.")
    st.stop()

selected_section = st.sidebar.selectbox("Select Section", sections)

# ---------------------------
# Top controls row
# ---------------------------
c1, c2, c3, c4 = st.columns([2.2, 0.8, 0.8, 1.5])

with c1:
    st.markdown("### Preview Timetable")
    st.markdown(f"**Department:** {dept}  •  **Section:** {selected_section}")

with c2:
    if st.button("Download CSV"):
        buffer = io.StringIO()
        tt[selected_section].to_csv(buffer)
        b64 = base64.b64encode(buffer.getvalue().encode()).decode()
        href = f'<a href="data:file/csv;base64,{b64}" download="Timetable_{selected_section}.csv" class="small-btn">Download CSV</a>'
        st.markdown(href, unsafe_allow_html=True)

with c3:
    if st.button("Download Excel"):
        out = io.BytesIO()
        with pd.ExcelWriter(out, engine="openpyxl") as writer:
            for s, df in tt.items():
                # sanitize sheet name
                sheet = str(s)[:31]
                df.to_excel(writer, sheet_name=sheet)
            writer.save()
        b64 = base64.b64encode(out.getvalue()).decode()
        href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="Timetables.xlsx" class="small-btn">Download XLSX</a>'
        st.markdown(href, unsafe_allow_html=True)

with c4:
    if st.button("Regenerate (fresh)"):
        tt = build_timetable(DEPARTMENT_NAME)
        st.rerun()


# ---------------------------
# Render timetable as HTML table (styled)
# ---------------------------
def render_timetable_html(df: pd.DataFrame):
    # produce HTML table; classify cells by keywords
    html = '<div class="tt-card"><table class="tt-table"><thead><tr><th>Day / Period</th>'
    for col in df.columns:
        html += f"<th>{col}</th>"
    html += "</tr></thead><tbody>"

    for day in df.index:
        html += f"<tr><th style='text-align:left'>{day}</th>"
        for col in df.columns:
            val = df.loc[day, col]
            cls = ""
            display = val

            if not val or str(val).strip() == "":
                cls = "free"
                display = "<span class='free'>Free Period</span>"
            elif "Lunch" in str(val):
                cls = "lunch"
                display = "<span class='lunch'>Lunch</span>"
            elif "Lab" in str(val):
                cls = "lab"
                safe_val = str(val).replace("\n", "<br/>")
                display = f"<div class='lab'>{safe_val}</div>"
            else:
                cls = "class"
                safe_val = str(val).replace("\n", "<br/>")
                display = f"<div class='class'>{safe_val}</div>"

            html += f"<td class='{cls}'>{display}</td>"
        html += "</tr>"
    html += "</tbody></table></div>"
    return html

# display
st.markdown(render_timetable_html(tt[selected_section]), unsafe_allow_html=True)

# ---------------------------
# Footer / Tips
# ---------------------------
with st.container():
    st.markdown(
        """
        <div style="margin-top:14px; color: rgba(255,255,255,0.7)">
          <b>Tips:</b> Use 'Regenerate' to get a fresh allocation. Click downloads to export timetables. 
          If you change datasets, click 'Regenerate (fresh)'.
        </div>
        """, unsafe_allow_html=True
    )
