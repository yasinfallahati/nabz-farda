(() => {
  "use strict";
  document.addEventListener("click", (e) => {
    const btn = e.target.closest(".share-copy");
    if (!btn) return;
    const url = btn.getAttribute("data-url") || location.href;
    const done = () => {
      const prev = btn.textContent;
      btn.textContent = "کپی شد";
      btn.classList.add("copied");
      setTimeout(() => { btn.textContent = prev; btn.classList.remove("copied"); }, 1600);
    };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(url).then(done).catch(() => fallback());
    } else fallback();
    function fallback() {
      const t = document.createElement("textarea");
      t.value = url; document.body.appendChild(t); t.select();
      try { document.execCommand("copy"); done(); } catch (_) {}
      t.remove();
    }
  });

  if ("serviceWorker" in navigator) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {});
    });
  }
})();
