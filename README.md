# docsite

通用 HTML 文档站：把**自包含 HTML 文档**放进目录，自动生成可分类、可搜索的网站，给团队通过网址访问。

适合：团队的报告、指南、设计稿、API 文档、benchmark 结果——任何「一堆 HTML + 图片」想集中展示的场景。

## 特点
- **文档自包含**：每篇 = 一个目录（入口 HTML + 它的全部图片/视频），不依赖外部路径，换环境不破图
- **零配置**：分类和日期从目录名自动推断；可选 `.docmeta.yaml` 精确控制
- **分类 / 日期归档 / 前端搜索**（纯 JS，无后端数据库）
- **静态站点**：部署简单，Caddy / nginx / 任意静态服务器
- **多人协作**：git push 自动部署，自带版本 / 审计 / 回滚

## 快速开始
```bash
git clone <repo> docsite && cd docsite
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
└── hooks/post-receive    # git 自动部署钩子
```

## License
MIT
