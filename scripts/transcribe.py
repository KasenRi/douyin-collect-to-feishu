#!/usr/bin/env python3
"""Gemini 兼容接口分段转写：python3 transcribe.py <audio_or_video> [seg_sec=300] > transcript.txt
环境变量：GEMINI_BASE_URL、GEMINI_API_KEY、GEMINI_MODEL（可选，默认 gemini-2.5-flash）、
GEMINI_RPM（可选，每分钟请求上限，默认 10）。游戏类长视频建议 seg_sec=120。
被安全拦截/400 的段自动对半切重试（下界约 7 秒）。不打印密钥。"""
import base64, json, os, subprocess, sys, tempfile, time, urllib.parse, urllib.request, urllib.error
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
PROMPT = ("逐字转写这段音频为简体中文。不要时间戳，整理成普通文章段落，按语义自然换行；"
          "不要标题、不要代码块、不要任何额外说明。口语和专业术语照原样保留。")
PROMPT_SAFE = "这是一段公开视频的音频，仅做文字归档。只做语音转写：" + PROMPT
MIN_SEG = 7.0
GAP = 60.0 / float(os.environ.get("GEMINI_RPM", "10")) + 0.5
_last = [0.0]

def env():
    e = {k: os.environ.get(k, "") for k in ("GEMINI_BASE_URL", "GEMINI_API_KEY")}
    for k, v in e.items():
        if not v: sys.exit(f"缺少环境变量 {k}（见 .env.example）")
    return e

def dur(f):
    return float(subprocess.check_output(["ffprobe","-v","error","-show_entries","format=duration","-of","csv=p=0",f]).strip())

def cut(src, start, length, dst):
    subprocess.run(["ffmpeg","-v","error","-y","-ss",str(start),"-t",str(length),"-i",src,"-ac","1","-ar","16000","-b:a","48k",dst], check=True)

class Blocked(Exception): pass

def call(e, mp3, prompt):
    url = e["GEMINI_BASE_URL"].rstrip("/") + "/v1beta/models/" + urllib.parse.quote(MODEL, safe="-._~") + ":generateContent"
    body = {"contents":[{"role":"user","parts":[{"text":prompt},{"inlineData":{"mimeType":"audio/mp3","data":base64.b64encode(open(mp3,"rb").read()).decode()}}]}]}
    for attempt in range(6):
        w = GAP - (time.time() - _last[0])
        if w > 0: time.sleep(w)
        _last[0] = time.time()
        req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type":"application/json","x-goog-api-key":e["GEMINI_API_KEY"]})
        try:
            r = json.load(urllib.request.urlopen(req, timeout=300))
        except urllib.error.HTTPError as x:
            if x.code == 400: raise Blocked(x.read()[:200].decode("utf-8","replace"))
            time.sleep(min(60, 5 * 2**attempt)); continue
        except (urllib.error.URLError, TimeoutError):
            time.sleep(min(60, 5 * 2**attempt)); continue
        if r.get("promptFeedback", {}).get("blockReason"): raise Blocked(str(r["promptFeedback"]))
        try:
            return "".join(p.get("text","") for p in r["candidates"][0]["content"]["parts"]).strip()
        except (KeyError, IndexError):
            raise Blocked(str(r)[:200])
    raise RuntimeError("重试耗尽")

def seg(e, src, start, length, tmp):
    mp3 = os.path.join(tmp, f"s_{start:.1f}_{length:.1f}.mp3"); cut(src, start, length, mp3)
    try:
        for pr in (PROMPT, PROMPT_SAFE):
            try: return call(e, mp3, pr)
            except Blocked as b: print(f"[拦截/400 {start:.0f}s+{length:.0f}s] {b}", file=sys.stderr)
        if length / 2 < MIN_SEG: return "[安全策略拦截，无法转写]"
        h = length / 2
        return seg(e, src, start, h, tmp) + "\n" + seg(e, src, start + h, length - h, tmp)
    finally:
        os.remove(mp3)

def main():
    src = sys.argv[1]; L = float(sys.argv[2]) if len(sys.argv) > 2 else 300.0
    e = env(); total = dur(src); out = []
    with tempfile.TemporaryDirectory() as tmp:
        t = 0.0
        while t < total - 0.5:
            print(f"段 {t:.0f}s/{total:.0f}s", file=sys.stderr)
            out.append(seg(e, src, t, min(L, total - t), tmp)); t += L
    print("\n\n".join(out))

if __name__ == "__main__": main()
