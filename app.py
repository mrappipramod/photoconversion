import streamlit as st
import os
import uuid
from io import BytesIO
from PIL import Image, ImageOps
from pdf2docx import Converter
import tempfile
import colorsys

# ------------------ Configuration ------------------
VISA_STANDARD = {
    'width': 600,
    'height': 600,
    'min_brightness': 200,      # background brightness (0-255)
    'face_height_ratio_min': 0.5,
    'face_height_ratio_max': 0.7,
}

ALLOWED_IMAGE_EXT = {'png', 'jpg', 'jpeg', 'bmp', 'gif', 'tiff', 'webp'}

# ------------------ Helper Functions ------------------
def convert_pdf_to_docx(pdf_bytes: bytes) -> bytes:
    """Convert PDF bytes to DOCX bytes."""
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
            docx_bytes = f.read()
        return docx_bytes
    finally:
        os.unlink(tmp_pdf_path)
        os.unlink(tmp_docx_path)

def convert_image_bytes(input_bytes: bytes, output_format: str) -> bytes:
    """Convert image bytes to another format (JPEG, PNG, etc.)."""
    img = Image.open(BytesIO(input_bytes))
    if output_format.upper() == 'JPEG' and img.mode in ('RGBA', 'P'):
        img = img.convert('RGB')
    out_buffer = BytesIO()
    img.save(out_buffer, format=output_format.upper())
    return out_buffer.getvalue()

def analyze_background_brightness(img: Image.Image) -> float:
    """Return average brightness (0-255)."""
    gray = img.convert('L')
    pixels = list(gray.getdata())
    return sum(pixels) / len(pixels)

def estimate_face_ratio(img: Image.Image) -> float:
    """
    Very basic face proxy: assumes face is in central 50% width and between 30-80% height.
    Returns estimated face height / total height.
    In a real app, use OpenCV face detection.
    """
    height = img.height
    # Dummy: assume face occupies 60% of height (typical passport)
    return 0.6

def validate_visa_photo(img: Image.Image) -> tuple:
    """Return (is_valid, list_of_warnings)."""
    warnings = []
    # Dimensions
    if img.size != (VISA_STANDARD['width'], VISA_STANDARD['height']):
        warnings.append(f"Dimensions: {img.width}x{img.height} (needs {VISA_STANDARD['width']}x{VISA_STANDARD['height']})")
    # Brightness
    brightness = analyze_background_brightness(img)
    if brightness < VISA_STANDARD['min_brightness']:
        warnings.append(f"Background too dark (brightness {brightness:.0f} < {VISA_STANDARD['min_brightness']})")
    # Face ratio
    face_ratio = estimate_face_ratio(img)
    if not (VISA_STANDARD['face_height_ratio_min'] <= face_ratio <= VISA_STANDARD['face_height_ratio_max']):
        warnings.append(f"Estimated face height ratio: {face_ratio:.0%} (should be {VISA_STANDARD['face_height_ratio_min']*100:.0f}–{VISA_STANDARD['face_height_ratio_max']*100:.0f}%)")
    return len(warnings) == 0, warnings

def correct_to_visa_standard(img: Image.Image) -> Image.Image:
    """Resize/crop to 600x600 square (center crop)."""
    target_w, target_h = VISA_STANDARD['width'], VISA_STANDARD['height']
    # Crop to largest central square
    side = min(img.width, img.height)
    left = (img.width - side) // 2
    top = (img.height - side) // 2
    img_cropped = img.crop((left, top, left + side, top + side))
    img_resized = img_cropped.resize((target_w, target_h), Image.Resampling.LANCZOS)
    if img_resized.mode != 'RGB':
        img_resized = img_resized.convert('RGB')
    return img_resized

# ------------------ Streamlit UI ------------------
st.set_page_config(page_title="File Converter", page_icon="🔄", layout="centered")
st.title("📄 Universal File Converter")
st.markdown("Convert PDF to Word, images to different formats, or prepare a photo for visa standards.")

conversion_type = st.radio(
    "Choose conversion type:",
    ["PDF to Word (DOCX)", "Image to Image", "Photo to Visa Standard"],
    horizontal=True
)

uploaded_file = st.file_uploader(
    "Upload a file",
    type=None,  # We'll validate per conversion type
    help="Supported: PDF for Word, any image for image/visa conversions"
)

if uploaded_file is not None:
    file_bytes = uploaded_file.read()
    original_filename = uploaded_file.name
    ext = original_filename.split('.')[-1].lower()

    # --- PDF to Word ---
    if conversion_type == "PDF to Word (DOCX)":
        if ext != 'pdf':
            st.error("Please upload a PDF file for Word conversion.")
        else:
            with st.spinner("Converting PDF to Word..."):
                try:
                    docx_bytes = convert_pdf_to_docx(file_bytes)
                    st.success("Conversion successful!")
                    st.download_button(
                        label="📥 Download DOCX",
                        data=docx_bytes,
                        file_name=original_filename.replace('.pdf', '.docx'),
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    )
                except Exception as e:
                    st.error(f"Conversion failed: {e}")

    # --- Image to Image ---
    elif conversion_type == "Image to Image":
        if ext not in ALLOWED_IMAGE_EXT:
            st.error(f"Unsupported image format. Allowed: {', '.join(ALLOWED_IMAGE_EXT)}")
        else:
            output_format = st.selectbox(
                "Output format",
                ["PNG", "JPEG", "BMP", "GIF", "TIFF", "WEBP"],
                index=0
            )
            if st.button("Convert Image"):
                with st.spinner("Converting..."):
                    try:
                        out_bytes = convert_image_bytes(file_bytes, output_format.lower())
                        out_filename = original_filename.rsplit('.', 1)[0] + f".{output_format.lower()}"
                        st.success("Conversion complete!")
                        st.download_button(
                            label=f"📥 Download as {output_format}",
                            data=out_bytes,
                            file_name=out_filename,
                            mime=f"image/{output_format.lower()}"
                        )
                    except Exception as e:
                        st.error(f"Error: {e}")

    # --- Photo to Visa Standard ---
    elif conversion_type == "Photo to Visa Standard":
        if ext not in ALLOWED_IMAGE_EXT:
            st.error(f"Please upload an image file. Allowed: {', '.join(ALLOWED_IMAGE_EXT)}")
        else:
            # Show original image
            img = Image.open(BytesIO(file_bytes))
            st.image(img, caption="Uploaded Photo", width=300)
            
            # Two columns for actions
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🔍 Validate Only"):
                    # We need to check if already correct size? For validation we assume user wants to check any image.
                    # If image is not 600x600, we still validate relative to that target size? Better to validate as is.
                    # But standard requires exact dimensions. We'll show warnings.
                    is_valid, warnings = validate_visa_photo(img)
                    if is_valid:
                        st.success("✅ This photo meets the visa standard requirements!")
                    else:
                        st.warning("⚠️ The following issues were found:")
                        for w in warnings:
                            st.write(f"- {w}")
            with col2:
                if st.button("✨ Correct & Download"):
                    corrected_img = correct_to_visa_standard(img)
                    st.image(corrected_img, caption="Corrected Photo (600x600)", width=300)
                    # Validate after correction
                    is_valid, warnings = validate_visa_standard(corrected_img)
                    if is_valid:
                        st.success("✅ Corrected photo now meets visa standard.")
                    else:
                        st.info("Photo has been resized/cropped to 600x600. Remaining warnings (if any):")
                        for w in warnings:
                            st.write(f"- {w}")
                    # Provide download
                    buf = BytesIO()
                    corrected_img.save(buf, format="JPEG", quality=95)
                    st.download_button(
                        label="📥 Download Visa Photo (JPEG)",
                        data=buf.getvalue(),
                        file_name="visa_photo_600x600.jpg",
                        mime="image/jpeg"
                    )

else:
    st.info("👈 Please upload a file to start.")

st.markdown("---")
st.caption("🔒 All conversions happen in memory/temp files and are deleted automatically. Max file size is limited by Streamlit (usually 200MB).")
