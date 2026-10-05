(() => {
  "use strict";
  const TZ = "Asia/Tehran";
  const CATS = { ai: "هوش مصنوعی", tech: "تکنولوژی", game: "گیم" };
  const $ = (s, r = document) => r.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const faNum = (n) => Number(n).toLocaleString("fa-IR");
  const jDate = (d, o = {}) => new Intl.DateTimeFormat("fa-IR-u-ca-persian", { timeZone: TZ, ...o }).format(d);
  // compose parts ourselves: some ICU builds render the combined weekday format as "۱۴۰۵ مهر ۱۲, یکشنبه"
  const fullDate = (d) => `${jDate(d, { weekday: "long" })} ${jDate(d, { day: "numeric" })} ${jDate(d, { month: "long" })} ${jDate(d, { year: "numeric" })}`;
  const timeFa = (d) => jDate(d, { hour: "2-digit", minute: "2-digit", hour12: false });
  const dayLabel = (iso) => fullDate(new Date(iso + "T12:00:00+03:30"));
  function rel(d, ref) {
    const m = Math.round((ref - d) / 60000);
    if (m < 1) return "لحظاتی پیش";
    if (m < 60) return faNum(m) + " دقیقه پیش";
    const h = Math.round(m / 60);
    if (h < 24) return faNum(h) + " ساعت پیش";
    return jDate(d, { day: "numeric" }) + " " + jDate(d, { month: "long" });
  }

  const params = new URLSearchParams(location.search);
  const state = { cat: CATS[params.get("c")] ? params.get("c") : "all", q: "", day: null, items: [], archive: [], isLatest: true, ref: Date.now() };

  function media(it, eager = false) {
    const fb = `<div class="fallback"><span>${esc(it.source)}</span></div>`;
    if (!it.image) return fb;
    return fb + `<img class="img" src="${esc(it.image)}" alt="" loading="${eager ? "eager" : "lazy"}" decoding="async" referrerpolicy="no-referrer" onerror="this.classList.add('broken')">`;
  }
  function meta(it) {
    const d = new Date(it.published);
    return `<div class="meta"><span class="src">${esc(it.source)}</span><i class="sep"></i><time datetime="${esc(it.published)}" title="${esc(fullDate(d) + "، ساعت " + timeFa(d))}">${state.isLatest ? rel(d, state.ref) : timeFa(d)}</time></div>`;
  }
  const T = (it) => esc(it.title_fa || it.title);
  // cards open the on-site article page (built by scripts/sitegen.py); that page links on to the source
  const pageUrl = (it) => it.page || `/news/${state.day}/${it.id}`;
  const kicker = (it) => `<span class="kicker">${CATS[it.category] || ""}</span>`;

  const card = (it) => `<a class="card" data-cat="${it.category}" href="${esc(pageUrl(it))}">
      <div class="media">${media(it)}</div>
      <div class="txt">${kicker(it)}<h3>${T(it)}</h3>${meta(it)}</div></a>`;

  function filtered() {
    const q = state.q.trim().toLowerCase();
    return state.items.filter((it) => (state.cat === "all" || it.category === state.cat) &&
      (!q || [it.title_fa, it.summary_fa, it.title, it.source].join(" ").toLowerCase().includes(q)));
  }

  function render() {
    const list = filtered();
    const hero = $("#hero"), grid = $("#list");
    $("#empty").hidden = list.length > 0;
    $(".latest").hidden = list.length < 2;
    if (!list.length) { hero.innerHTML = ""; grid.innerHTML = ""; return; }
    const lead = (state.cat === "all" && !state.q && list.find((i) => i.featured)) || list.find((i) => i.image) || list[0];
    hero.innerHTML = `<a class="lead" data-cat="${lead.category}" href="${esc(pageUrl(lead))}">
        <div class="media">${media(lead, true)}</div>
        <div class="lead-txt">${kicker(lead)}<h2>${T(lead)}</h2><p>${esc(lead.summary_fa || "")}</p>${meta(lead)}</div></a>`;
    const rest = list.filter((i) => i !== lead);
    $("#count").textContent = faNum(rest.length) + " خبر";
    $("#latestTitle").textContent = state.q ? "نتایج جست‌وجو" : state.cat === "all" ? "آخرین خبرها" : CATS[state.cat];
    grid.innerHTML = rest.map(card).join("");
  }

  function renderArchive() {
    $("#days").innerHTML = state.archive.map((d, i) =>
      `<a class="day${d.date === state.day ? " cur" : ""}" href="${i === 0 ? "/" : "/?d=" + d.date}"><span>${dayLabel(d.date)}${i === 0 ? "، امروز" : ""}</span><small>${faNum(d.count)} خبر</small></a>`).join("");
  }

  function setTab(cat, push) {
    state.cat = cat;
    document.querySelectorAll(".tab").forEach((x) => { const on = x.dataset.cat === cat; x.classList.toggle("active", on); x.setAttribute("aria-selected", on); });
    if (push) {
      const u = new URL(location.href);
      cat === "all" ? u.searchParams.delete("c") : u.searchParams.set("c", cat);
      history.replaceState(null, "", u);
    }
    render();
  }

  async function load() {
    const ts = Date.now();
    const want = params.get("d");
    // Parallel: archive + day JSON (latest.json mirror when viewing today — avoids sequential waterfall)
    const archP = fetch("/data/archive.json?t=" + ts).then((r) => r.json());
    const dayUrl = want
      ? `/data/days/${want}.json?t=${ts}`
      : `/data/latest.json?t=${ts}`;
    const dayP = fetch(dayUrl).then((r) => {
      if (!r.ok) throw new Error("day " + r.status);
      return r.json();
    });
    let arch, data;
    try {
      [arch, data] = await Promise.all([archP, dayP]);
    } catch (err) {
      // Fallback if latest.json missing: wait for archive then fetch named day
      arch = await archP;
      const day = want && (arch.days || []).some((d) => d.date === want) ? want : arch.days?.[0]?.date;
      data = await fetch(`/data/days/${day}.json?t=${ts}`).then((r) => r.json());
    }
    state.archive = arch.days || [];
    const day = data.date || (want && state.archive.some((d) => d.date === want) ? want : state.archive[0]?.date);
    // If ?d= pointed at a day but latest was fetched by mistake, re-fetch
    if (want && data.date && data.date !== want) {
      data = await fetch(`/data/days/${want}.json?t=${ts}`).then((r) => r.json());
    }
    state.day = data.date || day;
    state.isLatest = state.day === state.archive[0]?.date;
    state.items = (data.items || []).slice().sort((a, b) => new Date(b.published) - new Date(a.published));
    state.ref = state.isLatest ? Date.now() : new Date(data.updated_at).getTime();
    const up = new Date(data.updated_at);
    $("#updated span").textContent = "به‌روزرسانی " + jDate(up, { day: "numeric" }) + " " + jDate(up, { month: "long" }) + "، ساعت " + timeFa(up);
    if (!state.isLatest) {
      const n = $("#archiveNote");
      n.hidden = false;
      n.innerHTML = `در حال مشاهدهٔ آرشیو <b>${dayLabel(state.day)}</b> هستید. <a href="/">بازگشت به اخبار امروز</a>`;
      document.title = "آرشیو " + dayLabel(state.day) + " | نبض فردا";
    }
    $("#sources").textContent = [...new Set(state.items.map((i) => i.source))].sort().join(" · ");
    renderArchive(); setTab(state.cat, false);
  }

  // UI wiring — category chips filter in-DOM items only (no search-index on home)
  $("#today").textContent = fullDate(new Date());
  document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => { setTab(b.dataset.cat, true); }));
  const sBtn = $("#searchBtn"), sRow = $("#searchRow"), q = $("#q");
  sBtn.addEventListener("click", () => {
    const open = sRow.hidden; sRow.hidden = !open; sBtn.setAttribute("aria-expanded", open);
    if (open) q.focus(); else if (state.q) { q.value = ""; state.q = ""; render(); }
  });
  let qt; q.addEventListener("input", (e) => { clearTimeout(qt); qt = setTimeout(() => { state.q = e.target.value; render(); }, 150); });
  q.addEventListener("keydown", (e) => { if (e.key === "Escape") sBtn.click(); });
  const dlg = $("#archive");
  $("#archiveBtn").addEventListener("click", () => dlg.showModal());
  $("#archiveClose").addEventListener("click", () => dlg.close());
  dlg.addEventListener("click", (e) => { if (e.target === dlg) dlg.close(); });
  load().catch((err) => { console.error(err); $("#hero").innerHTML = '<p class="empty">خطا در بارگذاری اخبار. لطفاً صفحه را دوباره بارگذاری کنید.</p>'; });
})();
