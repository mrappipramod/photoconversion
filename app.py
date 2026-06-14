import streamlit as st
import os
from io import BytesIO
from PIL import Image, ImageStat, ImageEnhance
import uuid

import fitz  # PyMuPDF (safe PDF engine)
import pytesseract

# ================= CONFIG =================
VISA_STANDARD = {
    "width": 600,
    "height": 600,
    "min_brightness": 180,
}

ALLOWED_IMAGE_EXT = {"png", "jpg", "jpeg", "bmp", "tiff", "webp"}

# ================= SESSION =================
if "history" not in st.session_state:
    st.session_state.history = []

if "user" not in st.session_state:
    st.session_state.user = None

# ================= SUPABASE (LAZY) =================
supabase = None

def get_supabase():
    global supabase
    if supabase is None:
        from supabase import create_client
        SUPABASE_URL = "YOUR_SUPABASE_URL"
        SUPABASE_KEY = "YOUR_SUPABASE_ANON_KEY"
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    return supabase

# ================= HISTORY =================
def save_history(name, action):
    st.session_state.history.append({
        "id": str(uuid.uuid4()),
        "name": name,
        "action": action
    })

# ================= PDF → TEXT → DOCX =================
def pdf_to_docx(pdf_bytes):
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    text = ""
    for page in doc:
        text += page.get_text()

    from docx import Document
    word = Document()
    word.add_paragraph(text)

    buf = BytesIO()
    word.save(buf)
    return buf.getvalue()

# ================= OCR =================
def image_to_text(img):
    return pytesseract.image_to_string(img)

# ================= BACKGROUND REMOVAL (LAZY) =================
def remove_background(img):
    from rembg import remove  # lazy import FIX (prevents freeze)

    output = remove(img)
    return Image.open(BytesIO(output)).convert("RGB")

# ================= VISA VALIDATION =================
def validate_visa(img):
    warnings = []

    if img.size != (600, 600):
        warnings.append("Image must be 600x600")

    brightness = ImageStat.Stat(img.convert("L")).mean[0]
    if brightness < VISA_STANDARD["min_brightness"]:
        warnings.append("Image too dark")

    return len(warnings) == 0, warnings

# ================= VISA FIX =================
def fix_visa(img):
    img = img.convert("RGB")

    enhancer = ImageEnhance.Brightness(img)
    img = enhancer.enhance(1.2)

    return img.resize((600, 600))

# ================= AUTH =================
def login_ui():
    st.title("🔐 Login")

    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Login"):
            client = get_supabase()
            res = client.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            st.session_state.user = res.user
            st.rerun()

    with col2:
        if st.button("Sign Up"):
            client = get_supabase()
            client.auth.sign_up({
                "email": email,
                "password": password
            })
            st.success("Check email to confirm")

# ================= UI =================
st.set_page_config(page_title="AI Smart Studio", layout="wide")

if st.session_state.user is None:
    login_ui()
    st.stop()

st.title("⚡ AI Smart Document & Photo Processor")

tabs = st.tabs([
    "📄 PDF OCR",
    "🪪 Visa Photo AI",
    "✂️ Background Removal",
    "📦 History"
])

# ================= PDF =================
with tabs[0]:
    file = st.file_uploader("Upload PDF", type=["pdf"])

    if file:
        if st.button("Convert to Word"):
            with st.spinner("Processing PDF..."):
                out = pdf_to_docx(file.read())
                save_history(file.name, "PDF → DOCX")

                st.download_button(
                    "Download DOCX",
                    out,
                    "output.docx"
                )

# ================= VISA =================
with tabs[1]:
    file = st.file_uploader("Upload Image", type=list(ALLOWED_IMAGE_EXT))

    if file:
        img = Image.open(file)

        st.image(img, caption="Original")

        col1, col2 = st.columns(2)

        with col1:
            if st.button("Validate"):
                ok, warns = validate_visa(img)
                if ok:
                    st.success("Valid visa photo")
                else:
                    st.warning(warns)

        with col2:
            if st.button("Fix"):
                fixed = fix_visa(img)
                save_history(file.name, "Visa Fix")

                st.image(fixed)

                buf = BytesIO()
                fixed.save(buf, format="JPEG")

                st.download_button(
                    "Download",
                    buf.getvalue(),
                    "visa.jpg"
                )

# ================= BG REMOVE =================
with tabs[2]:
    file = st.file_uploader("Upload Image", type=list(ALLOWED_IMAGE_EXT))

    if file:
        img = Image.open(file)

        if st.button("Remove Background"):
            with st.spinner("Processing..."):
                result = remove_background(img)
                save_history(file.name, "BG Removed")

                st.image(result)

                buf = BytesIO()
                result.save(buf, format="PNG")

                st.download_button(
                    "Download PNG",
                    buf.getvalue(),
                    "no_bg.png"
                )

# ================= HISTORY =================
with tabs[3]:
    st.subheader("History")

    for item in st.session_state.history[::-1]:
        st.write(f"📄 {item['name']} → {item['action']}")
