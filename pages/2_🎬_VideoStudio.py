import streamlit as st
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import os, tempfile, subprocess, json
from utils import inject_css, save_upload, save_history

st.set_page_config(page_title="Video Studio", page_icon="🎬", layout="wide", initial_sidebar_state="expanded")
inject_css()

# ── Sidebar ───────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="padding:0.5rem 0 1rem 0;">
        <div style="font-family:'Space Grotesk',sans-serif;font-size:1.1rem;font-weight:700;color:#1e293b;">🎬 Video Studio</div>
    </div>
    """, unsafe_allow_html=True)
    st.page_link("app.py", label="← Home", icon="🏠")
    st.page_link("pages/1_📄_SmartDoc.py", label="📄 SmartDoc Studio", icon="📄")
    st.divider()
    st.caption("SESSION HISTORY")
    if "history" not in st.session_state or not st.session_state.history:
        st.caption("No actions yet.")
    else:
        for item in reversed(st.session_state.history[-8:]):
            st.markdown(f'<div class="hist-badge">· <b>{item["name"][:22]}</b><br><span style="color:#94a3b8;font-size:0.78rem">{item["action"]}</span></div>', unsafe_allow_html=True)

# Override tab accent to red for video page
st.markdown("""
<style>
.stTabs [aria-selected="true"] { background:#fff1f2 !important; color:#e11d48 !important; }
.stButton > button { background: linear-gradient(135deg,#e11d48,#7c3aed) !important; }
.stDownloadButton > button { background:#fff1f2 !important; color:#e11d48 !important; border-color:#fecdd3 !important; }
</style>
""", unsafe_allow_html=True)

# ── Config ────────────────────────────────────────────────────────
PLATFORM_SPECS = {
    "Instagram Reels": {"width":1080,"height":1920,"fps":30,"max_duration":90,"aspect":"9:16"},
    "YouTube Shorts":  {"width":1080,"height":1920,"fps":60,"max_duration":60,"aspect":"9:16"},
    "YouTube":         {"width":1920,"height":1080,"fps":30,"max_duration":3600,"aspect":"16:9"},
}
VIDEO_FILTERS = {
    "None":        "",
    "Vivid":       "eq=saturation=1.8:contrast=1.1:brightness=0.05",
    "Cinematic":   "eq=saturation=0.85:contrast=1.2:brightness=-0.03,curves=r='0/0 0.5/0.42 1/1':g='0/0 0.5/0.5 1/0.9':b='0/0.05 0.5/0.5 1/0.85'",
    "Warm Sunset": "eq=saturation=1.3:brightness=0.04,curves=r='0/0 0.5/0.6 1/1':b='0/0 0.5/0.4 1/0.8'",
    "Cool Blue":   "eq=saturation=1.1:brightness=-0.02,curves=b='0/0.05 0.5/0.6 1/1':r='0/0 0.5/0.4 1/0.9'",
    "Black & White":"colorchannelmixer=.299:.587:.114:0:.299:.587:.114:0:.299:.587:.114",
    "Vintage":     "curves=r='0/0.1 0.5/0.55 1/0.9':g='0/0.05 0.5/0.5 1/0.85':b='0/0.1 0.5/0.45 1/0.75',eq=saturation=0.7",
    "HDR Pop":     "eq=saturation=2.0:contrast=1.3:brightness=0.02,unsharp=5:5:1.5:5:5:0.0",
    "Matte":       "curves=r='0/0.08 1/0.9':g='0/0.05 1/0.88':b='0/0.1 1/0.85',eq=saturation=0.85",
    "Neon Night":  "eq=saturation=2.2:contrast=1.4:brightness=-0.05,curves=b='0/0.1 0.5/0.7 1/1'",
}
FONT_PATH = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# ── FFmpeg helpers ────────────────────────────────────────────────
def ff(*args):
    r = subprocess.run(["ffmpeg","-y"]+list(args), capture_output=True, text=True)
    return r.returncode==0, r.stderr

def probe(path):
    r = subprocess.run(["ffprobe","-v","quiet","-print_format","json","-show_streams","-show_format",path], capture_output=True, text=True)
    if r.returncode!=0: return None
    d = json.loads(r.stdout)
    info={"duration":0,"width":0,"height":0,"fps":0,"has_audio":False,"size_mb":0}
    for s in d.get("streams",[]):
        if s.get("codec_type")=="video":
            info["width"]=s.get("width",0); info["height"]=s.get("height",0)
            try:
                n,dv=s.get("r_frame_rate","0/1").split("/")
                info["fps"]=round(int(n)/int(dv),2)
            except: pass
            info["duration"]=float(s.get("duration",d.get("format",{}).get("duration",0)))
        if s.get("codec_type")=="audio": info["has_audio"]=True
    info["size_mb"]=round(int(d.get("format",{}).get("size",0))/1_048_576,1)
    return info

def tmpout(suffix=".mp4"):
    t=tempfile.NamedTemporaryFile(delete=False,suffix=suffix); t.close(); return t.name

def dl_btn(path, label, filename, key):
    with open(path,"rb") as f:
        st.download_button(label, f.read(), filename, "video/mp4", key=key)

# ── Header ────────────────────────────────────────────────────────
st.markdown('<div class="hero-title">🎬 Video Studio</div>', unsafe_allow_html=True)
st.markdown('<div class="hero-sub">Instagram Reels · YouTube Shorts · YouTube — trim, caption, grade, export</div>', unsafe_allow_html=True)

# ── Global upload ─────────────────────────────────────────────────
st.markdown("### Upload Video")
vf = st.file_uploader("MP4, MOV, MKV or AVI", type=["mp4","mov","mkv","avi"], key="vid_up")

vpath = None
info  = None

if vf:
    ext = vf.name.rsplit(".",1)[-1]
    vpath = save_upload(vf, "."+ext)
    info  = probe(vpath)
    c1,c2 = st.columns([2,1])
    with c1: st.video(vf)
    with c2:
        if info:
            st.markdown('<div class="card-title">Video Info</div>', unsafe_allow_html=True)
            for lbl,val in [("Resolution",f"{info['width']}×{info['height']}"),
                            ("Duration",  f"{info['duration']:.1f}s"),
                            ("FPS",       str(info['fps'])),
                            ("Audio",     "✅ Yes" if info["has_audio"] else "❌ No"),
                            ("Size",      f"{info['size_mb']} MB")]:
                st.markdown(f'<div class="spec-card"><div class="spec-label">{lbl}</div><div class="spec-value">{val}</div></div>', unsafe_allow_html=True)

st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

tabs = st.tabs(["✂️ Trim","🎨 Filter","📝 Subtitles","🎵 Audio","⚡ Speed","📐 Export","🖼️ Thumbnail","💧 Watermark","🕓 History"])

# ── TRIM ──────────────────────────────────────────────────────────
with tabs[0]:
    st.markdown('<div class="card-title">✂️ Trim & Cut</div>', unsafe_allow_html=True)
    if not vpath:
        st.info("Upload a video above.")
    else:
        dur = info["duration"]
        c1,c2 = st.columns(2)
        with c1: s = st.number_input("Start (s)", 0.0, float(dur)-0.1, 0.0, 0.5, key="tr_s")
        with c2: e = st.number_input("End (s)",   0.1, float(dur),     float(dur), 0.5, key="tr_e")
        st.caption(f"Clip: **{e-s:.1f}s**")
        if st.button("✂️ Trim", key="trim_btn"):
            if e<=s: st.error("End must be after start.")
            else:
                with st.spinner("Trimming..."):
                    out=tmpout()
                    ok,err=ff("-ss",str(s),"-i",vpath,"-t",str(e-s),"-c:v","libx264","-c:a","aac","-preset","fast",out)
                if ok:
                    save_history(vf.name,f"Trim {s:.1f}–{e:.1f}s"); st.success("✅ Done!")
                    dl_btn(out,"⬇️ Download Trimmed Video","trimmed.mp4","trim_dl")
                else: st.error(err[-400:])

# ── FILTER ────────────────────────────────────────────────────────
with tabs[1]:
    st.markdown('<div class="card-title">🎨 Filter & Color Grade</div>', unsafe_allow_html=True)
    if not vpath:
        st.info("Upload a video above.")
    else:
        c1,c2=st.columns(2)
        with c1:
            fn=st.selectbox("Filter",list(VIDEO_FILTERS.keys()),key="filt_sel")
            descriptions={
                "None":"No filter.","Vivid":"Boosted saturation — great for Reels.",
                "Cinematic":"Teal & orange film look.","Warm Sunset":"Golden lifestyle tones.",
                "Cool Blue":"Clean minimal look.","Black & White":"Classic monochrome.",
                "Vintage":"Faded film aesthetic.","HDR Pop":"High dynamic range + sharpening.",
                "Matte":"Lifted blacks — popular on Instagram.","Neon Night":"Hyper-saturated neon.",
            }
            st.caption(descriptions.get(fn,""))
        with c2:
            br=st.slider("Brightness",-0.5,0.5,0.0,0.05,key="gr_br")
            co=st.slider("Contrast",0.5,2.0,1.0,0.05,key="gr_co")
            sa=st.slider("Saturation",0.0,3.0,1.0,0.1,key="gr_sa")
        if st.button("🎨 Apply", key="filt_btn"):
            with st.spinner("Grading..."):
                out=tmpout()
                base=VIDEO_FILTERS[fn]
                adj=f"eq=brightness={br}:contrast={co}:saturation={sa}"
                vff=",".join(filter(None,[base, adj if fn=="None" else ""]))
                if not vff: vff=adj
                ok,err=ff("-i",vpath,"-vf",vff,"-c:v","libx264","-c:a","aac","-preset","fast",out)
            if ok:
                save_history(vf.name,f"Filter: {fn}"); st.success(f"✅ {fn} applied!")
                dl_btn(out,f"⬇️ Download Graded Video",f"graded_{fn.lower().replace(' ','_')}.mp4","filt_dl")
            else: st.error(err[-400:])

# ── SUBTITLES ─────────────────────────────────────────────────────
with tabs[2]:
    st.markdown('<div class="card-title">📝 Subtitles & Captions</div>', unsafe_allow_html=True)
    if not vpath:
        st.info("Upload a video above.")
    else:
        n=st.number_input("Number of subtitle lines",1,20,3,key="sub_n")
        lines=[]
        for i in range(int(n)):
            c1,c2,c3=st.columns([1,1,3])
            with c1: s2=st.number_input(f"Start {i+1}",0.0,float(info["duration"]),float(i*3),0.5,key=f"ss{i}")
            with c2: e2=st.number_input(f"End {i+1}",  0.0,float(info["duration"]),float(i*3+2.5),0.5,key=f"se{i}")
            with c3: t=st.text_input(f"Text {i+1}",f"Caption {i+1}",key=f"st{i}")
            lines.append({"start":s2,"end":e2,"text":t})
        if st.button("📝 Burn Subtitles", key="sub_btn"):
            with st.spinner("Burning..."):
                srt=tempfile.NamedTemporaryFile(delete=False,suffix=".srt",mode="w")
                for i,ln in enumerate(lines,1):
                    def ft(t):
                        h=int(t//3600);m=int((t%3600)//60);s=int(t%60);ms=int((t-int(t))*1000)
                        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
                    srt.write(f"{i}\n{ft(ln['start'])} --> {ft(ln['end'])}\n{ln['text']}\n\n")
                srt.close()
                out=tmpout()
                ok,err=ff("-i",vpath,"-vf",
                    f"subtitles={srt.name}:force_style='FontSize=24,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Bold=1'",
                    "-c:a","copy",out)
                os.unlink(srt.name)
            if ok:
                save_history(vf.name,f"Subtitles ({len(lines)} lines)"); st.success("✅ Done!")
                dl_btn(out,"⬇️ Download with Subtitles","subtitled.mp4","sub_dl")
            else: st.error(err[-400:])

# ── AUDIO ─────────────────────────────────────────────────────────
with tabs[3]:
    st.markdown('<div class="card-title">🎵 Audio & Music</div>', unsafe_allow_html=True)
    if not vpath:
        st.info("Upload a video above.")
    else:
        action=st.radio("Action",["🔇 Mute","🎵 Replace with music","🔀 Mix with music","🔊 Adjust volume"],key="aud_act")
        if "Mute" in action:
            if st.button("🔇 Mute",key="mute_btn"):
                with st.spinner("Muting..."):
                    out=tmpout(); ok,err=ff("-i",vpath,"-c:v","copy","-an",out)
                if ok: save_history(vf.name,"Muted"); st.success("✅"); dl_btn(out,"⬇️ Download","muted.mp4","mute_dl")
                else: st.error(err[-300:])
        elif "volume" in action.lower():
            vol=st.slider("Volume multiplier",0.1,4.0,1.5,0.1,key="vol_sl")
            if st.button("🔊 Apply",key="vol_btn"):
                with st.spinner("Adjusting..."):
                    out=tmpout(); ok,err=ff("-i",vpath,"-af",f"volume={vol}","-c:v","copy",out)
                if ok: save_history(vf.name,f"Volume ×{vol}"); st.success("✅"); dl_btn(out,"⬇️ Download","volume.mp4","vol_dl")
                else: st.error(err[-300:])
        else:
            af=st.file_uploader("Upload music (MP3/WAV)",type=["mp3","wav"],key="aud_up")
            if af:
                apath=save_upload(af,"."+af.name.rsplit(".",1)[-1])
                if "Mix" in action:
                    mv=st.slider("Music vol",0.0,2.0,0.5,0.05,key="mv"); ov=st.slider("Original vol",0.0,2.0,1.0,0.05,key="ov")
                if st.button("🎵 Apply",key="aud_btn"):
                    with st.spinner("Processing..."):
                        out=tmpout()
                        if "Replace" in action:
                            ok,err=ff("-i",vpath,"-i",apath,"-c:v","copy","-map","0:v:0","-map","1:a:0","-shortest",out)
                        else:
                            ok,err=ff("-i",vpath,"-i",apath,
                                "-filter_complex",f"[0:a]volume={ov}[a1];[1:a]volume={mv}[a2];[a1][a2]amix=inputs=2:duration=first[ao]",
                                "-map","0:v","-map","[ao]","-c:v","copy","-shortest",out)
                    if ok: save_history(vf.name,"Audio edited"); st.success("✅"); dl_btn(out,"⬇️ Download","audio_edit.mp4","aud_dl")
                    else: st.error(err[-300:])

# ── SPEED ─────────────────────────────────────────────────────────
with tabs[4]:
    st.markdown('<div class="card-title">⚡ Speed Control</div>', unsafe_allow_html=True)
    if not vpath:
        st.info("Upload a video above.")
    else:
        presets={"0.25× Slow-mo":0.25,"0.5× Slow":0.5,"0.75× Slightly slow":0.75,
                 "1.0× Normal":1.0,"1.5× Slightly fast":1.5,"2.0× Fast":2.0,"4.0× Time-lapse":4.0}
        pr=st.selectbox("Preset",list(presets.keys()),index=1,key="spd_pr")
        speed=presets[pr]
        if st.checkbox("Custom speed",key="spd_cust"):
            speed=st.slider("Multiplier",0.1,8.0,speed,0.05,key="spd_val")
        fix_audio=st.checkbox("Keep natural voice pitch",True,key="spd_aud")
        st.caption(f"Output: **{info['duration']/speed:.1f}s**")
        if st.button("⚡ Apply Speed",key="spd_btn"):
            with st.spinner("Processing..."):
                out=tmpout()
                vff=f"setpts={1/speed}*PTS"
                if fix_audio and info.get("has_audio"):
                    parts=[]; rem=speed
                    while rem>2.0: parts.append("atempo=2.0"); rem/=2.0
                    while rem<0.5: parts.append("atempo=0.5"); rem*=2.0
                    parts.append(f"atempo={rem:.3f}")
                    ok,err=ff("-i",vpath,"-vf",vff,"-af",",".join(parts),"-c:v","libx264","-preset","fast",out)
                else:
                    ok,err=ff("-i",vpath,"-vf",vff,"-an","-c:v","libx264","-preset","fast",out)
            if ok: save_history(vf.name,f"Speed ×{speed}"); st.success("✅"); dl_btn(out,"⬇️ Download",f"speed_{speed}x.mp4","spd_dl")
            else: st.error(err[-400:])

# ── EXPORT ────────────────────────────────────────────────────────
with tabs[5]:
    st.markdown('<div class="card-title">📐 Export for Platform</div>', unsafe_allow_html=True)
    if not vpath:
        st.info("Upload a video above.")
    else:
        plat=st.selectbox("Platform",list(PLATFORM_SPECS.keys()),key="exp_plat")
        spec=PLATFORM_SPECS[plat]
        c1,c2=st.columns(2)
        with c1:
            for lbl,val in [("Resolution",f"{spec['width']}×{spec['height']}"),
                            ("Aspect",spec["aspect"]),("FPS",str(spec["fps"])),
                            ("Max duration",f"{spec['max_duration']}s")]:
                st.markdown(f'<div class="spec-card"><div class="spec-label">{lbl}</div><div class="spec-value">{val}</div></div>', unsafe_allow_html=True)
        with c2:
            crop=st.radio("Fit mode",["📐 Crop to fill","📦 Letterbox (black bars)"],key="exp_crop")
            q=st.select_slider("Quality",["Draft","Standard","High","Max"],value="High",key="exp_q")
            crf={"Draft":32,"Standard":26,"High":20,"Max":16}[q]
        if st.button(f"📐 Export for {plat}",key="exp_btn"):
            with st.spinner("Encoding..."):
                out=tmpout(); w,h=spec["width"],spec["height"]
                vff=f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}" if "Crop" in crop \
                    else f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black"
                ok,err=ff("-i",vpath,"-vf",vff,"-r",str(spec["fps"]),"-c:v","libx264","-crf",str(crf),"-preset","fast","-c:a","aac","-b:a","192k",out)
            if ok:
                save_history(vf.name,f"Export → {plat}"); st.success(f"✅ Exported for {plat}!")
                dl_btn(out,f"⬇️ Download {plat} Video",f"{plat.lower().replace(' ','_')}.mp4","exp_dl")
            else: st.error(err[-400:])

# ── THUMBNAIL ─────────────────────────────────────────────────────
with tabs[6]:
    st.markdown('<div class="card-title">🖼️ Thumbnail Generator</div>', unsafe_allow_html=True)
    if not vpath:
        st.info("Upload a video above.")
    else:
        c1,c2=st.columns(2)
        with c1: ts=st.slider("Timestamp (s)",0.0,float(info["duration"]),min(1.0,info["duration"]/2),0.5,key="th_ts")
        with c2:
            title=st.text_input("Title","Your Title Here",key="th_title")
            sub=st.text_input("Subtitle (optional)","",key="th_sub")
            style=st.selectbox("Style",["Bold Yellow","White Clean","Dark Banner","Neon Green","Red Impact"],key="th_style")
            tp=st.selectbox("Size",list(PLATFORM_SPECS.keys()),key="th_plat")
        if st.button("🖼️ Generate",key="th_btn"):
            with st.spinner("Extracting frame..."):
                spec=PLATFORM_SPECS[tp]; w,h=spec["width"],spec["height"]
                tmp=tmpout(".jpg")
                ok,err=ff("-ss",str(ts),"-i",vpath,"-vframes","1","-vf",f"scale={w}:{h}",tmp)
            if ok and os.path.exists(tmp):
                img=Image.open(tmp).copy()
                if title:
                    draw=ImageDraw.Draw(img)
                    try: fb=ImageFont.truetype(FONT_PATH,max(40,w//18)); fs=ImageFont.truetype(FONT_PATH,max(24,w//30))
                    except: fb=fs=ImageFont.load_default()
                    colors={"Bold Yellow":(255,230,0),"White Clean":(255,255,255),"Dark Banner":(255,255,255),"Neon Green":(0,255,120),"Red Impact":(255,50,50)}
                    tc=colors.get(style,(255,230,0))
                    if style=="Dark Banner":
                        ov=Image.new("RGBA",img.size,(0,0,0,0)); od=ImageDraw.Draw(ov)
                        od.rectangle([0,h-130,w,h],fill=(0,0,0,160)); img=Image.alpha_composite(img.convert("RGBA"),ov).convert("RGB"); draw=ImageDraw.Draw(img)
                    draw.text((32,h//2-60+2),title,font=fb,fill=(0,0,0,200)); draw.text((32,h//2-60),title,font=fb,fill=tc)
                    if sub: draw.text((32,h//2+20+2),sub,font=fs,fill=(0,0,0,180)); draw.text((32,h//2+20),sub,font=fs,fill=(255,255,255))
                save_history(vf.name,f"Thumbnail @ {ts}s"); st.image(img,use_container_width=True)
                buf=BytesIO(); img.save(buf,format="JPEG",quality=95)
                st.download_button("⬇️ Download JPEG",buf.getvalue(),"thumbnail.jpg","image/jpeg",key="th_dl_j")
                bufp=BytesIO(); img.save(bufp,format="PNG")
                st.download_button("⬇️ Download PNG",bufp.getvalue(),"thumbnail.png","image/png",key="th_dl_p")
            else: st.error("Could not extract frame. Try a different timestamp.")

# ── WATERMARK ─────────────────────────────────────────────────────
with tabs[7]:
    st.markdown('<div class="card-title">💧 Watermark & Logo</div>', unsafe_allow_html=True)
    if not vpath:
        st.info("Upload a video above.")
    else:
        wtype=st.radio("Type",["✏️ Text watermark","🖼️ Logo / image"],key="wm_type")
        positions={"Top Left":"10:10","Top Right":"main_w-overlay_w-10:10",
                   "Bottom Left":"10:main_h-overlay_h-10","Bottom Right":"main_w-overlay_w-10:main_h-overlay_h-10",
                   "Center":"(main_w-overlay_w)/2:(main_h-overlay_h)/2"}
        dt_pos={"Top Left":("10","10"),"Top Right":("w-text_w-10","10"),
                "Bottom Left":("10","h-text_h-10"),"Bottom Right":("w-text_w-10","h-text_h-10"),
                "Center":("(w-text_w)/2","(h-text_h)/2")}
        pos=st.selectbox("Position",list(positions.keys()),index=3,key="wm_pos")
        opa=st.slider("Opacity",0.1,1.0,0.7,0.05,key="wm_opa")
        if "Text" in wtype:
            c1,c2,c3=st.columns(3)
            with c1: txt=st.text_input("Text","@yourbrand",key="wm_txt")
            with c2: col=st.selectbox("Color",["white","black","yellow","red","cyan"],key="wm_col")
            with c3: sz=st.slider("Size",12,72,32,key="wm_sz")
            if st.button("💧 Apply Text",key="wm_txt_btn"):
                with st.spinner("Adding watermark..."):
                    out=tmpout(); x,y=dt_pos[pos]
                    vff=f"drawtext=text='{txt}':fontsize={sz}:fontcolor={col}@{opa}:x={x}:y={y}:shadowcolor=black@0.5:shadowx=2:shadowy=2"
                    ok,err=ff("-i",vpath,"-vf",vff,"-c:v","libx264","-c:a","aac","-preset","fast",out)
                if ok: save_history(vf.name,f"Watermark '{txt}'"); st.success("✅"); dl_btn(out,"⬇️ Download","watermarked.mp4","wm_txt_dl")
                else: st.error(err[-400:])
        else:
            lf=st.file_uploader("Logo (PNG recommended)",type=["png","jpg"],key="logo_up")
            ls=st.slider("Logo size (% of width)",5,50,15,key="logo_sz")
            if lf and st.button("🖼️ Apply Logo",key="wm_logo_btn"):
                with st.spinner("Compositing..."):
                    lpath=save_upload(lf,".png"); out=tmpout()
                    ovp=positions[pos]
                    vff=f"[1:v]scale=iw*{ls/100:.2f}:-1,format=rgba,colorchannelmixer=aa={opa}[logo];[0:v][logo]overlay={ovp}"
                    ok,err=ff("-i",vpath,"-i",lpath,"-filter_complex",vff,"-c:v","libx264","-c:a","aac","-preset","fast",out)
                if ok: save_history(vf.name,"Logo watermark"); st.success("✅"); dl_btn(out,"⬇️ Download","logo_watermark.mp4","wm_logo_dl")
                else: st.error(err[-400:])

# ── HISTORY ───────────────────────────────────────────────────────
with tabs[8]:
    st.markdown('<div class="card-title">🕓 History</div>', unsafe_allow_html=True)
    if "history" not in st.session_state or not st.session_state.history:
        st.info("No actions yet.")
    else:
        for item in reversed(st.session_state.history):
            st.markdown(f'<div class="hist-badge">🎬 <b>{item["name"]}</b> → {item["action"]}</div>', unsafe_allow_html=True)
