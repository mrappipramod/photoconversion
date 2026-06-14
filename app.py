import streamlit as st
import os
import tempfile
import uuid
from io import BytesIO

import numpy as np
from PIL import Image, ImageStat, ImageEnhance
from pdf2docx import Converter
import pytesseract
import cv2
from rembg import remove
from docx import Document
from supabase import create_client

# ================= SUPABASE CONFIG =================
SUPABASE_URL = "YOUR_SUPABASE_URL"
SUPABASE_KEY = "YOUR_SUPABASE_ANON_KEY"
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ================= CONFIG =================
VISA_STANDARD = {
    "width": 600,
    "height": 600,
    "min_brightness": 180,
}

ALLOWED_IMAGE_EXT = {"png", "jpg", "jpeg", "bmp", "tiff", "webp"}

# ================= SESSION HISTORY =================
if "history" not in st.session_state:
    st.session_state.history = []

# ================= AUTH =================
def login_ui():
    st.title("🔐 Login")

    email = st.text_input("Email")
    password = st.text_input("Password", type="password")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Login"):
            res = supabase.auth.sign_in_with_password({
                "email": email,
                "password": password
            })
            st.session_state.user = res.user
            st.success("Logged in!")
            st.rerun()

    with col2:
        if st.button("Sign Up"):
            supabase.auth.sign_up({
                "email": email,
                "password": password
            })
            st.success("Check email for confirmation")

# ================= FACE DETECTION =================
def detect_face_ratio(img: Image.Image):
    img_cv = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)

    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )

    faces = face_cascade.detectMultiScale(gray, 1.1, 5)

    if len(faces) == 0:
        return None

    x, y, w, h = faces[0]
    face_ratio = h / img.height
    return face_ratio

# ================= VISA VALIDATION =================
def validate_visa(img):
    warnings = []

    if img.size != (600, 600):
        warnings.append("Must be 600x600")

    brightness = ImageStat.Stat(img.convert("L")).mean[0]
    if brightness < VISA_STANDARD["min_brightness"]:
        warnings.append("Image too dark")

    face_ratio = detect_face_ratio(img)
    if face_ratio:
        if not (0.5 <= face_ratio <= 0.75):
            warnings.append("Face not centered properly")
    else:
        warnings.append("No face detected")

    return len(warnings) == 0, warnings

# ================= BACKGROUND REMOVAL =================
def remove_bg(img):
    output = remove(img)
    return Image.open(BytesIO(output)).convert("RGB")

# ================= IMAGE CORRECTION =================
def fix_visa(img):
    img = img.convert("RGB")

    # auto brightness boost
    enhancer = ImageEnhance.Brightness(img)
    img = enhancer.enhance(1.2)

    # resize
    img = img.resize((600, 600))

    return img

# ================= PDF OCR TO WORD =================
def pdf_to_searchable_docx(pdf_bytes):
    tmp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    tmp_pdf.write(pdf_bytes)
    tmp_pdf.close()

    doc = Document()
    text = pytesseract.image_to_string(Image.open(tmp_pdf.name))

    doc.add_paragraph(text)

    tmp_docx = tempfile.NamedTemporaryFile(delete=False, suffix=".docx")
    doc.save(tmp_docx.name)

    with open(tmp_docx.name, "rb") as f:
        return f.read()

# ================= HISTORY =================
def save_history(name, filetype):
    st.session_state.history.append({
        "id": str(uuid.uuid4()),
        "name": name,
        "type": filetype
    })

# ================= UI =================
st.set_page_config(page_title="AI Smart Processor", layout="wide")

if "user" not in st.session_state:
    login_ui()
    st.stop()

st.title("⚡ AI Smart Document & Photo Processor")

tabs = st.tabs([
    "📄 PDF OCR",
    "🪪 Visa Photo AI",
    "✂️ Background Removal",
    "📦 History"
])

# ================= PDF OCR =================
with tabs[0]:
    file = st.file_uploader("Upload PDF", type=["pdf"])

    if file:
        if st.button("Convert to Searchable Word"):
            with st.spinner("Processing OCR..."):
                result = pdf_to_searchable_docx(file.read())
                save_history(file.name, "PDF OCR")

                st.download_button(
                    "Download DOCX",
                    result,
                    "output.docx"
                )

# ================= VISA PHOTO =================
with tabs[1]:
    file = st.file_uploader("Upload Photo", type=list(ALLOWED_IMAGE_EXT))

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
            if st.button("Fix Photo"):
                fixed = fix_visa(img)
                save_history(file.name, "Visa Fix")

                st.image(fixed, caption="Fixed")
                buf = BytesIO()
                fixed.save(buf, format="JPEG")

                st.download_button(
                    "Download",
                    buf.getvalue(),
                    "visa.jpg"
                )

# ================= BACKGROUND REMOVAL =================
with tabs[2]:
    file = st.file_uploader("Upload Image", type=list(ALLOWED_IMAGE_EXT))

    if file:
        img = Image.open(file)

        if st.button("Remove Background"):
            result = remove_bg(img)
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
    st.subheader("Download History")

    for item in st.session_state.history[::-1]:
        st.write(f"📄 {item['name']} — {item['type']}")
