"""Assemble the TSM pitch video at 4K.

  python build.py narrate     ElevenLabs narration per shot → build/vo/<id>.mp3 (skips ones that exist)
  python build.py assemble    one 4K clip per shot timed to its narration, then the master with fades, music and loudness
  python build.py report      durations per shot and the total

Visuals
  card:<id>   build/motion/<id>.webm (animated, recorded at 4K) — or build/cards/<id>.png with a slow push-in
  scene:<n>   ../docs/tsm/captures/<n>-scene.mp4 presented inside the product frame (build/overlays/<shot>-frame.png),
              with a slow push-in and timed lower-third callouts; optional trim/trims, fit=speed
Audio
  narration (tempo-lifted, compressed, loudness-normalised) over a music bed ducked under the voice.
Output: 3840x2160 H.264 CRF 19 Rec709, AAC 192k; plus a 1080p downscale.
"""
import json, os, subprocess, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "build")
CAPT = os.path.join(HERE, "..", "docs", "tsm", "captures")
SHOTS = json.load(open(os.path.join(HERE, "shots.json")))
FPS = 30
GAP = 0.30
XF = 0.5
TEMPO = 1.085
W, H = 3840, 2160
WIN_X, WIN_Y, WIN_W, WIN_H = 220, 236, 3400, 1868        # window interior of the frame overlay, in 4K pixels
VIDEO = ["-c:v", "libx264", "-preset", "medium", "-crf", "19", "-pix_fmt", "yuv420p", "-r", str(FPS),
         "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709"]
MUSIC = os.path.join(BUILD, "music", "bed.mp3")


def sh(*a):
    return subprocess.run(a, check=True, capture_output=True, text=True)


def dur(path):
    return float(sh("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path).stdout.strip())


def vo_dur(path):
    return dur(path) / TEMPO


def narrate():
    key = open(os.path.expanduser("~/.elevenlabs_key")).read().strip()
    v = SHOTS["voice"]
    os.makedirs(os.path.join(BUILD, "vo"), exist_ok=True)
    for s in SHOTS["shots"]:
        out = os.path.join(BUILD, "vo", s["id"] + ".mp3")
        if os.path.exists(out):
            continue
        body = json.dumps({"text": s["text"], "model_id": v["model"],
                           "voice_settings": {"stability": v["stability"], "similarity_boost": v["similarity"], "style": v["style"], "use_speaker_boost": v["boost"]}}).encode()
        req = urllib.request.Request(f"https://api.elevenlabs.io/v1/text-to-speech/{v['id']}?output_format=mp3_44100_192", data=body,
                                     headers={"xi-api-key": key, "content-type": "application/json", "accept": "audio/mpeg"})
        with urllib.request.urlopen(req, timeout=120) as r, open(out, "wb") as f:
            f.write(r.read())
        print(s["id"], f"{dur(out):.1f}s", flush=True)


def _source_clip(s, src):
    """trims (several windows) or trim (one window) → (clip path, start, available seconds)."""
    if s.get("trims"):
        parts = []
        for i, (x, y) in enumerate(s["trims"]):
            part = os.path.join(BUILD, "segs", f"{s['id']}-part{i}.mp4")
            sh("ffmpeg", "-y", "-loglevel", "error", "-ss", f"{x:.3f}", "-t", f"{y - x:.3f}", "-i", src, "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "16", "-r", str(FPS), part)
            parts.append(part)
        lst = os.path.join(BUILD, "segs", f"{s['id']}-parts.txt")
        with open(lst, "w") as f:
            f.write("".join(f"file '{q}'\n" for q in parts))
        joined = os.path.join(BUILD, "segs", f"{s['id']}-joined.mp4")
        sh("ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", joined)
        return joined, 0.0, dur(joined)
    a, b = s.get("trim", [0, dur(src)])
    return src, a, b - a


def shot_video(s, length):
    os.makedirs(os.path.join(BUILD, "segs"), exist_ok=True)
    out = os.path.join(BUILD, "segs", s["id"] + ".mp4")
    kind, name = s["visual"].split(":", 1)
    frames = int(length * FPS)
    push = f"zoompan=z='min(1+0.00042*on,1.07)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={W}x{H}:fps={FPS}"
    if kind == "card":
        motion = os.path.join(BUILD, "motion", name + ".webm")
        if os.path.exists(motion):
            sh("ffmpeg", "-y", "-loglevel", "error", "-i", motion, "-an", "-vf", f"scale={W}:{H}:flags=lanczos,tpad=stop_mode=clone:stop_duration=2",
               "-t", f"{length:.3f}", *VIDEO, out)
        else:
            src = os.path.join(BUILD, "cards", name + ".png")
            sh("ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", src, "-vf",
               f"scale={W * 2}:{H * 2},zoompan=z='1+0.045*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={W}x{H}:fps={FPS},format=yuv420p",
               "-t", f"{length:.3f}", *VIDEO, out)
        return out
    # ---- a console scene inside the product frame, with callouts and a slow push-in
    src, a, avail = _source_clip(s, os.path.join(CAPT, name + "-scene.mp4"))
    if s.get("fit") == "speed" and avail > length:
        tempo = f"setpts={length / avail:.4f}*PTS"
    elif avail < length * 0.75:
        tempo = f"tpad=stop_mode=clone:stop_duration={length - avail + 0.2:.3f}"
    elif avail < length:
        tempo = f"setpts={length / avail:.4f}*PTS"
    else:
        tempo = "null"
    frame = os.path.join(BUILD, "overlays", f"{s['id']}-frame.png")
    inputs = ["-ss", f"{a:.3f}", "-i", src, "-i", frame]
    fc = [f"[0:v]{tempo},scale={WIN_W}:{WIN_H}:flags=lanczos,setsar=1[win]",
          f"color=c=black:s={W}x{H}:r={FPS}:d={length + 1:.3f}[bg]",
          f"[bg][win]overlay={WIN_X}:{WIN_Y}:shortest=1[v0]",
          "[v0][1:v]overlay=0:0[v1]"]
    last = "[v1]"
    for i, c in enumerate(s.get("callouts", [])):
        png = os.path.join(BUILD, "overlays", f"{s['id']}-c{i}.png")
        inputs += ["-loop", "1", "-t", f"{c['for'] + 0.1:.3f}", "-i", png]
        n = 2 + i
        fc.append(f"[{n}:v]format=rgba,fade=t=in:st=0:d=0.35:alpha=1,fade=t=out:st={c['for'] - 0.35:.3f}:d=0.35:alpha=1,setpts=PTS+{c['at']:.3f}/TB[c{i}]")
        fc.append(f"{last}[c{i}]overlay=0:0:eof_action=pass[v{n}]")
        last = f"[v{n}]"
    fc.append(f"{last}{push},format=yuv420p[vout]")
    sh("ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(fc), "-map", "[vout]", "-t", f"{length:.3f}", *VIDEO, out)
    return out


def assemble():
    segs, auds, lengths = [], [], []
    for s in SHOTS["shots"]:
        vo = os.path.join(BUILD, "vo", s["id"] + ".mp3")
        length = vo_dur(vo) + GAP + (XF if s is not SHOTS["shots"][-1] else 0)
        segs.append(shot_video(s, length)); auds.append(vo); lengths.append(length)
        print(s["id"], s["visual"], f"{length:.1f}s", flush=True)
    total = sum(lengths) - XF * (len(lengths) - 1)
    # ---- narration track: per-shot wavs padded to the shot's advance, concatenated
    os.makedirs(os.path.join(BUILD, "aud"), exist_ok=True)
    wavs = []
    for s, vo, length in zip(SHOTS["shots"], auds, lengths):
        adv = length - (XF if s is not SHOTS["shots"][-1] else 0)
        w = os.path.join(BUILD, "aud", s["id"] + ".wav")
        sh("ffmpeg", "-y", "-loglevel", "error", "-i", vo, "-af", f"atempo={TEMPO},adelay=250|250,apad,atrim=0:{adv:.3f},asetpts=N/SR/TB", "-ar", "48000", "-ac", "2", w)
        wavs.append(w)
    lst = os.path.join(BUILD, "aud", "list.txt")
    with open(lst, "w") as f:
        f.write("".join(f"file '{w}'\n" for w in wavs))
    raw = os.path.join(BUILD, "aud", "track-raw.wav")
    sh("ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", raw)
    voice = os.path.join(BUILD, "aud", "voice.wav")
    sh("ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-af",
       "highpass=f=80,acompressor=threshold=-20dB:ratio=2.5:attack=12:release=140:makeup=3,loudnorm=I=-16:TP=-1.5:LRA=9", voice)
    mix = os.path.join(BUILD, "aud", "mix.wav")
    if os.path.exists(MUSIC):
        sh("ffmpeg", "-y", "-loglevel", "error", "-stream_loop", "-1", "-i", MUSIC, "-i", voice, "-filter_complex",
           f"[0:a]atrim=0:{total:.3f},asetpts=N/SR/TB,aformat=sample_rates=48000:channel_layouts=stereo,volume=-21dB,afade=t=in:st=0:d=2,afade=t=out:st={total - 4:.3f}:d=4[m];"
           f"[1:a]asplit=2[v1][v2];[m][v2]sidechaincompress=threshold=0.015:ratio=5:attack=60:release=700[md];"
           f"[v1][md]amix=inputs=2:normalize=0,alimiter=limit=0.95:level=false[out]", "-map", "[out]", "-t", f"{total:.3f}", mix)
    else:
        mix = voice
    # ---- video: chain of crossfades
    n = len(segs)
    inputs = []
    for p in segs: inputs += ["-i", p]
    inputs += ["-i", mix]
    fc, prev, offset = [], "[0:v]", 0.0
    for i in range(1, n):
        offset += lengths[i - 1] - XF
        fc.append(f"{prev}[{i}:v]xfade=transition=fade:duration={XF}:offset={offset:.3f}[v{i}]")
        prev = f"[v{i}]"
    fc.append(f"{prev}fade=t=in:st=0:d=0.6,fade=t=out:st={total - 1.2:.3f}:d=1.2[vout]")
    fc.append(f"[{n}:a]afade=t=out:st={total - 1.2:.3f}:d=1.2[aout]")
    master = os.path.join(HERE, "tacit-tsm-master-4k.mp4")
    sh("ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(fc), "-map", "[vout]", "-map", "[aout]",
       *VIDEO, "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-t", f"{total:.3f}", master)
    hd = os.path.join(HERE, "tacit-tsm-master-1080p.mp4")
    sh("ffmpeg", "-y", "-loglevel", "error", "-i", master, "-vf", "scale=1920:1080:flags=lanczos", "-c:v", "libx264", "-preset", "slow", "-crf", "18",
       "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-c:a", "copy", "-movflags", "+faststart", hd)
    print(f"master {master} {dur(master):.1f}s {os.path.getsize(master) / 1e6:.1f} MB | 1080p {os.path.getsize(hd) / 1e6:.1f} MB")


def report():
    tot = 0
    for s in SHOTS["shots"]:
        d = vo_dur(os.path.join(BUILD, "vo", s["id"] + ".mp3")); tot += d + GAP
        print(f"{s['id']} {s['visual']:28} {d:5.1f}s  {len(s['text'].split()):3d} words")
    print(f"total {tot - XF * (len(SHOTS['shots']) - 1):.1f}s = {(tot - XF * (len(SHOTS['shots']) - 1)) / 60:.2f} min (limit 5:00)")


if __name__ == "__main__":
    {"narrate": narrate, "assemble": assemble, "report": report}[sys.argv[1]]()
