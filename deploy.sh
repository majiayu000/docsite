#!/usr/bin/env bash
# docsite 一键部署（部署选项 B：本地 build → rsync 到远程主机）。
# 远程只需 Caddy 服务 site/，不需要 git/python。
#
# 用法：
#   DEPLOY_HOST=user@host DEPLOY_DIR=/srv/docsite ./deploy.sh
#
# 环境变量：
#   DEPLOY_HOST  远程主机（user@host），必填
#   DEPLOY_DIR   远程 docsite 目录，默认 /srv/docsite
set -euo pipefail

: "${DEPLOY_HOST:?请设置 DEPLOY_HOST=user@host}"
DEPLOY_DIR="${DEPLOY_DIR:-/srv/docsite}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "[deploy] 1/2 本地构建 site/ ..."
cd "$SCRIPT_DIR"
python3 build.py

echo "[deploy] 2/2 同步到 ${DEPLOY_HOST}:${DEPLOY_DIR}/site/ ..."
rsync -avz --delete site/ "${DEPLOY_HOST}:${DEPLOY_DIR}/site/"

echo "[deploy] 完成。访问该主机的站点端口（见 Caddyfile）。"
