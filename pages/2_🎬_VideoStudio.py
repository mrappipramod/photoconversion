import streamlit as st
import os, shutil, tempfile
from utils import inject_css, save_upload, save_history
from video_engine import (
    probe, run_pipeline, extract_frame, do_merge,
    FILTERS, PLATFORMS,
)

st.set_page_config(
    page_title="Video Studio",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="collapsed",
)
inject_css()

st.markdown("""
<style>
/* Override tab accent to red */
.stTabs [aria-selected="true"] { background:#fff1f2 !important; color:#e11d48 !important; }

/* Primary action buttons */
.stButton > button {
    background: linear-gradient(135deg,#e11d48,#7c3aed) !important;
    color: white !important; border: none !important;
    border-radius: 8px !important; font-weight: 600 !important;
}
.stDownloadButton > button {
    background: #fff1f2 !important; color: #e11d48 !important;
    border: 1px solid #fecdd3 !important; border-radius: 8px !important;
    font-weight: 600 !important;
}

/* Section cards */
.section {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 14px;
    padding: 1.4rem 1.6rem;
    margin-bottom: 1.2rem;
}
.section-title {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 1rem; font-weight: 700; color: #1e293b;
    margin-bottom: 1rem;
    display: flex; align-items: center; gap: 8px;
}
.num {
    display: inline-flex; align-items: center; justify-content: center;
    width: 26px; height: 26px;
    background: linear-gradient(135deg,#e11d48,#7c3aed);
    color: white; border-radius: 50%; font-size: 12px; font-weight: 700;
    flex-shrink: 0;
}

/* Queue items */
.qitem {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-left: 4px solid #e11d48;
    border-radius: 8px;
    padding: 0.55rem 1rem;
    margin-bottom: 0.35rem;
}
.qi-name { font-size: 0.88rem; font-weight: 600; color: #1e293b; }
.qi-detail { font-size: 0.75rem; color: #64748b; margin-top: 2px; }

/* Template buttons */
.stButton > button[kind="secondary"] {
    background: #f8fafc !important; color: #1e293b !important;
    border: 1px solid #e2e8f0 !important;
}
</style>
""", unsafe_allow_html=True)

# ── Sidebar ────────────────────────────────────────────────────────
with st.sidebar:
    st.page_link("app.py",                    label="← Home",           icon="🏠")
    st.page_link("pages/1_📄_SmartDoc.py",   label="📄 SmartDoc Studio")

# ── Session state ──────────────────────────────────────────────────
DEFAULTS = {
    "src": None,           # path to working source video
    "src_name": "",
    "audio_path": None,
    "logo_path": None,
    "queue": [],           # list of step dicts
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

def add_step(step):
    st.session_state.queue.append(step)
    st.rerun()

# ─── Templates ────────────────────────────────────────────────────
TEMPLATES = {
    "🔥 Viral Reel": [
        {"type":"filter","filter":"Vivid","brightness":0.05,"contrast":1.1,"saturation":1.8},
        {"type":"watermark_text","text":"@yourbrand","position":"Bottom Right","opacity":0.75,"size":28},
        {"type":"export","platform":"Instagram Reels (9:16)","quality":"High","fit":"crop"},
    ],
    "🎬 Cinematic": [
        {"type":"filter","filter":"Cinematic","brightness":-0.03,"contrast":1.2,"saturation":0.85},
        {"type":"kenburns","zoom_start":1.0,"zoom_end":1.08},
        {"type":"export","platform":"YouTube Shorts (9:16)","quality":"Max","fit":"letterbox"},
    ],
    "🌅 Travel Vlog": [
        {"type":"filter","filter":"Warm Sunset","brightness":0.04,"contrast":1.0,"saturation":1.3},
        {"type":"text","text":"Your Destination","style":"Lower Third","animation":"None",
         "font_size":52,"color":"#FFFFFF","x_pct":5,"y_pct":78,"start":1.0,"end":4.5,"shadow":True,"bg_box":False},
        {"type":"export","platform":"YouTube (16:9)","quality":"High","fit":"letterbox"},
    ],
    "🎵 Music Video": [
        {"type":"filter","filter":"Neon Night","brightness":-0.05,"contrast":1.4,"saturation":2.2},
        {"type":"watermark_text","text":"@yourbrand","position":"Bottom Right","opacity":0.8,"size":28},
        {"type":"export","platform":"Instagram Reels (9:16)","quality":"High","fit":"crop"},
    ],
    "📰 News / Talk": [
        {"type":"filter","filter":"None","brightness":0.02,"contrast":1.05,"saturation":1.0},
        {"type":"progress_bar","color":"#e11d48","height":8,"position":"bottom"},
        {"type":"text","text":"Breaking News","style":"News Ticker","animation":"None",
         "font_size":40,"color":"#FFFFFF","x_pct":2,"y_pct":87,"start":0.5,"end":5.0,"shadow":True,"bg_box":False},
        {"type":"export","platform":"YouTube (16:9)","quality":"High","fit":"letterbox"},
    ],
    "⚡ Quick Export": [
        {"type":"export","platform":"Instagram Reels (9:16)","quality":"Standard","fit":"crop"},
    ],
}

STEP_ICONS = {
    "trim": "✂️", "filter": "🎨", "speed": "⚡",
    "text": "📝", "watermark_text": "💧", "watermark_logo": "🖼️",
    "progress_bar": "📊", "kenburns": "🔍",
    "audio_mute": "🔇", "audio_volume": "🔊",
    "audio_replace": "🎵", "audio_mix": "🎵",
    "export": "📐",
}

def step_detail(s):
    t = s.get("type","")
    if t == "trim":          return f'{s["start"]:.1f}s → {s["end"]:.1f}s'
    if t == "filter":        return f'{s.get("filter","None")} | brightness {s.get("brightness",0):+.2f} contrast {s.get("contrast",1):.2f} saturation {s.get("saturation",1):.2f}'
    if t == "speed":         return f'×{s["speed"]}'
    if t == "text":          return f'"{s.get("text","")[:30]}" — {s.get("style","")} | {s.get("start",0):.1f}s–{s.get("end",0):.1f}s'
    if t == "watermark_text":return f'"{s.get("text","")}" at {s.get("position","")} opacity {int(s.get("opacity",0.75)*100)}%'
    if t == "watermark_logo":return f'{s.get("position","")} size {s.get("size_pct",15)}% opacity {int(s.get("opacity",0.75)*100)}%'
    if t == "progress_bar":  return f'{s.get("position","bottom")} bar {s.get("color","")} {s.get("height",8)}px'
    if t == "kenburns":      return f'zoom {s.get("zoom_start",1.0):.2f} → {s.get("zoom_end",1.08):.2f}'
    if t == "audio_mute":    return "Remove all audio"
    if t == "audio_volume":  return f'Volume ×{s.get("multiplier",1.5)}'
    if t == "audio_replace": return "Replace audio with music track"
    if t == "audio_mix":     return f'Mix: music {s.get("music_vol",0.5):.1f} + original {s.get("orig_vol",1.0):.1f}'
    if t == "export":        return f'{s.get("platform","")} | {s.get("quality","")} | {s.get("fit","")}'
    return ""

# ══════════════════════════════════════════════════════════════════
# HEADER
# ══════════════════════════════════════════════════════════════════
st.markdown(
    '<div style="font-family:\'Space Grotesk\',sans-serif;font-size:2rem;font-weight:700;'
    'background:linear-gradient(135deg,#e11d48,#7c3aed);'
    '-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:2px">'
    '🎬 Video Studio</div>', unsafe_allow_html=True
)
st.markdown(
    '<div style="color:#64748b;font-size:0.9rem;margin-bottom:1.4rem">'
    'Upload → Choose edits → Render → Download</div>', unsafe_allow_html=True
)

# ══════════════════════════════════════════════════════════════════
# SECTION 1 — UPLOAD
# ══════════════════════════════════════════════════════════════════
st.markdown('<div class="section">', unsafe_allow_html=True)
st.markdown('<div class="section-title"><span class="num">1</span> Upload Video</div>', unsafe_allow_html=True)

up_col, info_col = st.columns([3, 2])
with up_col:
    vf = st.file_uploader(
        "Drag & drop or click to upload (MP4, MOV, MKV, AVI)",
        type=["mp4","mov","mkv","avi"], key="vid_up",
        label_visibility="collapsed",
    )
    if vf:
        p = save_upload(vf, "." + vf.name.rsplit(".", 1)[-1])
        st.session_state.src      = p
        st.session_state.src_name = vf.name
        st.video(vf)

with info_col:
    if st.session_state.src:
        inf = probe(st.session_state.src)
        st.success(f"✅  **{st.session_state.src_name}**")
        st.markdown(
            f"- **Resolution:** {inf['width']}×{inf['height']}\n"
            f"- **Duration:** {inf['duration']:.1f} s\n"
            f"- **FPS:** {inf['fps']}\n"
            f"- **Audio:** {'Yes ✅' if inf['has_audio'] else 'No ❌'}\n"
            f"- **Size:** {inf['size_mb']} MB"
        )
    else:
        st.info("Upload a video to get started.")

# Merge multiple clips
with st.expander("➕ Have multiple clips? Merge them first"):
    clips = st.file_uploader(
        "Upload clips in order",
        type=["mp4","mov","mkv","avi"],
        accept_multiple_files=True,
        key="clips_up",
    )
    if clips and st.button("Merge Clips", key="merge_btn"):
        with st.spinner(f"Merging {len(clips)} clips…"):
            paths = [save_upload(c, "." + c.name.rsplit(".",1)[-1]) for c in clips]
            result, err = do_merge(paths)
        if result:
            st.session_state.src      = result
            st.session_state.src_name = f"merged_{len(clips)}_clips.mp4"
            st.success(f"✅  Merged {len(clips)} clips — ready to edit!")
            st.rerun()
        else:
            st.error(f"Merge failed: {err}")

st.markdown('</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════
# SECTION 2 — CHOOSE EDITS
# ══════════════════════════════════════════════════════════════════
st.markdown('<div class="section">', unsafe_allow_html=True)
st.markdown('<div class="section-title"><span class="num">2</span> Choose Edits</div>', unsafe_allow_html=True)

dur = probe(st.session_state.src)["duration"] if st.session_state.src else 30.0

# ── Quick templates ─────────────────────────────────────────────
st.markdown("**⚡ Quick Templates** — one click to load a full edit")
tc = st.columns(len(TEMPLATES))
for i, (name, steps) in enumerate(TEMPLATES.items()):
    with tc[i]:
        if st.button(name, key=f"t{i}", use_container_width=True):
            st.session_state.queue = [dict(s) for s in steps]
            st.success(f"Loaded **{name}** — {len(steps)} steps ready")
            st.rerun()

st.markdown('<hr style="border:none;border-top:1px solid #e2e8f0;margin:1.2rem 0">', unsafe_allow_html=True)
st.markdown("**Or build your own edit step by step:**")

# ── Tabs for each edit type ──────────────────────────────────────
etabs = st.tabs(["✂️ Trim", "🎨 Filter", "⚡ Speed", "📝 Text",
                 "💧 Watermark", "🎵 Audio", "📊 Bar", "🔍 Zoom", "📐 Export"])

# ── TRIM ────────────────────────────────────────────────────────
with etabs[0]:
    c1, c2 = st.columns(2)
    with c1: s_t = st.number_input("Start (seconds)", 0.0, float(dur), 0.0, 0.5, key="tr_s")
    with c2: e_t = st.number_input("End (seconds)",   0.1, float(dur), float(dur), 0.5, key="tr_e")
    st.caption(f"Clip will be **{e_t - s_t:.1f} s** long")
    if st.button("➕ Add Trim", key="btn_trim"):
        if e_t > s_t:
            add_step({"type":"trim","start":s_t,"end":e_t})
        else:
            st.error("End time must be after start time.")

# ── FILTER ──────────────────────────────────────────────────────
with etabs[1]:
    c1, c2 = st.columns([1,1])
    with c1:
        fn = st.selectbox("Filter preset", list(FILTERS.keys()), key="flt_sel")
        descriptions = {
            "None":"No filter — use the sliders only.",
            "Vivid":"Boosted colours and contrast — great for Reels.",
            "Cinematic":"Teal & orange film look.",
            "Warm Sunset":"Golden lifestyle and travel tones.",
            "Cool Blue":"Clean, minimal, tech-forward look.",
            "Black & White":"Classic monochrome.",
            "Vintage":"Faded film aesthetic.",
            "HDR Pop":"High dynamic range with punch.",
            "Matte":"Lifted blacks — popular on Instagram.",
            "Neon Night":"Hyper-saturated neon for nightlife content.",
        }
        st.caption(descriptions.get(fn, ""))
    with c2:
        br = st.slider("Brightness", -0.5,  0.5, 0.0,  0.05, key="br")
        co = st.slider("Contrast",    0.5,  2.0, 1.0,  0.05, key="co")
        sa = st.slider("Saturation",  0.0,  3.0, 1.0,  0.1,  key="sa")
    if st.button("➕ Add Filter", key="btn_flt"):
        add_step({"type":"filter","filter":fn,"brightness":br,"contrast":co,"saturation":sa})

# ── SPEED ───────────────────────────────────────────────────────
with etabs[2]:
    spd = st.select_slider(
        "Speed multiplier",
        [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0, 4.0],
        value=1.0, key="spd_sl",
    )
    labels = {0.25:"Super slow-mo",0.5:"Slow motion",0.75:"Slightly slow",
              1.0:"Normal",1.25:"Slightly fast",1.5:"Fast",2.0:"Double speed",
              3.0:"Triple speed",4.0:"Time-lapse"}
    st.caption(f"{labels.get(spd,'')} — output will be **{dur/spd:.1f} s**")
    if st.button("➕ Add Speed", key="btn_spd"):
        add_step({"type":"speed","speed":spd})

# ── TEXT ────────────────────────────────────────────────────────
with etabs[3]:
    c1, c2 = st.columns(2)
    with c1:
        tx_txt   = st.text_input("Text content", "Your Title Here", key="tx_txt")
        tx_style = st.selectbox("Style", ["Custom","Lower Third","News Ticker","Title Card","Subtitle","Kinetic Bold"], key="tx_style")
        tx_anim  = st.selectbox("Animation", ["None","Fade In","Slide Up","Slide Left","Zoom In"], key="tx_anim")
        tx_fs    = st.slider("Font size", 16, 120, 52, key="tx_fs")
        tx_col   = st.color_picker("Text colour", "#FFFFFF", key="tx_col")
    with c2:
        tx_start = st.number_input("Show from (s)", 0.0, float(dur), 0.5, 0.5, key="tx_s")
        tx_end   = st.number_input("Hide at (s)",   0.1, float(dur), min(4.5, float(dur)), 0.5, key="tx_e")
        tx_x     = st.slider("X position %", 0, 90, 5,  key="tx_x")
        tx_y     = st.slider("Y position %", 0, 90, 80, key="tx_y")
        tx_shad  = st.checkbox("Drop shadow", True, key="tx_shad")
        tx_bg    = st.checkbox("Background box", False, key="tx_bg")
        if tx_bg:
            tx_bgcol = st.color_picker("Box colour", "#000000", key="tx_bgcol")
        else:
            tx_bgcol = "#000000"
    if st.button("➕ Add Text Layer", key="btn_txt"):
        add_step({
            "type":"text","text":tx_txt,"style":tx_style,"animation":tx_anim,
            "font_size":tx_fs,"color":tx_col,
            "x_pct":tx_x,"y_pct":tx_y,
            "start":tx_start,"end":tx_end,
            "shadow":tx_shad,"bg_box":tx_bg,"bg_color":tx_bgcol,
        })

# ── WATERMARK ───────────────────────────────────────────────────
with etabs[4]:
    wm_type = st.radio("Type", ["Text watermark", "Logo / image"], horizontal=True, key="wm_type")
    wm_pos  = st.selectbox("Position", ["Bottom Right","Bottom Left","Top Right","Top Left","Center"], key="wm_pos")
    wm_opa  = st.slider("Opacity", 0.1, 1.0, 0.75, 0.05, key="wm_opa")

    if wm_type == "Text watermark":
        wm_txt = st.text_input("Watermark text", "@yourbrand", key="wm_txt")
        wm_sz  = st.slider("Font size", 14, 72, 28, key="wm_sz")
        if st.button("➕ Add Text Watermark", key="btn_wmt"):
            add_step({"type":"watermark_text","text":wm_txt,"position":wm_pos,"opacity":wm_opa,"size":wm_sz})
    else:
        logo_f = st.file_uploader("Upload logo (PNG with transparency works best)", type=["png","jpg"], key="logo_up")
        if logo_f:
            st.session_state.logo_path = save_upload(logo_f, ".png")
            st.caption(f"✅ {logo_f.name} saved")
        logo_sz = st.slider("Logo size (% of video width)", 5, 40, 15, key="logo_sz")
        if st.button("➕ Add Logo Watermark", key="btn_wml"):
            if st.session_state.logo_path:
                add_step({"type":"watermark_logo","position":wm_pos,"opacity":wm_opa,"size_pct":logo_sz})
            else:
                st.error("Please upload a logo image first.")

# ── AUDIO ───────────────────────────────────────────────────────
with etabs[5]:
    aud_action = st.radio(
        "What do you want to do?",
        ["Mute (remove all audio)", "Adjust volume", "Replace with music track", "Mix music with original"],
        key="aud_action",
    )
    if "music" in aud_action.lower() or "mix" in aud_action.lower():
        aud_f = st.file_uploader("Upload music file (MP3 or WAV)", type=["mp3","wav"], key="aud_up")
        if aud_f:
            st.session_state.audio_path = save_upload(aud_f, "." + aud_f.name.rsplit(".",1)[-1])
            st.caption(f"✅ {aud_f.name} saved")

    if aud_action == "Adjust volume":
        vol_mult = st.slider("Volume multiplier", 0.1, 4.0, 1.5, 0.1, key="vol_mult")
        if st.button("➕ Add Volume Adjust", key="btn_vol"):
            add_step({"type":"audio_volume","multiplier":vol_mult})

    elif aud_action == "Mute (remove all audio)":
        if st.button("➕ Add Mute", key="btn_mute"):
            add_step({"type":"audio_mute"})

    elif aud_action == "Replace with music track":
        if st.button("➕ Add Replace Audio", key="btn_repl"):
            if st.session_state.audio_path:
                add_step({"type":"audio_replace"})
            else:
                st.error("Upload a music file first.")

    elif aud_action == "Mix music with original":
        c1, c2 = st.columns(2)
        with c1: mv = st.slider("Music volume",   0.0, 2.0, 0.5, 0.05, key="mv")
        with c2: ov = st.slider("Original volume",0.0, 2.0, 1.0, 0.05, key="ov")
        if st.button("➕ Add Mix Audio", key="btn_mix"):
            if st.session_state.audio_path:
                add_step({"type":"audio_mix","music_vol":mv,"orig_vol":ov})
            else:
                st.error("Upload a music file first.")

# ── PROGRESS BAR ────────────────────────────────────────────────
with etabs[6]:
    c1, c2, c3 = st.columns(3)
    with c1: pb_col = st.color_picker("Bar colour", "#e11d48", key="pb_col")
    with c2: pb_h   = st.slider("Height (px)", 2, 24, 8, key="pb_h")
    with c3: pb_pos = st.radio("Position", ["bottom","top"], horizontal=True, key="pb_pos")
    st.caption("A bar that fills left-to-right as the video plays — great for tutorials and vlogs.")
    if st.button("➕ Add Progress Bar", key="btn_pb"):
        add_step({"type":"progress_bar","color":pb_col,"height":pb_h,"position":pb_pos})

# ── KEN BURNS ───────────────────────────────────────────────────
with etabs[7]:
    c1, c2 = st.columns(2)
    with c1: kz_s = st.slider("Start zoom", 1.00, 1.50, 1.00, 0.01, key="kz_s")
    with c2: kz_e = st.slider("End zoom",   1.00, 1.50, 1.08, 0.01, key="kz_e")
    st.caption("Slow smooth zoom over the duration of the clip. Great for photos or talking-head shots.")
    if st.button("➕ Add Ken Burns Zoom", key="btn_kb"):
        add_step({"type":"kenburns","zoom_start":kz_s,"zoom_end":kz_e})

# ── EXPORT ──────────────────────────────────────────────────────
with etabs[8]:
    st.caption("This resizes and re-encodes to exact platform specs. Add it as the last step.")
    c1, c2, c3 = st.columns(3)
    with c1:
        exp_plat = st.selectbox("Platform", list(PLATFORMS.keys()), key="exp_plat")
        spec     = PLATFORMS[exp_plat]
        st.caption(f"{spec['w']}×{spec['h']} @ {spec['fps']}fps")
    with c2:
        exp_q = st.select_slider("Quality", ["Draft","Standard","High","Max"], value="High", key="exp_q")
    with c3:
        exp_fit = st.radio("Fit mode", ["Crop to fill","Letterbox (black bars)"], key="exp_fit")
    if st.button("➕ Add Export Step", key="btn_exp"):
        add_step({
            "type":"export","platform":exp_plat,"quality":exp_q,
            "fit":"crop" if "Crop" in exp_fit else "letterbox",
        })

st.markdown('</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════
# SECTION 3 — EDIT QUEUE
# ══════════════════════════════════════════════════════════════════
if st.session_state.queue:
    st.markdown('<div class="section">', unsafe_allow_html=True)
    h1, h2 = st.columns([5,1])
    with h1:
        st.markdown(
            f'<div class="section-title"><span class="num">✓</span> '
            f'Edit Queue &nbsp;—&nbsp; {len(st.session_state.queue)} step(s)</div>',
            unsafe_allow_html=True,
        )
    with h2:
        if st.button("Clear All", key="clear_q"):
            st.session_state.queue = []
            st.rerun()

    for i, step in enumerate(st.session_state.queue):
        ic   = STEP_ICONS.get(step["type"], "•")
        name = step["type"].replace("_", " ").title()
        det  = step_detail(step)
        col_item, col_del = st.columns([9, 1])
        with col_item:
            st.markdown(
                f'<div class="qitem">'
                f'<div class="qi-name">{ic} {name}</div>'
                f'<div class="qi-detail">{det}</div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        with col_del:
            if st.button("🗑", key=f"del_{i}", help="Remove this step"):
                st.session_state.queue.pop(i)
                st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════
# SECTION 4 — RENDER
# ══════════════════════════════════════════════════════════════════
st.markdown('<div class="section">', unsafe_allow_html=True)
st.markdown('<div class="section-title"><span class="num">3</span> Render & Download</div>', unsafe_allow_html=True)

if not st.session_state.src:
    st.info("Upload a video in Step 1 to get started.")
elif not st.session_state.queue:
    st.info("Choose at least one edit in Step 2, then render.")
else:
    n = len(st.session_state.queue)
    st.markdown(f"**{n} edit step(s)** queued on **{st.session_state.src_name}**")

    if st.button("🎬 Render Video Now", key="render_btn", type="primary", use_container_width=False):
        prog    = st.progress(0, text="Starting render…")
        log_box = st.empty()

        final, log = run_pipeline(
            st.session_state.src,
            st.session_state.queue,
            audio_path = st.session_state.audio_path,
            logo_path  = st.session_state.logo_path,
        )

        prog.empty()
        # Show log
        with st.expander("Render log", expanded=(final is None)):
            for line in log:
                st.text(line)

        if final and os.path.exists(final) and os.path.getsize(final) > 1000:
            save_history(st.session_state.src_name, f"Rendered {n} steps")
            st.success("🎉 Render complete!")

            result_col, preview_col = st.columns([1, 1])
            with result_col:
                sz = round(os.path.getsize(final) / 1_048_576, 1)
                inf2 = probe(final)
                st.markdown(
                    f"- **Resolution:** {inf2['width']}×{inf2['height']}\n"
                    f"- **Duration:** {inf2['duration']:.1f} s\n"
                    f"- **File size:** {sz} MB"
                )
                with open(final, "rb") as f:
                    st.download_button(
                        "⬇️ Download Video",
                        f.read(),
                        file_name = "studio_output.mp4",
                        mime      = "video/mp4",
                        key       = "dl_btn",
                        use_container_width = True,
                    )
            with preview_col:
                frame = extract_frame(final, ts=min(1.0, inf2["duration"] / 2))
                if frame:
                    st.image(frame, caption="Preview frame from rendered video", use_container_width=True)
        else:
            st.error("Render failed. Check the log above for details.")

st.markdown('</div>', unsafe_allow_html=True)
