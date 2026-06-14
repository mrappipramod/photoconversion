import streamlit as st
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import os, tempfile, subprocess, json, shutil, uuid
from utils import inject_css, save_upload, save_history

st.set_page_config(page_title="Video Studio", page_icon="🎬", layout="wide", initial_sidebar_state="expanded")
inject_css()

# ─── Red accent override ───────────────────────────────────────────
st.markdown("""<style>
.stTabs [aria-selected="true"] { background:#fff1f2 !important; color:#e11d48 !important; }
.stButton > button { background: linear-gradient(135deg,#e11d48,#7c3aed) !important; }
.stDownloadButton > button { background:#fff1f2 !important; color:#e11d48 !important; border-color:#fecdd3 !important; }
.edit-step {
    background:#fff; border:1px solid #e2e8f0; border-left:4px solid #e11d48;
    border-radius:8px; padding:0.6rem 1rem; margin-bottom:0.4rem;
    display:flex; justify-content:space-between; align-items:center;
}
.step-label { font-weight:600; color:#1e293b; font-size:0.9rem; }
.step-detail { font-size:0.78rem; color:#64748b; margin-top:2px; }
.pipeline-header {
    background:linear-gradient(135deg,#fff1f2,#fdf4ff);
    border:1px solid #fecdd3; border-radius:12px; padding:1rem 1.2rem; margin-bottom:1rem;
}
.template-card {
    background:#fff; border:1px solid #e2e8f0; border-radius:12px;
    padding:1.1rem; cursor:pointer; transition:all 0.2s; text-align:center;
}
.template-card:hover { border-color:#e11d48; box-shadow:0 4px 12px rgba(225,29,72,0.1); }
.template-icon { font-size:2rem; margin-bottom:0.4rem; }
.template-name { font-weight:700; color:#1e293b; font-size:0.9rem; }
.template-desc { font-size:0.75rem; color:#64748b; margin-top:3px; }
</style>""", unsafe_allow_html=True)

# ─── Session state init ───────────────────────────────────────────
for key, default in {
    "pipeline": [],          # list of edit steps
    "working_path": None,    # current working video path
    "source_path": None,     # original uploaded path
    "source_name": "",
    "clip_paths": [],        # for merge: multiple clips
    "text_layers": [],       # text overlay definitions
    "render_log": [],        # render messages
}.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ─── Constants ────────────────────────────────────────────────────
PLATFORM_SPECS = {
    "Instagram Reels (9:16)": {"w":1080,"h":1920,"fps":30,"dur":90},
    "YouTube Shorts (9:16)":  {"w":1080,"h":1920,"fps":60,"dur":60},
    "YouTube (16:9)":         {"w":1920,"h":1080,"fps":30,"dur":3600},
    "TikTok (9:16)":          {"w":1080,"h":1920,"fps":30,"dur":180},
    "Square (1:1)":           {"w":1080,"h":1080,"fps":30,"dur":60},
}

VIDEO_FILTERS = {
    "None":        "",
    "Vivid":       "eq=saturation=1.8:contrast=1.1:brightness=0.05",
    "Cinematic":   "eq=saturation=0.85:contrast=1.2:brightness=-0.03,curves=r='0/0 0.5/0.42 1/1':g='0/0 0.5/0.5 1/0.9':b='0/0.05 0.5/0.5 1/0.85'",
    "Warm Sunset": "eq=saturation=1.3:brightness=0.04,curves=r='0/0 0.5/0.6 1/1':b='0/0 0.5/0.4 1/0.8'",
    "Cool Blue":   "eq=saturation=1.1:brightness=-0.02,curves=b='0/0.05 0.5/0.6 1/1':r='0/0 0.5/0.4 1/0.9'",
    "B&W":         "colorchannelmixer=.299:.587:.114:0:.299:.587:.114:0:.299:.587:.114",
    "Vintage":     "curves=r='0/0.1 0.5/0.55 1/0.9':g='0/0.05 0.5/0.5 1/0.85':b='0/0.1 0.5/0.45 1/0.75',eq=saturation=0.7",
    "HDR Pop":     "eq=saturation=2.0:contrast=1.3:brightness=0.02,unsharp=5:5:1.5:5:5:0.0",
    "Matte":       "curves=r='0/0.08 1/0.9':g='0/0.05 1/0.88':b='0/0.1 1/0.85',eq=saturation=0.85",
    "Neon Night":  "eq=saturation=2.2:contrast=1.4:brightness=-0.05,curves=b='0/0.1 0.5/0.7 1/1'",
}

TRANSITIONS = {
    "None":      "",
    "Fade":      "fade=t=in:st=0:d=0.5,fade=t=out:st={end}:d=0.5",
    "Dissolve":  "fade=t=in:st=0:d=1:alpha=1",
    "Zoom In":   "zoompan=z='min(zoom+0.002,1.3)':d=125:s=1080x1920",
}

TEXT_ANIMS = ["None","Fade In","Slide Up","Slide Left","Typewriter","Zoom In"]

FONT_PATH_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_PATH_REG  = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_PATH_MONO = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"

TEMPLATES = {
    "🔥 Viral Reel": {
        "desc": "Fast cuts, vivid filter, bold captions, music fade",
        "platform": "Instagram Reels (9:16)",
        "steps": [
            {"type":"filter","filter":"Vivid","brightness":0.05,"contrast":1.1,"saturation":1.8},
            {"type":"speed","speed":1.2},
            {"type":"export","platform":"Instagram Reels (9:16)","quality":"High","crop":"crop"},
        ]
    },
    "🎬 Cinematic Short": {
        "desc": "Cinematic grade, letterbox bars, slow zoom",
        "platform": "YouTube Shorts (9:16)",
        "steps": [
            {"type":"filter","filter":"Cinematic","brightness":-0.03,"contrast":1.2,"saturation":0.85},
            {"type":"kenburns","zoom_start":1.0,"zoom_end":1.08,"duration":0},
            {"type":"export","platform":"YouTube Shorts (9:16)","quality":"Max","crop":"letterbox"},
        ]
    },
    "🌅 Travel Vlog": {
        "desc": "Warm tones, lower third title, YouTube export",
        "platform": "YouTube (16:9)",
        "steps": [
            {"type":"filter","filter":"Warm Sunset","brightness":0.04,"contrast":1.0,"saturation":1.3},
            {"type":"text","text":"Your Destination","style":"Lower Third","start":1.0,"end":4.0,"anim":"Slide Up","font_size":48,"color":"#FFFFFF","x_pct":5,"y_pct":80},
            {"type":"export","platform":"YouTube (16:9)","quality":"High","crop":"letterbox"},
        ]
    },
    "🎵 Music Video": {
        "desc": "Neon filter, beat-synced speed, watermark",
        "platform": "Instagram Reels (9:16)",
        "steps": [
            {"type":"filter","filter":"Neon Night","brightness":-0.05,"contrast":1.4,"saturation":2.2},
            {"type":"watermark_text","text":"@yourbrand","position":"Bottom Right","opacity":0.8,"color":"white","size":28},
            {"type":"export","platform":"Instagram Reels (9:16)","quality":"High","crop":"crop"},
        ]
    },
    "📰 News / Talking Head": {
        "desc": "Clean grade, lower third, progress bar",
        "platform": "YouTube (16:9)",
        "steps": [
            {"type":"filter","filter":"None","brightness":0.02,"contrast":1.05,"saturation":1.0},
            {"type":"progress_bar","color":"#e11d48","height":6,"position":"bottom"},
            {"type":"text","text":"Breaking News","style":"News Ticker","start":0.5,"end":5.0,"anim":"Slide Left","font_size":40,"color":"#FFFFFF","x_pct":2,"y_pct":88},
            {"type":"export","platform":"YouTube (16:9)","quality":"High","crop":"letterbox"},
        ]
    },
    "⚡ Quick Export": {
        "desc": "No edits — just resize & export for your platform",
        "platform": "Instagram Reels (9:16)",
        "steps": [
            {"type":"export","platform":"Instagram Reels (9:16)","quality":"Standard","crop":"crop"},
        ]
    },
}

# ─── FFmpeg helpers ───────────────────────────────────────────────
def ff(*args):
    r = subprocess.run(["ffmpeg","-y"]+list(args), capture_output=True, text=True)
    return r.returncode==0, r.stderr

def probe(path):
    r = subprocess.run(["ffprobe","-v","quiet","-print_format","json",
                        "-show_streams","-show_format",path], capture_output=True, text=True)
    if r.returncode != 0: return {"duration":0,"width":0,"height":0,"fps":0,"has_audio":False,"size_mb":0}
    d = json.loads(r.stdout)
    info = {"duration":0,"width":0,"height":0,"fps":0,"has_audio":False,"size_mb":0}
    for s in d.get("streams",[]):
        if s.get("codec_type")=="video":
            info["width"]=s.get("width",0); info["height"]=s.get("height",0)
            try:
                n,dv=s.get("r_frame_rate","30/1").split("/")
                info["fps"]=round(int(n)/max(int(dv),1),2)
            except: info["fps"]=30
            info["duration"]=float(s.get("duration") or d.get("format",{}).get("duration",0))
        if s.get("codec_type")=="audio": info["has_audio"]=True
    info["size_mb"]=round(int(d.get("format",{}).get("size",0))/1_048_576,1)
    return info

def tmpout(suffix=".mp4"):
    t = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    t.close(); return t.name

def copy_to_working(src):
    dst = tmpout(".mp4")
    shutil.copy2(src, dst)
    return dst

# ─── Step renderers ───────────────────────────────────────────────
def render_trim(inp, step):
    out = tmpout()
    ok, err = ff("-ss", str(step["start"]), "-i", inp,
                 "-t", str(step["end"]-step["start"]),
                 "-c:v","libx264","-c:a","aac","-preset","fast", out)
    return (out, None) if ok else (None, err)

def render_filter(inp, step):
    out = tmpout()
    base = VIDEO_FILTERS.get(step.get("filter","None"), "")
    adj  = f"eq=brightness={step.get('brightness',0)}:contrast={step.get('contrast',1)}:saturation={step.get('saturation',1)}"
    vf   = ",".join(filter(None, [base, adj if step.get("filter","None")=="None" else ""]))
    if not vf: vf = adj
    ok, err = ff("-i",inp,"-vf",vf,"-c:v","libx264","-c:a","aac","-preset","fast",out)
    return (out, None) if ok else (None, err)

def render_speed(inp, step):
    out = tmpout(); spd = step["speed"]; info = probe(inp)
    vf  = f"setpts={1/spd}*PTS"
    parts=[]; rem=spd
    while rem>2.0: parts.append("atempo=2.0"); rem/=2.0
    while rem<0.5: parts.append("atempo=0.5"); rem*=2.0
    parts.append(f"atempo={rem:.3f}")
    if info["has_audio"]:
        ok,err=ff("-i",inp,"-vf",vf,"-af",",".join(parts),"-c:v","libx264","-preset","fast",out)
    else:
        ok,err=ff("-i",inp,"-vf",vf,"-an","-c:v","libx264","-preset","fast",out)
    return (out,None) if ok else (None,err)

def render_text_layer(inp, step):
    """Burn a single text layer with optional animation using drawtext."""
    out   = tmpout()
    info  = probe(inp)
    dur   = info["duration"]
    w, h  = info["width"] or 1080, info["height"] or 1920

    text  = step.get("text","Text").replace("'","\\'").replace(":","\\:")
    color = step.get("color","#FFFFFF").lstrip("#")
    r,g,b = int(color[0:2],16), int(color[2:4],16), int(color[4:6],16)
    fc    = f"0x{color}FF"
    fs    = step.get("font_size", 48)
    ts    = step.get("start", 0.0)
    te    = step.get("end", dur)
    xp    = step.get("x_pct", 10)
    yp    = step.get("y_pct", 50)
    anim  = step.get("anim","None")
    style = step.get("style","Custom")
    bg    = step.get("bg", False)
    bg_col= step.get("bg_color","#000000").lstrip("#")
    shadow= step.get("shadow", True)

    x_expr = f"(w*{xp/100})"
    y_expr = f"(h*{yp/100})"

    # Animation expressions
    if anim == "Fade In":
        alpha = f"if(lt(t,{ts}),0,if(lt(t,{ts+0.6}),(t-{ts})/0.6,if(lt(t,{te-0.4}),1,(t-({te-0.4}))/0.4*(-1)+1)))"
    elif anim == "Slide Up":
        y_expr = f"if(lt(t,{ts}),h,if(lt(t,{ts+0.5}),(h*{yp/100})+(h*(1-{yp/100}))*(1-(t-{ts})/0.5),(h*{yp/100})))"
        alpha  = f"if(lt(t,{ts}),0,1)"
    elif anim == "Slide Left":
        x_expr = f"if(lt(t,{ts}),w,if(lt(t,{ts+0.5}),(w*{xp/100})+(w*(1-{xp/100}))*(1-(t-{ts})/0.5),(w*{xp/100})))"
        alpha  = f"if(lt(t,{ts}),0,1)"
    elif anim == "Zoom In":
        alpha = f"if(lt(t,{ts}),0,1)"
    elif anim == "Typewriter":
        alpha = f"if(lt(t,{ts}),0,1)"
    else:
        alpha = f"if(between(t,{ts},{te}),1,0)"

    enable = f"between(t,{ts},{te})"

    shadow_str = ":shadowcolor=black@0.6:shadowx=2:shadowy=2" if shadow else ""
    box_str    = f":box=1:boxcolor=0x{bg_col}@0.6:boxborderw=8" if bg else ""

    try:
        font_arg = f":fontfile={FONT_PATH_BOLD}"
    except:
        font_arg = ""

    dt = (f"drawtext=text='{text}':fontsize={fs}{font_arg}"
          f":fontcolor={fc}@1.0:alpha='{alpha}'"
          f":x={x_expr}:y={y_expr}"
          f":enable='{enable}'"
          f"{shadow_str}{box_str}")

    # Progress bar or lower third overlay for special styles
    vf_chain = dt
    if style == "Lower Third":
        bar = (f"drawbox=x=0:y=(h*{yp/100})-{fs+16}:w=iw:h={fs+32}"
               f":color=0x00000080:t=fill:enable='{enable}'")
        vf_chain = f"{bar},{dt}"
    elif style == "News Ticker":
        bar = f"drawbox=x=0:y=(h*{yp/100})-8:w=iw:h={fs+20}:color=0xe11d48CC:t=fill:enable='{enable}'"
        vf_chain = f"{bar},{dt}"
    elif style == "Title Card":
        bar = (f"drawbox=x=(w*{xp/100})-16:y=(h*{yp/100})-{fs+8}:w=text_w+32:h=text_h+16"
               f":color=0x000000AA:t=fill:enable='{enable}'")
        vf_chain = f"{bar},{dt}"

    ok,err = ff("-i",inp,"-vf",vf_chain,"-c:v","libx264","-c:a","aac","-preset","fast",out)
    return (out,None) if ok else (None,err)

def render_watermark_text(inp, step):
    out  = tmpout()
    text = step.get("text","@brand").replace("'","\\'")
    pos  = step.get("position","Bottom Right")
    opa  = step.get("opacity", 0.75)
    col  = step.get("color","white")
    sz   = step.get("size", 28)
    coords = {
        "Top Left":    ("20","20"),
        "Top Right":   ("w-text_w-20","20"),
        "Bottom Left": ("20","h-text_h-20"),
        "Bottom Right":("w-text_w-20","h-text_h-20"),
        "Center":      ("(w-text_w)/2","(h-text_h)/2"),
    }
    x,y = coords.get(pos,("w-text_w-20","h-text_h-20"))
    vf = f"drawtext=text='{text}':fontsize={sz}:fontcolor={col}@{opa}:x={x}:y={y}:shadowcolor=black@0.5:shadowx=2:shadowy=2"
    ok,err = ff("-i",inp,"-vf",vf,"-c:v","libx264","-c:a","aac","-preset","fast",out)
    return (out,None) if ok else (None,err)

def render_watermark_logo(inp, logo_path, step):
    out = tmpout()
    pos = step.get("position","Bottom Right")
    opa = step.get("opacity",0.75)
    sz  = step.get("size_pct",15)
    positions = {
        "Top Left":    "10:10",
        "Top Right":   "main_w-overlay_w-10:10",
        "Bottom Left": "10:main_h-overlay_h-10",
        "Bottom Right":"main_w-overlay_w-10:main_h-overlay_h-10",
        "Center":      "(main_w-overlay_w)/2:(main_h-overlay_h)/2",
    }
    ovp = positions.get(pos,"main_w-overlay_w-10:main_h-overlay_h-10")
    vf  = (f"[1:v]scale=iw*{sz/100:.2f}:-1,format=rgba,"
           f"colorchannelmixer=aa={opa}[logo];[0:v][logo]overlay={ovp}")
    ok,err = ff("-i",inp,"-i",logo_path,"-filter_complex",vf,
                "-c:v","libx264","-c:a","aac","-preset","fast",out)
    return (out,None) if ok else (None,err)

def render_progress_bar(inp, step):
    out  = tmpout()
    info = probe(inp)
    dur  = info["duration"]
    col  = step.get("color","#e11d48").lstrip("#")
    ht   = step.get("height",8)
    pos  = step.get("position","bottom")
    y    = f"h-{ht}" if pos=="bottom" else "0"
    vf   = (f"drawbox=x=0:y={y}:w=iw*(t/{dur}):h={ht}"
            f":color=0x{col}FF:t=fill")
    ok,err = ff("-i",inp,"-vf",vf,"-c:v","libx264","-c:a","aac","-preset","fast",out)
    return (out,None) if ok else (None,err)

def render_kenburns(inp, step):
    out  = tmpout()
    info = probe(inp)
    w,h  = info["width"] or 1080, info["height"] or 1920
    fps  = info["fps"] or 30
    dur  = info["duration"]
    zs   = step.get("zoom_start",1.0)
    ze   = step.get("zoom_end",1.08)
    frames = max(int(dur * fps), 1)
    vf = (f"scale=iw*{ze}:ih*{ze},"
          f"zoompan=z='min(zoom+{(ze-zs)/frames:.6f},{ze})':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={fps}")
    ok,err = ff("-i",inp,"-vf",vf,"-c:v","libx264","-c:a","aac","-preset","fast",out)
    return (out,None) if ok else (None,err)

def render_audio(inp, step, audio_path=None):
    out    = tmpout()
    action = step.get("action","replace")
    if action == "mute":
        ok,err = ff("-i",inp,"-c:v","copy","-an",out)
    elif action == "volume":
        ok,err = ff("-i",inp,"-af",f"volume={step.get('vol',1.5)}","-c:v","copy",out)
    elif action == "replace" and audio_path:
        ok,err = ff("-i",inp,"-i",audio_path,"-c:v","copy","-map","0:v:0","-map","1:a:0","-shortest",out)
    elif action == "mix" and audio_path:
        mv=step.get("music_vol",0.5); ov=step.get("orig_vol",1.0)
        ok,err = ff("-i",inp,"-i",audio_path,
            "-filter_complex",f"[0:a]volume={ov}[a1];[1:a]volume={mv}[a2];[a1][a2]amix=inputs=2:duration=first[ao]",
            "-map","0:v","-map","[ao]","-c:v","copy","-shortest",out)
    else:
        return inp, None
    return (out,None) if ok else (None,err)

def render_export(inp, step):
    out  = tmpout()
    spec = PLATFORM_SPECS.get(step.get("platform","Instagram Reels (9:16)"),
                               {"w":1080,"h":1920,"fps":30})
    w,h  = spec["w"],spec["h"]
    crf  = {"Draft":32,"Standard":26,"High":20,"Max":16}.get(step.get("quality","High"),20)
    mode = step.get("crop","crop")
    vf   = (f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}" if mode=="crop"
            else f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black")
    ok,err = ff("-i",inp,"-vf",vf,"-r",str(spec["fps"]),
                "-c:v","libx264","-crf",str(crf),"-preset","fast",
                "-c:a","aac","-b:a","192k",out)
    return (out,None) if ok else (None,err)

def render_subtitles(inp, step):
    out  = tmpout()
    lines= step.get("lines",[])
    if not lines: return inp, None
    srt  = tempfile.NamedTemporaryFile(delete=False,suffix=".srt",mode="w")
    def ft(t):
        h=int(t//3600);m=int((t%3600)//60);s=int(t%60);ms=int((t-int(t))*1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    for i,ln in enumerate(lines,1):
        srt.write(f"{i}\n{ft(ln['start'])} --> {ft(ln['end'])}\n{ln['text']}\n\n")
    srt.close()
    ok,err = ff("-i",inp,
        "-vf",f"subtitles={srt.name}:force_style='FontSize=24,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Bold=1'",
        "-c:a","copy",out)
    os.unlink(srt.name)
    return (out,None) if ok else (None,err)

def render_merge(paths, transition="None"):
    """Concatenate multiple clips with optional transition."""
    if len(paths) < 2: return paths[0], None
    # Write concat list
    lst = tempfile.NamedTemporaryFile(delete=False,suffix=".txt",mode="w")
    for p in paths:
        lst.write(f"file '{p}'\n")
    lst.close()
    out = tmpout()
    ok,err = ff("-f","concat","-safe","0","-i",lst.name,
                "-c:v","libx264","-c:a","aac","-preset","fast",out)
    os.unlink(lst.name)
    return (out,None) if ok else (None,err)

# ─── Render full pipeline ─────────────────────────────────────────
def run_pipeline(source_path, steps, audio_store):
    """Apply all steps sequentially. Returns final path or None."""
    current = copy_to_working(source_path)
    log = []
    for i, step in enumerate(steps):
        t = step["type"]
        log.append(f"Step {i+1}/{len(steps)}: {t}…")
        if   t == "trim":           result, err = render_trim(current, step)
        elif t == "filter":         result, err = render_filter(current, step)
        elif t == "speed":          result, err = render_speed(current, step)
        elif t == "text":           result, err = render_text_layer(current, step)
        elif t == "watermark_text": result, err = render_watermark_text(current, step)
        elif t == "watermark_logo":
            lp = audio_store.get("logo_path")
            result, err = render_watermark_logo(current, lp, step) if lp else (current, None)
        elif t == "progress_bar":   result, err = render_progress_bar(current, step)
        elif t == "kenburns":       result, err = render_kenburns(current, step)
        elif t == "audio":
            ap = audio_store.get("audio_path")
            result, err = render_audio(current, step, ap)
        elif t == "subtitles":      result, err = render_subtitles(current, step)
        elif t == "export":         result, err = render_export(current, step)
        else: result, err = current, None

        if result is None:
            log.append(f"  ❌ Failed: {err[-200:] if err else 'unknown'}")
            return None, log
        current = result
        log.append(f"  ✅ Done")
    return current, log

# ─── Pipeline display ─────────────────────────────────────────────
def show_pipeline():
    steps = st.session_state.pipeline
    if not steps:
        st.info("No edits queued yet. Add steps from the tabs below.", icon="ℹ️")
        return
    st.markdown(f"""<div class="pipeline-header">
        <b style="color:#e11d48">⚡ Edit Pipeline</b>
        <span style="color:#64748b;font-size:0.85rem;margin-left:8px">{len(steps)} step(s) queued — all applied in order when you render</span>
    </div>""", unsafe_allow_html=True)
    icons = {"trim":"✂️","filter":"🎨","speed":"⚡","text":"📝","watermark_text":"💧",
             "watermark_logo":"🖼️","progress_bar":"📊","kenburns":"🔍","audio":"🎵",
             "subtitles":"💬","export":"📐"}
    for i, step in enumerate(steps):
        detail = {
            "trim":    f"{step.get('start',0):.1f}s → {step.get('end',0):.1f}s",
            "filter":  step.get("filter","None"),
            "speed":   f"×{step.get('speed',1.0)}",
            "text":    f'"{step.get("text","")[:30]}" @ {step.get("start",0):.1f}s',
            "watermark_text": f'"{step.get("text","")}" {step.get("position","")}',
            "watermark_logo": f'{step.get("position","")} opacity {step.get("opacity",0.75)}',
            "progress_bar":   f'{step.get("position","bottom")} bar',
            "kenburns": f'zoom {step.get("zoom_start",1.0)}→{step.get("zoom_end",1.08)}',
            "audio":   step.get("action",""),
            "subtitles": f'{len(step.get("lines",[]))} lines',
            "export":  step.get("platform",""),
        }.get(step["type"], "")
        ic = icons.get(step["type"],"•")
        col1, col2 = st.columns([6,1])
        with col1:
            st.markdown(f"""<div class="edit-step">
                <div><div class="step-label">{ic} {step["type"].replace("_"," ").title()}</div>
                <div class="step-detail">{detail}</div></div>
                <div style="color:#94a3b8;font-size:0.8rem">#{i+1}</div>
            </div>""", unsafe_allow_html=True)
        with col2:
            if st.button("🗑", key=f"del_step_{i}", help="Remove this step"):
                st.session_state.pipeline.pop(i)
                st.rerun()

def add_step(step):
    st.session_state.pipeline.append(step)
    st.success(f"✅ Added to pipeline! ({len(st.session_state.pipeline)} steps queued)")

# ─── Sidebar ──────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div style="font-family:\'Space Grotesk\',sans-serif;font-size:1.1rem;font-weight:700;color:#1e293b;padding:0.5rem 0 0.8rem">🎬 Video Studio</div>', unsafe_allow_html=True)
    st.page_link("app.py", label="← Home", icon="🏠")
    st.page_link("pages/1_📄_SmartDoc.py", label="📄 SmartDoc Studio")
    st.divider()
    steps = st.session_state.pipeline
    st.caption(f"PIPELINE — {len(steps)} STEP(S)")
    if steps:
        icons2={"trim":"✂️","filter":"🎨","speed":"⚡","text":"📝","watermark_text":"💧",
                "watermark_logo":"🖼️","progress_bar":"📊","kenburns":"🔍","audio":"🎵","subtitles":"💬","export":"📐"}
        for s in steps:
            ic=icons2.get(s["type"],"•")
            st.markdown(f'<div class="hist-badge" style="font-size:0.78rem">{ic} {s["type"].replace("_"," ").title()}</div>', unsafe_allow_html=True)
        if st.button("🗑 Clear All Steps", key="clear_pipe"):
            st.session_state.pipeline = []
            st.rerun()
    else:
        st.caption("No steps yet.")

# ─── Header ───────────────────────────────────────────────────────
st.markdown('<div class="hero-title">🎬 Video Studio</div>', unsafe_allow_html=True)
st.markdown('<div class="hero-sub">Non-destructive pipeline editor — add steps, render once, download</div>', unsafe_allow_html=True)

# ─── Source video upload ──────────────────────────────────────────
with st.expander("📂 Source Videos", expanded=st.session_state.source_path is None):
    up_tab, merge_tab = st.tabs(["Single Video", "Merge Multiple Clips"])

    with up_tab:
        vf = st.file_uploader("Upload video (MP4, MOV, MKV, AVI)", type=["mp4","mov","mkv","avi"], key="src_up")
        if vf:
            if st.button("Use this video", key="use_vid"):
                p = save_upload(vf, "."+vf.name.rsplit(".",1)[-1])
                st.session_state.source_path = p
                st.session_state.source_name = vf.name
                st.session_state.working_path= p
                st.success(f"✅ Loaded: {vf.name}")
                st.rerun()

    with merge_tab:
        clips = st.file_uploader("Upload clips to merge (in order)", type=["mp4","mov","mkv","avi"],
                                  accept_multiple_files=True, key="merge_up")
        trans = st.selectbox("Transition between clips", ["None","Fade"], key="merge_trans")
        if clips and st.button("Merge Clips", key="merge_btn"):
            with st.spinner("Merging…"):
                paths = []
                for c in clips:
                    cp = save_upload(c, "."+c.name.rsplit(".",1)[-1])
                    # normalise to same codec first
                    n = tmpout()
                    ff("-i",cp,"-c:v","libx264","-c:a","aac","-preset","fast",n)
                    paths.append(n)
                result, err = render_merge(paths, trans)
            if result:
                st.session_state.source_path  = result
                st.session_state.source_name  = "merged_clips.mp4"
                st.session_state.working_path = result
                st.success(f"✅ Merged {len(clips)} clips!")
                st.rerun()
            else:
                st.error(f"Merge failed: {err}")

# Show current source info
if st.session_state.source_path:
    info = probe(st.session_state.source_path)
    c1,c2,c3,c4,c5 = st.columns(5)
    for col,lbl,val in zip([c1,c2,c3,c4,c5],
        ["File","Resolution","Duration","FPS","Size"],
        [st.session_state.source_name, f"{info['width']}×{info['height']}",
         f"{info['duration']:.1f}s", str(info['fps']), f"{info['size_mb']}MB"]):
        col.markdown(f'<div class="spec-card"><div class="spec-label">{lbl}</div><div class="spec-value" style="font-size:0.85rem">{val}</div></div>', unsafe_allow_html=True)
    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

# ─── Audio & Logo store (files that steps reference) ─────────────
if "audio_store" not in st.session_state:
    st.session_state.audio_store = {}

# ─── Pipeline panel ───────────────────────────────────────────────
st.markdown("### ⚡ Edit Pipeline")
show_pipeline()
st.markdown('<div class="divider"></div>', unsafe_allow_html=True)

# ─── Add steps tabs ───────────────────────────────────────────────
st.markdown("### ➕ Add Edit Steps")
tabs = st.tabs(["🗂 Templates","✂️ Trim","🎨 Filter","⚡ Speed","📝 Text & Titles",
                "💧 Watermark","📊 Progress Bar","🔍 Ken Burns","🎵 Audio","💬 Subtitles","📐 Export"])

# ── TEMPLATES ────────────────────────────────────────────────────
with tabs[0]:
    st.markdown('<div class="card-title">Auto-Edit Templates</div>', unsafe_allow_html=True)
    st.caption("One click to load a full edit pipeline. You can then modify individual steps above.")
    cols = st.columns(3)
    for i,(name,tmpl) in enumerate(TEMPLATES.items()):
        with cols[i%3]:
            st.markdown(f"""<div class="template-card">
                <div class="template-icon">{name.split()[0]}</div>
                <div class="template-name">{' '.join(name.split()[1:])}</div>
                <div class="template-desc">{tmpl['desc']}</div>
            </div>""", unsafe_allow_html=True)
            if st.button(f"Load Template", key=f"tmpl_{i}"):
                st.session_state.pipeline = [dict(s) for s in tmpl["steps"]]
                st.success(f"✅ Loaded '{name}' — {len(tmpl['steps'])} steps ready. Hit Render!")
                st.rerun()

# ── TRIM ────────────────────────────────────────────────────────
with tabs[1]:
    st.markdown('<div class="card-title">✂️ Trim & Cut</div>', unsafe_allow_html=True)
    dur = probe(st.session_state.source_path)["duration"] if st.session_state.source_path else 60.0
    c1,c2 = st.columns(2)
    with c1: ts = st.number_input("Start (s)",0.0,float(dur)-0.1,0.0,0.5,key="tr_s")
    with c2: te = st.number_input("End (s)",  0.1,float(dur),    float(dur),0.5,key="tr_e")
    st.caption(f"Clip length: **{te-ts:.1f}s**")
    if st.button("➕ Add Trim Step", key="add_trim"):
        if te > ts: add_step({"type":"trim","start":ts,"end":te})
        else: st.error("End must be after start.")

# ── FILTER ──────────────────────────────────────────────────────
with tabs[2]:
    st.markdown('<div class="card-title">🎨 Filter & Color Grade</div>', unsafe_allow_html=True)
    c1,c2 = st.columns(2)
    with c1:
        fn = st.selectbox("Filter preset",list(VIDEO_FILTERS.keys()),key="flt_sel")
        st.caption({"None":"No filter.","Vivid":"Boosted saturation.","Cinematic":"Teal & orange film look.",
                    "Warm Sunset":"Golden lifestyle.","Cool Blue":"Minimal clean.",
                    "B&W":"Monochrome.","Vintage":"Faded film.","HDR Pop":"High dynamic range.",
                    "Matte":"Lifted blacks.","Neon Night":"Hyper-saturated neon."}.get(fn,""))
    with c2:
        br = st.slider("Brightness",-0.5,0.5,0.0,0.05,key="gr_br")
        co = st.slider("Contrast",  0.5,2.0,1.0,0.05,key="gr_co")
        sa = st.slider("Saturation",0.0,3.0,1.0,0.1, key="gr_sa")
    if st.button("➕ Add Filter Step", key="add_flt"):
        add_step({"type":"filter","filter":fn,"brightness":br,"contrast":co,"saturation":sa})

# ── SPEED ───────────────────────────────────────────────────────
with tabs[3]:
    st.markdown('<div class="card-title">⚡ Speed Control</div>', unsafe_allow_html=True)
    spd_map={"0.25× Slow-mo":0.25,"0.5× Slow":0.5,"0.75× Slightly slow":0.75,
             "1.0× Normal":1.0,"1.5× Fast":1.5,"2.0× Faster":2.0,"4.0× Time-lapse":4.0}
    sp = st.selectbox("Preset",list(spd_map.keys()),index=1,key="spd_pr")
    spd_val = spd_map[sp]
    if st.checkbox("Custom",key="spd_cust"):
        spd_val = st.slider("Multiplier",0.1,8.0,spd_val,0.05,key="spd_v")
    dur2 = probe(st.session_state.source_path)["duration"] if st.session_state.source_path else 10
    st.caption(f"Output: **{dur2/spd_val:.1f}s**")
    if st.button("➕ Add Speed Step", key="add_spd"):
        add_step({"type":"speed","speed":spd_val})

# ── TEXT & TITLES ────────────────────────────────────────────────
with tabs[4]:
    st.markdown('<div class="card-title">📝 Text Overlays & Titles</div>', unsafe_allow_html=True)
    dur3 = probe(st.session_state.source_path)["duration"] if st.session_state.source_path else 10.0

    c1,c2 = st.columns(2)
    with c1:
        txt = st.text_input("Text content", "Your Title Here", key="tx_txt")
        style_preset = st.selectbox("Style preset", [
            "Custom","Lower Third","News Ticker","Title Card","Subtitle","Kinetic Bold"], key="tx_style")
        anim = st.selectbox("Animation", TEXT_ANIMS, key="tx_anim")
        font_sz = st.slider("Font size (px)", 16, 120, 48, key="tx_sz")

    with c2:
        txt_color = st.color_picker("Text color", "#FFFFFF", key="tx_col")
        bg_on = st.checkbox("Background box", value=(style_preset!="Custom"), key="tx_bg")
        bg_col = st.color_picker("Box color", "#000000", key="tx_bg_col") if bg_on else "#000000"
        shadow = st.checkbox("Drop shadow", True, key="tx_shad")

        t_start = st.number_input("Show from (s)", 0.0, float(dur3), 0.5, 0.5, key="tx_s")
        t_end   = st.number_input("Hide at (s)",   0.1, float(dur3), min(4.0,float(dur3)), 0.5, key="tx_e")

    st.markdown("**Position** (% from top-left)")
    xc,yc = st.columns(2)
    with xc: xp = st.slider("X position %", 0, 90, 5, key="tx_x")
    with yc: yp = st.slider("Y position %", 0, 90, 80, key="tx_y")

    # Preview text style hint
    style_hints = {
        "Lower Third":"Semi-transparent bar behind text — great for names & locations.",
        "News Ticker":"Red bar background — bold breaking news feel.",
        "Title Card":"Dark box framing around text.",
        "Subtitle":"Centered bottom caption style.",
        "Kinetic Bold":"Large bold centred impact text.",
        "Custom":"Full manual control.",
    }
    st.caption(f"💡 {style_hints.get(style_preset,'')}")

    # Preset overrides
    if style_preset == "Subtitle":    xp,yp,font_sz = 5,88,32
    if style_preset == "Kinetic Bold": xp,yp,font_sz = 5,40,80

    if st.button("➕ Add Text Layer", key="add_txt"):
        add_step({"type":"text","text":txt,"style":style_preset,"anim":anim,
                  "font_size":font_sz,"color":txt_color,"x_pct":xp,"y_pct":yp,
                  "start":t_start,"end":t_end,"bg":bg_on,"bg_color":bg_col,"shadow":shadow})

# ── WATERMARK ───────────────────────────────────────────────────
with tabs[5]:
    st.markdown('<div class="card-title">💧 Watermark & Logo</div>', unsafe_allow_html=True)
    wtype = st.radio("Type",["Text watermark","Logo / image"],key="wm_t",horizontal=True)
    pos_opts = ["Top Left","Top Right","Bottom Left","Bottom Right","Center"]
    pos  = st.selectbox("Position",pos_opts,index=3,key="wm_pos")
    opa  = st.slider("Opacity",0.1,1.0,0.75,0.05,key="wm_opa")

    if wtype=="Text watermark":
        c1,c2,c3 = st.columns(3)
        with c1: wm_txt = st.text_input("Text","@yourbrand",key="wm_tx")
        with c2: wm_col = st.selectbox("Color",["white","black","yellow","red","cyan"],key="wm_col")
        with c3: wm_sz  = st.slider("Size",12,72,28,key="wm_sz")
        if st.button("➕ Add Text Watermark", key="add_wmt"):
            add_step({"type":"watermark_text","text":wm_txt,"position":pos,
                      "opacity":opa,"color":wm_col,"size":wm_sz})
    else:
        logo_f = st.file_uploader("Logo PNG (transparent bg works best)",type=["png","jpg"],key="logo_up")
        logo_sz= st.slider("Logo size (% of width)",5,50,15,key="logo_sz")
        if logo_f:
            lpath = save_upload(logo_f, ".png")
            st.session_state.audio_store["logo_path"] = lpath
            st.caption(f"✅ Logo stored: {logo_f.name}")
        if st.button("➕ Add Logo Watermark", key="add_wml"):
            if "logo_path" in st.session_state.audio_store:
                add_step({"type":"watermark_logo","position":pos,"opacity":opa,"size_pct":logo_sz})
            else:
                st.error("Upload a logo first.")

# ── PROGRESS BAR ────────────────────────────────────────────────
with tabs[6]:
    st.markdown('<div class="card-title">📊 Progress Bar</div>', unsafe_allow_html=True)
    c1,c2,c3 = st.columns(3)
    with c1: pb_col  = st.color_picker("Bar color","#e11d48",key="pb_col")
    with c2: pb_ht   = st.slider("Height (px)",2,20,8,key="pb_ht")
    with c3: pb_pos  = st.selectbox("Position",["bottom","top"],key="pb_pos")
    st.caption("A video progress bar that fills from left to right as the video plays.")
    if st.button("➕ Add Progress Bar", key="add_pb"):
        add_step({"type":"progress_bar","color":pb_col,"height":pb_ht,"position":pb_pos})

# ── KEN BURNS ───────────────────────────────────────────────────
with tabs[7]:
    st.markdown('<div class="card-title">🔍 Ken Burns / Zoom Effect</div>', unsafe_allow_html=True)
    c1,c2 = st.columns(2)
    with c1: kz_s = st.slider("Start zoom",1.0,1.5,1.0,0.01,key="kz_s")
    with c2: kz_e = st.slider("End zoom",  1.0,1.5,1.08,0.01,key="kz_e")
    st.caption("Slow zoom from start to end zoom level over the full clip duration.")
    if st.button("➕ Add Ken Burns", key="add_kb"):
        add_step({"type":"kenburns","zoom_start":kz_s,"zoom_end":kz_e})

# ── AUDIO ───────────────────────────────────────────────────────
with tabs[8]:
    st.markdown('<div class="card-title">🎵 Audio</div>', unsafe_allow_html=True)
    aud_act = st.radio("Action",["Mute","Replace with music","Mix music + original","Adjust volume"],key="aud_act",horizontal=True)
    if "music" in aud_act.lower() or "mix" in aud_act.lower() or "replace" in aud_act.lower():
        af = st.file_uploader("Upload music (MP3 / WAV)",type=["mp3","wav"],key="aud_up")
        if af:
            ap = save_upload(af, "."+af.name.rsplit(".",1)[-1])
            st.session_state.audio_store["audio_path"] = ap
            st.caption(f"✅ Audio stored: {af.name}")
    step_extra = {}
    if "volume" in aud_act.lower():
        step_extra["vol"] = st.slider("Volume ×",0.1,4.0,1.5,0.1,key="vol_sl")
    if "mix" in aud_act.lower():
        c1,c2=st.columns(2)
        with c1: step_extra["music_vol"]=st.slider("Music vol",0.0,2.0,0.5,0.05,key="mv")
        with c2: step_extra["orig_vol"] =st.slider("Original vol",0.0,2.0,1.0,0.05,key="ov")
    act_map={"Mute":"mute","Replace with music":"replace","Mix music + original":"mix","Adjust volume":"volume"}
    if st.button("➕ Add Audio Step", key="add_aud"):
        add_step({"type":"audio","action":act_map.get(aud_act,"mute"),**step_extra})

# ── SUBTITLES ───────────────────────────────────────────────────
with tabs[9]:
    st.markdown('<div class="card-title">💬 Subtitles & Captions</div>', unsafe_allow_html=True)
    dur4 = probe(st.session_state.source_path)["duration"] if st.session_state.source_path else 10.0
    n = st.number_input("Lines",1,30,3,key="sub_n")
    lines=[]
    for i in range(int(n)):
        c1,c2,c3=st.columns([1,1,3])
        with c1: ss=st.number_input(f"Start {i+1}",0.0,float(dur4),float(i*3),0.5,key=f"ss{i}")
        with c2: se=st.number_input(f"End {i+1}",  0.0,float(dur4),float(i*3+2.5),0.5,key=f"se{i}")
        with c3: st2=st.text_input(f"Line {i+1}",f"Caption {i+1}",key=f"sl{i}")
        lines.append({"start":ss,"end":se,"text":st2})
    if st.button("➕ Add Subtitles Step", key="add_sub"):
        add_step({"type":"subtitles","lines":lines})

# ── EXPORT ──────────────────────────────────────────────────────
with tabs[10]:
    st.markdown('<div class="card-title">📐 Export for Platform</div>', unsafe_allow_html=True)
    plat = st.selectbox("Platform",list(PLATFORM_SPECS.keys()),key="exp_plat")
    spec = PLATFORM_SPECS[plat]
    c1,c2,c3 = st.columns(3)
    with c1:
        st.markdown(f'<div class="spec-card"><div class="spec-label">Resolution</div><div class="spec-value">{spec["w"]}×{spec["h"]}</div></div>', unsafe_allow_html=True)
        st.markdown(f'<div class="spec-card"><div class="spec-label">FPS</div><div class="spec-value">{spec["fps"]}</div></div>', unsafe_allow_html=True)
    with c2:
        q   = st.select_slider("Quality",["Draft","Standard","High","Max"],value="High",key="exp_q")
        cmode = st.radio("Fit",["Crop to fill","Letterbox"],key="exp_cm",horizontal=True)
    with c3:
        st.caption("Adds a final resize + encode step to match platform specs exactly.")
    if st.button("➕ Add Export Step", key="add_exp"):
        add_step({"type":"export","platform":plat,"quality":q,
                  "crop":"crop" if "Crop" in cmode else "letterbox"})

# ─── RENDER BUTTON ────────────────────────────────────────────────
st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
st.markdown("### 🎬 Render")

if not st.session_state.source_path:
    st.warning("Upload a source video first (see 'Source Videos' above).")
elif not st.session_state.pipeline:
    st.warning("Add at least one edit step above, then render.")
else:
    ncols = st.columns([2,1,1])
    with ncols[0]:
        st.markdown(f"**{len(st.session_state.pipeline)} step(s)** queued on **{st.session_state.source_name}**")
    with ncols[1]:
        if st.button("🎬 Render All Steps", key="render_btn", type="primary"):
            with st.spinner("Rendering pipeline… this may take a minute"):
                final, log = run_pipeline(
                    st.session_state.source_path,
                    st.session_state.pipeline,
                    st.session_state.audio_store,
                )
            with st.expander("Render log", expanded=final is None):
                for line in log:
                    st.text(line)
            if final and os.path.exists(final):
                save_history(st.session_state.source_name, f"Rendered {len(st.session_state.pipeline)} steps")
                st.success("✅ Render complete!")
                with open(final,"rb") as f:
                    st.download_button("⬇️ Download Final Video", f.read(),
                        "studio_output.mp4","video/mp4",key="render_dl")
            else:
                st.error("Render failed. Check the log above.")
    with ncols[2]:
        if st.button("🗑 Clear Pipeline", key="clear_render"):
            st.session_state.pipeline = []
            st.rerun()
