#!/usr/bin/env bash
# 下载完整性校验：check_video.sh <file.mp4> [期望字节数]
set -euo pipefail
f="$1"; want="${2:-}"
size=$(stat -c %s "$f"); dur=$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$f")
last=$(ffprobe -v error -select_streams a:0 -show_entries packet=pts_time -of csv=p=0 "$f" | tail -1)
echo "size=$size duration=$dur last_audio_pts=$last"
[ -n "$want" ] && [ "$size" != "$want" ] && { echo "FAIL: 大小与 Content-Length 不符"; exit 1; }
python3 -c "import sys; d,l=float('$dur'),float('$last' or 0); sys.exit(0 if l>=d-3 else 1)" || { echo "FAIL: 数据在 ${last}s 处截断"; exit 1; }
ffmpeg -v error -i "$f" -f null - 2>&1 | grep -qi "partial file\|invalid data" && { echo "FAIL: 解码报错"; exit 1; }
echo OK
