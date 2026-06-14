import streamlit as st
import streamlit.components.v1 as components
from PIL import Image
from io import BytesIO
import os, tempfile, subprocess, json, shutil
from utils import inject_css, save_upload, save_history

st.set_page_config(page_title="Video Studio", page_icon="🎬", layout="wide", initial_sidebar_state="collapsed")
inject_css()

st.markdown("""<style>
.stButton>button{background:linear-gradient(135deg,#e11d48,#7c3aed)!important;color:white!important;border:none!important;border-radius:8px!important;font-weight:600!important}
.stDownloadButton>button{background:#fff1f2!important;color:#e11d48!important;border:1px solid #fecdd3!important;border-radius:8px!important;font-weight:600!important}
.step-box{background:#fff;border:1.5px solid #e2e8f0;border-radius:14px;padding:1.4rem 1.5rem;margin-bottom:1rem}
.step-num{display:inline-flex;align-items:center;justify-content:center;width:28px;height:28px;background:linear-gradient(135deg,#e11d48,#7c3aed);color:white;border-radius:50%;font-size:13px;font-weight:700;margin-right:10px}
.step-title{font-family:'Space Grotesk',sans-serif;font-size:1.05rem;font-weight:700;color:#1e293b}
.queue-item{background:#f8fafc;border:1px solid #e2e8f0;border-left:4px solid #e11d48;border-radius:8px;padding:0.5rem 0.9rem;margin-bottom:0.35rem;display:flex;justify-content:space-between;align-items:center}
.qi-label{font-size:0.85rem;font-weight:600;color:#1e293b}
.qi-detail{font-size:0.75rem;color:#64748b;margin-top:1px}
</style>""", unsafe_allow_html=True)

# ── Session state ──────────────────────────────────────────────────
for k,v in {"src":None,"src_name":"","audio_path":None,"logo_path":None,"pipeline":[]}.items():
    if k not in st.session_state: st.session_state[k]=v

# ── FFmpeg ─────────────────────────────────────────────────────────
def ff(*a):
    r=subprocess.run(["ffmpeg","-y"]+list(a),capture_output=True,text=True)
    return r.returncode==0, r.stderr

def probe(p):
    r=subprocess.run(["ffprobe","-v","quiet","-print_format","json","-show_streams","-show_format",p],capture_output=True,text=True)
    if r.returncode!=0: return {"duration":0,"width":0,"height":0,"fps":30,"has_audio":False}
    d=json.loads(r.stdout)
    info={"duration":0,"width":0,"height":0,"fps":30,"has_audio":False}
    for s in d.get("streams",[]):
        if s.get("codec_type")=="video":
            info["width"]=s.get("width",0); info["height"]=s.get("height",0)
            try: n,dv=s.get("r_frame_rate","30/1").split("/"); info["fps"]=round(int(n)/max(int(dv),1),1)
            except: pass
            info["duration"]=float(s.get("duration") or d.get("format",{}).get("duration",0))
        if s.get("codec_type")=="audio": info["has_audio"]=True
    return info

def tmp(ext=".mp4"):
    t=tempfile.NamedTemporaryFile(delete=False,suffix=ext); t.close(); return t.name

def extract_frame(path, ts=1.0):
    out=tmp(".jpg")
    ok,_=ff("-ss",str(min(ts,max(0,probe(path)["duration"]-0.1))),"-i",path,"-vframes","1","-q:v","2",out)
    if ok and os.path.exists(out) and os.path.getsize(out)>0:
        return Image.open(out).copy()
    return None

FILTERS={
    "None":"",
    "Vivid":"eq=saturation=1.8:contrast=1.1:brightness=0.05",
    "Cinematic":"eq=saturation=0.85:contrast=1.2:brightness=-0.03,curves=r='0/0 0.5/0.42 1/1':g='0/0 0.5/0.5 1/0.9':b='0/0.05 0.5/0.5 1/0.85'",
    "Warm Sunset":"eq=saturation=1.3:brightness=0.04,curves=r='0/0 0.5/0.6 1/1':b='0/0 0.5/0.4 1/0.8'",
    "Cool Blue":"eq=saturation=1.1:brightness=-0.02,curves=b='0/0.05 0.5/0.6 1/1':r='0/0 0.5/0.4 1/0.9'",
    "Black & White":"colorchannelmixer=.299:.587:.114:0:.299:.587:.114:0:.299:.587:.114",
    "Vintage":"curves=r='0/0.1 0.5/0.55 1/0.9':g='0/0.05 0.5/0.5 1/0.85':b='0/0.1 0.5/0.45 1/0.75',eq=saturation=0.7",
    "HDR Pop":"eq=saturation=2.0:contrast=1.3:brightness=0.02",
    "Matte":"curves=r='0/0.08 1/0.9':g='0/0.05 1/0.88':b='0/0.1 1/0.85',eq=saturation=0.85",
    "Neon Night":"eq=saturation=2.2:contrast=1.4:brightness=-0.05",
}
PLATFORMS={
    "Instagram Reels (9:16)":{"w":1080,"h":1920,"fps":30},
    "YouTube Shorts (9:16)": {"w":1080,"h":1920,"fps":60},
    "YouTube (16:9)":        {"w":1920,"h":1080,"fps":30},
    "TikTok (9:16)":         {"w":1080,"h":1920,"fps":30},
    "Square (1:1)":          {"w":1080,"h":1080,"fps":30},
}
TEMPLATES={
    "🔥 Viral Reel":    [{"type":"filter","filter":"Vivid","br":0.05,"co":1.1,"sa":1.8},{"type":"wm","text":"@yourbrand","pos":"Bottom Right","opa":0.75},{"type":"export","platform":"Instagram Reels (9:16)","quality":"High","fit":"crop"}],
    "🎬 Cinematic":     [{"type":"filter","filter":"Cinematic","br":-0.03,"co":1.2,"sa":0.85},{"type":"kenburns","zs":1.0,"ze":1.08},{"type":"export","platform":"YouTube Shorts (9:16)","quality":"Max","fit":"letterbox"}],
    "🌅 Travel Vlog":   [{"type":"filter","filter":"Warm Sunset","br":0.04,"co":1.0,"sa":1.3},{"type":"text","text":"Your Destination","style":"Lower Third","anim":"Slide Up","fs":48,"color":"#FFFFFF","xp":5,"yp":80,"ts":1.0,"te":4.0},{"type":"export","platform":"YouTube (16:9)","quality":"High","fit":"letterbox"}],
    "🎵 Music Video":   [{"type":"filter","filter":"Neon Night","br":-0.05,"co":1.4,"sa":2.2},{"type":"wm","text":"@yourbrand","pos":"Bottom Right","opa":0.8},{"type":"export","platform":"Instagram Reels (9:16)","quality":"High","fit":"crop"}],
    "📰 News/Talk":     [{"type":"filter","filter":"None","br":0.02,"co":1.05,"sa":1.0},{"type":"bar","color":"#e11d48","height":8,"pos":"bottom"},{"type":"text","text":"Breaking News","style":"News Ticker","anim":"Slide Left","fs":40,"color":"#FFFFFF","xp":2,"yp":88,"ts":0.5,"te":5.0},{"type":"export","platform":"YouTube (16:9)","quality":"High","fit":"letterbox"}],
    "⚡ Quick Export":  [{"type":"export","platform":"Instagram Reels (9:16)","quality":"Standard","fit":"crop"}],
}
FONT_B="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

def run_step(inp, step):
    out=tmp(); t=step.get("type","")
    if t=="trim":
        ok,e=ff("-ss",str(step["start"]),"-i",inp,"-t",str(step["end"]-step["start"]),"-c:v","libx264","-c:a","aac","-preset","ultrafast",out)
    elif t=="filter":
        base=FILTERS.get(step.get("filter","None"),"")
        br=step.get("br",0); co=step.get("co",1); sa=step.get("sa",1)
        adj=f"eq=brightness={br}:contrast={co}:saturation={sa}"
        vf=",".join(x for x in [base, adj if step.get("filter","None")=="None" else ""] if x)
        if not vf: vf=adj
        ok,e=ff("-i",inp,"-vf",vf,"-c:v","libx264","-c:a","aac","-preset","ultrafast",out)
    elif t=="speed":
        spd=step["speed"]; info=probe(inp); vf=f"setpts={1/spd}*PTS"
        parts=[]; rem=spd
        while rem>2.0: parts.append("atempo=2.0"); rem/=2.0
        while rem<0.5: parts.append("atempo=0.5"); rem*=2.0
        parts.append(f"atempo={rem:.3f}")
        if info["has_audio"]: ok,e=ff("-i",inp,"-vf",vf,"-af",",".join(parts),"-c:v","libx264","-preset","ultrafast",out)
        else: ok,e=ff("-i",inp,"-vf",vf,"-an","-c:v","libx264","-preset","ultrafast",out)
    elif t=="text":
        info=probe(inp); dur=info["duration"]
        txt=step.get("text","Text").replace("'","\\'").replace(":","\\:")
        col=step.get("color","#FFFFFF").lstrip("#"); fc=f"0x{col}FF"
        fs=step.get("fs",48); ts=step.get("ts",0.0); te=step.get("te",dur)
        xp=step.get("xp",5); yp=step.get("yp",80)
        anim=step.get("anim","None"); style=step.get("style","Custom")
        try: fa=f":fontfile={FONT_B}"
        except: fa=""
        xe=f"(w*{xp/100})"; ye=f"(h*{yp/100})"
        if anim=="Fade In":   al=f"if(lt(t,{ts}),0,if(lt(t,{ts+0.5}),(t-{ts})/0.5,if(lt(t,{te-0.3}),1,max(0,1-(t-{te-0.3})/0.3))))"
        elif anim=="Slide Up": ye=f"if(lt(t,{ts}),h,if(lt(t,{ts+0.4}),(h*{yp/100})+(h-h*{yp/100})*(1-(t-{ts})/0.4),(h*{yp/100})))"; al=f"if(lt(t,{ts}),0,1)"
        elif anim=="Slide Left": xe=f"if(lt(t,{ts}),w,if(lt(t,{ts+0.4}),(w*{xp/100})+(w-w*{xp/100})*(1-(t-{ts})/0.4),(w*{xp/100})))"; al=f"if(lt(t,{ts}),0,1)"
        else: al=f"if(between(t,{ts},{te}),1,0)"
        en=f"between(t,{ts},{te})"
        sh=":shadowcolor=black@0.6:shadowx=2:shadowy=2"
        dt=f"drawtext=text='{txt}':fontsize={fs}{fa}:fontcolor={fc}@1.0:alpha='{al}':x={xe}:y={ye}:enable='{en}'{sh}"
        vf=dt
        if style=="Lower Third": vf=f"drawbox=x=0:y=(h*{yp/100})-{fs+16}:w=iw:h={fs+32}:color=0x00000080:t=fill:enable='{en}',{dt}"
        elif style=="News Ticker": vf=f"drawbox=x=0:y=(h*{yp/100})-8:w=iw:h={fs+20}:color=0xe11d48CC:t=fill:enable='{en}',{dt}"
        elif style=="Title Card": vf=f"drawbox=x=(w*{xp/100})-16:y=(h*{yp/100})-{fs+8}:w=iw/3:h={fs+16}:color=0x000000AA:t=fill:enable='{en}',{dt}"
        ok,e=ff("-i",inp,"-vf",vf,"-c:v","libx264","-c:a","aac","-preset","ultrafast",out)
    elif t=="wm":
        txt=step.get("text","@brand").replace("'","\\'")
        coords={"Top Left":("20","20"),"Top Right":("w-text_w-20","20"),"Bottom Left":("20","h-text_h-20"),"Bottom Right":("w-text_w-20","h-text_h-20"),"Center":("(w-text_w)/2","(h-text_h)/2")}
        x,y=coords.get(step.get("pos","Bottom Right"),("w-text_w-20","h-text_h-20"))
        vf=f"drawtext=text='{txt}':fontsize=28:fontcolor=white@{step.get('opa',0.75)}:x={x}:y={y}:shadowcolor=black@0.5:shadowx=2:shadowy=2"
        ok,e=ff("-i",inp,"-vf",vf,"-c:v","libx264","-c:a","aac","-preset","ultrafast",out)
    elif t=="logo" and st.session_state.logo_path:
        lp=st.session_state.logo_path; sz=step.get("size",15)/100; opa=step.get("opa",0.75)
        coords2={"Top Left":"10:10","Top Right":"main_w-overlay_w-10:10","Bottom Left":"10:main_h-overlay_h-10","Bottom Right":"main_w-overlay_w-10:main_h-overlay_h-10","Center":"(main_w-overlay_w)/2:(main_h-overlay_h)/2"}
        ovp=coords2.get(step.get("pos","Bottom Right"),"main_w-overlay_w-10:main_h-overlay_h-10")
        vf=f"[1:v]scale=iw*{sz:.2f}:-1,format=rgba,colorchannelmixer=aa={opa}[logo];[0:v][logo]overlay={ovp}"
        ok,e=ff("-i",inp,"-i",lp,"-filter_complex",vf,"-c:v","libx264","-c:a","aac","-preset","ultrafast",out)
    elif t=="bar":
        info=probe(inp); dur=info["duration"]
        col=step.get("color","#e11d48").lstrip("#"); ht=step.get("height",8)
        y=f"h-{ht}" if step.get("pos","bottom")=="bottom" else "0"
        vf=f"drawbox=x=0:y={y}:w=iw*(t/{dur}):h={ht}:color=0x{col}FF:t=fill"
        ok,e=ff("-i",inp,"-vf",vf,"-c:v","libx264","-c:a","aac","-preset","ultrafast",out)
    elif t=="kenburns":
        info=probe(inp); w,h=info["width"] or 1080,info["height"] or 1920
        fps=info["fps"] or 30; dur=info["duration"]
        zs=step.get("zs",1.0); ze=step.get("ze",1.08)
        frames=max(int(dur*fps),1)
        vf=(f"scale=iw*{ze}:ih*{ze},"
            f"zoompan=z='min(zoom+{(ze-zs)/frames:.6f},{ze})':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={fps}")
        ok,e=ff("-i",inp,"-vf",vf,"-c:v","libx264","-c:a","aac","-preset","ultrafast",out)
    elif t=="audio":
        action=step.get("action","mute"); ap=st.session_state.audio_path
        if action=="mute": ok,e=ff("-i",inp,"-c:v","copy","-an",out)
        elif action=="volume": ok,e=ff("-i",inp,"-af",f"volume={step.get('vol',1.5)}","-c:v","copy",out)
        elif action=="replace" and ap: ok,e=ff("-i",inp,"-i",ap,"-c:v","copy","-map","0:v:0","-map","1:a:0","-shortest",out)
        elif action=="mix" and ap:
            mv=step.get("mv",0.5); ov=step.get("ov",1.0)
            ok,e=ff("-i",inp,"-i",ap,"-filter_complex",f"[0:a]volume={ov}[a1];[1:a]volume={mv}[a2];[a1][a2]amix=inputs=2:duration=first[ao]","-map","0:v","-map","[ao]","-c:v","copy","-shortest",out)
        else: return inp,None
    elif t=="export":
        spec=PLATFORMS.get(step.get("platform","YouTube (16:9)"),{"w":1920,"h":1080,"fps":30})
        w,h=spec["w"],spec["h"]
        crf={"Draft":32,"Standard":26,"High":20,"Max":16}.get(step.get("quality","High"),20)
        fit=step.get("fit","crop")
        vf=(f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}" if fit=="crop"
            else f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black")
        ok,e=ff("-i",inp,"-vf",vf,"-r",str(spec["fps"]),"-c:v","libx264","-crf",str(crf),"-preset","fast","-c:a","aac","-b:a","192k",out)
    else:
        return inp,None
    if ok and os.path.exists(out) and os.path.getsize(out)>0: return out,None
    return None, e or "Output empty"

# ─────────────────────────────────────────────────────────────────
# PAGE
# ─────────────────────────────────────────────────────────────────
with st.sidebar:
    st.page_link("app.py", label="← Home", icon="🏠")
    st.page_link("pages/1_📄_SmartDoc.py", label="📄 SmartDoc")

st.markdown('<div style="font-family:\'Space Grotesk\',sans-serif;font-size:2rem;font-weight:700;background:linear-gradient(135deg,#e11d48,#7c3aed);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:4px">🎬 Video Studio</div>', unsafe_allow_html=True)
st.markdown('<div style="color:#64748b;font-size:0.9rem;margin-bottom:1.5rem">Upload → Add edits → Render & download</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════
# STEP 1 — UPLOAD
# ══════════════════════════════════════════════════════════
st.markdown('<div class="step-box">', unsafe_allow_html=True)
st.markdown('<span class="step-num">1</span><span class="step-title">Upload Video</span>', unsafe_allow_html=True)
st.markdown("")

col_up, col_info = st.columns([3,2])
with col_up:
    vf = st.file_uploader("Choose a video file (MP4, MOV, MKV, AVI)", type=["mp4","mov","mkv","avi"], key="vid_up", label_visibility="collapsed")
    if vf:
        p = save_upload(vf, "."+vf.name.rsplit(".",1)[-1])
        st.session_state.src = p
        st.session_state.src_name = vf.name
        st.video(vf)

with col_info:
    if st.session_state.src:
        info = probe(st.session_state.src)
        st.success(f"✅ **{st.session_state.src_name}**")
        st.markdown(f"""
- **Resolution:** {info['width']}×{info['height']}
- **Duration:** {info['duration']:.1f}s
- **FPS:** {info['fps']}
- **Audio:** {'Yes' if info['has_audio'] else 'No'}
""")

# Multiple clips merge
with st.expander("➕ Merge multiple clips into one", expanded=False):
    clips = st.file_uploader("Upload clips (will be joined in order)", type=["mp4","mov","mkv","avi"], accept_multiple_files=True, key="clips_up")
    if clips and st.button("Merge Clips", key="merge_btn"):
        with st.spinner(f"Merging {len(clips)} clips…"):
            paths=[]
            for c in clips:
                cp=save_upload(c,"."+c.name.rsplit(".",1)[-1])
                n=tmp()
                ff("-i",cp,"-c:v","libx264","-c:a","aac","-preset","ultrafast",n)
                paths.append(n)
            lst=tempfile.NamedTemporaryFile(delete=False,suffix=".txt",mode="w")
            for p2 in paths: lst.write(f"file '{p2}'\n")
            lst.close()
            out=tmp()
            ok,e=ff("-f","concat","-safe","0","-i",lst.name,"-c:v","libx264","-c:a","aac","-preset","ultrafast",out)
            os.unlink(lst.name)
        if ok and os.path.exists(out):
            st.session_state.src=out; st.session_state.src_name=f"merged_{len(clips)}_clips.mp4"
            st.success(f"✅ Merged {len(clips)} clips!")
            st.rerun()
        else: st.error(f"Merge failed: {e[-200:]}")

st.markdown('</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════
# STEP 2 — ADD EDITS
# ══════════════════════════════════════════════════════════
st.markdown('<div class="step-box">', unsafe_allow_html=True)
st.markdown('<span class="step-num">2</span><span class="step-title">Add Edits</span>', unsafe_allow_html=True)
st.markdown("")

dur = probe(st.session_state.src)["duration"] if st.session_state.src else 30.0

# ── Quick Templates ────────────────────────────────────────
st.markdown("**⚡ Quick Templates** — load a full edit in one click")
tcols = st.columns(len(TEMPLATES))
for i,(name,steps) in enumerate(TEMPLATES.items()):
    with tcols[i]:
        if st.button(name, key=f"tmpl_{i}", use_container_width=True):
            st.session_state.pipeline = [dict(s) for s in steps]
            st.success(f"Loaded {name}!")
            st.rerun()

st.markdown('<div style="border-top:1px solid #e2e8f0;margin:1rem 0"></div>', unsafe_allow_html=True)

# ── Edit sections as columns ───────────────────────────────
st.markdown("**Or build your own edit:**")

c1, c2, c3 = st.columns(3)

with c1:
    with st.expander("✂️ Trim", expanded=False):
        s_t = st.number_input("Start (s)", 0.0, float(dur), 0.0, 0.5, key="tr_s")
        e_t = st.number_input("End (s)", 0.1, float(dur), float(dur), 0.5, key="tr_e")
        if st.button("Add Trim", key="add_trim"):
            if e_t>s_t: st.session_state.pipeline.append({"type":"trim","start":s_t,"end":e_t}); st.rerun()
            else: st.error("End must be after start")

    with st.expander("🎨 Filter & Color", expanded=False):
        fn = st.selectbox("Filter", list(FILTERS.keys()), key="flt")
        br = st.slider("Brightness", -0.5, 0.5, 0.0, 0.05, key="br")
        co = st.slider("Contrast",   0.5,  2.0, 1.0, 0.05, key="co")
        sa = st.slider("Saturation", 0.0,  3.0, 1.0, 0.1,  key="sa")
        if st.button("Add Filter", key="add_flt"):
            st.session_state.pipeline.append({"type":"filter","filter":fn,"br":br,"co":co,"sa":sa}); st.rerun()

    with st.expander("⚡ Speed", expanded=False):
        spd = st.select_slider("Speed", [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 4.0], value=1.0, key="spd")
        st.caption(f"Output: {dur/spd:.1f}s")
        if st.button("Add Speed", key="add_spd"):
            st.session_state.pipeline.append({"type":"speed","speed":spd}); st.rerun()

with c2:
    with st.expander("📝 Text & Titles", expanded=False):
        txt = st.text_input("Text", "Your Title", key="tx")
        style = st.selectbox("Style", ["Custom","Lower Third","News Ticker","Title Card","Subtitle","Kinetic Bold"], key="txs")
        anim = st.selectbox("Animation", ["None","Fade In","Slide Up","Slide Left","Zoom In"], key="txa")
        fs = st.slider("Font size", 16, 100, 48, key="txfs")
        col2a, col2b = st.columns(2)
        with col2a: txcol = st.color_picker("Color", "#FFFFFF", key="txcol")
        with col2b:
            ts2 = st.number_input("From", 0.0, float(dur), 0.5, 0.5, key="txts")
            te2 = st.number_input("To", 0.1, float(dur), min(4.0,float(dur)), 0.5, key="txte")
        xp = st.slider("X position %", 0, 90, 5, key="txx")
        yp = st.slider("Y position %", 0, 90, 80, key="txy")
        if st.button("Add Text", key="add_txt"):
            st.session_state.pipeline.append({"type":"text","text":txt,"style":style,"anim":anim,"fs":fs,"color":txcol,"xp":xp,"yp":yp,"ts":ts2,"te":te2}); st.rerun()

    with st.expander("💧 Watermark", expanded=False):
        wm_txt = st.text_input("Watermark text", "@yourbrand", key="wmt")
        wm_pos = st.selectbox("Position", ["Bottom Right","Bottom Left","Top Right","Top Left","Center"], key="wmp")
        wm_opa = st.slider("Opacity", 0.1, 1.0, 0.75, 0.05, key="wmo")
        if st.button("Add Watermark", key="add_wm"):
            st.session_state.pipeline.append({"type":"wm","text":wm_txt,"pos":wm_pos,"opa":wm_opa}); st.rerun()

        st.markdown('<div style="border-top:1px solid #f1f5f9;margin:8px 0"></div>', unsafe_allow_html=True)
        logo_f = st.file_uploader("Or upload logo (PNG)", type=["png","jpg"], key="logo_up")
        if logo_f:
            st.session_state.logo_path = save_upload(logo_f, ".png")
            logo_pos = st.selectbox("Logo position", ["Bottom Right","Bottom Left","Top Right","Top Left","Center"], key="lgp")
            logo_sz  = st.slider("Logo size %", 5, 40, 15, key="lgsz")
            logo_opa = st.slider("Logo opacity", 0.1, 1.0, 0.75, key="lgopa")
            if st.button("Add Logo", key="add_logo"):
                st.session_state.pipeline.append({"type":"logo","pos":logo_pos,"size":logo_sz,"opa":logo_opa}); st.rerun()

with c3:
    with st.expander("🎵 Audio", expanded=False):
        aud_act = st.radio("Action", ["Mute original","Adjust volume","Replace with music","Mix music + original"], key="audact")
        if "music" in aud_act.lower() or "mix" in aud_act.lower():
            aud_f = st.file_uploader("Music (MP3/WAV)", type=["mp3","wav"], key="aud_up")
            if aud_f: st.session_state.audio_path = save_upload(aud_f, "."+aud_f.name.rsplit(".",1)[-1]); st.caption(f"✅ {aud_f.name}")
        extra={}
        if "volume" in aud_act.lower(): extra["vol"]=st.slider("Volume ×",0.1,4.0,1.5,0.1,key="vol")
        if "mix" in aud_act.lower():
            extra["mv"]=st.slider("Music vol",0.0,2.0,0.5,0.05,key="mv")
            extra["ov"]=st.slider("Original vol",0.0,2.0,1.0,0.05,key="ov")
        act_map={"Mute original":"mute","Adjust volume":"volume","Replace with music":"replace","Mix music + original":"mix"}
        if st.button("Add Audio Step", key="add_aud"):
            st.session_state.pipeline.append({"type":"audio","action":act_map.get(aud_act,"mute"),**extra}); st.rerun()

    with st.expander("📊 Progress Bar", expanded=False):
        pb_col = st.color_picker("Bar color","#e11d48",key="pbc")
        pb_h   = st.slider("Height px",2,20,8,key="pbh")
        pb_pos = st.radio("Position",["bottom","top"],horizontal=True,key="pbpos")
        if st.button("Add Progress Bar",key="add_pb"):
            st.session_state.pipeline.append({"type":"bar","color":pb_col,"height":pb_h,"pos":pb_pos}); st.rerun()

    with st.expander("🔍 Ken Burns Zoom", expanded=False):
        kz_s = st.slider("Start zoom",1.0,1.5,1.0,0.01,key="kzs")
        kz_e = st.slider("End zoom",  1.0,1.5,1.08,0.01,key="kze")
        if st.button("Add Zoom",key="add_kb"):
            st.session_state.pipeline.append({"type":"kenburns","zs":kz_s,"ze":kz_e}); st.rerun()

    with st.expander("📐 Platform Export", expanded=False):
        exp_plat = st.selectbox("Platform", list(PLATFORMS.keys()), key="eplat")
        exp_q    = st.select_slider("Quality", ["Draft","Standard","High","Max"], value="High", key="eq")
        exp_fit  = st.radio("Fit", ["Crop to fill","Letterbox"], horizontal=True, key="efit")
        if st.button("Add Export Step", key="add_exp"):
            st.session_state.pipeline.append({"type":"export","platform":exp_plat,"quality":exp_q,"fit":"crop" if "Crop" in exp_fit else "letterbox"}); st.rerun()

    with st.expander("💬 Subtitles", expanded=False):
        n_subs = st.number_input("Lines",1,20,2,key="nsubs")
        sub_lines=[]
        for i in range(int(n_subs)):
            ca,cb,cc=st.columns([1,1,2])
            with ca: ss=st.number_input(f"S{i+1}",0.0,float(dur),float(i*3),0.5,key=f"ss{i}")
            with cb: se=st.number_input(f"E{i+1}",0.0,float(dur),float(i*3+2.5),0.5,key=f"se{i}")
            with cc: sl=st.text_input(f"L{i+1}",f"Caption {i+1}",key=f"sl{i}")
            sub_lines.append({"start":ss,"end":se,"text":sl})
        if st.button("Add Subtitles",key="add_sub"):
            # burn subs via drawtext chain
            for ln in sub_lines:
                st.session_state.pipeline.append({"type":"text","text":ln["text"],"style":"Subtitle","anim":"Fade In","fs":32,"color":"#FFFFFF","xp":10,"yp":85,"ts":ln["start"],"te":ln["end"]})
            st.rerun()

st.markdown('</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════
# QUEUE
# ══════════════════════════════════════════════════════════
if st.session_state.pipeline:
    st.markdown('<div class="step-box">', unsafe_allow_html=True)
    ICONS={"trim":"✂️","filter":"🎨","speed":"⚡","text":"📝","wm":"💧","logo":"🖼️","bar":"📊","kenburns":"🔍","audio":"🎵","export":"📐"}
    hdr_col, clr_col = st.columns([5,1])
    with hdr_col: st.markdown(f'<span class="step-num">✓</span><span class="step-title">Edit Queue — {len(st.session_state.pipeline)} step(s)</span>', unsafe_allow_html=True)
    with clr_col:
        if st.button("Clear All", key="clr"):
            st.session_state.pipeline=[]; st.rerun()
    st.markdown("")
    for i,step in enumerate(st.session_state.pipeline):
        ic=ICONS.get(step["type"],"•")
        detail={
            "trim":f'{step.get("start",0):.1f}s → {step.get("end",0):.1f}s',
            "filter":f'{step.get("filter","None")} | br:{step.get("br",0):+.2f} co:{step.get("co",1):.1f} sa:{step.get("sa",1):.1f}',
            "speed":f'×{step.get("speed",1)}',
            "text":f'"{step.get("text","")[:28]}" — {step.get("style","")} {step.get("anim","")}',
            "wm":f'"{step.get("text","")}" at {step.get("pos","")}',
            "logo":f'{step.get("pos","")} size {step.get("size",15)}%',
            "bar":f'{step.get("pos","bottom")} {step.get("color","")} {step.get("height",8)}px',
            "kenburns":f'zoom {step.get("zs",1.0)}→{step.get("ze",1.08)}',
            "audio":step.get("action",""),
            "export":f'{step.get("platform","")} {step.get("quality","")}',
        }.get(step["type"],"")
        dc1,dc2=st.columns([8,1])
        with dc1:
            st.markdown(f'<div class="queue-item"><div><div class="qi-label">{ic} {step["type"].replace("_"," ").title()}</div><div class="qi-detail">{detail}</div></div></div>', unsafe_allow_html=True)
        with dc2:
            if st.button("🗑", key=f"del_{i}", help="Remove"):
                st.session_state.pipeline.pop(i); st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════
# STEP 3 — RENDER
# ══════════════════════════════════════════════════════════
st.markdown('<div class="step-box">', unsafe_allow_html=True)
st.markdown('<span class="step-num">3</span><span class="step-title">Render & Download</span>', unsafe_allow_html=True)
st.markdown("")

if not st.session_state.src:
    st.info("Upload a video in Step 1 first.")
elif not st.session_state.pipeline:
    st.info("Add at least one edit in Step 2.")
else:
    st.markdown(f"Ready to render **{len(st.session_state.pipeline)} edit(s)** on **{st.session_state.src_name}**")
    if st.button("🎬 Render Video", key="render", type="primary"):
        prog = st.progress(0, text="Starting…")
        cur = tmp(); shutil.copy2(st.session_state.src, cur)
        steps = st.session_state.pipeline; ok_all=True; err_msg=""
        for i,step in enumerate(steps):
            prog.progress(i/len(steps), text=f"Step {i+1}/{len(steps)}: {step['type']}…")
            result,err=run_step(cur,step)
            if result is None: ok_all=False; err_msg=err or "Failed"; break
            cur=result
        prog.progress(1.0, text="Done!")
        if ok_all and os.path.exists(cur) and os.path.getsize(cur)>0:
            save_history(st.session_state.src_name, f"Rendered {len(steps)} steps")
            st.success("🎉 Done! Your video is ready.")
            r1,r2=st.columns([1,2])
            with r1:
                frame=extract_frame(cur,1.0)
                if frame: st.image(frame, caption="Preview frame", use_container_width=True)
            with r2:
                sz=round(os.path.getsize(cur)/1_048_576,1)
                st.markdown(f"**File size:** {sz} MB")
                with open(cur,"rb") as f:
                    st.download_button("⬇️ Download Video", f.read(), "edited_video.mp4", "video/mp4", key="dl", use_container_width=True)
        else:
            prog.empty()
            st.error(f"Render failed: {err_msg[-300:] if err_msg else 'Unknown error'}")

st.markdown('</div>', unsafe_allow_html=True)
