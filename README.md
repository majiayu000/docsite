# docsite

通用 HTML 文档站：把**自包含 HTML 文档**放进目录，自动生成可分类、可搜索的网站，给团队通过网址访问。

适合：团队的报告、指南、设计稿、API 文档、benchmark 结果——任何「一堆 HTML + 图片」想集中展示的场景。

## 先判断输入是否合适

docsite 收集已经写好的 HTML，生成分类、日期归档和搜索索引；它不会替你从代码提取 API 文档，也不会把任意 Markdown 项目转换成完整文档站。如果主要输入是 Markdown、需要围绕章节持续写作，可先看 [MkDocs 的官方说明](https://www.mkdocs.org/)；需要自定义模板与多种输入格式，可阅读 [Eleventy 文档](https://www.11ty.dev/docs/)。已有报告需要保留自身布局、图片和脚本时，再按下方流程使用 docsite。

本仓库没有公开在线示例地址。可以用 `sample-docs/` 在本地预览，部署入口见 [DEPLOY.md](DEPLOY.md)。[提交问题](https://github.com/majiayu000/docsite/issues)时提供构建命令、目录结构和脱敏错误，不上传团队内部文档或访问凭据。

## 特点
- **文档自包含**：每篇 = 一个目录（入口 HTML + 它的全部图片/视频），不依赖外部路径，换环境不破图
- **零配置**：分类和日期从目录名自动推断；可选 `.docmeta.yaml` 精确控制
- **分类 / 日期归档 / 前端搜索**（纯 JS，无后端数据库）
- **静态站点**：部署简单，Caddy / nginx / 任意静态服务器
- **多人协作**：git push 自动部署，自带版本 / 审计 / 回滚

## 快速开始
```bash
git clone https://github.com/majiayu000/docsite.git
cd docsite
pip install jinja2 pyyaml

# 预览自带 demo
cp -R sample-docs/* site/docs/
python3 build.py
python3 -m http.server -d site 8090
# 浏览器打开 http://localhost:8090
```

## 发布一篇文档
1. 准备一篇自包含文档（入口 HTML + 它引用的全部图片，在同一目录）
2. 放进 `site/docs/`，可选加 `.docmeta.yaml`
3. `python3 build.py`

**跨目录引用的文档**（HTML 里有 `../xxx`）先打包成自包含：
```bash
python3 publish_doc.py path/to/your-doc     # 产物在 dist/your-doc/
cp -R dist/your-doc site/docs/
python3 build.py
```

### 文档元数据 `.docmeta.yaml`（可选）

例如给一篇指南建立独立目录，入口与素材相邻：

```text
site/docs/guide-2026-10-01/
├── index.html
├── assets/chart.png
└── .docmeta.yaml
```

`index.html` 中使用 `src="assets/chart.png"`；元数据控制索引展示，不会重写原报告的正文。每次新增文档后运行 `python3 build.py`，从站点首页的分类或搜索进入，再检查图片是否加载。
```yaml
title: 你的标题          # 缺省: summary.md 首行 或 目录名
category: 你的分类        # 缺省: 目录名首段（可用 docsite.yaml 的 category_map 美化）
date: 2026-06-22         # 缺省: 目录名时间戳 或 文件修改时间
summary: 一句话摘要
tags: [标签1, 标签2]
```

## 配置（可选）
复制 `docsite.yaml.example` 为 `docsite.yaml`，配置站点名、文档目录、类别映射。

## 部署
见 [DEPLOY.md](DEPLOY.md)：本地预览 / rsync 一键部署 / git push 自动部署。

## 大文件 / 视频处理
git 不适合存大视频（仓库膨胀、push/clone 慢）。docsite 的做法：**HTML+图片进 git，视频单独 rsync**。

1. 内容仓库 `.gitignore` 排除视频（`*.mp4 *.mov *.mkv ...`），`git push` 只传 HTML+图片
2. 视频用 `sync_videos.sh` 单独 rsync 到服务器对应文档的 `assets/`：
   ```bash
   ./sync_videos.sh                                          # 默认 ~/docsite-content -> gpu
   DOCSITE_DOCS=user@host:/path ./sync_videos.sh /your/docs   # 自定义目标
   ```

发布含视频的文档：
```bash
python3 publish_doc.py your-doc          # 打包（视频进 dist/assets，本地预览完整）
cp -R dist/your-doc ~/docsite-content/
git add . && git commit && git push      # 传 HTML+图片（视频被 .gitignore 挡掉）
./sync_videos.sh                         # 视频单独 rsync 到服务器
```

HTML 里 `<video src="assets/x.mp4" controls></video>` 即可，浏览器直接播。

## 复制后资源缺失，先查哪里？

- 图片路径包含 `../`：文档依赖了兄弟目录，复制单个目录不会把依赖带走。先运行上面的 `publish_doc.py`，检查 `dist/文档名/` 内资源和入口，再复制打包结果。
- 入口文件不叫 `index.html` 或 `report.html`：打包器可从 `.docmeta.yaml` 的 `entry: 文件名.html` 指定入口；该文件必须存在。未找到入口会报错，不能靠空索引判断发布成功。
- 本地视频可播放，远端没有视频：检查 HTML 引用的目标路径，以及视频是否只被 `.gitignore` 排除、尚未执行 `sync_videos.sh`。视频传输与 HTML 的 git 部署是两条独立步骤。
- 模板或分类改了，首页没变化：运行构建并确认预览的是新生成的 `site/`，再核对部署目标目录，不能只刷新浏览器判断构建已生效。

打包后仍需在浏览器检查真实资源。当前工具扫描本地 HTML/CSS 的资源引用，不保证所有运行时脚本动态生成的地址都被发现。

## 项目结构
```
docsite/
├── build.py              # 索引生成器（核心）
├── publish_doc.py        # 打包自包含工具
├── templates/            # Jinja2 模板
├── static/               # CSS + 前端搜索
├── sample-docs/          # 自带 demo
├── docsite.yaml.example  # 配置模板
├── Caddyfile.example     # 部署模板
├── deploy.sh             # rsync 一键部署
├── sync_videos.sh        # 视频单独 rsync（git 不存大视频）
└── hooks/post-receive    # git 自动部署钩子
```

## License
MIT
