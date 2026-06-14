"""
video_engine.py  —  all ffmpeg logic, cleanly isolated.
Every function returns (output_path, error_string|None).
output_path is None on failure.
"""
import os, subprocess, tempfile, json, shutil, math

FONT  = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONTR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

FILTERS = {
    "None":          None,
    "Vivid":         "eq=saturation=1.8:contrast=1.1:brightness=0.05",
    "Cinematic":     "eq=saturation=0.85:contrast=1.2:brightness=-0.03",
    "Warm Sunset":   "eq=saturation=1.3:brightness=0.04",
    "Cool Blue":     "eq=saturation=1.1:brightness=-0.02",
    "Black & White": "colorchannelmixer=.299:.587:.114:0:.299:.587:.114:0:.299:.587:.114",
    "Vintage":       "eq=saturation=0.7,curves=r='0/0.1 0.5/0.55 1/0.9'",
    "HDR Pop":       "eq=saturation=2.0:contrast=1.3:brightness=0.02",
    "Matte":         "eq=saturation=0.85,curves=r='0/0.08 1/0.9'",
    "Neon Night":    "eq=saturation=2.2:contrast=1.4:brightness=-0.05",
}

PLATFORMS = {
    "Instagram Reels (9:16)": {"w": 1080, "h": 1920, "fps": 30},
    "YouTube Shorts (9:16)":  {"w": 1080, "h": 1920, "fps": 60},
    "YouTube (16:9)":         {"w": 1920, "h": 1080, "fps": 30},
    "TikTok (9:16)":          {"w": 1080, "h": 1920, "fps": 30},
    "Square (1:1)":           {"w": 1080, "h": 1080, "fps": 30},
}

# ── internal helpers ───────────────────────────────────────────────

def _tmp(ext=".mp4"):
    t = tempfile.NamedTemporaryFile(delete=False, suffix=ext)
    t.close()
    return t.name

def _run(*args):
    cmd = ["ffmpeg", "-y"] + [str(a) for a in args]
    r   = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode == 0, r.stderr

def _ok(p):
    return bool(p and os.path.exists(p) and os.path.getsize(p) > 1000)

def _safe(text):
    """Escape text for ffmpeg drawtext."""
    return (text
            .replace("\\", "\\\\")
            .replace("'",  "\u2019")
            .replace(":",  "\\:")
            .replace("%",  "\\%")
            .replace("[",  "\\[")
            .replace("]",  "\\]"))

def _hex(color, fallback="FFFFFF"):
    h = color.lstrip("#")
    return h.upper() if len(h) == 6 else fallback

def _font():
    return f":fontfile={FONT}" if os.path.exists(FONT) else ""

def _pos_xy(position):
    """Return (x_expr, y_expr) for watermark position."""
    return {
        "Top Left":     ("20",            "20"),
        "Top Right":    ("w-text_w-20",   "20"),
        "Bottom Left":  ("20",            "h-text_h-20"),
        "Bottom Right": ("w-text_w-20",   "h-text_h-20"),
        "Center":       ("(w-text_w)/2",  "(h-text_h)/2"),
    }.get(position, ("w-text_w-20", "h-text_h-20"))

def _overlay_pos(position):
    return {
        "Top Left":     "10:10",
        "Top Right":    "main_w-overlay_w-10:10",
        "Bottom Left":  "10:main_h-overlay_h-10",
        "Bottom Right": "main_w-overlay_w-10:main_h-overlay_h-10",
        "Center":       "(main_w-overlay_w)/2:(main_h-overlay_h)/2",
    }.get(position, "main_w-overlay_w-10:main_h-overlay_h-10")

# ── probe ──────────────────────────────────────────────────────────

def probe(path):
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_streams", "-show_format", path],
        capture_output=True, text=True,
    )
    info = {"duration": 0.0, "width": 0, "height": 0,
            "fps": 30.0, "has_audio": False, "size_mb": 0.0}
    if r.returncode != 0:
        return info
    try:
        d = json.loads(r.stdout)
        for s in d.get("streams", []):
            if s.get("codec_type") == "video":
                info["width"]  = int(s.get("width",  0))
                info["height"] = int(s.get("height", 0))
                try:
                    n, dv = s.get("r_frame_rate", "30/1").split("/")
                    info["fps"] = round(int(n) / max(int(dv), 1), 2)
                except Exception:
                    pass
                raw = s.get("duration") or d.get("format", {}).get("duration", 0)
                info["duration"] = float(raw or 0)
            if s.get("codec_type") == "audio":
                info["has_audio"] = True
        info["size_mb"] = round(
            int(d.get("format", {}).get("size", 0)) / 1_048_576, 1)
    except Exception:
        pass
    return info

# ── frame extraction ───────────────────────────────────────────────

def extract_frame(path, ts=1.0):
    from PIL import Image
    info = probe(path)
    ts   = max(0.0, min(float(ts), info["duration"] - 0.1))
    out  = _tmp(".jpg")
    ok, _ = _run("-ss", str(ts), "-i", path, "-vframes", "1", "-q:v", "2", out)
    if ok and _ok(out):
        try:
            img = Image.open(out); img.load(); return img
        except Exception:
            pass
    return None

def extract_frames(path, count=5):
    """Return list of (timestamp, PIL.Image) evenly spaced through video."""
    info   = probe(path)
    dur    = info["duration"]
    frames = []
    for i in range(count):
        ts  = dur * (i + 0.5) / count
        img = extract_frame(path, ts)
        if img:
            frames.append((round(ts, 1), img))
    return frames

# ── step functions ─────────────────────────────────────────────────

def do_trim(inp, start, end):
    out = _tmp()
    ok, e = _run("-ss", str(start), "-i", inp,
                 "-t", str(end - start),
                 "-c:v", "libx264", "-c:a", "aac", "-preset", "ultrafast", out)
    return (out, None) if _ok(out) else (None, e)


def do_filter(inp, filter_name="None", brightness=0.0, contrast=1.0, saturation=1.0):
    out   = _tmp()
    parts = []
    base  = FILTERS.get(filter_name)
    if base:
        parts.append(base)
    if abs(brightness) > 0.001 or abs(contrast-1.0) > 0.01 or abs(saturation-1.0) > 0.01:
        parts.append(f"eq=brightness={brightness:.3f}:contrast={contrast:.3f}:saturation={saturation:.3f}")
    vf = ",".join(parts) if parts else "null"
    ok, e = _run("-i", inp, "-vf", vf, "-c:v", "libx264", "-c:a", "aac", "-preset", "ultrafast", out)
    return (out, None) if _ok(out) else (None, e)


def do_speed(inp, speed=1.0):
    out  = _tmp()
    info = probe(inp)
    pts  = f"setpts={1.0/speed:.6f}*PTS"
    if info["has_audio"]:
        parts = []; rem = float(speed)
        while rem > 2.0: parts.append("atempo=2.0"); rem /= 2.0
        while rem < 0.5: parts.append("atempo=0.5"); rem *= 2.0
        parts.append(f"atempo={rem:.4f}")
        ok, e = _run("-i", inp, "-vf", pts, "-af", ",".join(parts),
                     "-c:v", "libx264", "-preset", "ultrafast", out)
    else:
        ok, e = _run("-i", inp, "-vf", pts, "-an",
                     "-c:v", "libx264", "-preset", "ultrafast", out)
    return (out, None) if _ok(out) else (None, e)


def do_text(inp, text="Text", style="Custom", font_size=48,
            color="#FFFFFF", x_pct=5, y_pct=80,
            start=0.0, end=None, shadow=True,
            bg_box=False, bg_color="#000000", pill=False):
    out   = _tmp()
    info  = probe(inp)
    dur   = info["duration"] or 10.0
    end   = min(float(end if end is not None else dur), dur)
    start = float(start)
    safe  = _safe(text)
    fc    = f"0x{_hex(color)}FF"
    en    = f"between(t\\,{start:.3f}\\,{end:.3f})"
    fa    = _font()
    shd   = ":shadowcolor=black@0.7:shadowx=2:shadowy=2" if shadow else ""
    xe    = f"(w*{x_pct/100:.4f})"
    ye    = f"(h*{y_pct/100:.4f})"

    # Background box / pill
    if pill or bg_box:
        bh  = _hex(bg_color, "000000")
        box = f":box=1:boxcolor=0x{bh}BB:boxborderw={12 if pill else 8}"
    else:
        box = ""

    dt = (f"drawtext=text='{safe}':fontsize={font_size}{fa}"
          f":fontcolor={fc}:x={xe}:y={ye}"
          f":enable='{en}'{shd}{box}")

    # Style bars
    fs = font_size
    if style == "Lower Third":
        bar = (f"drawbox=x=0:y=(h*{y_pct/100:.4f})-{fs+16}:w=iw:h={fs+32}"
               f":color=0x00000099:t=fill:enable='{en}'")
        vf = f"{bar},{dt}"
    elif style == "News Ticker":
        bar = (f"drawbox=x=0:y=(h*{y_pct/100:.4f})-8:w=iw:h={fs+20}"
               f":color=0xe11d48CC:t=fill:enable='{en}'")
        vf = f"{bar},{dt}"
    elif style == "Title Card":
        bar = (f"drawbox=x=(w*{x_pct/100:.4f})-20:y=(h*{y_pct/100:.4f})-{fs+8}"
               f":w=iw/2:h={fs+20}:color=0x000000BB:t=fill:enable='{en}'")
        vf = f"{bar},{dt}"
    elif style == "Subtitle":
        bar = (f"drawbox=x=0:y=(h*{y_pct/100:.4f})-10:w=iw:h={fs+20}"
               f":color=0x000000AA:t=fill:enable='{en}'")
        vf  = f"{bar},{dt}"
    else:
        vf = dt

    ok, e = _run("-i", inp, "-vf", vf, "-c:v", "libx264", "-c:a", "aac", "-preset", "ultrafast", out)
    return (out, None) if _ok(out) else (None, e)


def do_watermark_text(inp, text="@brand", position="Bottom Right", opacity=0.75, size=28):
    out  = _tmp()
    safe = _safe(text)
    x, y = _pos_xy(position)
    fa   = _font()
    vf   = (f"drawtext=text='{safe}':fontsize={size}{fa}"
            f":fontcolor=white@{opacity:.2f}:x={x}:y={y}"
            f":shadowcolor=black@0.6:shadowx=2:shadowy=2")
    ok, e = _run("-i", inp, "-vf", vf, "-c:v", "libx264", "-c:a", "aac", "-preset", "ultrafast", out)
    return (out, None) if _ok(out) else (None, e)


def do_watermark_logo(inp, logo_path, position="Bottom Right", opacity=0.75, size_pct=15):
    out  = _tmp()
    ovp  = _overlay_pos(position)
    sc   = size_pct / 100.0
    vf   = (f"[1:v]scale=iw*{sc:.3f}:-1,format=rgba,"
            f"colorchannelmixer=aa={opacity:.2f}[logo];"
            f"[0:v][logo]overlay={ovp}")
    ok, e = _run("-i", inp, "-i", logo_path, "-filter_complex", vf,
                 "-c:v", "libx264", "-c:a", "aac", "-preset", "ultrafast", out)
    return (out, None) if _ok(out) else (None, e)


def do_progress_bar(inp, color="#e11d48", height=8, position="bottom"):
    out  = _tmp()
    info = probe(inp)
    dur  = info["duration"] or 1.0
    hx   = _hex(color, "e11d48")
    y    = f"h-{height}" if position == "bottom" else "0"
    vf   = (f"drawbox=x=0:y={y}:w=iw*(t/{dur:.4f}):h={height}"
            f":color=0x{hx}FF:t=fill")
    ok, e = _run("-i", inp, "-vf", vf, "-c:v", "libx264", "-c:a", "aac", "-preset", "ultrafast", out)
    return (out, None) if _ok(out) else (None, e)


def do_kenburns(inp, zoom_start=1.0, zoom_end=1.08):
    out    = _tmp()
    info   = probe(inp)
    w, h   = info["width"] or 1080, info["height"] or 1920
    fps    = info["fps"] or 30.0
    dur    = info["duration"] or 5.0
    frames = max(int(dur * fps), 1)
    step   = (zoom_end - zoom_start) / frames
    vf     = (f"scale=iw*{zoom_end:.3f}:ih*{zoom_end:.3f},"
              f"zoompan=z='min(zoom+{step:.6f},{zoom_end:.4f})':"
              f"d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
              f"s={w}x{h}:fps={fps:.2f}")
    ok, e = _run("-i", inp, "-vf", vf, "-c:v", "libx264", "-c:a", "aac", "-preset", "ultrafast", out)
    return (out, None) if _ok(out) else (None, e)


def do_fade(inp, fade_in=0.5, fade_out=0.5):
    """Fade video in at start and out at end."""
    out  = _tmp()
    info = probe(inp)
    dur  = info["duration"] or 5.0
    fo_start = max(0.0, dur - fade_out)
    vf = (f"fade=t=in:st=0:d={fade_in:.2f},"
          f"fade=t=out:st={fo_start:.3f}:d={fade_out:.2f}")
    af = ""
    if info["has_audio"]:
        af = (f"afade=t=in:st=0:d={fade_in:.2f},"
              f"afade=t=out:st={fo_start:.3f}:d={fade_out:.2f}")
    if af:
        ok, e = _run("-i", inp, "-vf", vf, "-af", af,
                     "-c:v", "libx264", "-c:a", "aac", "-preset", "ultrafast", out)
    else:
        ok, e = _run("-i", inp, "-vf", vf,
                     "-c:v", "libx264", "-preset", "ultrafast", out)
    return (out, None) if _ok(out) else (None, e)


def do_blur_background(inp, blur_strength=20):
    """Blur the full frame (useful as background effect)."""
    out = _tmp()
    vf  = f"boxblur={blur_strength}:{blur_strength}"
    ok, e = _run("-i", inp, "-vf", vf, "-c:v", "libx264", "-c:a", "aac", "-preset", "ultrafast", out)
    return (out, None) if _ok(out) else (None, e)


def do_split_screen(inp1, inp2, layout="side-by-side"):
    """Combine two videos side by side or top/bottom."""
    out  = _tmp()
    info = probe(inp1)
    w, h = info["width"] or 1920, info["height"] or 1080
    if layout == "side-by-side":
        hw  = w // 2
        fc  = (f"[0:v]scale={hw}:{h}[v0];"
               f"[1:v]scale={hw}:{h}[v1];"
               f"[v0][v1]hstack=inputs=2[out]")
    else:  # top-bottom
        hh  = h // 2
        fc  = (f"[0:v]scale={w}:{hh}[v0];"
               f"[1:v]scale={w}:{hh}[v1];"
               f"[v0][v1]vstack=inputs=2[out]")
    ok, e = _run("-i", inp1, "-i", inp2,
                 "-filter_complex", fc, "-map", "[out]",
                 "-c:v", "libx264", "-preset", "ultrafast", "-an", out)
    return (out, None) if _ok(out) else (None, e)


def do_auto_subtitles(inp, full_text, words_per_line=6, line_duration=2.5,
                       font_size=38, color="#FFFFFF", y_pct=85):
    """Split full_text into timed subtitle lines and burn them in."""
    words = full_text.split()
    lines = []
    t = 0.0
    for i in range(0, len(words), words_per_line):
        chunk = " ".join(words[i:i+words_per_line])
        lines.append((chunk, t, t + line_duration))
        t += line_duration

    out = _tmp()
    # Build SRT file
    srt = tempfile.NamedTemporaryFile(delete=False, suffix=".srt", mode="w")
    def ft(x):
        h=int(x//3600); m=int((x%3600)//60); s=int(x%60); ms=int((x-int(x))*1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
    for i, (txt, s, e) in enumerate(lines, 1):
        srt.write(f"{i}\n{ft(s)} --> {ft(e)}\n{txt}\n\n")
    srt.close()

    fa    = _font()
    hx    = _hex(color, "FFFFFF")
    style = f"FontSize={font_size},PrimaryColour=&H00{hx},OutlineColour=&H00000000,Outline=2,Bold=1,MarginV={int((100-y_pct)/100*100)}"
    vf    = f"subtitles={srt.name}:force_style='{style}'"
    ok, e = _run("-i", inp, "-vf", vf, "-c:v", "libx264", "-c:a", "aac", "-preset", "ultrafast", out)
    os.unlink(srt.name)
    return (out, None) if _ok(out) else (None, e)


def do_emoji_overlay(inp, emoji_text="⭐", x_pct=50, y_pct=10, start=0.0, end=None, size=80):
    """Overlay emoji/sticker text using drawtext."""
    info = probe(inp)
    dur  = info["duration"] or 10.0
    end  = min(float(end if end else dur), dur)
    return do_text(inp, text=emoji_text, font_size=size, color="#FFFFFF",
                   x_pct=x_pct, y_pct=y_pct, start=start, end=end,
                   shadow=True, bg_box=False)


def do_audio_mute(inp):
    out = _tmp()
    ok, e = _run("-i", inp, "-c:v", "copy", "-an", out)
    return (out, None) if _ok(out) else (None, e)


def do_audio_volume(inp, multiplier=1.5):
    out = _tmp()
    ok, e = _run("-i", inp, "-af", f"volume={multiplier:.2f}", "-c:v", "copy", out)
    return (out, None) if _ok(out) else (None, e)


def do_audio_replace(inp, audio_path):
    out = _tmp()
    ok, e = _run("-i", inp, "-i", audio_path, "-c:v", "copy",
                 "-map", "0:v:0", "-map", "1:a:0", "-shortest", out)
    return (out, None) if _ok(out) else (None, e)


def do_audio_mix(inp, audio_path, music_vol=0.5, orig_vol=1.0):
    out = _tmp()
    fc  = (f"[0:a]volume={orig_vol:.2f}[a1];"
           f"[1:a]volume={music_vol:.2f}[a2];"
           f"[a1][a2]amix=inputs=2:duration=first[ao]")
    ok, e = _run("-i", inp, "-i", audio_path, "-filter_complex", fc,
                 "-map", "0:v", "-map", "[ao]", "-c:v", "copy", "-shortest", out)
    return (out, None) if _ok(out) else (None, e)


def do_export(inp, platform="YouTube (16:9)", quality="High", fit="crop"):
    out  = _tmp()
    spec = PLATFORMS.get(platform, {"w": 1920, "h": 1080, "fps": 30})
    w, h = spec["w"], spec["h"]
    crf  = {"Draft": 32, "Standard": 26, "High": 20, "Max": 16}.get(quality, 20)
    if fit == "crop":
        vf = f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h}"
    else:
        vf = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black"
    ok, e = _run("-i", inp, "-vf", vf, "-r", str(spec["fps"]),
                 "-c:v", "libx264", "-crf", str(crf), "-preset", "fast",
                 "-c:a", "aac", "-b:a", "192k", out)
    return (out, None) if _ok(out) else (None, e)


def do_merge(paths):
    if len(paths) == 1:
        out = _tmp(); shutil.copy2(paths[0], out); return out, None
    normed = []
    for p in paths:
        n = _tmp()
        ok, e = _run("-i", p, "-c:v", "libx264", "-c:a", "aac", "-preset", "ultrafast", n)
        if not _ok(n): return None, f"Normalise failed: {e[-200:]}"
        normed.append(n)
    lst = tempfile.NamedTemporaryFile(delete=False, suffix=".txt", mode="w")
    for n in normed: lst.write(f"file '{n}'\n")
    lst.close()
    out = _tmp()
    ok, e = _run("-f", "concat", "-safe", "0", "-i", lst.name,
                 "-c:v", "libx264", "-c:a", "aac", "-preset", "ultrafast", out)
    os.unlink(lst.name)
    return (out, None) if _ok(out) else (None, e)


# ── pipeline runner ────────────────────────────────────────────────

def run_pipeline(source_path, steps, audio_path=None, logo_path=None,
                 second_video_path=None, progress_cb=None):
    cur = _tmp(); shutil.copy2(source_path, cur)
    log = []
    total = len(steps)

    for i, step in enumerate(steps):
        t   = step.get("type", "")
        num = f"[{i+1}/{total}]"
        if progress_cb:
            progress_cb(i, total, t)

        if   t == "trim":
            result, err = do_trim(cur, step["start"], step["end"])
        elif t == "filter":
            result, err = do_filter(cur, step.get("filter","None"),
                                    step.get("brightness",0.0),
                                    step.get("contrast",1.0),
                                    step.get("saturation",1.0))
        elif t == "speed":
            result, err = do_speed(cur, step["speed"])
        elif t == "text":
            result, err = do_text(cur,
                text      = step.get("text","Text"),
                style     = step.get("style","Custom"),
                font_size = step.get("font_size",48),
                color     = step.get("color","#FFFFFF"),
                x_pct     = step.get("x_pct",5),
                y_pct     = step.get("y_pct",80),
                start     = step.get("start",0.0),
                end       = step.get("end",None),
                shadow    = step.get("shadow",True),
                bg_box    = step.get("bg_box",False),
                bg_color  = step.get("bg_color","#000000"),
                pill      = step.get("pill",False),
            )
        elif t == "watermark_text":
            result, err = do_watermark_text(cur,
                text     = step.get("text","@brand"),
                position = step.get("position","Bottom Right"),
                opacity  = step.get("opacity",0.75),
                size     = step.get("size",28))
        elif t == "watermark_logo":
            if logo_path:
                result, err = do_watermark_logo(cur, logo_path,
                    position = step.get("position","Bottom Right"),
                    opacity  = step.get("opacity",0.75),
                    size_pct = step.get("size_pct",15))
            else:
                result, err = cur, None
        elif t == "progress_bar":
            result, err = do_progress_bar(cur,
                color    = step.get("color","#e11d48"),
                height   = step.get("height",8),
                position = step.get("position","bottom"))
        elif t == "kenburns":
            result, err = do_kenburns(cur,
                zoom_start = step.get("zoom_start",1.0),
                zoom_end   = step.get("zoom_end",1.08))
        elif t == "fade":
            result, err = do_fade(cur,
                fade_in  = step.get("fade_in",0.5),
                fade_out = step.get("fade_out",0.5))
        elif t == "blur":
            result, err = do_blur_background(cur, step.get("strength",20))
        elif t == "split_screen":
            if second_video_path:
                result, err = do_split_screen(cur, second_video_path,
                    layout = step.get("layout","side-by-side"))
            else:
                result, err = cur, None
        elif t == "auto_subtitles":
            result, err = do_auto_subtitles(cur,
                full_text    = step.get("text",""),
                words_per_line = step.get("words_per_line",6),
                line_duration  = step.get("line_duration",2.5),
                font_size      = step.get("font_size",38),
                color          = step.get("color","#FFFFFF"),
                y_pct          = step.get("y_pct",85))
        elif t == "emoji":
            result, err = do_emoji_overlay(cur,
                emoji_text = step.get("text","⭐"),
                x_pct      = step.get("x_pct",50),
                y_pct      = step.get("y_pct",10),
                start      = step.get("start",0.0),
                end        = step.get("end",None),
                size       = step.get("font_size",80))
        elif t == "audio_mute":
            result, err = do_audio_mute(cur)
        elif t == "audio_volume":
            result, err = do_audio_volume(cur, step.get("multiplier",1.5))
        elif t == "audio_replace":
            result, err = (do_audio_replace(cur, audio_path)
                           if audio_path else (cur, None))
        elif t == "audio_mix":
            result, err = (do_audio_mix(cur, audio_path,
                           step.get("music_vol",0.5),
                           step.get("orig_vol",1.0))
                           if audio_path else (cur, None))
        elif t == "export":
            result, err = do_export(cur,
                platform = step.get("platform","YouTube (16:9)"),
                quality  = step.get("quality","High"),
                fit      = step.get("fit","crop"))
        else:
            log.append(f"{num} ⚠️ Unknown step '{t}' — skipped"); continue

        if result is None:
            log.append(f"{num} ❌ {t} failed: {(err or '')[-300:]}")
            return None, log

        log.append(f"{num} ✅ {t}")
        cur = result

    if progress_cb:
        progress_cb(total, total, "done")
    return cur, log
