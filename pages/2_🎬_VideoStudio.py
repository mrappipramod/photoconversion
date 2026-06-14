import streamlit as st
import os, shutil
from utils import inject_css, save_upload, save_history
from video_engine import (
    probe, run_pipeline, extract_frame, extract_frames, do_merge,
    FILTERS, PLATFORMS,
)

st.set_page_config(page_title="Video Studio", page_icon="🎬",
                   layout="wide", initial_sidebar_state="collapsed")
inject_css()
st.markdown("""<style>
.stTabs [aria-selected="true"]{background:#fff1f2!important;color:#e11d48!important}
.stButton>button{background:linear-gradient(135deg,#e11d48,#7c3aed)!important;
  color:white!important;border:none!important;border-radius:8px!important;font-weight:600!important}
.stDownloadButton>button{background:#fff1f2!important;color:#e11d48!important;
  border:1px solid #fecdd3!important;border-radius:8px!important;font-weight:600!important}
.sec{background:#fff;border:1px solid #e2e8f0;border-radius:14px;
  padding:1.4rem 1.6rem;margin-bottom:1.2rem}
.sec-title{font-family:'Space Grotesk',sans-serif;font-size:1rem;font-weight:700;
  color:#1e293b;margin-bottom:1rem;display:flex;align-items:center;gap:8px}
.num{display:inline-flex;align-items:center;justify-content:center;
  width:26px;height:26px;background:linear-gradient(135deg,#e11d48,#7c3aed);
  color:white;border-radius:50%;font-size:12px;font-weight:700;flex-shrink:0}
.qi{background:#f8fafc;border:1px solid #e2e8f0;border-left:4px solid #e11d48;
  border-radius:8px;padding:.5rem 1rem;margin-bottom:.35rem}
.qi-n{font-size:.88rem;font-weight:600;color:#1e293b}
.qi-d{font-size:.75rem;color:#64748b;margin-top:2px}
.tmpl-card{background:#fff;border:1.5px solid #e2e8f0;border-radius:12px;
  padding:.9rem 1rem;cursor:pointer;transition:border .15s}
.tmpl-card:hover{border-color:#e11d48}
.tmpl-icon{font-size:1.6rem;margin-bottom:.3rem}
.tmpl-name{font-size:.85rem;font-weight:700;color:#1e293b}
.tmpl-desc{font-size:.73rem;color:#64748b;margin-top:3px;line-height:1.4}
.prev-frame{border-radius:8px;border:1px solid #e2e8f0}
</style>""", unsafe_allow_html=True)

with st.sidebar:
    st.page_link("app.py", label="← Home", icon="🏠")
    st.page_link("pages/1_📄_SmartDoc.py", label="📄 SmartDoc Studio")

# ── session defaults ───────────────────────────────────────────────
for k,v in {"src":None,"src_name":"","src2":None,
            "audio_path":None,"logo_path":None,"queue":[]}.items():
    if k not in st.session_state: st.session_state[k]=v

def add(step): st.session_state.queue.append(step); st.rerun()

STEP_ICON = {
    "trim":"✂️","filter":"🎨","speed":"⚡","text":"📝",
    "watermark_text":"💧","watermark_logo":"🖼️","progress_bar":"📊",
    "kenburns":"🔍","fade":"🌅","blur":"🌫️","split_screen":"⬛",
    "auto_subtitles":"💬","emoji":"⭐",
    "audio_mute":"🔇","audio_volume":"🔊","audio_replace":"🎵","audio_mix":"🎵",
    "export":"📐",
}

def step_label(s):
    t=s.get("type","")
    if t=="trim":           return f'{s.get("start",0):.1f}s → {s.get("end",0):.1f}s'
    if t=="filter":         return f'{s.get("filter","None")} | br:{s.get("brightness",0):+.2f} co:{s.get("contrast",1):.1f} sa:{s.get("saturation",1):.1f}'
    if t=="speed":          return f'×{s.get("speed",1)}'
    if t=="text":           return f'"{s.get("text","")[:28]}" {s.get("style","")} {s.get("start",0):.1f}–{s.get("end",0):.1f}s'
    if t=="auto_subtitles": return f'"{s.get("text","")[:30]}…" auto-split'
    if t=="watermark_text": return f'"{s.get("text","")}" {s.get("position","")}'
    if t=="watermark_logo": return f'{s.get("position","")} {s.get("size_pct",15)}%'
    if t=="progress_bar":   return f'{s.get("position","bottom")} {s.get("color","")} {s.get("height",8)}px'
    if t=="kenburns":       return f'zoom {s.get("zoom_start",1):.2f}→{s.get("zoom_end",1.08):.2f}'
    if t=="fade":           return f'in {s.get("fade_in",.5)}s  out {s.get("fade_out",.5)}s'
    if t=="blur":           return f'strength {s.get("strength",20)}'
    if t=="split_screen":   return s.get("layout","side-by-side")
    if t=="emoji":          return f'{s.get("text","⭐")} at {s.get("x_pct",50)}%,{s.get("y_pct",10)}%'
    if t=="audio_volume":   return f'×{s.get("multiplier",1.5)}'
    if t=="audio_mix":      return f'music {s.get("music_vol",.5)} + orig {s.get("orig_vol",1)}'
    if t=="export":         return f'{s.get("platform","")} {s.get("quality","High")}'
    return ""

# ── templates ──────────────────────────────────────────────────────
TEMPLATES = {
    "🔥 Viral Reel": {
        "desc": "Vivid grade · watermark · Reels export",
        "steps": [
            {"type":"filter","filter":"Vivid","brightness":0.05,"contrast":1.1,"saturation":1.8},
            {"type":"watermark_text","text":"@yourbrand","position":"Bottom Right","opacity":0.75,"size":28},
            {"type":"export","platform":"Instagram Reels (9:16)","quality":"High","fit":"crop"},
        ]},
    "🎬 Cinematic": {
        "desc": "Film grade · Ken Burns zoom · Shorts export",
        "steps": [
            {"type":"filter","filter":"Cinematic","brightness":-0.03,"contrast":1.2,"saturation":0.85},
            {"type":"kenburns","zoom_start":1.0,"zoom_end":1.08},
            {"type":"fade","fade_in":0.5,"fade_out":0.5},
            {"type":"export","platform":"YouTube Shorts (9:16)","quality":"Max","fit":"letterbox"},
        ]},
    "🌅 Travel Vlog": {
        "desc": "Warm tones · lower third · YouTube",
        "steps": [
            {"type":"filter","filter":"Warm Sunset","brightness":0.04,"contrast":1.0,"saturation":1.3},
            {"type":"text","text":"Your Destination","style":"Lower Third","font_size":52,
             "color":"#FFFFFF","x_pct":5,"y_pct":78,"start":1.0,"end":4.5,"shadow":True},
            {"type":"export","platform":"YouTube (16:9)","quality":"High","fit":"letterbox"},
        ]},
    "🎵 Music Video": {
        "desc": "Neon grade · watermark · Reels",
        "steps": [
            {"type":"filter","filter":"Neon Night","brightness":-0.05,"contrast":1.4,"saturation":2.2},
            {"type":"watermark_text","text":"@yourbrand","position":"Bottom Right","opacity":0.8,"size":28},
            {"type":"export","platform":"Instagram Reels (9:16)","quality":"High","fit":"crop"},
        ]},
    "📰 News / Talk": {
        "desc": "Clean grade · progress bar · news ticker",
        "steps": [
            {"type":"filter","filter":"None","brightness":0.02,"contrast":1.05,"saturation":1.0},
            {"type":"progress_bar","color":"#e11d48","height":8,"position":"bottom"},
            {"type":"text","text":"Breaking News","style":"News Ticker","font_size":40,
             "color":"#FFFFFF","x_pct":2,"y_pct":87,"start":0.5,"end":5.0,"shadow":True},
            {"type":"export","platform":"YouTube (16:9)","quality":"High","fit":"letterbox"},
        ]},
    "💼 Corporate": {
        "desc": "Clean grade · logo watermark · progress bar",
        "steps": [
            {"type":"filter","filter":"Cool Blue","brightness":0.02,"contrast":1.08,"saturation":0.95},
            {"type":"progress_bar","color":"#2563eb","height":6,"position":"bottom"},
            {"type":"watermark_logo","position":"Top Right","opacity":0.85,"size_pct":12},
            {"type":"export","platform":"YouTube (16:9)","quality":"High","fit":"letterbox"},
        ]},
    "🍳 Recipe / Food": {
        "desc": "Warm tones · auto-captions · ingredient text",
        "steps": [
            {"type":"filter","filter":"Warm Sunset","brightness":0.05,"contrast":1.05,"saturation":1.4},
            {"type":"text","text":"Step 1: Prep ingredients","style":"Lower Third","font_size":44,
             "color":"#FFFFFF","x_pct":4,"y_pct":80,"start":1.0,"end":5.0,"shadow":True},
            {"type":"text","text":"Step 2: Cook on medium heat","style":"Lower Third","font_size":44,
             "color":"#FFFFFF","x_pct":4,"y_pct":80,"start":6.0,"end":10.0,"shadow":True},
            {"type":"export","platform":"YouTube (16:9)","quality":"High","fit":"crop"},
        ]},
    "🎉 Event Promo": {
        "desc": "Neon filter · countdown text · upbeat Reels",
        "steps": [
            {"type":"filter","filter":"Neon Night","brightness":-0.03,"contrast":1.3,"saturation":2.0},
            {"type":"text","text":"COMING SOON","style":"Title Card","font_size":72,
             "color":"#FFDD00","x_pct":10,"y_pct":35,"start":0.5,"end":3.5,"shadow":True,"pill":True,"bg_box":True,"bg_color":"#000000"},
            {"type":"text","text":"Save the Date","style":"Custom","font_size":48,
             "color":"#FFFFFF","x_pct":20,"y_pct":55,"start":1.0,"end":4.0,"shadow":True},
            {"type":"fade","fade_in":0.5,"fade_out":0.8},
            {"type":"export","platform":"Instagram Reels (9:16)","quality":"High","fit":"crop"},
        ]},
    "🏠 Real Estate": {
        "desc": "Ken Burns · property details · warm tones",
        "steps": [
            {"type":"filter","filter":"Warm Sunset","brightness":0.03,"contrast":1.05,"saturation":1.2},
            {"type":"kenburns","zoom_start":1.0,"zoom_end":1.12},
            {"type":"text","text":"3 Bed · 2 Bath · $850,000","style":"Lower Third","font_size":46,
             "color":"#FFFFFF","x_pct":4,"y_pct":80,"start":1.5,"end":5.0,"shadow":True},
            {"type":"text","text":"Contact: agent@realty.com","style":"Subtitle","font_size":34,
             "color":"#FFFFFF","x_pct":4,"y_pct":90,"start":2.0,"end":5.0,"shadow":True},
            {"type":"export","platform":"YouTube (16:9)","quality":"High","fit":"letterbox"},
        ]},
    "⚽ Sports Highlight": {
        "desc": "Vivid grade · score overlay · team watermark",
        "steps": [
            {"type":"filter","filter":"Vivid","brightness":0.05,"contrast":1.2,"saturation":1.9},
            {"type":"speed","speed":1.25},
            {"type":"text","text":"GOAL! 2 – 1","style":"Title Card","font_size":64,
             "color":"#FFFFFF","x_pct":5,"y_pct":5,"start":0.5,"end":4.0,"shadow":True,
             "bg_box":True,"bg_color":"#e11d48","pill":True},
            {"type":"watermark_text","text":"@YourTeam","position":"Bottom Right","opacity":0.85,"size":30},
            {"type":"export","platform":"YouTube (16:9)","quality":"High","fit":"crop"},
        ]},
    "💡 Motivational": {
        "desc": "Bold centred text · fade · matte grade",
        "steps": [
            {"type":"filter","filter":"Matte","brightness":0.0,"contrast":1.1,"saturation":0.9},
            {"type":"text","text":"Believe in yourself.","style":"Custom","font_size":72,
             "color":"#FFFFFF","x_pct":8,"y_pct":40,"start":0.5,"end":5.0,
             "shadow":True,"bg_box":True,"bg_color":"#000000","pill":True},
            {"type":"fade","fade_in":1.0,"fade_out":1.0},
            {"type":"export","platform":"Instagram Reels (9:16)","quality":"High","fit":"crop"},
        ]},
    "🛍️ Product Review": {
        "desc": "Zoom highlights · rating overlay · Shorts",
        "steps": [
            {"type":"filter","filter":"Vivid","brightness":0.03,"contrast":1.1,"saturation":1.5},
            {"type":"kenburns","zoom_start":1.0,"zoom_end":1.15},
            {"type":"text","text":"★★★★★  5/5","style":"Title Card","font_size":52,
             "color":"#FFDD00","x_pct":5,"y_pct":8,"start":1.0,"end":4.0,"shadow":True,
             "bg_box":True,"bg_color":"#000000"},
            {"type":"text","text":"10/10 — Would recommend!","style":"Subtitle","font_size":36,
             "color":"#FFFFFF","x_pct":5,"y_pct":85,"start":2.0,"end":5.5,"shadow":True},
            {"type":"export","platform":"YouTube Shorts (9:16)","quality":"High","fit":"crop"},
        ]},
    "🎙️ Podcast Clip": {
        "desc": "Clean grade · guest lower third · progress bar",
        "steps": [
            {"type":"filter","filter":"Cool Blue","brightness":0.0,"contrast":1.05,"saturation":0.9},
            {"type":"progress_bar","color":"#7c3aed","height":5,"position":"bottom"},
            {"type":"text","text":"Jane Smith · CEO, Acme Corp","style":"Lower Third","font_size":42,
             "color":"#FFFFFF","x_pct":4,"y_pct":82,"start":0.5,"end":5.0,"shadow":True},
            {"type":"export","platform":"YouTube (16:9)","quality":"High","fit":"letterbox"},
        ]},
    "📚 YouTube Tutorial": {
        "desc": "Intro card · chapter text · end screen",
        "steps": [
            {"type":"filter","filter":"None","brightness":0.02,"contrast":1.05,"saturation":1.0},
            {"type":"text","text":"How to Edit Videos Like a Pro","style":"Title Card","font_size":56,
             "color":"#FFFFFF","x_pct":5,"y_pct":35,"start":0.0,"end":4.0,"shadow":True,
             "bg_box":True,"bg_color":"#000000"},
            {"type":"text","text":"Chapter 1: Getting Started","style":"Lower Third","font_size":40,
             "color":"#FFFFFF","x_pct":4,"y_pct":80,"start":5.0,"end":9.0,"shadow":True},
            {"type":"progress_bar","color":"#e11d48","height":5,"position":"top"},
            {"type":"export","platform":"YouTube (16:9)","quality":"High","fit":"letterbox"},
        ]},
    "📱 Instagram Story": {
        "desc": "9:16 · CTA text · swipe up sticker",
        "steps": [
            {"type":"filter","filter":"Vivid","brightness":0.04,"contrast":1.1,"saturation":1.6},
            {"type":"text","text":"SWIPE UP 👆","style":"Custom","font_size":52,
             "color":"#FFFFFF","x_pct":28,"y_pct":88,"start":0.5,"end":999,
             "shadow":True,"bg_box":True,"bg_color":"#e11d48","pill":True},
            {"type":"text","text":"Limited offer — today only!","style":"Custom","font_size":40,
             "color":"#FFDD00","x_pct":8,"y_pct":75,"start":1.0,"end":999,"shadow":True},
            {"type":"export","platform":"Instagram Reels (9:16)","quality":"High","fit":"crop"},
        ]},
    "⚡ Quick Export": {
        "desc": "No edits — just resize for your platform",
        "steps": [
            {"type":"export","platform":"Instagram Reels (9:16)","quality":"Standard","fit":"crop"},
        ]},
}

# ══ HEADER ════════════════════════════════════════════════════════
st.markdown(
    '<div style="font-family:\'Space Grotesk\',sans-serif;font-size:2rem;font-weight:700;'
    'background:linear-gradient(135deg,#e11d48,#7c3aed);'
    '-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:2px">'
    '🎬 Video Studio</div>', unsafe_allow_html=True)
st.markdown('<div style="color:#64748b;font-size:.9rem;margin-bottom:1.4rem">'
            'Upload → Choose edits → Preview → Render → Download</div>',
            unsafe_allow_html=True)

# ══ STEP 1 — UPLOAD ═══════════════════════════════════════════════
st.markdown('<div class="sec">', unsafe_allow_html=True)
st.markdown('<div class="sec-title"><span class="num">1</span> Upload Video</div>',
            unsafe_allow_html=True)

up_col, info_col = st.columns([3, 2])
with up_col:
    vf = st.file_uploader("MP4, MOV, MKV or AVI", type=["mp4","mov","mkv","avi"],
                           key="vid_up", label_visibility="collapsed")
    if vf:
        p = save_upload(vf, "." + vf.name.rsplit(".",1)[-1])
        st.session_state.src      = p
        st.session_state.src_name = vf.name
        st.video(vf)

with info_col:
    if st.session_state.src:
        inf = probe(st.session_state.src)
        st.success(f"✅ **{st.session_state.src_name}**")
        st.markdown(
            f"- **Resolution:** {inf['width']}×{inf['height']}\n"
            f"- **Duration:** {inf['duration']:.1f} s\n"
            f"- **FPS:** {inf['fps']}\n"
            f"- **Audio:** {'Yes ✅' if inf['has_audio'] else 'No ❌'}\n"
            f"- **Size:** {inf['size_mb']} MB")

        # ── FRAME SCRUBBER PREVIEW ─────────────────────────────
        st.markdown("**🎞️ Preview frames — scrub through your video:**")
        dur = inf["duration"]
        ts  = st.slider("Timestamp (s)", 0.0, float(max(dur-0.1,0.1)),
                        float(dur/2), 0.1, key="scrub_ts",
                        format="%.1fs")
        if st.button("📷 Capture Frame", key="cap_frame"):
            img = extract_frame(st.session_state.src, ts)
            if img:
                st.image(img, caption=f"Frame at {ts:.1f}s",
                         use_container_width=True)
            else:
                st.warning("Could not extract frame.")

        # Thumbnail strip
        if st.button("🎞️ Show 5-frame strip", key="strip_btn"):
            with st.spinner("Extracting frames…"):
                frames = extract_frames(st.session_state.src, 5)
            if frames:
                cols = st.columns(5)
                for (t2,img),col in zip(frames,cols):
                    with col:
                        st.image(img, caption=f"{t2}s", use_container_width=True)
    else:
        st.info("Upload a video to get started.")

with st.expander("➕ Merge multiple clips into one"):
    clips = st.file_uploader("Upload clips in order",
                              type=["mp4","mov","mkv","avi"],
                              accept_multiple_files=True, key="clips_up")
    if clips and st.button("Merge Clips", key="merge_btn"):
        with st.spinner(f"Merging {len(clips)} clips…"):
            paths  = [save_upload(c, "."+c.name.rsplit(".",1)[-1]) for c in clips]
            result, err = do_merge(paths)
        if result:
            st.session_state.src      = result
            st.session_state.src_name = f"merged_{len(clips)}_clips.mp4"
            st.success(f"✅ Merged {len(clips)} clips!")
            st.rerun()
        else:
            st.error(f"Merge failed: {err}")

with st.expander("➕ Upload second video (for split screen)"):
    vf2 = st.file_uploader("Second video", type=["mp4","mov","mkv","avi"], key="vid2_up")
    if vf2:
        st.session_state.src2 = save_upload(vf2, "."+vf2.name.rsplit(".",1)[-1])
        st.caption(f"✅ {vf2.name}")

st.markdown('</div>', unsafe_allow_html=True)

# ══ STEP 2 — CHOOSE EDITS ═════════════════════════════════════════
st.markdown('<div class="sec">', unsafe_allow_html=True)
st.markdown('<div class="sec-title"><span class="num">2</span> Choose Edits</div>',
            unsafe_allow_html=True)

dur = probe(st.session_state.src)["duration"] if st.session_state.src else 30.0

# ── Templates grid ─────────────────────────────────────────────
st.markdown("**⚡ Templates — one click to load a complete edit**")
rows = [list(TEMPLATES.items())[i:i+4] for i in range(0, len(TEMPLATES), 4)]
for row in rows:
    cols = st.columns(4)
    for col, (name, tmpl) in zip(cols, row):
        with col:
            icon = name.split()[0]
            label = " ".join(name.split()[1:])
            st.markdown(
                f'<div class="tmpl-card">'
                f'<div class="tmpl-icon">{icon}</div>'
                f'<div class="tmpl-name">{label}</div>'
                f'<div class="tmpl-desc">{tmpl["desc"]}</div>'
                f'</div>', unsafe_allow_html=True)
            if st.button("Load", key=f"t_{name}", use_container_width=True):
                st.session_state.queue = [dict(s) for s in tmpl["steps"]]
                st.success(f"Loaded **{name}** — {len(tmpl['steps'])} steps")
                st.rerun()

st.markdown('<hr style="border:none;border-top:1px solid #e2e8f0;margin:1.2rem 0">',
            unsafe_allow_html=True)
st.markdown("**Or build your own edit:**")

etabs = st.tabs(["✂️ Trim","🎨 Filter","⚡ Speed","📝 Text","💬 Auto Subtitles",
                 "⭐ Emoji","💧 Watermark","🎵 Audio","📊 Bar",
                 "🔍 Zoom","🌅 Fade","🌫️ Blur","⬛ Split Screen","📐 Export"])

# TRIM
with etabs[0]:
    c1,c2 = st.columns(2)
    with c1: s_t = st.number_input("Start (s)",0.0,float(dur),0.0,0.5,key="tr_s")
    with c2: e_t = st.number_input("End (s)",0.1,float(dur),float(dur),0.5,key="tr_e")
    st.caption(f"Clip will be **{e_t-s_t:.1f}s** long")
    if st.button("➕ Add Trim",key="btn_trim"):
        if e_t>s_t: add({"type":"trim","start":s_t,"end":e_t})
        else: st.error("End must be after start.")

# FILTER
with etabs[1]:
    c1,c2 = st.columns(2)
    with c1:
        fn = st.selectbox("Filter preset",list(FILTERS.keys()),key="flt_sel")
        st.caption({"None":"Sliders only.","Vivid":"Boosted colours — great for Reels.",
                    "Cinematic":"Teal & orange film look.","Warm Sunset":"Golden lifestyle tones.",
                    "Cool Blue":"Clean minimal look.","Black & White":"Classic monochrome.",
                    "Vintage":"Faded film aesthetic.","HDR Pop":"High dynamic range.",
                    "Matte":"Lifted blacks — popular on Instagram.",
                    "Neon Night":"Hyper-saturated neon."}.get(fn,""))
    with c2:
        br = st.slider("Brightness",-0.5,0.5,0.0,0.05,key="br")
        co = st.slider("Contrast",0.5,2.0,1.0,0.05,key="co")
        sa = st.slider("Saturation",0.0,3.0,1.0,0.1,key="sa")
    if st.button("➕ Add Filter",key="btn_flt"):
        add({"type":"filter","filter":fn,"brightness":br,"contrast":co,"saturation":sa})

# SPEED
with etabs[2]:
    spd = st.select_slider("Speed",[0.25,0.5,0.75,1.0,1.25,1.5,2.0,3.0,4.0],
                           value=1.0,key="spd_sl")
    st.caption({0.25:"Super slow-mo",0.5:"Slow motion",0.75:"Slightly slow",
                1.0:"Normal speed",1.25:"Slightly fast",1.5:"Fast",
                2.0:"Double speed",3.0:"Triple",4.0:"Time-lapse"}.get(spd,"")
               + f" — output: {dur/spd:.1f}s")
    if st.button("➕ Add Speed",key="btn_spd"):
        add({"type":"speed","speed":spd})

# TEXT
with etabs[3]:
    c1,c2 = st.columns(2)
    with c1:
        tx   = st.text_input("Text content","Your Title Here",key="tx")
        txs  = st.selectbox("Style",["Custom","Lower Third","News Ticker","Title Card","Subtitle"],key="txs")
        txfs = st.slider("Font size",16,120,52,key="txfs")
        txcl = st.color_picker("Text colour","#FFFFFF",key="txcl")
        txsh = st.checkbox("Drop shadow",True,key="txsh")
        txbg = st.checkbox("Background box",False,key="txbg")
        txpl = st.checkbox("Pill style",False,key="txpl")
        if txbg or txpl:
            txbc = st.color_picker("Box colour","#000000",key="txbc")
        else: txbc="#000000"
    with c2:
        txts = st.number_input("Show from (s)",0.0,float(dur),0.5,0.5,key="txts")
        txte = st.number_input("Hide at (s)",0.1,float(dur),min(4.5,float(dur)),0.5,key="txte")
        txx  = st.slider("X position %",0,90,5,key="txx")
        txy  = st.slider("Y position %",0,90,80,key="txy")
    if st.button("➕ Add Text Layer",key="btn_txt"):
        add({"type":"text","text":tx,"style":txs,"font_size":txfs,
             "color":txcl,"x_pct":txx,"y_pct":txy,
             "start":txts,"end":txte,
             "shadow":txsh,"bg_box":txbg,"bg_color":txbc,"pill":txpl})

# AUTO SUBTITLES
with etabs[4]:
    st.caption("Type your full script — it will be auto-split into timed subtitle lines.")
    sub_text = st.text_area("Full script / transcript",
                            "Welcome to this video. Today we will learn something amazing. "
                            "Let us get started with the basics.",key="sub_text",height=100)
    c1,c2,c3 = st.columns(3)
    with c1: wpl = st.number_input("Words per line",2,12,6,key="wpl")
    with c2: lpd = st.number_input("Seconds per line",1.0,6.0,2.5,0.5,key="lpd")
    with c3:
        sub_fs  = st.slider("Font size",20,72,38,key="sub_fs")
        sub_col = st.color_picker("Colour","#FFFFFF",key="sub_col")
    if st.button("➕ Add Auto Subtitles",key="btn_sub"):
        add({"type":"auto_subtitles","text":sub_text,
             "words_per_line":int(wpl),"line_duration":float(lpd),
             "font_size":sub_fs,"color":sub_col,"y_pct":85})

# EMOJI / STICKER
with etabs[5]:
    st.caption("Overlay an emoji or any Unicode symbol as a sticker on your video.")
    em_txt  = st.text_input("Emoji / sticker","⭐",key="em_txt")
    em_size = st.slider("Size",30,200,80,key="em_sz")
    c1,c2   = st.columns(2)
    with c1:
        em_x = st.slider("X %",0,90,50,key="em_x")
        em_y = st.slider("Y %",0,90,5,key="em_y")
    with c2:
        em_s = st.number_input("From (s)",0.0,float(dur),0.0,0.5,key="em_s")
        em_e = st.number_input("To (s)",0.1,float(dur),float(dur),0.5,key="em_e")
    if st.button("➕ Add Emoji",key="btn_em"):
        add({"type":"emoji","text":em_txt,"font_size":em_size,
             "x_pct":em_x,"y_pct":em_y,"start":em_s,"end":em_e})

# WATERMARK
with etabs[6]:
    wm_type = st.radio("Type",["Text","Logo / image"],horizontal=True,key="wm_type")
    wm_pos  = st.selectbox("Position",["Bottom Right","Bottom Left","Top Right","Top Left","Center"],key="wm_pos")
    wm_opa  = st.slider("Opacity",0.1,1.0,0.75,0.05,key="wm_opa")
    if wm_type=="Text":
        wm_txt = st.text_input("Watermark text","@yourbrand",key="wm_txt")
        wm_sz  = st.slider("Font size",14,72,28,key="wm_sz")
        if st.button("➕ Add Text Watermark",key="btn_wmt"):
            add({"type":"watermark_text","text":wm_txt,"position":wm_pos,"opacity":wm_opa,"size":wm_sz})
    else:
        lf = st.file_uploader("Logo (PNG)",type=["png","jpg"],key="logo_up")
        if lf:
            st.session_state.logo_path = save_upload(lf,".png")
            st.caption(f"✅ {lf.name}")
        lsz = st.slider("Logo size %",5,40,15,key="lsz")
        if st.button("➕ Add Logo",key="btn_wml"):
            if st.session_state.logo_path:
                add({"type":"watermark_logo","position":wm_pos,"opacity":wm_opa,"size_pct":lsz})
            else: st.error("Upload a logo first.")

# AUDIO
with etabs[7]:
    aa = st.radio("Action",["Mute","Adjust volume","Replace with music","Mix music + original"],
                  key="aa",horizontal=True)
    if "music" in aa.lower() or "mix" in aa.lower():
        af2 = st.file_uploader("Music (MP3/WAV)",type=["mp3","wav"],key="aud_up")
        if af2:
            st.session_state.audio_path = save_upload(af2,"."+af2.name.rsplit(".",1)[-1])
            st.caption(f"✅ {af2.name}")
    if aa=="Mute":
        if st.button("➕ Add Mute",key="btn_mute"): add({"type":"audio_mute"})
    elif aa=="Adjust volume":
        vm = st.slider("Volume ×",0.1,4.0,1.5,0.1,key="vm")
        if st.button("➕ Add Volume",key="btn_vol"): add({"type":"audio_volume","multiplier":vm})
    elif aa=="Replace with music":
        if st.button("➕ Add Replace",key="btn_repl"):
            if st.session_state.audio_path: add({"type":"audio_replace"})
            else: st.error("Upload music first.")
    else:
        c1,c2 = st.columns(2)
        with c1: mv2=st.slider("Music vol",0.0,2.0,0.5,0.05,key="mv2")
        with c2: ov2=st.slider("Original vol",0.0,2.0,1.0,0.05,key="ov2")
        if st.button("➕ Add Mix",key="btn_mix"):
            if st.session_state.audio_path: add({"type":"audio_mix","music_vol":mv2,"orig_vol":ov2})
            else: st.error("Upload music first.")

# PROGRESS BAR
with etabs[8]:
    c1,c2,c3 = st.columns(3)
    with c1: pb_c=st.color_picker("Colour","#e11d48",key="pb_c")
    with c2: pb_h=st.slider("Height px",2,24,8,key="pb_h")
    with c3: pb_p=st.radio("Position",["bottom","top"],horizontal=True,key="pb_p")
    st.caption("Fills left→right as the video plays.")
    if st.button("➕ Add Progress Bar",key="btn_pb"):
        add({"type":"progress_bar","color":pb_c,"height":pb_h,"position":pb_p})

# KEN BURNS
with etabs[9]:
    c1,c2=st.columns(2)
    with c1: kzs=st.slider("Start zoom",1.00,1.50,1.00,0.01,key="kzs")
    with c2: kze=st.slider("End zoom",1.00,1.50,1.08,0.01,key="kze")
    st.caption("Smooth slow zoom over the full clip.")
    if st.button("➕ Add Zoom",key="btn_kb"):
        add({"type":"kenburns","zoom_start":kzs,"zoom_end":kze})

# FADE
with etabs[10]:
    c1,c2=st.columns(2)
    with c1: fi=st.slider("Fade in (s)",0.0,3.0,0.5,0.1,key="fi")
    with c2: fo=st.slider("Fade out (s)",0.0,3.0,0.5,0.1,key="fo")
    st.caption("Fades video and audio in at start, out at end.")
    if st.button("➕ Add Fade",key="btn_fade"):
        add({"type":"fade","fade_in":fi,"fade_out":fo})

# BLUR
with etabs[11]:
    bls=st.slider("Blur strength",5,50,20,key="bls")
    st.caption("Blurs the entire frame — useful for background effects or dreamlike look.")
    if st.button("➕ Add Blur",key="btn_blur"):
        add({"type":"blur","strength":bls})

# SPLIT SCREEN
with etabs[12]:
    slay=st.radio("Layout",["side-by-side","top-bottom"],horizontal=True,key="slay")
    st.caption("Combines your main video with the second video uploaded above.")
    if not st.session_state.src2:
        st.warning("Upload a second video using the expander in Step 1 first.")
    if st.button("➕ Add Split Screen",key="btn_split"):
        if st.session_state.src2:
            add({"type":"split_screen","layout":slay})
        else: st.error("Upload a second video first.")

# EXPORT
with etabs[13]:
    c1,c2,c3=st.columns(3)
    with c1:
        ep=st.selectbox("Platform",list(PLATFORMS.keys()),key="ep")
        sp=PLATFORMS[ep]; st.caption(f"{sp['w']}×{sp['h']} @ {sp['fps']}fps")
    with c2: eq=st.select_slider("Quality",["Draft","Standard","High","Max"],value="High",key="eq")
    with c3: ef=st.radio("Fit",["Crop to fill","Letterbox"],key="ef")
    if st.button("➕ Add Export",key="btn_exp"):
        add({"type":"export","platform":ep,"quality":eq,
             "fit":"crop" if "Crop" in ef else "letterbox"})

st.markdown('</div>', unsafe_allow_html=True)

# ══ EDIT QUEUE ════════════════════════════════════════════════════
if st.session_state.queue:
    st.markdown('<div class="sec">', unsafe_allow_html=True)
    h1,h2=st.columns([6,1])
    with h1:
        st.markdown(
            f'<div class="sec-title"><span class="num">✓</span> '
            f'Edit Queue — {len(st.session_state.queue)} step(s)</div>',
            unsafe_allow_html=True)
    with h2:
        if st.button("Clear All",key="clr"):
            st.session_state.queue=[]; st.rerun()
    for i,s in enumerate(st.session_state.queue):
        ic=STEP_ICON.get(s["type"],"•")
        name=s["type"].replace("_"," ").title()
        det=step_label(s)
        d1,d2=st.columns([9,1])
        with d1:
            st.markdown(
                f'<div class="qi"><div class="qi-n">{ic} {name}</div>'
                f'<div class="qi-d">{det}</div></div>',
                unsafe_allow_html=True)
        with d2:
            if st.button("🗑",key=f"del_{i}"):
                st.session_state.queue.pop(i); st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# ══ STEP 3 — RENDER & PREVIEW ═════════════════════════════════════
st.markdown('<div class="sec">', unsafe_allow_html=True)
st.markdown('<div class="sec-title"><span class="num">3</span> Render & Download</div>',
            unsafe_allow_html=True)

if not st.session_state.src:
    st.info("Upload a video in Step 1 first.")
elif not st.session_state.queue:
    st.info("Add at least one edit in Step 2.")
else:
    st.markdown(f"**{len(st.session_state.queue)} edit(s)** queued on "
                f"**{st.session_state.src_name}**")

    if st.button("🎬 Render Video Now", key="render_btn", type="primary"):
        prog   = st.progress(0, text="Starting…")
        steps  = st.session_state.queue

        def cb(i, total, label):
            pct = int(i/total*100) if total else 0
            prog.progress(pct, text=f"Step {i}/{total}: {label}…" if i<total else "Finishing…")

        final, log = run_pipeline(
            st.session_state.src, steps,
            audio_path       = st.session_state.audio_path,
            logo_path        = st.session_state.logo_path,
            second_video_path= st.session_state.src2,
            progress_cb      = cb,
        )
        prog.empty()

        with st.expander("Render log", expanded=(final is None)):
            for line in log: st.text(line)

        if final and os.path.exists(final) and os.path.getsize(final)>1000:
            save_history(st.session_state.src_name,
                         f"Rendered {len(steps)} steps")
            st.success("🎉 Render complete!")
            inf2 = probe(final)
            sz   = round(os.path.getsize(final)/1_048_576,1)

            # ── BEFORE / AFTER PREVIEW ─────────────────────────
            st.markdown("#### Before & After Preview")
            ba1,ba2 = st.columns(2)
            with ba1:
                st.markdown("**Before**")
                before = extract_frame(st.session_state.src,
                                       probe(st.session_state.src)["duration"]/2)
                if before: st.image(before, use_container_width=True)
            with ba2:
                st.markdown("**After**")
                after = extract_frame(final, inf2["duration"]/2)
                if after: st.image(after, use_container_width=True)

            # ── SCRUB OUTPUT ───────────────────────────────────
            st.markdown("#### Scrub rendered video")
            scrub_ts = st.slider("Preview timestamp (s)", 0.0,
                                 float(max(inf2["duration"]-0.1,0.1)),
                                 float(inf2["duration"]/2), 0.1, key="out_scrub")
            if st.button("📷 Preview this frame", key="prev_out"):
                pf = extract_frame(final, scrub_ts)
                if pf: st.image(pf, caption=f"Output at {scrub_ts:.1f}s",
                                use_container_width=True)

            # ── DOWNLOAD ───────────────────────────────────────
            st.markdown(f"**Output:** {inf2['width']}×{inf2['height']}  "
                        f"{inf2['duration']:.1f}s  {sz} MB")
            with open(final,"rb") as f:
                st.download_button("⬇️ Download Rendered Video", f.read(),
                                   "studio_output.mp4","video/mp4",
                                   key="dl_btn", use_container_width=True)
        else:
            st.error("Render failed. Check the log above.")

st.markdown('</div>', unsafe_allow_html=True)
