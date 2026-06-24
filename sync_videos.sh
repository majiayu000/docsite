#!/usr/bin/env bash
# 视频不进 git（docsite-content/.gitignore 已排除），用此脚本单独 rsync 到服务器。
# 在 git push（HTML+图片）之后跑这个，把视频补传到服务器对应文档的 assets/。
#
# 用法:
#   ./sync_videos.sh [本地文档目录，默认 ~/docsite-content]
# 环境变量:
#   DOCSITE_DOCS  服务器文档目录，默认 gpu:~/docsite/site/docs
set -euo pipefail
SRC="${1:-$HOME/docsite-content}"
DST="${DOCSITE_DOCS:-gpu:~/docsite/site/docs}"

echo "[sync_videos] $SRC -> $DST"
rsync -avz \
  --include='*/' \
  --include='*.mp4' --include='*.mov' --include='*.mkv' \
  --include='*.avi' --include='*.webm' --include='*.m4v' \
  --exclude='*' \
  "$SRC/" "$DST/"
echo "[sync_videos] 完成。视频在服务器文档站对应文档的 assets/ 下，浏览器 <video> 直接播放。"
