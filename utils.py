"""Shared theme, CSS, and utilities for SmartDoc + Video Studio."""
import streamlit as st
import os, tempfile

SHARED_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@500;700&display=swap');

html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.stApp { background: #f5f7fa; color: #1a1d23; }

.hero-title {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 2.2rem; font-weight: 700;
    background: linear-gradient(135deg, #2563eb 0%, #7c3aed 60%, #db2777 100%);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    margin-bottom: 0.15rem;
}
.hero-sub { color: #64748b; font-size: 0.95rem; margin-bottom: 1.2rem; }

/* Sidebar nav */
[data-testid="stSidebarNav"] { padding-top: 1rem; }
[data-testid="stSidebarNav"] a {
    font-weight: 500; font-size: 0.95rem; border-radius: 8px; padding: 0.4rem 0.8rem;
}
[data-testid="stSidebarNav"] a:hover { background: #eff6ff; }

/* Tabs */
.stTabs [data-baseweb="tab-list"] {
    background: #ffffff; border-radius: 12px; padding: 4px; gap: 4px;
    border: 1px solid #e2e8f0; box-shadow: 0 1px 4px rgba(0,0,0,0.06);
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px; color: #64748b; font-weight: 500; font-size: 0.88rem; padding: 0.45rem 1rem;
}
.stTabs [aria-selected="true"] { background: #eff6ff !important; color: #2563eb !important; }

/* Buttons */
.stButton > button {
    background: linear-gradient(135deg, #2563eb, #7c3aed);
    color: white !important; border: none; border-radius: 8px;
    font-weight: 600; padding: 0.5rem 1.3rem; font-size: 0.9rem;
}
.stButton > button:hover { opacity: 0.88; }

/* Download button */
.stDownloadButton > button {
    background: #eff6ff; color: #2563eb !important; border: 1px solid #bfdbfe;
    border-radius: 8px; font-weight: 600;
}
.stDownloadButton > button:hover { background: #dbeafe; }

/* File uploader */
[data-testid="stFileUploader"] {
    background: #ffffff; border: 1.5px dashed #cbd5e1; border-radius: 12px; padding: 1rem;
}

.card-title {
    font-family: 'Space Grotesk', sans-serif; font-size: 1.05rem;
    font-weight: 700; color: #1e293b; margin-bottom: 0.6rem;
}
.spec-card {
    background: #ffffff; border: 1px solid #e2e8f0; border-radius: 10px;
    padding: 0.75rem 1rem; margin-bottom: 0.45rem;
}
.spec-label { font-size: 0.72rem; color: #94a3b8; font-weight: 500; text-transform: uppercase; letter-spacing: 0.05em; }
.spec-value { font-size: 0.95rem; color: #1e293b; font-weight: 600; }

.chip {
    display: inline-block; background: #eff6ff; border-radius: 20px;
    padding: 2px 10px; font-size: 0.78rem; color: #2563eb;
    margin-right: 6px; border: 1px solid #bfdbfe; font-weight: 500;
}
.hist-badge {
    display: block; background: #ffffff; border: 1px solid #e2e8f0;
    border-radius: 8px; padding: 0.4rem 0.85rem; font-size: 0.85rem;
    color: #475569; margin-bottom: 0.4rem;
}
.divider { border-top: 1px solid #e2e8f0; margin: 1.1rem 0; }

/* Alert boxes */
.stSuccess { background: #f0fdf4 !important; border-color: #86efac !important; color: #166534 !important; border-radius: 8px; }
.stWarning { background: #fffbeb !important; border-color: #fcd34d !important; color: #92400e !important; border-radius: 8px; }
.stInfo    { background: #eff6ff !important; border-color: #bfdbfe !important; color: #1e40af !important; border-radius: 8px; }

/* Text visibility */
label, .stSelectbox label, .stRadio label, .stSlider label,
.stMultiSelect label, .stFileUploader label { color: #1e293b !important; font-weight: 500; }
p, li { color: #334155; }
h1, h2, h3 { color: #0f172a; }
</style>
"""

def inject_css():
    st.markdown(SHARED_CSS, unsafe_allow_html=True)

def save_upload(uploaded_file, suffix):
    """Save Streamlit UploadedFile to a temp file, return path."""
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp.write(uploaded_file.read())
    tmp.close()
    return tmp.name

def save_history(name, action):
    if "history" not in st.session_state:
        st.session_state.history = []
    st.session_state.history.append({"name": name, "action": action})
