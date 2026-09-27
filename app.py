"""
TISL Backup Viewer — a small desktop app for reading .wnkjba backup files.

Run it with:   streamlit run app.py

It opens an encrypted TISL backup (.wnkjba), asks for the passphrase, and lets
you browse the data table by table and export any table to CSV. Everything
happens locally on this machine — nothing is uploaded anywhere, and the app
never writes to a database.
"""

from __future__ import annotations

import io
import zipfile

import pandas as pd
import streamlit as st

import wnkjba

PRIMARY = "#7c3aed"  # brand purple

st.set_page_config(
    page_title="TISL Backup Viewer",
    page_icon="🗄️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── styling ──────────────────────────────────────────────────────────────
st.markdown(
    f"""
    <style>
      .stApp {{ background: #faf9fc; }}
      .block-container {{ padding-top: 2rem; }}
      h1, h2, h3 {{ color: #1f2937; }}
      .wnkj-badge {{
        display:inline-block; padding:2px 10px; border-radius:999px;
        background: {PRIMARY}1a; color:{PRIMARY}; font-weight:700; font-size:.75rem;
      }}
      .wnkj-metric {{
        background:white; border:1px solid {PRIMARY}1a; border-radius:12px;
        padding:14px 16px; box-shadow:0 2px 10px {PRIMARY}0f;
      }}
      .wnkj-metric .v {{ font-size:1.4rem; font-weight:800; color:#111827; }}
      .wnkj-metric .l {{ font-size:.72rem; color:#6b7280; text-transform:uppercase; letter-spacing:.04em; }}
    </style>
    """,
    unsafe_allow_html=True,
)


def _reset():
    for k in ("backup", "opened_name"):
        st.session_state.pop(k, None)


# ── header ───────────────────────────────────────────────────────────────
st.markdown(
    f"<h1 style='margin-bottom:0'>🗄️ TISL Backup Viewer</h1>"
    f"<p style='color:#6b7280;margin-top:4px'>Open and read an encrypted "
    f"<code>.wnkjba</code> backup. <span class='wnkj-badge'>offline &amp; read-only</span></p>",
    unsafe_allow_html=True,
)

# ── step 1: pick a file ──────────────────────────────────────────────────
uploaded = st.file_uploader(
    "Choose a backup file",
    type=["wnkjba"],
    on_change=_reset,
    help="Select a .wnkjba file produced by the TISL platform's backup engine.",
)

if uploaded is None:
    st.info(
        "Select a `.wnkjba` file to begin. You'll need the **backup passphrase** "
        "that was set on the server when the backup was made — without it the file "
        "cannot be read."
    )
    st.stop()

data = uploaded.getvalue()

# Show the (unencrypted) header so the user knows the file is well-formed.
try:
    header = wnkjba.peek_header(data)
except wnkjba.WnkjbaError as e:
    st.error(str(e))
    st.stop()

st.success(
    f"**{uploaded.name}** looks like a valid backup "
    f"({len(data)/1024/1024:.2f} MB · {header.get('cipher','?')} · {header.get('kdf','?')}). "
    "Enter the passphrase to open it."
)

# ── step 2: passphrase + open ────────────────────────────────────────────
if "backup" not in st.session_state or st.session_state.get("opened_name") != uploaded.name:
    with st.form("open_form"):
        passphrase = st.text_input("Backup passphrase", type="password")
        submit = st.form_submit_button("Open backup", type="primary")
    if submit:
        if not passphrase:
            st.warning("Enter the passphrase.")
            st.stop()
        with st.spinner("Decrypting…"):
            try:
                bk = wnkjba.open_backup(data, passphrase)
            except wnkjba.WrongPassphrase as e:
                st.error(str(e))
                st.stop()
            except wnkjba.WnkjbaError as e:
                st.error(str(e))
                st.stop()
        st.session_state["backup"] = bk
        st.session_state["opened_name"] = uploaded.name
        st.rerun()
    st.stop()

bk: wnkjba.Backup = st.session_state["backup"]

# ── step 3: overview ─────────────────────────────────────────────────────
st.divider()
cols = st.columns(4)
overview = [
    ("Business", bk.business or "—"),
    ("Modules", str(len(bk.modules))),
    ("Tables", str(len(bk.tables))),
    ("Rows", f"{bk.total_rows:,}"),
]
for c, (label, value) in zip(cols, overview):
    c.markdown(
        f"<div class='wnkj-metric'><div class='v'>{value}</div>"
        f"<div class='l'>{label}</div></div>",
        unsafe_allow_html=True,
    )

meta = []
if bk.created_at:
    meta.append(f"**Created:** {bk.created_at}")
if bk.client_uuid:
    meta.append(f"**Client UUID:** `{bk.client_uuid}`")
if meta:
    st.caption("  ·  ".join(meta))

# ── step 4: browse ───────────────────────────────────────────────────────
st.sidebar.header("Browse")
if st.sidebar.button("← Open a different backup"):
    _reset()
    st.rerun()

module = st.sidebar.selectbox(
    "Module",
    options=bk.modules,
    format_func=lambda m: f"{m}  ({len(bk.tables_for(m))} tables)",
)
tables = bk.tables_for(module)
table = st.sidebar.selectbox(
    "Table",
    options=[t.name for t in tables],
    format_func=lambda n: f"{n}  ({bk.get(module, n).row_count:,} rows)",
)

st.sidebar.divider()

# whole-backup export (all tables → one CSV zip)
def _all_csv_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for t in bk.tables:
            if t.rows:
                df = pd.DataFrame(t.rows)
                z.writestr(f"{t.module}/{t.name}.csv", df.to_csv(index=False))
    return buf.getvalue()


st.sidebar.download_button(
    "⬇ Export everything (CSV .zip)",
    data=_all_csv_zip(),
    file_name=f"{(bk.business or 'backup').replace(' ', '_')}_tables.zip",
    mime="application/zip",
    use_container_width=True,
)

# ── selected table ───────────────────────────────────────────────────────
current = bk.get(module, table)
st.subheader(f"{module} · {table}")
st.caption(f"{current.row_count:,} rows · {len(current.columns)} columns")

if not current.rows:
    st.info("This table is empty.")
else:
    df = pd.DataFrame(current.rows)
    # keep original column order from the JSONL
    df = df.reindex(columns=current.columns)

    q = st.text_input("Filter rows (matches any cell, case-insensitive)", "")
    view = df
    if q:
        mask = df.apply(
            lambda row: row.astype(str).str.contains(q, case=False, na=False).any(),
            axis=1,
        )
        view = df[mask]
        st.caption(f"{len(view):,} of {len(df):,} rows match.")

    st.dataframe(view, use_container_width=True, height=520)

    st.download_button(
        f"⬇ Download {table}.csv",
        data=view.to_csv(index=False),
        file_name=f"{module}_{table}.csv",
        mime="text/csv",
    )
