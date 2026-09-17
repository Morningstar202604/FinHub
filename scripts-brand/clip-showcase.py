#!/usr/bin/env python3
"""Assemble the FinHub showcase film.

Pipeline: title-card (2.5s) → 6 recorded scenes (per-clip fade in/out,
scene 4 chat tail trimmed) → end-card (3s). Output 1920x1080 30fps H.264.
"""
import json
import os
import subprocess
import sys

VID = "/workspace/FinHub/screenshots/video"
OUT = f"{VID}/finhub-showcase.mp4"
TMP = f"{VID}/_tmp"
os.makedirs(TMP, exist_ok=True)

def sh(cmd):
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-1200:])
        sys.exit(1)

def probe(path):
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", path],
        capture_output=True, text=True)
    return float(json.loads(r.stdout)["format"]["duration"])

def normalize(src, dst, keep=None):
    """webm/png → mp4 30fps yuv420p; optional head-trim to `keep` seconds."""
    if src.endswith(".png"):
        dur = keep or 2.5
        sh(f'ffmpeg -y -loop 1 -i "{src}" -t {dur} -r 30 '
           f'-vf "scale=1920:1080" -c:v libopenh264 -profile:v high -b:v 4500k -pix_fmt yuv420p "{dst}"')
    else:
        trim = f"-t {keep} " if keep else ""
        sh(f'ffmpeg -y -i "{src}" {trim}-r 30 -vf "scale=1920:1080" '
           f'-c:v libopenh264 -profile:v high -b:v 4500k -pix_fmt yuv420p "{dst}"')
    return probe(dst)

def fade(src, dst, dur, fade_len=0.45):
    # Video-only: Playwright recordings carry no audio track, so no afade.
    out_st = max(0.0, dur - fade_len)
    sh(f'ffmpeg -y -i "{src}" '
       f'-vf "fade=t=in:st=0:d={fade_len},fade=t=out:st={out_st}:d={fade_len}" '
       f'-c:v libopenh264 -profile:v high -b:v 4500k -pix_fmt yuv420p "{dst}"')

# Deterministic scene→file mapping (showcase-video.mjs renames each take to
# scene-N.webm in creation order, and clears stale takes first).
SCENES = [
    ("dashboard", "scene1-dashboard.webm", None),
    ("market", "scene2-market.webm", None),
    ("finance", "scene3-finance.webm", None),
    ("chat", "scene4-chat.webm", 52.0),
    ("settings", "scene5-settings.webm", None),
    ("plugins-auto", "scene6-plugins-auto.webm", None),
]

KEEP = {"chat": 52.0}

playlist = []
for i, (name, webm, keep) in enumerate(SCENES):
    src = os.path.join(VID, webm)
    assert os.path.exists(src), f"missing scene file: {src}"
    raw = f"{TMP}/{i}-{name}-raw.mp4"
    dur = normalize(src, raw, keep=keep)
    faded = f"{TMP}/{i}-{name}.mp4"
    fade(raw, faded, dur)
    playlist.append(faded)
    print(f"scene {name}: {dur:.1f}s")

title = f"{TMP}/title.mp4"
end = f"{TMP}/end.mp4"
normalize(f"{VID}/title-card.png", title, keep=2.5)
fade(title, f"{TMP}/title-f.mp4", 2.5, fade_len=0.5)
normalize(f"{VID}/end-card.png", end, keep=3.0)
fade(end, f"{TMP}/end-f.mp4", 3.0, fade_len=0.6)

with open(f"{TMP}/list.txt", "w") as f:
    for p in [f"{TMP}/title-f.mp4"] + playlist + [f"{TMP}/end-f.mp4"]:
        f.write(f"file '{p}'\n")

sh(f'ffmpeg -y -f concat -safe 0 -i "{TMP}/list.txt" '
   f'-c:v libopenh264 -profile:v high -b:v 4500k -pix_fmt yuv420p -movflags +faststart "{OUT}"')
total = probe(OUT)
print(f"DONE {OUT} total={total:.1f}s ({total/60:.1f}min)")
