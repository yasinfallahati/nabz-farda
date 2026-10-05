/* نبض فردا — Instagram-style stories bar + full-screen viewer (data: /data/stories.json, 24h TTL) */
(() => {
  "use strict";
  const DURATION = 6000, TTL = 24 * 3600e3, SEEN_KEY = "nf_seen_stories_v1";
  const CAT = {
    ai: { fa: "هوش مصنوعی", icon: '<svg viewBox="0 0 24 24"><rect x="6" y="6" width="12" height="12" rx="3"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/></svg>' },
    tech: { fa: "تکنولوژی", icon: '<svg viewBox="0 0 24 24"><rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/></svg>' },
    game: { fa: "گیم", icon: '<svg viewBox="0 0 24 24"><path d="M6 8h12a4 4 0 0 1 4 4v1a4 4 0 0 1-7 2.6L14 15h-4l-1 .6A4 4 0 0 1 2 13v-1a4 4 0 0 1 4-4z"/></svg>' },
  };
  const LOGO = '<svg viewBox="0 0 48 48" aria-hidden="true"><path d="M3 26h9l4-10 7 20 6-26 5 16h11" fill="none" stroke="#ff5a4e" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"/></svg>';
  const I = {
    x: '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6 6 18"/></svg>',
    pause: '<svg class="i-pause" viewBox="0 0 24 24"><path d="M9 5v14M15 5v14"/></svg><svg class="i-play" viewBox="0 0 24 24"><path d="M8 5l11 7-11 7z"/></svg>',
    right: '<svg viewBox="0 0 24 24"><path d="m9 6 6 6-6 6"/></svg>',
    left: '<svg viewBox="0 0 24 24"><path d="m15 6-6 6 6 6"/></svg>',
    out: '<svg viewBox="0 0 24 24"><path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/></svg>',
  };
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const faNum = (n) => Number(n).toLocaleString("fa-IR");
  function ago(iso) {
    const m = Math.max(0, Math.round((Date.now() - new Date(iso)) / 60000));
    if (m < 1) return "لحظاتی پیش";
    if (m < 60) return faNum(m) + " دقیقه پیش";
    const h = Math.round(m / 60);
    if (h < 24) return faNum(h) + " ساعت پیش";
    return faNum(Math.round(h / 24)) + " روز پیش";
  }
  const seen = new Set((() => { try { return JSON.parse(localStorage.getItem(SEEN_KEY)) || []; } catch { return []; } })());
  const saveSeen = () => { try { localStorage.setItem(SEEN_KEY, JSON.stringify([...seen].slice(-300))); } catch {} };

  const bar = document.getElementById("stories");
  if (!bar) return;
  const row = bar.querySelector(".stories-row");
  let list = [];

  function renderBar() {
    row.innerHTML = list.map((s, k) => `<button class="story ${seen.has(s.id) ? "seen" : "unseen"}" data-cat="${esc(s.category)}" data-i="${k}" style="--k:${k}" role="listitem" aria-label="${esc(s.title_fa)}">
      <span class="ring"><span class="av">${s.image ? `<img src="${esc(s.image)}" alt="" loading="${k < 3 ? "eager" : "lazy"}" decoding="async" referrerpolicy="no-referrer" onerror="this.classList.add('broken')">` : ""}</span>
      <span class="badge" aria-hidden="true">${(CAT[s.category] || CAT.tech).icon}</span></span>
      <span class="lbl">${esc(s.title_fa)}</span></button>`).join("");
  }
  row.addEventListener("click", (e) => { const b = e.target.closest(".story"); if (b) open(+b.dataset.i, true); });

  /* ---------- viewer ---------- */
  let el, cur = 0, t0 = 0, elapsed = 0, paused = false, loading = false, raf = 0, isOpen = false, pushed = false, lastFocus = null;
  const hold = { on: false };

  function ensure() { if (!el) build(); }
  function build() {
    el = document.createElement("div");
    el.className = "sv";
    el.setAttribute("role", "dialog");
    el.setAttribute("aria-modal", "true");
    el.setAttribute("aria-label", "استوری خبر");
    el.innerHTML = `<div class="sv-bg"></div>
      <button class="sv-nav sv-prev" aria-label="قبلی">${I.right}</button>
      <div class="sv-card">
        <div class="sv-media"><img alt="" referrerpolicy="no-referrer"></div><div class="sv-shade"></div>
        <div class="sv-tap prev"></div><div class="sv-tap next"></div>
        <div class="sv-top"><div class="sv-bars"></div>
          <div class="sv-head"><span class="sv-logo">${LOGO}</span><div class="sv-who"><b>نبض فردا</b><small></small></div>
          <button class="sv-btn sv-pause" aria-label="توقف/پخش">${I.pause}</button><button class="sv-btn sv-x" aria-label="بستن">${I.x}</button></div></div>
        <div class="sv-body"></div>
      </div>
      <button class="sv-nav sv-next" aria-label="بعدی">${I.left}</button>
      <div class="sv-hint">← → برای جابه‌جایی · Esc برای بستن</div>`;
    el.hidden = true;
    document.body.appendChild(el);
    el.querySelector(".sv-x").addEventListener("click", (e) => { e.stopPropagation(); close(); });
    el.querySelector(".sv-pause").addEventListener("click", (e) => { e.stopPropagation(); setPaused(!paused); });
    el.querySelector(".sv-prev").addEventListener("click", () => go(-1));
    el.querySelector(".sv-next").addEventListener("click", () => go(1));
    el.addEventListener("click", (e) => { if (e.target === el || e.target.classList.contains("sv-bg")) close(); });
    const img = el.querySelector(".sv-media img");
    img.addEventListener("load", () => { img.classList.add("ok"); ready(); });
    img.addEventListener("error", () => ready());
    gestures(el.querySelector(".sv-card"));
  }

  function show(i) {
    cur = i;
    const s = list[i];
    const card = el.querySelector(".sv-card");
    card.dataset.cat = s.category;
    el.querySelector(".sv-bg").style.backgroundImage = s.image ? `url("${s.image.replace(/"/g, "%22")}")` : "none";
    el.querySelector(".sv-bars").innerHTML = list.map((_, k) => `<i class="${k < i ? "done" : k === i ? "cur" : ""}"><b></b></i>`).join("");
    el.querySelector(".sv-who small").innerHTML = `<span class="src">${esc(s.source)}</span> · ${ago(s.published)}`;
    el.querySelector(".sv-body").innerHTML = `<span class="pill">${(CAT[s.category] || CAT.tech).fa}</span>
      <h2>${esc(s.title_fa)}</h2><p>${esc(s.summary_fa)}</p>
      <a class="sv-cta" href="${esc(s.url)}" target="_blank" rel="noopener">خواندن خبر ${I.out}</a>`;
    el.querySelector(".sv-cta").addEventListener("click", () => setPaused(true));
    const img = el.querySelector(".sv-media img");
    img.classList.remove("ok");
    elapsed = 0; loading = true; el.classList.add("sv-loading");
    if (s.image) { img.src = s.image; if (img.complete && img.naturalWidth) { img.classList.add("ok"); ready(); } }
    else { img.removeAttribute("src"); ready(); }
    clearTimeout(show.t); show.t = setTimeout(ready, 2500); // never wait forever for a slow image
    el.querySelector(".sv-prev").disabled = i === 0;
    const n = list[i + 1]; if (n && n.image) new Image().src = n.image; // preload next
    seen.add(s.id); saveSeen();
    const b = row.querySelector(`.story[data-i="${i}"]`); if (b) { b.classList.replace("unseen", "seen"); }
    history.replaceState({ sv: 1 }, "", "#s=" + s.id); // shareable deep link to the current story
    t0 = performance.now();
  }
  function ready() { if (!loading) return; loading = false; el && el.classList.remove("sv-loading"); t0 = performance.now(); }

  function tick(now) {
    raf = requestAnimationFrame(tick);
    if (!el || paused || hold.on || loading) { t0 = now; return; }
    elapsed += now - t0; t0 = now;
    const b = el.querySelector(".sv-bars i.cur b");
    if (b) b.style.transform = `scaleX(${Math.min(1, elapsed / DURATION)})`;
    if (elapsed >= DURATION) go(1);
  }
  function go(d) {
    const n = cur + d;
    if (n >= list.length) return close();
    if (n < 0) { elapsed = 0; t0 = performance.now(); return; }
    show(n);
  }
  function setPaused(p) { paused = p; el && el.classList.toggle("paused", p); }

  function open(i, push) {
    ensure();
    if (!list.length) return;
    if (!el) build();
    lastFocus = document.activeElement;
    const c = el.querySelector(".sv-card"); c.style.transform = ""; c.style.opacity = "";
    setPaused(false);
    document.documentElement.style.overflow = "hidden";
    el.hidden = false;
    requestAnimationFrame(() => el.classList.add("open"));
    isOpen = true;
    pushed = !!push;  // pushed a history entry -> the phone's Back button closes the viewer
    if (push) history.pushState({ sv: 1 }, "", "#s=" + list[i].id);
    show(i);
    cancelAnimationFrame(raf); raf = requestAnimationFrame((n) => { t0 = n; tick(n); });
    el.querySelector(".sv-x").focus({ preventScroll: true });
  }
  function close(fromPop) {
    if (!isOpen) return;
    isOpen = false;
    cancelAnimationFrame(raf); clearTimeout(show.t);
    el.classList.remove("open");
    document.documentElement.style.overflow = "";
    setTimeout(() => { if (isOpen) return; el.hidden = true; const c = el.querySelector(".sv-card"); c.style.transform = ""; c.style.opacity = ""; }, 220);
    if (!fromPop) {
      if (pushed) history.back();
      else history.replaceState(null, "", location.pathname + location.search);
    }
    pushed = false;
    lastFocus && lastFocus.focus && lastFocus.focus({ preventScroll: true });
  }
  addEventListener("popstate", () => { if (isOpen) close(true); });

  addEventListener("keydown", (e) => {
    if (!isOpen) return;
    if (e.key === "Escape") { e.preventDefault(); close(); }
    else if (e.key === "ArrowLeft") { e.preventDefault(); go(1); }   // RTL: left = forward
    else if (e.key === "ArrowRight") { e.preventDefault(); go(-1); }
    else if (e.key === " ") { e.preventDefault(); setPaused(!paused); }
  });
  document.addEventListener("visibilitychange", () => { if (document.hidden && isOpen) setPaused(true); });

  function gestures(card) {
    let sx = 0, sy = 0, st = 0, id = null, drag = false;
    card.addEventListener("pointerdown", (e) => {
      if (e.target.closest("a,button")) return;
      id = e.pointerId; sx = e.clientX; sy = e.clientY; st = Date.now(); drag = false; hold.on = true;
      card.setPointerCapture(id);
    });
    card.addEventListener("pointermove", (e) => {
      if (e.pointerId !== id) return;
      const dy = e.clientY - sy, dx = e.clientX - sx;
      if (!drag && dy > 12 && Math.abs(dy) > Math.abs(dx)) drag = true;
      if (drag) {
        card.classList.add("dragging");
        const y = Math.max(0, dy);
        card.style.transform = `translateY(${y}px) scale(${1 - Math.min(y / 2000, .12)})`;
        el.style.background = `rgba(0,0,0,${Math.max(0.25, 1 - y / 500)})`;
      }
    });
    const end = (e) => {
      if (e.pointerId !== id) return;
      id = null; hold.on = false;
      const dy = e.clientY - sy, dx = e.clientX - sx, dt = Date.now() - st;
      card.classList.remove("dragging"); el.style.background = "";
      if (drag) {
        drag = false;
        if (dy > 110 || (dy > 50 && dt < 250)) { card.style.transform = `translateY(${innerHeight}px)`; card.style.opacity = "0"; return close(); }
        card.style.transform = ""; return;
      }
      if (e.type === "pointercancel") return;
      if (Math.abs(dx) > 60 && Math.abs(dx) > Math.abs(dy) * 1.5) return go(dx > 0 ? 1 : -1); // RTL swipe: drag right = next
      if (dt < 300 && Math.abs(dx) < 12 && Math.abs(dy) < 12) {
        const r = card.getBoundingClientRect();
        go(e.clientX > r.left + r.width * 0.66 ? -1 : 1); // right third = previous, left = next (RTL)
      }
    };
    card.addEventListener("pointerup", end);
    card.addEventListener("pointercancel", end);
    card.addEventListener("contextmenu", (e) => e.preventDefault());
  }

  /* ---------- load ---------- */
  fetch("/data/stories.json?t=" + Date.now()).then((r) => (r.ok ? r.json() : [])).then((data) => {
    const arr = Array.isArray(data) ? data : data.stories || [];
    const now = Date.now();
    const live = arr.filter((s) => s && s.id && s.title_fa && now - new Date(s.added_at || s.published) < TTL)
      .sort((a, b) => new Date(b.added_at) - new Date(a.added_at) || new Date(b.published) - new Date(a.published))
      .slice(0, 15);
    // Instagram order: unseen first, then seen (each newest first)
    list = [...live.filter((s) => !seen.has(s.id)), ...live.filter((s) => seen.has(s.id))];
    if (!list.length) { bar.hidden = true; return; }
    renderBar();
    bar.hidden = false;
    const m = location.hash.match(/^#s=([\w-]+)/);
    if (m) { const k = list.findIndex((s) => s.id === m[1]); if (k >= 0) open(k, false); }
  }).catch(() => { bar.hidden = true; });

})();
