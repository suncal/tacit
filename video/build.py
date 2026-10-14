"""Assemble the TSM pitch video.

  python build.py narrate     ElevenLabs narration per shot → build/vo/<id>.mp3 (skips ones that exist)
  python build.py assemble    one mp4 per shot timed to its narration, then the master with fades
  python build.py report      durations per shot and the total

Visuals: card:<id> = build/cards/<id>.png with a slow push-in; scene:<name> = ../docs/tsm/captures/<name>-scene.mp4,
optionally trimmed, slowed or held on its last frame to fit the narration. Output: 1920x1080 H.264 CRF 18 Rec709, AAC 192k.
"""
import json, os, subprocess, sys, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "build")
CAPT = os.path.join(HERE, "..", "docs", "tsm", "captures")
SHOTS = json.load(open(os.path.join(HERE, "shots.json")))
FPS = 30
GAP = 0.30           # silence after each narration segment, seconds
TEMPO = 1.085        # narration speed-up: Brian reads at ~155 wpm, this lands at ~168
XF = 0.5             # crossfade between shots
VIDEO = ["-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p", "-r", str(FPS),
         "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709"]


def sh(*a, **k):
    return subprocess.run(a, check=True, capture_output=True, text=True, **k)


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


def shot_video(s, length):
    """A silent video exactly `length` seconds long for this shot."""
    os.makedirs(os.path.join(BUILD, "segs"), exist_ok=True)
    out = os.path.join(BUILD, "segs", s["id"] + ".mp4")
    kind, name = s["visual"].split(":", 1)
    if kind == "card":
        src = os.path.join(BUILD, "cards", name + ".png")
        frames = int(length * FPS)
        # slow push-in: 1.00 → 1.045 over the shot (zoompan on a single still is fine; it is the concat that breaks)
        vf = f"scale=3840:2160,zoompan=z='1+0.045*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1920x1080:fps={FPS},format=yuv420p"
        sh("ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", src, "-vf", vf, "-t", f"{length:.3f}", *VIDEO, out)
    else:
        src = os.path.join(CAPT, name + "-scene.mp4")
        a, b = s.get("trim", [0, dur(src)])
        avail = b - a
        if avail >= length:                                   # plenty: play at speed, cut at length
            sh("ffmpeg", "-y", "-loglevel", "error", "-ss", f"{a:.3f}", "-t", f"{length:.3f}", "-i", src, "-an", *VIDEO, out)
        elif avail >= length * 0.75:                          # a little short: slow it down to fit
            sh("ffmpeg", "-y", "-loglevel", "error", "-ss", f"{a:.3f}", "-t", f"{avail:.3f}", "-i", src, "-an",
               "-vf", f"setpts={length / avail:.4f}*PTS", "-t", f"{length:.3f}", *VIDEO, out)
        else:                                                 # much shorter: play, then hold the last frame
            sh("ffmpeg", "-y", "-loglevel", "error", "-ss", f"{a:.3f}", "-t", f"{avail:.3f}", "-i", src, "-an",
               "-vf", f"tpad=stop_mode=clone:stop_duration={length - avail + 0.1:.3f}", "-t", f"{length:.3f}", *VIDEO, out)
    return out


def assemble():
    segs, auds, lengths = [], [], []
    for s in SHOTS["shots"]:
        vo = os.path.join(BUILD, "vo", s["id"] + ".mp3")
        length = vo_dur(vo) + GAP + (XF if s is not SHOTS["shots"][-1] else 0)
        segs.append(shot_video(s, length)); auds.append(vo); lengths.append(length)
        print(s["id"], s["visual"], f"{length:.1f}s", flush=True)
    # audio: one wav per shot = narration (tempo-adjusted, 0.25 s lead-in) padded to the shot's advance (length - XF),
    # then concatenated — the track lines up with the video by construction, no adelay/amix timestamp games
    os.makedirs(os.path.join(BUILD, "aud"), exist_ok=True)
    wavs = []
    for s, vo, length in zip(SHOTS["shots"], auds, lengths):
        adv = length - (XF if s is not SHOTS["shots"][-1] else 0)
        w = os.path.join(BUILD, "aud", s["id"] + ".wav")
        sh("ffmpeg", "-y", "-loglevel", "error", "-i", vo, "-af", f"atempo={TEMPO},adelay=250|250,apad,atrim=0:{adv:.3f},asetpts=N/SR/TB",
           "-ar", "48000", "-ac", "2", w)
        wavs.append(w)
    lst = os.path.join(BUILD, "aud", "list.txt")
    with open(lst, "w") as f:
        f.write("".join(f"file '{w}'\n" for w in wavs))
    track = os.path.join(BUILD, "aud", "track.wav")
    sh("ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", track)
    # video: chain of xfades
    n = len(segs)
    inputs = []
    for p in segs: inputs += ["-i", p]
    inputs += ["-i", track]
    fc, prev, offset = [], "[0:v]", 0.0
    for i in range(1, n):
        offset += lengths[i - 1] - XF
        fc.append(f"{prev}[{i}:v]xfade=transition=fade:duration={XF}:offset={offset:.3f}[v{i}]")
        prev = f"[v{i}]"
    total = offset + lengths[-1]
    fc.append(f"{prev}fade=t=in:st=0:d=0.5,fade=t=out:st={total - 1.0:.3f}:d=1.0[vout]")
    fc.append(f"[{n}:a]afade=t=out:st={total - 1.0:.3f}:d=1.0[aout]")
    master = os.path.join(HERE, "tacit-tsm-master.mp4")
    sh("ffmpeg", "-y", "-loglevel", "error", *inputs, "-filter_complex", ";".join(fc), "-map", "[vout]", "-map", "[aout]",
       *VIDEO, "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-t", f"{total:.3f}", master)
    print(f"master {master} {dur(master):.1f}s {os.path.getsize(master) / 1e6:.1f} MB")


def report():
    tot = 0
    for s in SHOTS["shots"]:
        d = vo_dur(os.path.join(BUILD, "vo", s["id"] + ".mp3")); tot += d + GAP
        print(f"{s['id']} {s['visual']:28} {d:5.1f}s  {len(s['text'].split()):3d} words")
    print(f"total narration+gaps {tot:.1f}s = {tot / 60:.2f} min (limit 5:00; crossfades subtract {XF * (len(SHOTS['shots']) - 1):.1f}s)")


if __name__ == "__main__":
    {"narrate": narrate, "assemble": assemble, "report": report}[sys.argv[1]]()
