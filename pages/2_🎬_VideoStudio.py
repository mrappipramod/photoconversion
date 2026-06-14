import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
import os, tempfile, subprocess, json, shutil, base64
from utils import inject_css, save_upload, save_history

st.set_page_config(page_title="Video Studio", page_icon="🎬", layout="wide", initial_sidebar_state="collapsed")
inject_css()

st.markdown("""<style>
.stButton > button{background:linear-gradient(135deg,#e11d48,#7c3aed)!important;color:white!important}
.stDownloadButton > button{background:#fff1f2!important;color:#e11d48!important;border-color:#fecdd3!important}
.render-card{background:#fff;border:1px solid #e2e8f0;border-radius:14px;padding:1.2rem;margin-bottom:1rem}
.pipe-badge{display:inline-block;background:#fff1f2;border:1px solid #fecdd3;border-radius:20px;padding:2px 10px;font-size:0.78rem;color:#e11d48;margin:2px;font-weight:500}
</style>""", unsafe_allow_html=True)

# ── Sidebar ────────────────────────────────────────────────────────
with st.sidebar:
    st.page_link("app.py", label="← Home", icon="🏠")
    st.page_link("pages/1_📄_SmartDoc.py", label="📄 SmartDoc")

# ── Session state ──────────────────────────────────────────────────
for k,v in {"source_path":None,"source_name":"","audio_store":{},"render_log":[],"pipeline":[]}.items():
    if k not in st.session_state: st.session_state[k]=v

# ── FFmpeg helpers ─────────────────────────────────────────────────
def ff(*args):
    r=subprocess.run(["ffmpeg","-y"]+list(args),capture_output=True,text=True)
    return r.returncode==0,r.stderr

def probe(path):
    r=subprocess.run(["ffprobe","-v","quiet","-print_format","json","-show_streams","-show_format",path],capture_output=True,text=True)
    if r.returncode!=0: return {"duration":0,"width":0,"height":0,"fps":30,"has_audio":False,"size_mb":0}
    d=json.loads(r.stdout)
    info={"duration":0,"width":0,"height":0,"fps":30,"has_audio":False,"size_mb":0}
    for s in d.get("streams",[]):
        if s.get("codec_type")=="video":
            info["width"]=s.get("width",0);info["height"]=s.get("height",0)
            try:
                n,dv=s.get("r_frame_rate","30/1").split("/")
                info["fps"]=round(int(n)/max(int(dv),1),2)
            except: pass
            info["duration"]=float(s.get("duration") or d.get("format",{}).get("duration",0))
        if s.get("codec_type")=="audio": info["has_audio"]=True
    info["size_mb"]=round(int(d.get("format",{}).get("size",0))/1_048_576,1)
    return info

def tmpout(suffix=".mp4"):
    t=tempfile.NamedTemporaryFile(delete=False,suffix=suffix);t.close();return t.name

VIDEO_FILTERS={
    "None":"","Vivid":"eq=saturation=1.8:contrast=1.1:brightness=0.05",
    "Cinematic":"eq=saturation=0.85:contrast=1.2:brightness=-0.03,curves=r='0/0 0.5/0.42 1/1':g='0/0 0.5/0.5 1/0.9':b='0/0.05 0.5/0.5 1/0.85'",
    "Warm Sunset":"eq=saturation=1.3:brightness=0.04,curves=r='0/0 0.5/0.6 1/1':b='0/0 0.5/0.4 1/0.8'",
    "Cool Blue":"eq=saturation=1.1:brightness=-0.02,curves=b='0/0.05 0.5/0.6 1/1':r='0/0 0.5/0.4 1/0.9'",
    "B&W":"colorchannelmixer=.299:.587:.114:0:.299:.587:.114:0:.299:.587:.114",
    "Vintage":"curves=r='0/0.1 0.5/0.55 1/0.9':g='0/0.05 0.5/0.5 1/0.85':b='0/0.1 0.5/0.45 1/0.75',eq=saturation=0.7",
    "HDR Pop":"eq=saturation=2.0:contrast=1.3:brightness=0.02,unsharp=5:5:1.5:5:5:0.0",
    "Matte":"curves=r='0/0.08 1/0.9':g='0/0.05 1/0.88':b='0/0.1 1/0.85',eq=saturation=0.85",
    "Neon Night":"eq=saturation=2.2:contrast=1.4:brightness=-0.05,curves=b='0/0.1 0.5/0.7 1/1'",
}
PLATFORM_SPECS={
    "Instagram Reels (9:16)":{"w":1080,"h":1920,"fps":30},
    "YouTube Shorts (9:16)": {"w":1080,"h":1920,"fps":60},
    "YouTube (16:9)":        {"w":1920,"h":1080,"fps":30},
    "TikTok (9:16)":         {"w":1080,"h":1920,"fps":30},
    "Square (1:1)":          {"w":1080,"h":1080,"fps":30},
}
FONT_B="/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# ── Step renderers ─────────────────────────────────────────────────
def run_step(inp, step, store):
    t=step.get("type","")
    out=tmpout()
    if t=="trim":
        ok,e=ff("-ss",str(step.get("start",0)),"-i",inp,"-t",str(step.get("end",10)-step.get("start",0)),"-c:v","libx264","-c:a","aac","-preset","ultrafast",out)
    elif t=="filter":
        base=VIDEO_FILTERS.get(step.get("filter","None"),"")
        br=step.get("brightness",0);co=step.get("contrast",1);sa=step.get("saturation",1)
        adj=f"eq=brightness={br}:contrast={co}:saturation={sa}"
        vf=",".join(filter(None,[base,adj if step.get("filter","None")=="None" else ""]))
        if not vf: vf=adj
        ok,e=ff("-i",inp,"-vf",vf,"-c:v","libx264","-c:a","aac","-preset","ultrafast",out)
    elif t=="speed":
        spd=step.get("speed",1.0);info=probe(inp)
        vf=f"setpts={1/spd}*PTS"
        parts=[];rem=spd
        while rem>2.0: parts.append("atempo=2.0");rem/=2.0
        while rem<0.5: parts.append("atempo=0.5");rem*=2.0
        parts.append(f"atempo={rem:.3f}")
        if info["has_audio"]: ok,e=ff("-i",inp,"-vf",vf,"-af",",".join(parts),"-c:v","libx264","-preset","ultrafast",out)
        else: ok,e=ff("-i",inp,"-vf",vf,"-an","-c:v","libx264","-preset","ultrafast",out)
    elif t=="text":
        info=probe(inp);dur=info["duration"]
        txt=step.get("text","Text").replace("'","\\'").replace(":","\\:")
        color=step.get("color","#FFFFFF").lstrip("#");fc=f"0x{color}FF"
        fs=step.get("font_size",48)
        ts=step.get("start",0.0);te=step.get("end",dur)
        xp=step.get("x_pct",5);yp=step.get("y_pct",80)
        anim=step.get("anim","None");style=step.get("style","Custom")
        shadow=":shadowcolor=black@0.6:shadowx=2:shadowy=2" if step.get("shadow",True) else ""
        bg_col=step.get("bg_color","000000").lstrip("#")
        box=f":box=1:boxcolor=0x{bg_col}@0.6:boxborderw=8" if step.get("bg",False) else ""
        try: fa=f":fontfile={FONT_B}"
        except: fa=""
        xe=f"(w*{xp/100})";ye=f"(h*{yp/100})"
        if anim=="Fade In":   al=f"if(lt(t,{ts}),0,if(lt(t,{ts+0.5}),(t-{ts})/0.5,if(lt(t,{te-0.3}),1,max(0,1-(t-{te-0.3})/0.3))))"
        elif anim=="Slide Up": ye=f"if(lt(t,{ts}),h,if(lt(t,{ts+0.4}),(h*{yp/100})+(h-h*{yp/100})*(1-(t-{ts})/0.4),(h*{yp/100})))";al=f"if(lt(t,{ts}),0,1)"
        elif anim=="Slide Left": xe=f"if(lt(t,{ts}),w,if(lt(t,{ts+0.4}),(w*{xp/100})+(w-w*{xp/100})*(1-(t-{ts})/0.4),(w*{xp/100})))";al=f"if(lt(t,{ts}),0,1)"
        else: al=f"if(between(t,{ts},{te}),1,0)"
        en=f"between(t,{ts},{te})"
        dt=f"drawtext=text='{txt}':fontsize={fs}{fa}:fontcolor={fc}@1.0:alpha='{al}':x={xe}:y={ye}:enable='{en}'{shadow}{box}"
        vf=dt
        if style=="Lower Third": vf=f"drawbox=x=0:y=(h*{yp/100})-{fs+16}:w=iw:h={fs+32}:color=0x00000080:t=fill:enable='{en}',{dt}"
        elif style=="News Ticker": vf=f"drawbox=x=0:y=(h*{yp/100})-8:w=iw:h={fs+20}:color=0xe11d48CC:t=fill:enable='{en}',{dt}"
        elif style=="Title Card": vf=f"drawbox=x=(w*{xp/100})-16:y=(h*{yp/100})-{fs+8}:w=iw/3:h={fs+16}:color=0x000000AA:t=fill:enable='{en}',{dt}"
        ok,e=ff("-i",inp,"-vf",vf,"-c:v","libx264","-c:a","aac","-preset","ultrafast",out)
    elif t=="watermark_text":
        txt=step.get("text","@brand").replace("'","\\'")
        pos=step.get("position","Bottom Right")
        opa=step.get("opacity",0.75);col=step.get("color","white");sz=step.get("size",28)
        coords={"Top Left":("20","20"),"Top Right":("w-text_w-20","20"),
                "Bottom Left":("20","h-text_h-20"),"Bottom Right":("w-text_w-20","h-text_h-20"),
                "Center":("(w-text_w)/2","(h-text_h)/2")}
        x,y=coords.get(pos,("w-text_w-20","h-text_h-20"))
        vf=f"drawtext=text='{txt}':fontsize={sz}:fontcolor={col}@{opa}:x={x}:y={y}:shadowcolor=black@0.5:shadowx=2:shadowy=2"
        ok,e=ff("-i",inp,"-vf",vf,"-c:v","libx264","-c:a","aac","-preset","ultrafast",out)
    elif t=="progress_bar":
        info=probe(inp);dur=info["duration"]
        col=step.get("color","#e11d48").lstrip("#");ht=step.get("height",8)
        y=f"h-{ht}" if step.get("position","bottom")=="bottom" else "0"
        vf=f"drawbox=x=0:y={y}:w=iw*(t/{dur}):h={ht}:color=0x{col}FF:t=fill"
        ok,e=ff("-i",inp,"-vf",vf,"-c:v","libx264","-c:a","aac","-preset","ultrafast",out)
    elif t=="kenburns":
        info=probe(inp);w,h=info["width"] or 1080,info["height"] or 1920
        fps=info["fps"] or 30;dur=info["duration"]
        zs=step.get("zoom_start",1.0);ze=step.get("zoom_end",1.08)
        frames=max(int(dur*fps),1)
        vf=(f"scale=iw*{ze}:ih*{ze},"
            f"zoompan=z='min(zoom+{(ze-zs)/frames:.6f},{ze})':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={fps}")
        ok,e=ff("-i",inp,"-vf",vf,"-c:v","libx264","-c:a","aac","-preset","ultrafast",out)
    elif t=="audio":
        action=step.get("action","mute");ap=store.get("audio_path")
        if action=="mute": ok,e=ff("-i",inp,"-c:v","copy","-an",out)
        elif action=="volume": ok,e=ff("-i",inp,"-af",f"volume={step.get('vol',1.5)}","-c:v","copy",out)
        elif action=="replace" and ap: ok,e=ff("-i",inp,"-i",ap,"-c:v","copy","-map","0:v:0","-map","1:a:0","-shortest",out)
        elif action=="mix" and ap:
            mv=step.get("music_vol",0.5);ov=step.get("orig_vol",1.0)
            ok,e=ff("-i",inp,"-i",ap,"-filter_complex",f"[0:a]volume={ov}[a1];[1:a]volume={mv}[a2];[a1][a2]amix=inputs=2:duration=first[ao]","-map","0:v","-map","[ao]","-c:v","copy","-shortest",out)
        else: return inp,None
    elif t=="subtitles":
        lines=step.get("lines",[])
        if not lines: return inp,None
        srt=tempfile.NamedTemporaryFile(delete=False,suffix=".srt",mode="w")
        def ft(x): h=int(x//3600);m=int((x%3600)//60);s=int(x%60);ms=int((x-int(x))*1000);return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
        for i,ln in enumerate(lines,1): srt.write(f"{i}\n{ft(ln['start'])} --> {ft(ln['end'])}\n{ln['text']}\n\n")
        srt.close()
        ok,e=ff("-i",inp,"-vf",f"subtitles={srt.name}:force_style='FontSize=24,PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,Outline=2,Bold=1'","-c:a","copy",out)
        os.unlink(srt.name)
    elif t=="export":
        spec=PLATFORM_SPECS.get(step.get("platform","YouTube (16:9)"),{"w":1920,"h":1080,"fps":30})
        w,h=spec["w"],spec["h"]
        crf={"Draft":32,"Standard":26,"High":20,"Max":16}.get(step.get("quality","High"),20)
        mode=step.get("crop","crop")
        vf=(f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}" if mode=="crop"
            else f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black")
        ok,e=ff("-i",inp,"-vf",vf,"-r",str(spec["fps"]),"-c:v","libx264","-crf",str(crf),"-preset","fast","-c:a","aac","-b:a","192k",out)
    else:
        return inp,None
    if ok and os.path.exists(out) and os.path.getsize(out)>0: return out,None
    return None,e if not ok else "Output file empty"

def run_pipeline(source, steps, store):
    cur=tmpout();shutil.copy2(source,cur)
    log=[]
    for i,step in enumerate(steps):
        t=step.get("type","")
        if t in ("merge_note",): continue  # handled separately
        log.append(f"Step {i+1}/{len(steps)}: {t}")
        result,err=run_step(cur,step,store)
        if result is None: log.append(f"  ❌ {err[-200:] if err else 'failed'}");return None,log
        cur=result;log.append(f"  ✅ OK")
    return cur,log

# ── Preview frame helper ───────────────────────────────────────────
def extract_frame(video_path, ts=1.0):
    out=tmpout(".jpg")
    ok,_=ff("-ss",str(ts),"-i",video_path,"-vframes","1","-q:v","2",out)
    if ok and os.path.exists(out):
        return Image.open(out).copy()
    return None

# ─────────────────────────────────────────────────────────────────
# UI
# ─────────────────────────────────────────────────────────────────
st.markdown('<div style="font-family:\'Space Grotesk\',sans-serif;font-size:2rem;font-weight:700;background:linear-gradient(135deg,#e11d48,#7c3aed);-webkit-background-clip:text;-webkit-text-fill-color:transparent;margin-bottom:4px">🎬 Video Studio</div>', unsafe_allow_html=True)
st.markdown('<div style="color:#64748b;font-size:0.9rem;margin-bottom:1rem">Visual canvas editor + ffmpeg render engine</div>', unsafe_allow_html=True)

# ── STEP 1: Upload ────────────────────────────────────────────────
with st.expander("📂 Step 1 — Upload Source Video", expanded=st.session_state.source_path is None):
    c1,c2=st.columns([3,1])
    with c1:
        vf=st.file_uploader("Upload video (MP4, MOV, MKV, AVI)",type=["mp4","mov","mkv","avi"],key="src_vid")
        if vf:
            p=save_upload(vf,"."+vf.name.rsplit(".",1)[-1])
            st.session_state.source_path=p
            st.session_state.source_name=vf.name
    with c2:
        if vf: st.success(f"✅ {vf.name}")
    if st.session_state.source_path:
        info=probe(st.session_state.source_path)
        cols=st.columns(5)
        for col,lbl,val in zip(cols,["File","Resolution","Duration","FPS","Size"],
            [st.session_state.source_name,f"{info['width']}×{info['height']}",
             f"{info['duration']:.1f}s",str(info['fps']),f"{info['size_mb']}MB"]):
            col.metric(lbl,val)

st.markdown("---")

# ── STEP 2: Visual Canvas Editor ─────────────────────────────────
st.markdown("### 🎨 Step 2 — Design in Visual Editor")
st.caption("Use the canvas editor to design your video. When done, export the config (⬇ Export Config button) and paste it in Step 3 to render.")

# Load the React editor HTML
EDITOR_HTML = open(__file__.replace("2_🎬_VideoStudio.py","../canvas_editor.html") if os.path.exists(__file__.replace("2_🎬_VideoStudio.py","../canvas_editor.html")) else "/dev/null").read() if False else None

# Embed the canvas editor via iframe pointing to the artifact
# Since we can't serve a separate file easily, we inline the full HTML
CANVAS_HTML = r"""
<!DOCTYPE html><html><head><meta charset="UTF-8">
<style>
*{box-sizing:border-box;margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Inter',sans-serif}
body{background:#111;color:#f1f5f9;height:100vh;overflow:hidden;display:flex;flex-direction:column;font-size:13px}
#topbar{height:44px;background:#1a1a2e;border-bottom:1px solid #2a2a3e;display:flex;align-items:center;padding:0 12px;gap:8px;flex-shrink:0}
.tb-logo{font-weight:700;font-size:13px;background:linear-gradient(135deg,#e11d48,#7c3aed);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.tb-btn{background:#2a2a3e;border:1px solid #3a3a5e;color:#cbd5e1;padding:4px 10px;border-radius:5px;font-size:11px;cursor:pointer}
.tb-btn:hover{background:#3a3a5e;color:#fff}
.tb-btn.red{background:linear-gradient(135deg,#e11d48,#7c3aed);border:none;color:#fff;font-weight:600}
#main{display:flex;flex:1;overflow:hidden}
#left{width:48px;background:#1a1a2e;border-right:1px solid #2a2a3e;display:flex;flex-direction:column;align-items:center;padding:6px 0;gap:3px}
.tool{width:36px;height:36px;border-radius:7px;border:none;background:transparent;color:#64748b;cursor:pointer;display:flex;flex-direction:column;align-items:center;justify-content:center;font-size:14px;gap:1px}
.tool:hover{background:#2a2a3e;color:#e2e8f0}
.tool.on{background:#e11d4820;color:#e11d48;border:1px solid #e11d4840}
.tlbl{font-size:7px;font-weight:500}
#cw{flex:1;display:flex;flex-direction:column;background:#0a0a15;overflow:hidden}
#ca{flex:1;display:flex;align-items:center;justify-content:center;position:relative;overflow:hidden}
#cv{position:relative;background:#000;overflow:hidden;box-shadow:0 0 0 1px #3a3a5e,0 4px 24px #0008}
#cv video{width:100%;height:100%;object-fit:cover;position:absolute;top:0;left:0}
#ov{position:absolute;top:0;left:0;width:100%;height:100%;pointer-events:none}
.clayer{position:absolute;cursor:move;pointer-events:all;user-select:none}
.clayer.sel{outline:2px solid #e11d48;outline-offset:1px}
#uz{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;cursor:pointer;z-index:5}
#uz.hidden{display:none}
.uico{font-size:32px;color:#3a3a5e}
.utxt{font-size:13px;color:#64748b}
#fi{display:none}
#pb{display:flex;align-items:center;gap:6px;padding:5px 12px;background:#16162a;border-top:1px solid #2a2a3e;flex-shrink:0}
.pbb{width:24px;height:24px;border-radius:50%;border:1px solid #3a3a5e;background:#2a2a3e;color:#94a3b8;cursor:pointer;display:flex;align-items:center;justify-content:center;font-size:10px}
.pbb:hover{background:#3a3a5e;color:#fff}
#td{font-size:11px;color:#64748b;font-family:monospace;min-width:72px}
#tl{height:90px;background:#13132a;border-top:1px solid #2a2a3e;flex-shrink:0;padding:6px 12px;overflow-x:auto}
.tls{display:flex;gap:4px;margin-top:6px;flex-wrap:nowrap}
.tli{background:#2a2a3e;border:1px solid #3a3a5e;border-radius:5px;padding:2px 8px;font-size:9px;color:#94a3b8;white-space:nowrap;cursor:pointer}
.tli:hover{border-color:#e11d48;color:#e11d48}
#right{width:240px;background:#1a1a2e;border-left:1px solid #2a2a3e;overflow-y:auto;flex-shrink:0}
#right::-webkit-scrollbar{width:3px}
#right::-webkit-scrollbar-thumb{background:#3a3a5e}
.pnl{padding:10px 12px;border-bottom:1px solid #2a2a3e}
.ptit{font-size:9px;font-weight:600;color:#64748b;text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px}
.pr{display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;gap:6px}
.pl{font-size:11px;color:#94a3b8;min-width:52px;flex-shrink:0}
.pv{font-size:11px;color:#e2e8f0;font-weight:500;min-width:30px;text-align:right}
input[type=range]{width:100%;accent-color:#e11d48;height:2px}
input[type=text],input[type=number],select,textarea{width:100%;background:#0f0f1a;border:1px solid #3a3a5e;color:#e2e8f0;padding:4px 6px;border-radius:5px;font-size:11px;outline:none}
input[type=text]:focus,input[type=number]:focus,select:focus,textarea:focus{border-color:#e11d48}
select option{background:#1a1a2e}
textarea{resize:vertical;min-height:48px;font-family:inherit}
input[type=color]{width:26px;height:22px;border:1px solid #3a3a5e;border-radius:3px;cursor:pointer;background:none;padding:1px}
.addbtn{width:100%;background:#e11d4820;border:1px solid #e11d4860;color:#e11d48;padding:6px;border-radius:5px;font-size:11px;font-weight:600;cursor:pointer;margin-top:4px}
.addbtn:hover{background:#e11d4840}
.addbtn.purple{background:#7c3aed20;border-color:#7c3aed60;color:#a78bfa}
.addbtn.purple:hover{background:#7c3aed40}
.fg{display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-bottom:4px}
.fc{background:#0f0f1a;border:1px solid #3a3a5e;border-radius:5px;padding:5px 6px;font-size:10px;color:#94a3b8;cursor:pointer;text-align:center}
.fc:hover{border-color:#7c3aed;color:#c4b5fd}
.fc.sel{background:#7c3aed20;border-color:#7c3aed;color:#c4b5fd}
.ps{background:#0f0f1a;border:1px solid #3a3a5e;border-left:3px solid #e11d48;border-radius:5px;padding:4px 8px;margin-bottom:3px;display:flex;justify-content:space-between;align-items:center}
.psn{font-size:10px;color:#cbd5e1;font-weight:500}
.psd{font-size:9px;color:#64748b}
.psx{background:none;border:none;color:#64748b;cursor:pointer;font-size:11px}
.psx:hover{color:#e11d48}
.rbtn{width:100%;background:linear-gradient(135deg,#e11d48,#7c3aed);border:none;color:#fff;padding:8px;border-radius:7px;font-size:12px;font-weight:700;cursor:pointer;margin-top:6px}
.tabrow{display:flex;gap:2px;margin-bottom:8px;background:#0f0f1a;border-radius:6px;padding:2px}
.tb{flex:1;padding:4px;border:none;background:transparent;color:#64748b;font-size:10px;font-weight:500;cursor:pointer;border-radius:4px}
.tb.on{background:#2a2a3e;color:#e2e8f0}
.li{display:flex;align-items:center;justify-content:space-between;padding:4px 6px;border-radius:5px;cursor:pointer;margin-bottom:2px;border:1px solid transparent}
.li:hover{background:#2a2a3e}
.li.sel{background:#e11d4820;border-color:#e11d4840}
.ln{font-size:11px;color:#cbd5e1}
.ld{background:none;border:none;color:#64748b;cursor:pointer;font-size:11px}
.ld:hover{color:#e11d48}
.ti{background:#0f0f1a;border:1px solid #3a3a5e;border-radius:6px;padding:6px 8px;cursor:pointer;margin-bottom:4px}
.ti:hover{border-color:#e11d48}
.tn{font-size:11px;font-weight:600;color:#e2e8f0}
.td2{font-size:9px;color:#64748b;margin-top:2px}
.snk{position:fixed;bottom:12px;left:50%;transform:translateX(-50%);background:#1e293b;border:1px solid #3a3a5e;color:#e2e8f0;padding:6px 14px;border-radius:7px;font-size:11px;z-index:999;opacity:0;transition:opacity .3s;pointer-events:none}
.snk.show{opacity:1}
</style></head><body>
<div id="topbar">
  <span class="tb-logo">Studio Canvas</span>
  <button class="tb-btn" onclick="tup()">&#8679; Upload</button>
  <button class="tb-btn" onclick="undo()">&#8617; Undo</button>
  <button class="tb-btn" onclick="pfr()">&#9654; Preview</button>
  <select id="psel" onchange="spf(this.value)" style="background:#2a2a3e;border:1px solid #3a3a5e;color:#cbd5e1;padding:3px 6px;border-radius:5px;font-size:11px;cursor:pointer">
    <option value="916">Reels/Shorts 9:16</option>
    <option value="169" selected>YouTube 16:9</option>
    <option value="11">Square 1:1</option>
  </select>
  <div style="margin-left:auto;display:flex;gap:6px">
    <button class="tb-btn" onclick="expc()">&#8595; Export Config</button>
    <button class="tb-btn red" onclick="rendv()">&#9654;&#9654; Send to Render</button>
  </div>
</div>
<div id="main">
  <div id="left">
    <button class="tool on" id="t-select" onclick="st('select')" title="Select">&#9654;<span class="tlbl">Select</span></button>
    <button class="tool" id="t-text" onclick="st('text')" title="Text">T<span class="tlbl">Text</span></button>
    <button class="tool" id="t-shape" onclick="st('shape')" title="Shape">&#9632;<span class="tlbl">Shape</span></button>
    <div style="flex:1"></div>
    <button class="tool" onclick="zi()" title="Zoom +">+<span class="tlbl">Zoom</span></button>
    <button class="tool" onclick="zo()" title="Zoom -">-<span class="tlbl">Zoom</span></button>
  </div>
  <div id="cw">
    <div id="ca">
      <div id="cv">
        <div id="ov"></div>
        <div id="uz" onclick="tup()">
          <div class="uico">&#9654;</div>
          <div class="utxt">Click or drag to upload video</div>
          <input type="file" id="fi" accept="video/*" onchange="hfu(this)">
        </div>
      </div>
    </div>
    <div id="pb">
      <button class="pbb" onclick="sk0()">&#9664;&#9664;</button>
      <button class="pbb" id="pbtn" onclick="tp()">&#9654;</button>
      <button class="pbb" onclick="ske()">&#9654;&#9654;</button>
      <span id="td">0:00 / 0:00</span>
      <div style="flex:1;height:3px;background:#2a2a3e;border-radius:2px;cursor:pointer;margin:0 6px" onclick="msk(event)" id="mseek">
        <div id="mprog" style="height:100%;width:0%;background:#e11d48;border-radius:2px"></div>
      </div>
      <span style="font-size:10px;color:#64748b">Zoom:</span>
      <input type="range" min="30" max="150" value="70" id="czoom" style="width:60px" oninput="sz2(this.value)">
      <span id="zv" style="font-size:10px;color:#64748b">70%</span>
    </div>
    <div id="tl">
      <div style="font-size:9px;color:#64748b;font-weight:600;text-transform:uppercase;letter-spacing:.05em">Pipeline</div>
      <div class="tls" id="tlsteps"></div>
    </div>
  </div>
  <div id="right">
    <div class="pnl" style="padding-bottom:6px">
      <div class="tabrow">
        <button class="tb on" onclick="swtab('props',this)">Props</button>
        <button class="tb" onclick="swtab('layers',this)">Layers</button>
        <button class="tb" onclick="swtab('pipe',this)">Pipeline</button>
        <button class="tb" onclick="swtab('tmpls',this)">Templates</button>
      </div>
    </div>
    <div id="tab-props">
      <div class="pnl">
        <div class="ptit">Color Grade</div>
        <div class="fg" id="fgrid"></div>
        <div class="pr"><span class="pl">Brightness</span><input type="range" min="-50" max="50" value="0" id="sbr" oninput="uf('brightness',this.value/100)"><span class="pv" id="vbr">0</span></div>
        <div class="pr"><span class="pl">Contrast</span><input type="range" min="50" max="200" value="100" id="sco" oninput="uf('contrast',this.value/100)"><span class="pv" id="vco">1.0</span></div>
        <div class="pr"><span class="pl">Saturation</span><input type="range" min="0" max="300" value="100" id="ssa" oninput="uf('saturation',this.value/100)"><span class="pv" id="vsa">1.0</span></div>
        <button class="addbtn" onclick="afs()">+ Add Filter to Pipeline</button>
      </div>
      <div class="pnl">
        <div class="ptit">Text Layer</div>
        <textarea id="txc" placeholder="Your text...">Your Title</textarea>
        <div class="pr" style="margin-top:6px"><span class="pl">Style</span>
          <select id="txs" style="flex:1"><option>Custom</option><option>Lower Third</option><option>News Ticker</option><option>Title Card</option><option>Subtitle</option><option>Kinetic Bold</option></select>
        </div>
        <div class="pr"><span class="pl">Animation</span>
          <select id="txa" style="flex:1"><option>None</option><option>Fade In</option><option>Slide Up</option><option>Slide Left</option><option>Zoom In</option><option>Typewriter</option></select>
        </div>
        <div class="pr"><span class="pl">Size</span><input type="range" min="12" max="120" value="48" id="sfs" oninput="document.getElementById('vfs').textContent=this.value+'px'"><span class="pv" id="vfs">48px</span></div>
        <div class="pr"><span class="pl">Color</span><input type="color" id="txcl" value="#FFFFFF"><input type="text" id="txch" value="#FFFFFF" style="width:60px;margin-left:4px" oninput="document.getElementById('txcl').value=this.value"></div>
        <div class="pr"><span class="pl">Show</span><input type="number" id="txst" value="0.5" step="0.5" style="width:44px">-<input type="number" id="txen" value="4" step="0.5" style="width:44px">s</div>
        <div class="pr"><span class="pl">X %</span><input type="range" min="0" max="90" value="5" id="sxp" oninput="document.getElementById('vxp').textContent=this.value+'%'"><span class="pv" id="vxp">5%</span></div>
        <div class="pr"><span class="pl">Y %</span><input type="range" min="0" max="90" value="80" id="syp" oninput="document.getElementById('vyp').textContent=this.value+'%'"><span class="pv" id="vyp">80%</span></div>
        <div class="pr">
          <label style="font-size:11px;color:#94a3b8;display:flex;align-items:center;gap:4px;cursor:pointer"><input type="checkbox" id="txsh" checked> Shadow</label>
          <label style="font-size:11px;color:#94a3b8;display:flex;align-items:center;gap:4px;cursor:pointer"><input type="checkbox" id="txbg"> BG Box</label>
        </div>
        <button class="addbtn" onclick="atc()">+ Preview on Canvas</button>
        <button class="addbtn purple" onclick="ats()" style="margin-top:3px">+ Add to Pipeline</button>
      </div>
      <div class="pnl">
        <div class="ptit">Watermark</div>
        <div class="pr"><span class="pl">Text</span><input type="text" id="wmt" value="@yourbrand"></div>
        <div class="pr"><span class="pl">Position</span>
          <select id="wmp" style="flex:1"><option>Bottom Right</option><option>Bottom Left</option><option>Top Right</option><option>Top Left</option><option>Center</option></select>
        </div>
        <div class="pr"><span class="pl">Opacity</span><input type="range" min="10" max="100" value="75" id="swmo" oninput="document.getElementById('vwmo').textContent=this.value+'%'"><span class="pv" id="vwmo">75%</span></div>
        <button class="addbtn" onclick="aws()">+ Add to Pipeline</button>
      </div>
      <div class="pnl">
        <div class="ptit">Speed</div>
        <div class="pr"><span class="pl">Speed</span><input type="range" min="25" max="400" value="100" id="sspd" oninput="document.getElementById('vspd').textContent=(this.value/100).toFixed(2)+'x'"><span class="pv" id="vspd">1.00x</span></div>
        <div style="display:flex;gap:4px;flex-wrap:wrap;margin-bottom:4px">
          <button class="fc" onclick="setspd(25)">0.25x</button><button class="fc" onclick="setspd(50)">0.5x</button>
          <button class="fc" onclick="setspd(100)">1x</button><button class="fc" onclick="setspd(150)">1.5x</button>
          <button class="fc" onclick="setspd(200)">2x</button><button class="fc" onclick="setspd(400)">4x</button>
        </div>
        <button class="addbtn" onclick="asp()">+ Add to Pipeline</button>
      </div>
      <div class="pnl">
        <div class="ptit">Progress Bar</div>
        <div class="pr"><span class="pl">Color</span><input type="color" id="pbc" value="#e11d48"></div>
        <div class="pr"><span class="pl">Height</span><input type="range" min="2" max="20" value="8" id="pbh" oninput="document.getElementById('vpbh').textContent=this.value+'px'"><span class="pv" id="vpbh">8px</span></div>
        <div class="pr"><span class="pl">Position</span><select id="pbpos"><option>bottom</option><option>top</option></select></div>
        <button class="addbtn" onclick="apbs()">+ Add to Pipeline</button>
      </div>
      <div class="pnl">
        <div class="ptit">Ken Burns Zoom</div>
        <div class="pr"><span class="pl">Start Z</span><input type="range" min="100" max="150" value="100" id="kbs" oninput="document.getElementById('vkbs').textContent=(this.value/100).toFixed(2)"><span class="pv" id="vkbs">1.00</span></div>
        <div class="pr"><span class="pl">End Z</span><input type="range" min="100" max="150" value="108" id="kbe" oninput="document.getElementById('vkbe').textContent=(this.value/100).toFixed(2)"><span class="pv" id="vkbe">1.08</span></div>
        <button class="addbtn" onclick="akbs()">+ Add to Pipeline</button>
      </div>
      <div class="pnl">
        <div class="ptit">Trim</div>
        <div class="pr"><span class="pl">Start</span><input type="number" id="trs" value="0" step="0.5" min="0">s</div>
        <div class="pr"><span class="pl">End</span><input type="number" id="tre" value="10" step="0.5" min="0">s</div>
        <button class="addbtn" onclick="atrim()">+ Add to Pipeline</button>
      </div>
      <div class="pnl">
        <div class="ptit">Export</div>
        <div class="pr"><span class="pl">Platform</span>
          <select id="epl" style="flex:1"><option>Instagram Reels (9:16)</option><option>YouTube Shorts (9:16)</option><option>YouTube (16:9)</option><option>TikTok (9:16)</option><option>Square (1:1)</option></select>
        </div>
        <div class="pr"><span class="pl">Quality</span>
          <select id="equ" style="flex:1"><option>Draft</option><option>Standard</option><option selected>High</option><option>Max</option></select>
        </div>
        <div class="pr"><span class="pl">Fit</span>
          <select id="efit" style="flex:1"><option value="crop">Crop to fill</option><option value="letterbox">Letterbox</option></select>
        </div>
        <button class="addbtn" onclick="aexp()">+ Add to Pipeline</button>
      </div>
    </div>
    <div id="tab-layers" style="display:none">
      <div class="pnl"><div class="ptit">Canvas Layers</div><div id="llist"></div></div>
    </div>
    <div id="tab-pipe" style="display:none">
      <div class="pnl"><div class="ptit">Edit Pipeline</div><div id="plist"></div>
        <button class="rbtn" onclick="rendv()">&#9654;&#9654; Render All Steps</button>
      </div>
    </div>
    <div id="tab-tmpls" style="display:none">
      <div class="pnl"><div class="ptit">Quick Templates</div><div id="tgrid"></div></div>
    </div>
  </div>
</div>
<div class="snk" id="snk"></div>
<script>
const FILTS={"None":"","Vivid":"eq=saturation=1.8:contrast=1.1:brightness=0.05","Cinematic":"eq=saturation=0.85:contrast=1.2:brightness=-0.03","Warm Sunset":"eq=saturation=1.3:brightness=0.04","Cool Blue":"eq=saturation=1.1:brightness=-0.02","B&W":"colorchannelmixer=.299:.587:.114:0:.299:.587:.114:0:.299:.587:.114","Vintage":"curves=r='0/0.1 0.5/0.55 1/0.9',eq=saturation=0.7","HDR Pop":"eq=saturation=2.0:contrast=1.3","Matte":"curves=r='0/0.08 1/0.9',eq=saturation=0.85","Neon Night":"eq=saturation=2.2:contrast=1.4:brightness=-0.05"};
const TMPLS=[
  {n:"Viral Reel",i:"🔥",d:"Vivid + watermark + Reels export",s:[{type:"filter",filter:"Vivid",brightness:.05,contrast:1.1,saturation:1.8},{type:"watermark_text",text:"@yourbrand",position:"Bottom Right",opacity:.75,color:"white",size:28},{type:"export",platform:"Instagram Reels (9:16)",quality:"High",crop:"crop"}]},
  {n:"Cinematic Short",i:"🎬",d:"Film grade + Ken Burns + Shorts export",s:[{type:"filter",filter:"Cinematic",brightness:-.03,contrast:1.2,saturation:.85},{type:"kenburns",zoom_start:1.0,zoom_end:1.08},{type:"export",platform:"YouTube Shorts (9:16)",quality:"Max",crop:"letterbox"}]},
  {n:"Travel Vlog",i:"🌅",d:"Warm tones + lower third + YouTube",s:[{type:"filter",filter:"Warm Sunset",brightness:.04,contrast:1,saturation:1.3},{type:"text",text:"Your Destination",style:"Lower Third",start:1,end:4,anim:"Slide Up",font_size:48,color:"#FFFFFF",x_pct:5,y_pct:80,shadow:true,bg:false},{type:"export",platform:"YouTube (16:9)",quality:"High",crop:"letterbox"}]},
  {n:"Music Video",i:"🎵",d:"Neon + watermark + Reels",s:[{type:"filter",filter:"Neon Night",brightness:-.05,contrast:1.4,saturation:2.2},{type:"watermark_text",text:"@yourbrand",position:"Bottom Right",opacity:.8,color:"white",size:28},{type:"export",platform:"Instagram Reels (9:16)",quality:"High",crop:"crop"}]},
  {n:"News/Talking Head",i:"📰",d:"Clean grade + progress bar + ticker",s:[{type:"filter",filter:"None",brightness:.02,contrast:1.05,saturation:1},{type:"progress_bar",color:"#e11d48",height:6,position:"bottom"},{type:"text",text:"Breaking News",style:"News Ticker",start:.5,end:5,anim:"Slide Left",font_size:40,color:"#FFFFFF",x_pct:2,y_pct:88,shadow:true,bg:false},{type:"export",platform:"YouTube (16:9)",quality:"High",crop:"letterbox"}]},
  {n:"Quick Export",i:"⚡",d:"Resize and export — no edits",s:[{type:"export",platform:"Instagram Reels (9:16)",quality:"Standard",crop:"crop"}]},
];
let S={pipeline:[],layers:[],selLayer:null,activeFilt:"None",fv:{brightness:0,contrast:1,saturation:1},tool:"select",zoom:70,dur:0,ct:0,hasVid:false,vname:"",hist:[]};

function init(){bfg();btg();scs("169")}
function scs(p){
  S.pf=p;const cv=document.getElementById("cv");const ca=document.getElementById("ca");
  const mh=ca.offsetHeight-20;const mw=ca.offsetWidth-20;
  let w,h;
  if(p==="916"){w=Math.min(220,mh*9/16);h=w*16/9}
  else if(p==="11"){w=h=Math.min(mh,mw,320)}
  else{h=Math.min(240,mh);w=h*16/9}
  cv.style.width=Math.round(w)+"px";cv.style.height=Math.round(h)+"px";
}
function spf(v){scs(v)}
function sz2(v){S.zoom=parseInt(v);document.getElementById("zv").textContent=v+"%";document.getElementById("cv").style.transform=`scale(${v/100})`}
function zi(){let z=Math.min(150,S.zoom+10);document.getElementById("czoom").value=z;sz2(z)}
function zo(){let z=Math.max(30,S.zoom-10);document.getElementById("czoom").value=z;sz2(z)}
function st(t){S.tool=t;document.querySelectorAll(".tool").forEach(b=>b.classList.remove("on"));document.getElementById("t-"+t)?.classList.add("on")}
function tup(){document.getElementById("fi").click()}
function hfu(inp){
  const f=inp.files[0];if(!f)return;
  S.hasVid=true;S.vname=f.name;
  document.getElementById("uz").classList.add("hidden");
  const cv=document.getElementById("cv");
  let vid=document.getElementById("pvid");
  if(!vid){vid=document.createElement("video");vid.id="pvid";vid.style.cssText="width:100%;height:100%;object-fit:cover;position:absolute;top:0;left:0;z-index:1";vid.muted=true;cv.insertBefore(vid,cv.firstChild)}
  vid.src=URL.createObjectURL(f);
  vid.onloadedmetadata=()=>{S.dur=vid.duration;document.getElementById("tre").value=vid.duration.toFixed(1);document.getElementById("txen").value=Math.min(4,vid.duration).toFixed(1);utd()};
  vid.ontimeupdate=()=>{S.ct=vid.currentTime;const p=S.dur>0?vid.currentTime/S.dur*100:0;document.getElementById("mprog").style.width=p+"%";utd()};
  snk("Video loaded: "+f.name);apfp();
}
function tp(){const v=document.getElementById("pvid");if(!v||!S.hasVid)return;if(v.paused){v.play();document.getElementById("pbtn").textContent="⏸"}else{v.pause();document.getElementById("pbtn").textContent="▶"}}
function sk0(){const v=document.getElementById("pvid");if(v)v.currentTime=0}
function ske(){const v=document.getElementById("pvid");if(v)v.currentTime=v.duration||0}
function msk(e){const b=document.getElementById("mseek");const v=document.getElementById("pvid");if(v&&S.dur>0)v.currentTime=(e.offsetX/b.offsetWidth)*S.dur}
function utd(){const f=s=>{const m=Math.floor(s/60);return m+":"+String(Math.floor(s%60)).padStart(2,"0")};document.getElementById("td").textContent=f(S.ct)+" / "+f(S.dur)}
function apfp(){const cv=document.getElementById("cv");cv.style.filter=`brightness(${1+S.fv.brightness}) contrast(${S.fv.contrast}) saturate(${S.fv.saturation})`}
function uf(k,v){S.fv[k]=parseFloat(v);document.getElementById("vbr").textContent=Math.round(S.fv.brightness*100);document.getElementById("vco").textContent=S.fv.contrast.toFixed(1);document.getElementById("vsa").textContent=S.fv.saturation.toFixed(1);apfp()}
function bfg(){const g=document.getElementById("fgrid");g.innerHTML="";Object.keys(FILTS).forEach(f=>{const el=document.createElement("div");el.className="fc"+(f===S.activeFilt?" sel":"");el.textContent=f;el.onclick=()=>{document.querySelectorAll(".fc").forEach(c=>c.classList.remove("sel"));el.classList.add("sel");S.activeFilt=f;apfp()};g.appendChild(el)})}
function btg(){const g=document.getElementById("tgrid");g.innerHTML="";TMPLS.forEach((t,i)=>{const el=document.createElement("div");el.className="ti";el.innerHTML=`<div class="tn">${t.i} ${t.n}</div><div class="td2">${t.d}</div>`;el.onclick=()=>{ph();S.pipeline=JSON.parse(JSON.stringify(t.s));rpl();rtl();snk("Loaded '"+t.n+"'");swtabid("pipe")};g.appendChild(el)})}
function afs(){ph();S.pipeline.push({type:"filter",filter:S.activeFilt,...S.fv});rpl();rtl();snk("Filter added")}
function atc(){
  const l={id:"tx_"+Date.now(),type:"text",content:document.getElementById("txc").value||"Text",
    style:document.getElementById("txs").value,anim:document.getElementById("txa").value,
    fontSize:parseInt(document.getElementById("sfs").value),color:document.getElementById("txcl").value,
    xPct:parseInt(document.getElementById("sxp").value),yPct:parseInt(document.getElementById("syp").value),
    shadow:document.getElementById("txsh").checked,bg:document.getElementById("txbg").checked,
    start:parseFloat(document.getElementById("txst").value),end:parseFloat(document.getElementById("txen").value)};
  S.layers.push(l);S.selLayer=l.id;rcl();rll();snk("Text on canvas — drag to move");
}
function ats(){ph();S.pipeline.push({type:"text",text:document.getElementById("txc").value||"Text",
  style:document.getElementById("txs").value,anim:document.getElementById("txa").value,
  font_size:parseInt(document.getElementById("sfs").value),color:document.getElementById("txcl").value,
  x_pct:parseInt(document.getElementById("sxp").value),y_pct:parseInt(document.getElementById("syp").value),
  start:parseFloat(document.getElementById("txst").value),end:parseFloat(document.getElementById("txen").value),
  shadow:document.getElementById("txsh").checked,bg:document.getElementById("txbg").checked});
  rpl();rtl();snk("Text added to pipeline")}
function aws(){ph();S.pipeline.push({type:"watermark_text",text:document.getElementById("wmt").value||"@brand",position:document.getElementById("wmp").value,opacity:parseInt(document.getElementById("swmo").value)/100,color:"white",size:28});rpl();rtl();snk("Watermark added")}
function setspd(v){document.getElementById("sspd").value=v;document.getElementById("vspd").textContent=(v/100).toFixed(2)+"x"}
function asp(){ph();S.pipeline.push({type:"speed",speed:parseInt(document.getElementById("sspd").value)/100});rpl();rtl();snk("Speed added")}
function apbs(){ph();S.pipeline.push({type:"progress_bar",color:document.getElementById("pbc").value,height:parseInt(document.getElementById("pbh").value),position:document.getElementById("pbpos").value});rpl();rtl();snk("Progress bar added")}
function akbs(){ph();S.pipeline.push({type:"kenburns",zoom_start:parseInt(document.getElementById("kbs").value)/100,zoom_end:parseInt(document.getElementById("kbe").value)/100});rpl();rtl();snk("Ken Burns added")}
function atrim(){ph();const s=parseFloat(document.getElementById("trs").value);const e=parseFloat(document.getElementById("tre").value);if(e>s){S.pipeline.push({type:"trim",start:s,end:e});rpl();rtl();snk("Trim added")}else snk("End must be after start")}
function aexp(){ph();S.pipeline.push({type:"export",platform:document.getElementById("epl").value,quality:document.getElementById("equ").value,crop:document.getElementById("efit").value});rpl();rtl();snk("Export step added")}
function rcl(){
  const ov=document.getElementById("ov");const cv=document.getElementById("cv");
  const cw2=cv.offsetWidth,ch2=cv.offsetHeight;ov.innerHTML="";
  S.layers.forEach(l=>{
    if(l.type!=="text")return;
    const el=document.createElement("div");el.className="clayer"+(l.id===S.selLayer?" sel":"");
    el.style.cssText=`left:${l.xPct}%;top:${l.yPct}%;position:absolute;z-index:10`;
    const sh=l.shadow?"text-shadow:2px 2px 4px rgba(0,0,0,.8)":"";
    const bg=l.bg?"background:rgba(0,0,0,.6);padding:3px 6px;border-radius:3px":"";
    el.innerHTML=`<div style="font-size:${l.fontSize/2.5}px;color:${l.color};font-weight:bold;white-space:pre;${sh};${bg}">${l.content}</div>`;
    el.addEventListener("mousedown",e=>{
      S.selLayer=l.id;rcl();rll();
      const sx=l.xPct,sy=l.yPct,ex=e.clientX,ey2=e.clientY;
      const mm=ev=>{l.xPct=Math.max(0,Math.min(90,sx+(ev.clientX-ex)/cw2*100));l.yPct=Math.max(0,Math.min(90,sy+(ev.clientY-ey2)/ch2*100));el.style.left=l.xPct+"%";el.style.top=l.yPct+"%"};
      const mu=()=>{document.removeEventListener("mousemove",mm);document.removeEventListener("mouseup",mu)};
      document.addEventListener("mousemove",mm);document.addEventListener("mouseup",mu);e.preventDefault();
    });
    ov.appendChild(el);
  });
}
function rll(){const list=document.getElementById("llist");list.innerHTML="";if(!S.layers.length){list.innerHTML='<div style="font-size:11px;color:#3a3a5e;text-align:center;padding:14px 0">No layers yet.</div>';return}
  [...S.layers].reverse().forEach(l=>{const el=document.createElement("div");el.className="li"+(l.id===S.selLayer?" sel":"");el.innerHTML=`<span class="ln">T ${l.content.substring(0,16)}</span><button class="ld" onclick="dll('${l.id}')">✕</button>`;el.onclick=e=>{if(e.target.classList.contains("ld"))return;S.selLayer=l.id;rcl();rll()};list.appendChild(el)})}
function dll(id){S.layers=S.layers.filter(l=>l.id!==id);if(S.selLayer===id)S.selLayer=null;rcl();rll()}
function rpl(){const list=document.getElementById("plist");list.innerHTML="";if(!S.pipeline.length){list.innerHTML='<div style="font-size:11px;color:#3a3a5e;text-align:center;padding:14px 0">No steps yet.</div>';return}
  const IC={trim:"✂",filter:"🎨",speed:"⚡",text:"T",watermark_text:"💧",watermark_logo:"🖼",progress_bar:"📊",kenburns:"🔍",audio:"🎵",subtitles:"💬",export:"📐"};
  S.pipeline.forEach((s,i)=>{
    const det={trim:`${(s.start||0).toFixed(1)}-${(s.end||0).toFixed(1)}s`,filter:s.filter||"None",speed:`${s.speed||1}x`,text:`"${(s.text||"").substring(0,14)}"`,watermark_text:`"${s.text||""}"`,progress_bar:`${s.position||""} ${s.color||""}`,kenburns:`${s.zoom_start||1}→${s.zoom_end||1.08}`,audio:s.action||"",subtitles:`${(s.lines||[]).length} lines`,export:`${(s.platform||"").substring(0,16)}`}[s.type]||"";
    const el=document.createElement("div");el.className="ps";
    el.innerHTML=`<div><div class="psn">${IC[s.type]||"•"} ${s.type.replace(/_/g," ").replace(/\b\w/g,c=>c.toUpperCase())}</div><div class="psd">${det}</div></div><button class="psx" onclick="rms(${i})">✕</button>`;
    list.appendChild(el);
  })}
function rms(i){ph();S.pipeline.splice(i,1);rpl();rtl()}
function rtl(){const tl=document.getElementById("tlsteps");tl.innerHTML="";const C=["#e11d48","#7c3aed","#2563eb","#059669","#d97706","#9333ea","#0891b2"];
  S.pipeline.forEach((s,i)=>{const el=document.createElement("div");el.className="tli";const bc=C[i%C.length];el.style.cssText=`border-color:${bc}50;background:${bc}15;color:${bc}`;
  const nm={trim:"✂ Trim",filter:"🎨 "+(s.filter||""),speed:"⚡ "+(s.speed||1)+"x",text:"T Text",watermark_text:"💧 WM",watermark_logo:"🖼 Logo",progress_bar:"📊 Bar",kenburns:"🔍 Zoom",audio:"🎵 Audio",subtitles:"💬 Subs",export:"📐 "+(s.platform||"").split(" ")[0]}[s.type]||s.type;
  el.textContent=nm;tl.appendChild(el)})}
function ph(){S.hist.push(JSON.stringify(S.pipeline))}
function undo(){if(!S.hist.length){snk("Nothing to undo");return}S.pipeline=JSON.parse(S.hist.pop());rpl();rtl();snk("Undone")}
function pfr(){const v=document.getElementById("pvid");if(!v||!S.hasVid){snk("Upload a video first");return}snk("Frame preview at "+document.getElementById("td").textContent.split("/")[0].trim())}
function swtab(n,btn){["props","layers","pipe","tmpls"].forEach(t=>document.getElementById("tab-"+t).style.display=t===n?"block":"none");document.querySelectorAll(".tb").forEach(t=>t.classList.remove("on"));if(btn)btn.classList.add("on")}
function swtabid(n){const ns=["props","layers","pipe","tmpls"];const i=ns.indexOf(n);if(i>=0)swtab(n,document.querySelectorAll(".tb")[i])}
function expc(){
  const cfg={video:S.vname,pipeline:S.pipeline,canvas_layers:S.layers.map(l=>({...l,text:l.content,x_pct:l.xPct,y_pct:l.yPct,font_size:l.fontSize}))};
  const blob=new Blob([JSON.stringify(cfg,null,2)],{type:"application/json"});
  const a=document.createElement("a");a.href=URL.createObjectURL(blob);a.download="studio_config.json";a.click();
  snk("Config exported — upload in Step 3 below to render");
}
function rendv(){
  if(!S.pipeline.length){snk("Add steps first");return}
  const cfg={pipeline:S.pipeline,canvas_layers:S.layers.map(l=>({...l,text:l.content,x_pct:l.xPct,y_pct:l.yPct,font_size:l.fontSize}))};
  try{window.parent.postMessage({type:"studio_render",config:cfg},"*")}catch(e){}
  snk(`${S.pipeline.length} steps ready — also downloading config for Step 3`);
  expc();
}
document.getElementById("cv").addEventListener("click",e=>{
  if(S.tool!=="text"||!S.hasVid) return;
  const cv=document.getElementById("cv");const r=cv.getBoundingClientRect();
  const xp=Math.round((e.clientX-r.left)/r.width*100);const yp=Math.round((e.clientY-r.top)/r.height*100);
  document.getElementById("sxp").value=xp;document.getElementById("vxp").textContent=xp+"%";
  document.getElementById("syp").value=yp;document.getElementById("vyp").textContent=yp+"%";
  atc();st("select");
});
document.getElementById("cv").addEventListener("dragover",e=>{e.preventDefault()});
document.getElementById("cv").addEventListener("drop",e=>{e.preventDefault();const f=e.dataTransfer.files[0];if(f&&f.type.startsWith("video/")){const inp=document.getElementById("fi");const dt=new DataTransfer();dt.items.add(f);inp.files=dt.files;hfu(inp)}});
window.addEventListener("resize",()=>scs(S.pf||"169"));
function snk(m){const el=document.getElementById("snk");el.textContent=m;el.classList.add("show");setTimeout(()=>el.classList.remove("show"),3000)}
init();
</script></body></html>
"""

components.html(CANVAS_HTML, height=680, scrolling=False)

st.markdown("---")

# ── STEP 3: Render ────────────────────────────────────────────────
st.markdown("### ⚙️ Step 3 — Render")
st.caption("Export the config from the canvas editor above, then upload it here along with any audio/logo files.")

col1, col2 = st.columns([2,1])
with col1:
    config_file = st.file_uploader("Upload studio_config.json (from canvas editor)", type=["json"], key="cfg_up")
    if config_file:
        try:
            cfg = json.loads(config_file.read())
            pipeline = cfg.get("pipeline", [])
            # Merge canvas text layers into pipeline if present
            canvas_layers = cfg.get("canvas_layers", [])
            for layer in canvas_layers:
                if layer.get("type") == "text":
                    pipeline.append({
                        "type": "text",
                        "text": layer.get("text", layer.get("content", "Text")),
                        "style": layer.get("style", "Custom"),
                        "anim": layer.get("anim", "None"),
                        "font_size": layer.get("font_size", layer.get("fontSize", 48)),
                        "color": layer.get("color", "#FFFFFF"),
                        "x_pct": layer.get("x_pct", layer.get("xPct", 5)),
                        "y_pct": layer.get("y_pct", layer.get("yPct", 80)),
                        "start": layer.get("start", 0.5),
                        "end": layer.get("end", 4.0),
                        "shadow": layer.get("shadow", True),
                        "bg": layer.get("bg", False),
                    })
            st.session_state.pipeline = pipeline
            st.success(f"✅ Config loaded — **{len(pipeline)} steps** ready to render")
            icons = {"trim":"✂️","filter":"🎨","speed":"⚡","text":"📝","watermark_text":"💧","watermark_logo":"🖼️","progress_bar":"📊","kenburns":"🔍","audio":"🎵","subtitles":"💬","export":"📐"}
            for s in pipeline:
                ic = icons.get(s.get("type",""),"•")
                st.markdown(f'<span class="pipe-badge">{ic} {s.get("type","").replace("_"," ").title()}</span>', unsafe_allow_html=True)
        except Exception as ex:
            st.error(f"Could not parse config: {ex}")

with col2:
    st.markdown("**Optional files:**")
    aud_f = st.file_uploader("Music track (MP3/WAV)", type=["mp3","wav"], key="aud_up")
    if aud_f:
        st.session_state.audio_store["audio_path"] = save_upload(aud_f, "."+aud_f.name.rsplit(".",1)[-1])
        st.caption(f"✅ {aud_f.name}")
    logo_f = st.file_uploader("Logo (PNG)", type=["png","jpg"], key="logo_up")
    if logo_f:
        st.session_state.audio_store["logo_path"] = save_upload(logo_f, ".png")
        st.caption(f"✅ {logo_f.name}")

if st.session_state.source_path and st.session_state.pipeline:
    st.markdown("")
    c1,c2,c3 = st.columns([3,2,1])
    with c1:
        st.info(f"**{len(st.session_state.pipeline)} step(s)** queued on **{st.session_state.source_name}**")
    with c2:
        if st.button("🎬 Render All Steps", key="render_btn", type="primary"):
            prog = st.progress(0, text="Starting render…")
            log_lines = []
            cur = tmpout(); shutil.copy2(st.session_state.source_path, cur)
            steps = st.session_state.pipeline
            success = True
            for i, step in enumerate(steps):
                t = step.get("type","")
                prog.progress((i)/len(steps), text=f"Step {i+1}/{len(steps)}: {t}…")
                if t in ("merge_note",): continue
                result, err = run_step(cur, step, st.session_state.audio_store)
                if result is None:
                    log_lines.append(f"❌ Step {i+1} ({t}) failed: {err[-200:] if err else 'unknown'}")
                    success = False; break
                cur = result
                log_lines.append(f"✅ Step {i+1}/{len(steps)}: {t}")
                prog.progress((i+1)/len(steps), text=f"✅ {t}")
            prog.empty()
            if success and os.path.exists(cur) and os.path.getsize(cur) > 0:
                save_history(st.session_state.source_name, f"Rendered {len(steps)} steps")
                st.success("🎉 Render complete!")
                with open(cur,"rb") as f:
                    st.download_button("⬇️ Download Final Video", f.read(), "studio_output.mp4", "video/mp4", key="render_dl")
                # Preview frame
                frame = extract_frame(cur, 1.0)
                if frame:
                    st.image(frame, caption="Preview frame from rendered video", width=400)
            else:
                st.error("Render failed")
                for ln in log_lines: st.text(ln)
    with c3:
        if st.button("🗑 Clear", key="clear_pipe"):
            st.session_state.pipeline = []
            st.rerun()
elif not st.session_state.source_path:
    st.warning("Upload a source video in Step 1 first.")
elif not st.session_state.pipeline:
    st.info("Upload a config JSON from the canvas editor, or the pipeline is empty.")
