import streamlit as st
from PIL import Image, ImageStat, ImageEnhance
from io import BytesIO
import uuid
import fitz  # PyMuPDF
import pytesseract
import os

# ================= SAFE ENV (optional speed tweak) =================
os.environ["U2NET_HOME"] = "/tmp"

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

def save_history(name, action):
    st.session_state.history.append({
        "id": str(uuid.uuid4()),
        "name": name,
        "action": action
    })

# ================= PDF → DOCX =================
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

# ================= SAFE BACKGROUND REMOVAL =================
def remove_background(img):
    from rembg import remove

    output = remove(img)

    # FIX: rembg may return PIL Image OR bytes depending on version
    if isinstance(output, Image.Image):
        return output.convert("RGB")

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

# ================= UI =================
st.set_page_config(page_title="AI Smart Studio", layout="wide")

st.title("⚡ AI Smart Document & Photo Processor")

tabs = st.tabs([
    "📄 PDF OCR",
    "🪪 Visa Photo AI",
    "✂️ Background Removal",
    "📦 History"
])

# ================= PDF TAB =================
with tabs[0]:
    file = st.file_uploader(
        "Upload PDF",
        type=["pdf"],
        key="pdf_uploader"
    )

    if file:
        if st.button("Convert to Word", key="pdf_btn"):
            with st.spinner("Processing PDF..."):
                out = pdf_to_docx(file.read())
                save_history(file.name, "PDF → DOCX")

                st.success("Done!")

                st.download_button(
                    "Download DOCX",
                    out,
                    "output.docx",
                    key="pdf_download"
                )

# ================= VISA TAB =================
with tabs[1]:
    file = st.file_uploader(
        "Upload Image",
        type=list(ALLOWED_IMAGE_EXT),
        key="visa_uploader"
    )

    if file:
        img = Image.open(file)

        st.image(img, caption="Original")

        col1, col2 = st.columns(2)

        with col1:
            if st.button("Validate", key="visa_validate"):
                ok, warns = validate_visa(img)
                if ok:
                    st.success("Valid visa photo")
                else:
                    st.warning(warns)

        with col2:
            if st.button("Fix", key="visa_fix"):
                fixed = fix_visa(img)
                save_history(file.name, "Visa Fix")

                st.image(fixed)

                buf = BytesIO()
                fixed.save(buf, format="JPEG")

                st.download_button(
                    "Download",
                    buf.getvalue(),
                    "visa.jpg",
                    key="visa_download"
                )

# ================= BACKGROUND REMOVAL TAB =================
with tabs[2]:
    file = st.file_uploader(
        "Upload Image",
        type=list(ALLOWED_IMAGE_EXT),
        key="bg_uploader"
    )

    if file:
        img = Image.open(file)

        if st.button("Remove Background", key="bg_btn"):
            with st.spinner("Processing AI model..."):
                result = remove_background(img)
                save_history(file.name, "BG Removed")

                st.image(result)

                buf = BytesIO()
                result.save(buf, format="PNG")

                st.download_button(
                    "Download PNG",
                    buf.getvalue(),
                    "no_bg.png",
                    key="bg_download"
                )

# ================= HISTORY TAB =================
with tabs[3]:
    st.subheader("Session History")

    if not st.session_state.history:
        st.info("No actions yet")

    for item in st.session_state.history[::-1]:
        st.write(f"📄 {item['name']} → {item['action']}")
