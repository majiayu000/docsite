// docsite 列表页通用交互：网格/列表视图切换、排序、二级分类筛选。
(function () {
  "use strict";
  const docs = document.getElementById("docs-list");
  if (!docs) return;
  const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  // 视图偏好恢复
  const savedView = localStorage.getItem("docsite-view");
  if (savedView === "grid" || savedView === "list") docs.dataset.view = savedView;
  const toggleBtns = document.querySelectorAll(".view-toggle button");
  toggleBtns.forEach(b => b.classList.toggle("active", b.dataset.view === docs.dataset.view));
  toggleBtns.forEach(btn => btn.addEventListener("click", () => {
    docs.dataset.view = btn.dataset.view;
    localStorage.setItem("docsite-view", btn.dataset.view);
    toggleBtns.forEach(b => b.classList.toggle("active", b === btn));
  }));

  // 排序
  const sortSel = document.getElementById("sort-select");
  if (sortSel) {
    const savedSort = localStorage.getItem("docsite-sort");
    if (savedSort) sortSel.value = savedSort;
    const sortCards = () => {
      const by = sortSel.value;
      Array.from(docs.querySelectorAll(".card"))
        .sort((a, b) => by === "title"
          ? (a.dataset.title || "").localeCompare(b.dataset.title || "", "zh")
          : (b.dataset.date || "").localeCompare(a.dataset.date || ""))
        .forEach(c => docs.appendChild(c));
    };
    sortSel.addEventListener("change", () => {
      localStorage.setItem("docsite-sort", sortSel.value);
      sortCards();
    });
    sortCards();
  }

  // 二级分类筛选（分类页 ?sub=）
  if (typeof CATEGORY_PAGE !== "undefined" && CATEGORY_PAGE) {
    const sub = new URLSearchParams(location.search).get("sub");
    if (sub) {
      let shown = 0;
      docs.querySelectorAll(".card").forEach(c => {
        const match = c.dataset.sub === sub;
        c.style.display = match ? "" : "none";
        if (match) shown++;
      });
      const cnt = document.getElementById("cat-count");
      if (cnt) cnt.textContent = shown;
      const hint = document.getElementById("sub-filter-hint");
      if (hint) {
        const clearUrl = location.pathname;
        hint.hidden = false;
        hint.innerHTML = `筛选二级分类：<b>${esc(sub)}</b>（${shown} 篇） · <a href="${clearUrl}" style="color:var(--primary)">清除筛选</a>`;
      }
    }
  }
})();
