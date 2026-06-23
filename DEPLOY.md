# 部署 docsite

三种方式，从简到繁。先选一种。

## 0. 本地预览
```bash
pip install jinja2 pyyaml
cp -R sample-docs/* site/docs/        # 或放你自己的文档
python3 build.py
python3 -m http.server -d site 8090   # 浏览器打开 http://localhost:8090
```

## 1. rsync 一键部署（deploy.sh）
本地 build，把 `site/` rsync 到远程，远程只需一个静态服务器（Caddy/nginx）。**远程不需要 git/python。**

```bash
# 远程：装 Caddy，按 Caddyfile.example 配好，serve <DEPLOY_DIR>/site/
# 本地：
DEPLOY_HOST=user@yourserver DEPLOY_DIR=/srv/docsite ./deploy.sh
```

## 2. git push 自动部署（bare 仓库 + post-receive 钩子）
文档放 git 仓库，**push 即部署**，适合多人协作。

```bash
# 远程：建 bare 仓库 + 部署 hook
ssh user@yourserver '
  git init --bare --shared=group /srv/docsite-content.git
'
scp hooks/post-receive user@yourserver:/srv/docsite-content.git/hooks/
ssh user@yourserver 'chmod +x /srv/docsite-content.git/hooks/post-receive'
# hook 路径通过环境变量配置：DOCSITE_REPO / DOCSITE_WORK / DOCSITE_ROOT（默认 /srv/docsite*）
# 也在远程放一份 build.py + templates/ + static/（DOCSITE_ROOT 指向它）

# 本地：clone + push
git clone user@yourserver:/srv/docsite-content.git my-docs
cd my-docs
cp -R /path/to/docsite/sample-docs/* ./
git add . && git commit -m "init docs" && git push
# push 触发远程 hook：checkout + build.py，站点数秒内更新
```

多人协作：给同事仓库 write 权限（git shared group），他们 clone+push 即可发布。版本/审计/回滚由 git 提供。

## 静态服务器配置（Caddy）
见 `Caddyfile.example`。改三处：站点目录、端口、认证用户/哈希。
```bash
caddy hash-password --plaintext "你的密码"    # 生成哈希填入 Caddyfile
caddy run --config Caddyfile
```

## 外网访问（可选）
- **有公网 IP + 域名**：Caddyfile 里把 `:8090` 改成域名，自动签 HTTPS。
- **无公网 IP**（内网机）：用 [cloudflared tunnel](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/) 主动出站到 Cloudflare，外部访问公网域名。

## 作为 systemd 服务常驻
```ini
# ~/.config/systemd/user/docsite.service
[Unit]
Description=docsite (Caddy)
After=network.target
[Service]
Type=simple
WorkingDirectory=/srv/docsite
ExecStart=/usr/bin/caddy run --config /srv/docsite/Caddyfile
Restart=on-failure
[Install]
WantedBy=default.target
```
开机自启需 `sudo loginctl enable-linger <user>`（一次性）。
