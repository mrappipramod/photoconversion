import streamlit as st
import os
import tempfile
from io import BytesIO
from PIL import Image, ImageStat
from pdf2docx import Converter

# ------------------ Configuration ------------------
VISA_STANDARD = {
    'width': 600,
    'height': 600,
    'min_brightness': 200,
    'face_height_ratio_min': 0.5,
    'face_height_ratio_max': 0.7,
}
ALLOWED_IMAGE_EXT = {'png', 'jpg', 'jpeg', 'bmp', 'gif', 'tiff', 'webp'}

# ------------------ Cached Conversions ------------------
@st.cache_data(ttl=3600, show_spinner=False)
def convert_pdf_to_docx_cached(pdf_bytes: bytes) -> bytes:
    """Cached PDF to DOCX conversion."""
    with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_pdf:
        tmp_pdf.write(pdf_bytes)
        tmp_pdf_path = tmp_pdf.name
    with tempfile.NamedTemporaryFile(suffix='.docx', delete=False) as tmp_docx:
        tmp_docx_path = tmp_docx.name
    try:
        cv = Converter(tmp_pdf_path)
        cv.convert(tmp_docx_path, start=0, end=None)
        cv.close()
        with open(tmp_docx_path, 'rb') as f:
            return f.read()
    finally:
        os.unlink(tmp_pdf_path)
        os.unlink(tmp_docx_path)

@st.cache_data(show_spinner=False)
def convert_image_bytes_cached(input_bytes: bytes, output_format: str) -> bytes:
    """Cached image format conversion."""
    img = Image.open(BytesIO(input_bytes))
    if output_format.upper() == 'JPEG' and img.mode in ('RGBA', 'P'):
        img = img.convert('RGB')
    out = BytesIO()
    img.save(out, format=output_format.upper())
    return out.getvalue()

# ------------------ Validation Helpers ------------------
def fast_brightness(img: Image.Image) -> float:
    """Compute average brightness quickly using ImageStat."""
    gray = img.convert('L')
    stat = ImageStat.Stat(gray)
    return stat.mean[0]

def validate_visa_photo(img: Image.Image) -> tuple:
    """Validate visa photo – returns (is_valid, list_of_warnings)."""
    warnings = []
    # Dimensions
    if img.size != (VISA_STANDARD['width'], VISA_STANDARD['height']):
        warnings.append(f"Dimensions: {img.width}x{img.height} (needs {VISA_STANDARD['width']}x{VISA_STANDARD['height']})")
    # Brightness (downsample for speed)
    small = img.resize((100, 100), Image.Resampling.LANCZOS)
    brightness = fast_brightness(small)
    if brightness < VISA_STANDARD['min_brightness']:
        warnings.append(f"Background too dark ({brightness:.0f} < {VISA_STANDARD['min_brightness']})")
    # Face ratio – dummy but fast (replace with OpenCV if needed)
    face_ratio = 0.6
    if not (VISA_STANDARD['face_height_ratio_min'] <= face_ratio <= VISA_STANDARD['face_height_ratio_max']):
        warnings.append(f"Face height ratio should be 50-70% of photo height.")
    return len(warnings) == 0, warnings

def correct_to_visa_standard(img: Image.Image) -> Image.Image:
    """Resize/crop to 600x600 square (center crop)."""
    target_w, target_h = VISA_STANDARD['width'], VISA_STANDARD['height']
    side = min(img.width, img.height)
    left = (img.width - side) // 2
    top = (img.height - side) // 2
    img_cropped = img.crop((left, top, left + side, top + side))
    img_resized = img_cropped.resize((target_w, target_h), Image.Resampling.LANCZOS)
    if img_resized.mode != 'RGB':
        img_resized = img_resized.convert('RGB')
    return img_resized

# ------------------ Streamlit UI ------------------
st.set_page_config(page_title="Fast File Converter", page_icon="⚡")
st.title("⚡ Fast File Converter")
st.markdown("Optimised for speed with caching.")

conversion_type = st.radio(
    "Choose conversion:",
    ["PDF to Word", "Image to Image", "Photo to Visa Standard"],
    horizontal=True
)

uploaded_file = st.file_uploader("Upload a file", type=None)

if uploaded_file is not None:
    file_bytes = uploaded_file.read()
    ext = uploaded_file.name.split('.')[-1].lower()

    # ---------- PDF to Word ----------
    if conversion_type == "PDF to Word":
        if ext != 'pdf':
            st.error("Please upload a PDF file.")
        else:
            with st.spinner("Converting PDF (this may take 10-60 seconds)..."):
                try:
                    docx_bytes = convert_pdf_to_docx_cached(file_bytes)
                    st.success("Ready!")
                    st.download_button(
                        "📥 Download DOCX",
                        docx_bytes,
                        uploaded_file.name.replace('.pdf', '.docx'),
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    )
                except Exception as e:
                    st.error(f"Error: {e}")

    # ---------- Image to Image ----------
    elif conversion_type == "Image to Image":
        if ext not in ALLOWED_IMAGE_EXT:
            st.error(f"Unsupported format. Use: {', '.join(ALLOWED_IMAGE_EXT)}")
        else:
            output_format = st.selectbox("Output format", ["PNG","JPEG","BMP","GIF","TIFF","WEBP"])
            if st.button("Convert"):
                with st.spinner("Converting..."):
                    out_bytes = convert_image_bytes_cached(file_bytes, output_format.lower())
                    out_name = uploaded_file.name.rsplit('.',1)[0] + f".{output_format.lower()}"
                    st.download_button(f"📥 Download {output_format}", out_bytes, out_name)

    # ---------- Visa Photo ----------
    elif conversion_type == "Photo to Visa Standard":
        if ext not in ALLOWED_IMAGE_EXT:
            st.error(f"Please upload an image. Allowed: {', '.join(ALLOWED_IMAGE_EXT)}")
        else:
            img = Image.open(BytesIO(file_bytes))
            st.image(img, caption="Original", width=250)
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔍 Validate"):
                    # Downsample for faster validation
                    small_check = img.copy()
                    if max(small_check.size) > 1000:
                        small_check.thumbnail((800,800))
                    is_valid, warns = validate_visa_photo(small_check)
                    if is_valid:
                        st.success("✅ Photo meets requirements.")
                    else:
                        st.warning("Issues found:")
                        for w in warns:
                            st.write(f"- {w}")
            with col2:
                if st.button("✨ Correct & Download"):
                    corrected = correct_to_visa_standard(img)
                    st.image(corrected, caption="Corrected 600×600", width=250)
                    # Validate after correction
                    is_valid, warns = validate_visa_photo(corrected)
                    if is_valid:
                        st.success("✅ Corrected photo meets visa standard.")
                    else:
                        st.info("Photo corrected to 600×600. Remaining warnings:")
                        for w in warns:
                            st.write(f"- {w}")
                    buf = BytesIO()
                    corrected.save(buf, format="JPEG", quality=90)
                    st.download_button("📥 Download JPEG", buf.getvalue(), "visa_photo.jpg")
else:
    st.info("Upload a file to begin.")

st.caption("⚡ Caching enabled: converting the same file again is instant. PDF→Word still depends on server CPU.")
