// docsite 搜索：加载 manifest.json，按 标题/摘要/分类/标签 子串匹配（标题加权，多词 AND）。
// 结果渲染成 .card（列表视图），复用主样式。中文为主，子串匹配比英文分词库实用。
let DOCS = [];
const input = document.getElementById("search-input");
const results = document.getElementById("search-results");
const hint = document.getElementById("search-hint");

const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function scoreDoc(d, q) {
  const hay = `${d.title || ""} ${d.summary || ""} ${d.category || ""} ${d.subcategory || ""} ${(d.tags || []).join(" ")} ${d.slug || ""}`.toLowerCase();
  const terms = q.toLowerCase().split(/\s+/).filter(Boolean);
  if (!terms.length) return 0;
  let s = 0;
  for (const t of terms) {
    if (!hay.includes(t)) return -1;
    if ((d.title || "").toLowerCase().includes(t)) s += 10;
    else if ((d.category || "").toLowerCase().includes(t)) s += 5;
    else if ((d.tags || []).some(x => x.toLowerCase().includes(t))) s += 4;
    else if ((d.summary || "").toLowerCase().includes(t)) s += 2;
    else s += 1;
  }
  return s;
}

function renderCard(d) {
  const sub = d.subcategory ? `<span class="sub">/${esc(d.subcategory)}</span>` : "";
  const tags = (d.tags || []).slice(0, 4).map(t => `<span class="mini-tag">${esc(t)}</span>`).join("");
  return `<a class="card" href="${esc(d.url)}" data-date="${esc(d.date)}">
    <div class="card-cover placeholder">📄</div>
    <div class="card-body">
      <div class="card-meta"><span class="cat-chip">${esc(d.category)}${sub}</span><span class="date">${esc(d.date)}</span></div>
      <h3 class="card-title">${esc(d.title)}</h3>
      ${d.summary ? `<p class="card-summary">${esc(d.summary)}</p>` : ""}
      ${tags ? `<div class="card-tags">${tags}</div>` : ""}
    </div>
  </a>`;
}

function run(q) {
  q = (q || "").trim();
  if (!q) { results.innerHTML = '<p class="empty">输入关键词开始搜索</p>'; return; }
  const hits = DOCS.map(d => ({ d, s: scoreDoc(d, q) })).filter(x => x.s >= 0).sort((a, b) => b.s - a.s);
  results.innerHTML = hits.length
    ? hits.map(h => renderCard(h.d)).join("")
    : '<p class="empty">无匹配文档</p>';
}

fetch(MANIFEST_URL).then(r => r.json()).then(d => {
  DOCS = d;
  hint.textContent = `共 ${DOCS.length} 篇文档可搜索`;
  const q = new URLSearchParams(location.search).get("q") || "";
  if (q) input.value = q;
  run(input.value);
}).catch(e => { hint.textContent = "加载 manifest 失败：" + e; });

input.addEventListener("input", () => run(input.value));
