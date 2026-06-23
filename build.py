#!/usr/bin/env python3
"""docsite — 通用 HTML 文档站索引生成器（侧边栏文档库版）。

扫描 docs_dir 下的自包含文档，读取/推断元数据，生成左侧分类树 + 标签云的
侧边栏布局站点。支持二级分类（.docmeta category 写 'a/b'）和 tags 第二维。

依赖：jinja2（pip install jinja2）。yaml 配置/元数据读取可选依赖 pyyaml。
"""
import json
import re
import shutil
import sys
from collections import OrderedDict
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "docsite.yaml"
TEMPLATES = ROOT / "templates"
STATIC_DIR = ROOT / "static"

SKIP_PREFIX = ("http://", "https://", "data:", "#", "//", "mailto:", "javascript:")


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        import yaml
        return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    except ImportError:
        print(f"[build] 警告: {CONFIG_PATH.name} 需要 pyyaml，已忽略配置", file=sys.stderr)
        return {}


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")


def parse_meta(doc_dir: Path) -> dict:
    jp = doc_dir / ".docmeta.json"
    if jp.exists():
        return json.loads(jp.read_text(encoding="utf-8"))
    yp = doc_dir / ".docmeta.yaml"
    if yp.exists():
        try:
            import yaml
            return yaml.safe_load(yp.read_text(encoding="utf-8")) or {}
        except ImportError:
            print(f"[build] 警告: {yp.name} 需要 pyyaml，已跳过", file=sys.stderr)
            return {}
    return {}


def parse_category(name: str, meta: dict, category_map: dict) -> tuple:
    """返回 (一级label, 一级slug, 二级label|None, 二级slug|None)。
    .docmeta category 支持 'a/b' 二级；否则用 category_map[目录首段] 自动推断。"""
    raw = meta.get("category")
    if raw:
        parts = str(raw).split("/", 1)
        cat = parts[0].strip()
        sub = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
    else:
        key = re.split(r"[_\-]", name, 1)[0] or name
        cat = category_map.get(key, key)
        sub = None
    first = re.split(r"[_\-]", name, 1)[0] or name
    cat_slug = slugify(cat) or slugify(first) or "cat"
    sub_slug = slugify(sub) if sub else None
    return cat, cat_slug, sub, sub_slug


def _date_str(v) -> str:
    if v is None:
        return ""
    if hasattr(v, "isoformat"):
        return v.isoformat()[:10]
    return str(v)


def infer_date(name: str, entry: Path) -> str:
    m = re.search(r"(\d{4})(\d{2})(\d{2})", name)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    import datetime
    return datetime.date.fromtimestamp(entry.stat().st_mtime).isoformat()


def read_summary_title(doc_dir: Path) -> str:
    p = doc_dir / "summary.md"
    if p.exists():
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip().lstrip("#").strip()
            if line:
                return line
    return ""


class _AttrCollector(HTMLParser):
    _ATTRS = ("src", "href", "poster")

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.urls = []

    def handle_starttag(self, tag, attrs):
        for k, v in attrs:
            if k in self._ATTRS and v:
                self.urls.append(v)


def check_broken(doc_dir: Path, entry_name: str) -> list:
    parser = _AttrCollector()
    try:
        parser.feed((doc_dir / entry_name).read_text(encoding="utf-8", errors="replace"))
    except Exception as e:
        print(f"[build] 警告: {entry_name} HTML 解析失败，跳过断链校验: {e}", file=sys.stderr)
    broken = set()
    for url in parser.urls:
        path = url.strip().split("#")[0].split("?")[0]
        if not path or path.lower().startswith(SKIP_PREFIX):
            continue
        if not (doc_dir / path).exists():
            broken.add(url)
    return sorted(broken)


def load_docs(docs_dir: Path, category_map: dict) -> list:
    docs = []
    if not docs_dir.exists():
        print(f"[build] 警告: {docs_dir} 不存在，尚无文档", file=sys.stderr)
        return docs
    for d in sorted(docs_dir.iterdir()):
        if not d.is_dir() or d.name.startswith(("_", ".")):
            continue
        meta = parse_meta(d)
        if meta.get("draft"):
            continue
        entry_name = meta.get("entry") or (
            "index.html" if (d / "index.html").exists() else "report.html")
        entry = d / entry_name
        if not entry.exists():
            print(f"[build] 跳过（无入口 {entry_name}）: {d.name}", file=sys.stderr)
            continue
        cat, cat_slug, sub, sub_slug = parse_category(d.name, meta, category_map)
        broken = check_broken(d, entry_name) if entry_name.endswith((".html", ".htm")) else []
        if broken:
            print(f"[build] 断链 {len(broken)}: {d.name}", file=sys.stderr)
        cover = meta.get("cover")
        docs.append({
            "slug": d.name,
            "title": meta.get("title") or read_summary_title(d) or d.name,
            "category": cat, "cat_slug": cat_slug,
            "subcategory": sub, "sub_slug": sub_slug,
            "date": _date_str(meta.get("date")) or infer_date(d.name, entry),
            "summary": meta.get("summary", ""),
            "entry": entry_name,
            "url": f"docs/{d.name}/{entry_name}",
            "cover": f"docs/{d.name}/{cover}" if cover and (d / cover).exists() else None,
            "tags": [str(t) for t in meta.get("tags", [])],
            "broken_count": len(broken),
        })
    docs.sort(key=lambda x: x["date"], reverse=True)
    return docs


def build_tree(docs: list) -> tuple:
    """构建分类树 + 标签云。返回 (categories, tags_cloud)。"""
    cats = OrderedDict()
    for d in docs:
        node = cats.setdefault(d["category"], {"slug": d["cat_slug"], "count": 0, "subs": OrderedDict()})
        node["count"] += 1
        if d["subcategory"]:
            sub = node["subs"].setdefault(d["subcategory"], {"slug": d["sub_slug"], "count": 0})
            sub["count"] += 1
    tags = {}
    for d in docs:
        for t in d["tags"]:
            tags[t] = tags.get(t, 0) + 1
    tags_cloud = sorted(tags.items(), key=lambda x: (-x[1], x[0]))
    return cats, tags_cloud


def copy_static(out_dir: Path):
    if STATIC_DIR.exists():
        for f in STATIC_DIR.rglob("*"):
            if f.is_file():
                dst = out_dir / "static" / f.relative_to(STATIC_DIR)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(f, dst)


def main():
    try:
        from jinja2 import Environment, FileSystemLoader, select_autoescape
    except ImportError:
        sys.exit("[build] 缺少 jinja2，请 pip install jinja2")

    cfg = load_config()
    site_name = cfg.get("site_name", "文档站")
    docs_dir = (ROOT / cfg.get("docs_dir", "site/docs")).resolve()
    out_dir = (ROOT / "site").resolve()
    category_map = cfg.get("category_map", {}) or {}

    docs = load_docs(docs_dir, category_map)
    cats, tags_cloud = build_tree(docs)
    env = Environment(loader=FileSystemLoader(str(TEMPLATES)),
                      autoescape=select_autoescape(["html", "xml"]))

    manifest = [{k: d[k] for k in
                 ("slug", "title", "category", "subcategory", "cat_slug", "sub_slug",
                  "date", "summary", "url", "tags")}
                for d in docs]
    (out_dir / "_data").mkdir(parents=True, exist_ok=True)
    (out_dir / "_data" / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    def render_tpl(name, depth, **kw):
        return env.get_template(name).render(
            depth=depth, categories=cats, tags_cloud=tags_cloud,
            all_count=len(docs), site_name=site_name, **kw)

    (out_dir / "index.html").write_text(
        render_tpl("index.html.j2", "", docs=docs), encoding="utf-8")

    (out_dir / "c").mkdir(exist_ok=True)
    for cat, info in cats.items():
        items = [d for d in docs if d["category"] == cat]
        (out_dir / "c" / f"{info['slug']}.html").write_text(
            render_tpl("category.html.j2", "../", docs=items, category=cat), encoding="utf-8")

    archives = OrderedDict()
    for d in docs:
        archives.setdefault(d["date"][:7], []).append(d)
    (out_dir / "archive").mkdir(exist_ok=True)
    for ym, items in archives.items():
        (out_dir / "archive" / f"{ym}.html").write_text(
            render_tpl("archive.html.j2", "../", docs=items, period=ym), encoding="utf-8")

    (out_dir / "search.html").write_text(render_tpl("search.html.j2", ""), encoding="utf-8")
    # 标签页
    (out_dir / "tags.html").write_text(render_tpl("tags.html.j2", "", docs=docs), encoding="utf-8")

    copy_static(out_dir)
    print(f"[build] {site_name}: {len(docs)} 篇文档，{len(cats)} 个分类，{len(tags_cloud)} 个标签 -> {out_dir}")


if __name__ == "__main__":
    main()
