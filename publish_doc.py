#!/usr/bin/env python3
"""把一个文档目录打包成自包含目录。

扫描入口 HTML 引用的全部本地资源（img/video/source/link/script/a 的 src/href，
以及 CSS 的 url()），复制进 assets/，并把 HTML 里的路径重写为本地 assets/ 路径。
跨目录引用（如 ../兄弟目录/outputs/x.png）会被解析、复制进来，产出可独立同步的文档。

用法:
    python3 publish_doc.py <源文档目录> [输出根目录，默认 dist]
"""
import re
import sys
import shutil
import hashlib
from pathlib import Path

# (src|href|poster)="..." —— 单/双引号都匹配
LINK_RE = re.compile(r"""(src|href|poster)\s*=\s*["']([^"']+)["']""", re.IGNORECASE)
# url(...) —— CSS 背景/inline style
URL_RE = re.compile(r"""url\(\s*["']?([^"')]+)["']?\s*\)""", re.IGNORECASE)
SKIP_PREFIX = ("http://", "https://", "data:", "#", "mailto:", "javascript:", "//")


def is_local(url: str) -> bool:
    u = url.strip().lower()
    return not u.startswith(SKIP_PREFIX)


def flatten(target: Path) -> str:
    """内容寻址式命名：<8位路径哈希>_<原文件名>，保证唯一且保留语义。"""
    h = hashlib.sha1(str(target.resolve()).encode()).hexdigest()[:8]
    return f"{h}_{target.name}"


def find_entry(doc_dir: Path) -> Path:
    meta = doc_dir / ".docmeta.yaml"
    if meta.exists():
        m = re.search(r"^entry:\s*(.+)$", meta.read_text(), re.M)
        if m and (doc_dir / m.group(1).strip()).exists():
            return (doc_dir / m.group(1).strip()).resolve()
    for name in ("index.html", "report.html"):
        if (doc_dir / name).exists():
            return (doc_dir / name).resolve()
    raise SystemExit(f"[publish_doc] 找不到入口 HTML（index.html/report.html）: {doc_dir}")


def remap(url: str, doc_dir: Path, assets_dir: Path, copied: set, broken: set) -> str:
    """把一个本地 url 解析、复制、重写为 assets/ 路径；外链/锚点原样返回。"""
    url = url.strip()
    if not is_local(url):
        return url
    path_part = url.split("#")[0].split("?")[0]
    if not path_part:
        return url
    target = (doc_dir / path_part).resolve()
    if not target.exists():
        broken.add(url)
        return url  # 断链：保留原路径，由 build.py 校验环节标记
    flat = flatten(target)
    if flat not in copied:
        if target.suffix.lower() in (".html", ".htm"):
            # 子 html 报告：递归重写其内部引用并收集其资源，避免双重 assets/ 路径
            sub = target.read_text(encoding="utf-8", errors="replace")
            sub = process_html(sub, target.parent, assets_dir, copied, broken)
            (assets_dir / flat).write_text(sub, encoding="utf-8")
        else:
            shutil.copy2(target, assets_dir / flat)
        copied.add(flat)
    suffix = url[len(path_part):]  # 保留 #锚点 / ?查询
    return f"assets/{flat}{suffix}"


def process_html(html_text: str, doc_dir: Path, assets_dir: Path, copied: set, broken: set) -> str:
    def cb_link(m):
        return f'{m.group(1)}="{remap(m.group(2), doc_dir, assets_dir, copied, broken)}"'

    def cb_url(m):
        return f'url("{remap(m.group(1), doc_dir, assets_dir, copied, broken)}")'

    html_text = LINK_RE.sub(cb_link, html_text)
    html_text = URL_RE.sub(cb_url, html_text)
    return html_text


def main():
    if len(sys.argv) < 2:
        sys.exit("用法: python3 publish_doc.py <源文档目录或单个HTML> [输出根目录]")
    src = Path(sys.argv[1]).resolve()
    out_root = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else Path("dist").resolve()
    # 支持单 HTML 文件输入：doc_dir 取所在目录（资源从这里解析），入口即该文件
    if src.is_file() and src.suffix.lower() in (".html", ".htm"):
        doc_dir, entry, doc_slug = src.parent, src, src.stem
    elif src.is_dir():
        doc_dir, entry, doc_slug = src, find_entry(src), src.name
    else:
        sys.exit(f"[publish_doc] 不是目录或 HTML 文件: {src}")
    out = out_root / doc_slug
    assets = out / "assets"
    if out.exists():
        shutil.rmtree(out)
    assets.mkdir(parents=True)

    copied, broken = set(), set()
    html = entry.read_text(encoding="utf-8", errors="replace")
    html = process_html(html, doc_dir, assets, copied, broken)
    (out / entry.name).write_text(html, encoding="utf-8")

    for f in (".docmeta.yaml", "summary.md"):  # 元数据/摘要一并带出
        p = doc_dir / f
        if p.exists():
            shutil.copy2(p, out / f)

    print(f"[publish_doc] {doc_slug}: 入口={entry.name} 资源={len(copied)} 断链={len(broken)} -> {out}")
    for b in sorted(broken):
        print(f"  [断链] {b}")
    if broken:
        sys.exit(1)


if __name__ == "__main__":
    main()
