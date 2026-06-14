import streamlit as st
import os
import tempfile
from io import BytesIO
from PIL import Image, ImageStat
from pdf2docx import Converter
import numpy as np
import mediapipe as mp

# ------------------ Initialization ------------------
# Initialize MediaPipe Face Detection
mp_face_detection = mp.solutions.face_detection

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
    """Cached PDF to DOCX conversion using a safer Temp Directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_pdf_path = os.path.join(tmpdir, 'input.pdf')
        tmp_docx_path = os.path.join(tmpdir, 'output.docx')
        
        with open(tmp_pdf_path, 'wb') as f:
            f.write(pdf_bytes)
            
        cv = Converter(tmp_pdf_path)
        cv.convert(tmp_docx_path, start=0, end=None)
        cv.close()
        
        with open(tmp_docx_path, 'rb') as f:
            return f.read()

@st.cache_data(show_spinner=False)
def convert_image_bytes_cached(input_bytes: bytes, output_format: str) -> bytes:
    """Cached image format conversion."""
    img = Image.open(BytesIO(input_bytes))
    if output_format.upper() == 'JPEG' and img.mode in ('RGBA', 'P'):
        img = img.convert('RGB')
    out = BytesIO()
    img.save(out, format=output_format.upper())
    return out.getvalue()

# ------------------ Validation & Correction Helpers ------------------
def fast_brightness(img: Image.Image) -> float:
    """Compute average brightness quickly using ImageStat."""
    gray = img.convert('L')
    stat = ImageStat.Stat(gray)
    return stat.mean[0]

def get_face_bounding_box(img: Image.Image):
    """Detects the primary face and returns absolute coordinates (x, y, w, h)."""
    img_np = np.array(img.convert('RGB'))
    
    # model_selection=1 is better for faces further away (standard for photos)
    with mp_face_detection.FaceDetection(model_selection=1, min_detection_confidence=0.5) as face_detection:
        results = face_detection.process(img_np)
        
        if not results.detections:
            return None
            
        # Get the highest confidence face (usually the first one)
        detection = results.detections[0]
        bboxC = detection.location_data.relative_bounding_box
        ih, iw, _ = img_np.shape
        
        # Convert relative bounding box to absolute pixel coordinates
        x = int(bboxC.xmin * iw)
        y = int(bboxC.ymin * ih)
        w = int(bboxC.width * iw)
        h = int(bboxC.height * ih)
        
        return x, y, w, h

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
        
    # Smart Face Validation
    bbox = get_face_bounding_box(img)
    if not bbox:
        warnings.append("No face detected in the photo.")
        return False, warnings
        
    _, _, _, face_box_height = bbox
    
    # MediaPipe's bounding box captures the face (eyebrows to chin). 
    # A full head (top of hair to chin) is roughly 1.3x taller than this box.
    estimated_head_height = face_box_height * 1.3 
    estimated_ratio = estimated_head_height / img.height
    
    if not (VISA_STANDARD['face_height_ratio_min'] <= estimated_ratio <= VISA_STANDARD['face_height_ratio_max']):
        warnings.append(f"Face ratio is ~{estimated_ratio*100:.0f}%. (Needs to be 50-70% of the photo height).")
        
    return len(warnings) == 0, warnings

@st.cache_data(show_spinner=False)
def correct_to_visa_standard(input_bytes: bytes) -> bytes:
    """Smart-crop to 600x600 using facial detection, padding with white if needed."""
    img = Image.open(BytesIO(input_bytes))
    if img.mode != 'RGB':
        img = img.convert('RGB')
        
    target_w, target_h = VISA_STANDARD['width'], VISA_STANDARD['height']
    bbox = get_face_bounding_box(img)
    
    if not bbox:
        # Fallback: If no face is found, revert to the math center-crop
        side = min(img.width, img.height)
        left = (img.width - side) // 2
        top = (img.height - side) // 2
    else:
        # Smart Crop logic
        x, y, w, h = bbox
        
        # Center of the detected face
        cx = x + (w // 2)
        cy = y + (h // 2)
        
        # We want the actual head (which is ~1.3x the bounding box) 
        # to take up exactly 60% of our new cropped square.
        crop_size = int((h * 1.3) / 0.6)
        
        # Adjust Y-center slightly so eyes sit in the upper half of the photo.
        cy = int(cy + (h * 0.15)) 
        
        left = cx - (crop_size // 2)
        top = cy - (crop_size // 2)
        side = crop_size

    # Create a solid white canvas to paste our crop onto.
    canvas = Image.new('RGB', (side, side), (255, 255, 255))
    
    # Calculate where to paste the image onto the canvas
    paste_x = max(0, -left)
    paste_y = max(0, -top)
    
    # Calculate what coordinates to actually grab from the original image
    crop_left = max(0, left)
    crop_top = max(0, top)
    crop_right = min(img.width, left + side)
    crop_bottom = min(img.height, top + side)
    
    # Crop and paste
    cropped_piece = img.crop((crop_left, crop_top, crop_right, crop_bottom))
    canvas.paste(cropped_piece, (paste_x, paste_y))
    
    # Finally, resize our perfectly scaled square down to the exact 600x600 requirement
    img_resized = canvas.resize((target_w, target_h), Image.Resampling.LANCZOS)
    
    buf = BytesIO()
    img_resized.save(buf, format="JPEG", quality=95)
    return buf.getvalue()

# ------------------ Streamlit UI ------------------
st.set_page_config(page_title="Fast File Converter", page_icon="⚡")
st.title("⚡ Fast File Converter")
st.markdown("Optimised for speed with caching and AI photo correction.")

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
                        label="📥 Download DOCX",
                        data=docx_bytes,
                        file_name=uploaded_file.name.replace('.pdf', '.docx'),
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    )
                except Exception as e:
                    st.error(f"Error processing PDF: {e}")

    # ---------- Image to Image ----------
    elif conversion_type == "Image to Image":
        if ext not in ALLOWED_IMAGE_EXT:
            st.error(f"Unsupported format. Use: {', '.join(ALLOWED_IMAGE_EXT)}")
        else:
            output_format = st.selectbox("Output format", ["PNG", "JPEG", "BMP", "GIF", "TIFF", "WEBP"])
            
            with st.spinner("Preparing download..."):
                out_bytes = convert_image_bytes_cached(file_bytes, output_format.lower())
                out_name = uploaded_file.name.rsplit('.', 1)[0] + f".{output_format.lower()}"
                
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
                st.subheader("Validation")
                small_check = img.copy()
                if max(small_check.size) > 1000:
                    small_check.thumbnail((800, 800))
                    
                is_valid, warns = validate_visa_photo(small_check)
                if is_valid:
                    st.success("✅ Photo meets requirements.")
                else:
                    st.warning("Issues found:")
                    for w in warns:
                        st.write(f"- {w}")
                        
            with col2:
                st.subheader("Correction")
                st.info("✨ AI Auto-Crop Enabled: Automatically centers and scales the face to meet requirements.")
                
                # Instantly prepare the corrected bytes (cached)
                corrected_bytes = correct_to_visa_standard(file_bytes)
                corrected_img = Image.open(BytesIO(corrected_bytes))
                
                st.image(corrected_img, caption="Corrected 600×600", width=250)
                st.download_button("📥 Download Corrected JPEG", corrected_bytes, "visa_photo.jpg", mime="image/jpeg")

else:
    st.info("Upload a file to begin.")

st.caption("⚡ Caching enabled: converting the same file again is instant. PDF→Word still depends on server CPU.")
