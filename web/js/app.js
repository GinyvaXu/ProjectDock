/**
 * app.js — ProjectDock 前端逻辑。
 */
(function () {
  "use strict";

  const { api, streamEvents } = window.API;
  const Spring = window.Spring;

  const S = {
    settings: null,
    presets: [],
    types: [],
    agents: [],
    projects: [],
    filter: "all",
    search: "",
    current: null,
    currentTab: "overview",
    versions: null,
    builds: [],
    chatRunning: false,
  };

  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const fmtSize = (n) => (n == null ? "" : n >= 1048576 ? (n / 1048576).toFixed(1) + " MB" : n >= 1024 ? (n / 1024).toFixed(1) + " KB" : n + " B");
  const TYPE_ICONS = { "软件": "💻", "网站": "🌐", "游戏": "🎮", "PPT": "📊", "文稿": "📄", "脚本": "🐍", "其他": "📁" };
  const typeIcon = (p) => TYPE_ICONS[p.type] || "📁";
  function logoHTML(p) {
    const emoji = "<span class='logo-fallback'>" + typeIcon(p) + "</span>";
    if (!p.has_logo) return emoji;
    return "<span class='logo-wrap'>" + emoji +
      "<img class='proj-logo' src='/api/projects/" + encodeURIComponent(p.id) + "/logo' alt='' onerror='this.remove()'></span>";
  }

  /* ============ 初始化 ============ */
  async function init() {
    const [settings, presets, agents, projects, health] = await Promise.all([
      api("/api/settings"), api("/api/presets"), api("/api/agents"), api("/api/projects"), api("/api/health"),
    ]);
    S.settings = settings;
    S.presets = presets;
    S.agents = agents;
    S.projects = projects;
    $("appVersion").textContent = "v" + health.version;
    applyTheme(settings.theme);
    fillTypeSelects();
    fillAgentSelect();
    renderSidebar();
    renderGrid();
    bindEvents();
  }

  function applyTheme(theme) {
    const mode = theme === "system"
      ? (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")
      : theme;
    document.documentElement.dataset.theme = mode;
  }

  /* ============ 渲染 ============ */
  function renderSidebar() {
    $("rootPath").textContent = S.settings.root;
    $("rootPath").title = S.settings.root;
    const counts = {};
    S.projects.forEach((p) => { counts[p.type] = (counts[p.type] || 0) + 1; });
    $("countAll").textContent = S.projects.length;
    const wrap = $("typeFilters");
    wrap.innerHTML = "";
    S.presets.forEach((preset) => {
      const btn = document.createElement("button");
      btn.className = "nav-item" + (S.filter === preset.type ? " active" : "");
      btn.dataset.filter = preset.type;
      btn.innerHTML = "<span class='nav-ico'>•</span><span>" + esc(preset.label) + "</span><span class='count'>" + (counts[preset.type] || 0) + "</span>";
      btn.addEventListener("click", () => setFilter(preset.type));
      wrap.appendChild(btn);
    });
  }

  function filtered() {
    let list = S.projects;
    if (S.filter !== "all") list = list.filter((p) => p.type === S.filter);
    const q = S.search.trim().toLowerCase();
    if (q) {
      list = list.filter((p) => (p.name + " " + p.title + " " + p.description + " " + p.type).toLowerCase().indexOf(q) >= 0);
    }
    return list;
  }

  function cardHTML(p) {
    return "<div class='card' data-id='" + esc(p.id) + "' style='opacity:0'>" +
      "<div class='card-head'>" +
        "<span class='card-logo type-" + esc(p.type) + "'>" + logoHTML(p) + "</span>" +
        "<div class='card-head-text'>" +
          "<h3 class='card-title'>" + esc(p.title) + "</h3>" +
          "<div class='card-top'><span class='badge " + esc(p.type) + "'>" + esc(p.type) + "</span>" +
          (p.compliant ? "" : "<span class='badge badge-warn' title='未达标项目管理规范'>⚠ 未合规</span>") +
          (p.version ? "<span class='card-version'>v" + esc(p.version) + "</span>" : "") + "</div>" +
        "</div>" +
      "</div>" +
      "<p class='card-desc'>" + esc(p.description || "（暂无描述）") + "</p>" +
      "<div class='card-meta'>" +
        "<span class='card-path'>" + esc(p.id) + "</span>" +
        (p.has_git ? "<span class='git-ok'>git ✓</span>" : "<span class='git-no'>git</span>") +
      "</div>" +
    "</div>";
  }

  function renderGrid() {
    const list = filtered();
    const grid = $("grid");
    const noProjects = S.projects.length === 0;
    $("empty").hidden = list.length > 0;
    if (!list.length) {
      $("emptyIco").textContent = noProjects ? "▢" : "⌕";
      $("emptyTitle").textContent = noProjects ? "这里还没有项目" : "没有匹配的项目";
      $("emptySub").textContent = noProjects
        ? "点击右上角「新建项目」开始，或用「导入项目」纳入已有文件夹"
        : "换个关键词或类型筛选试试";
    }
    grid.innerHTML = "";
    if (!list.length) return;
    const frag = document.createDocumentFragment();
    list.forEach((p, i) => {
      const el = document.createElement("div");
      el.innerHTML = cardHTML(p);
      const card = el.firstElementChild;
      card.addEventListener("click", () => openDrawer(p.id));
      frag.appendChild(card);
      Spring.enter(card, { delay: Math.min(i * 40, 320), distance: 22 });
    });
    grid.appendChild(frag);
  }

  function setFilter(type) {
    S.filter = type;
    document.querySelectorAll(".nav-item").forEach((el) => {
      el.classList.toggle("active", el.dataset.filter === type);
    });
    renderGrid();
  }

  /* ============ 抽屉 ============ */
  async function openDrawer(id) {
    const proj = S.projects.find((p) => p.id === id);
    if (!proj) return;
    S.current = proj;
    S.versions = null;
    S.builds = [];
    S.compliance = null;
    S.currentTab = "overview";
    $("drawerName").textContent = proj.title;
    $("drawerType").textContent = proj.type;
    $("drawerType").className = "badge " + esc(proj.type);
    $("drawerLogo").className = "drawer-logo type-" + esc(proj.type);
    $("drawerLogo").innerHTML = logoHTML(proj);
    $("drawerPath").textContent = proj.path;
    $("drawerPath").title = proj.path;
    showTab("overview");
    renderOverview(proj);
    showDrawer();
    try {
      const [versions, builds] = await Promise.all([
        api("/api/projects/" + encodeURIComponent(id) + "/versions"),
        api("/api/projects/" + encodeURIComponent(id) + "/builds"),
      ]);
      S.versions = versions;
      S.builds = builds;
      renderVersions();
    } catch (err) { toast("加载版本信息失败：" + err.message, "err"); }
  }

  function showDrawer() {
    const drawer = $("drawer");
    const backdrop = $("backdrop");
    drawer.hidden = false;
    backdrop.hidden = false;
    drawer.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
    requestAnimationFrame(() => {
      Spring.slideIn(drawer, { stiffness: 200, damping: 30 });
      backdrop.style.opacity = "1";
    });
  }

  function closeDrawer() {
    const drawer = $("drawer");
    const backdrop = $("backdrop");
    Spring.slideOut(drawer, {
      to: 120,
      onComplete: () => {
        drawer.hidden = true;
        backdrop.hidden = true;
        document.body.style.overflow = "";
      },
    });
    backdrop.style.opacity = "0";
  }

  function showTab(tab) {
    S.currentTab = tab;
    document.querySelectorAll(".tab").forEach((el) => el.classList.toggle("active", el.dataset.tab === tab));
    document.querySelectorAll(".panel").forEach((el) => el.classList.remove("active", "panel-in"));
    const panel = $("panel-" + tab);
    panel.classList.add("active");
    void panel.offsetWidth;
    panel.classList.add("panel-in");
    if (tab === "versions" && S.versions) renderVersions();
    if (tab === "compliance") renderCompliance();
  }

  function renderOverview(proj) {
    const version = proj.version ? "<div class='ov-version'>v" + esc(proj.version) + "</div><div class='ov-sub'>当前版本（来自 VERSION 文件）</div>" : "<div class='ov-sub' style='font-size:15px'>该类型项目暂无版本信息</div>";
    $("panel-overview").innerHTML =
      "<div class='overview-hero'>" + version + "</div>" +
      "<div class='desc-box'>" + esc(proj.description || "（暂无描述）") + "</div>" +
      "<div class='meta-list'>" +
        "<div class='meta-row'><span class='k'>文件夹</span><span class='v'>" + esc(proj.id) + "</span></div>" +
        "<div class='meta-row'><span class='k'>类型</span><span class='v'>" + esc(proj.type) + "</span></div>" +
        "<div class='meta-row'><span class='k'>路径</span><span class='v'>" + esc(proj.path) + "</span></div>" +
        "<div class='meta-row'><span class='k'>Git</span><span class='v'>" + (proj.has_git ? "已初始化 ✓" : "未初始化") + "</span></div>" +
        "<div class='meta-row'><span class='k'>管理规范</span><span class='v'>" + (proj.compliant ? "已达标 ✓" : "未达标（可一键合规）") + "</span></div>" +
        (proj.created_at ? "<div class='meta-row'><span class='k'>纳入时间</span><span class='v'>" + esc(proj.created_at) + "</span></div>" : "") +
      "</div>" +
      "<div class='git-panel'><div class='git-head'><h4>Git 状态</h4><button class='btn btn-sm' id='btnGitRefresh'>刷新</button></div><div class='git-body' id='gitBody'>加载中…</div></div>" +
      "<div class='doc-panel'><div class='git-head'><h4>项目文档</h4><button class='btn btn-sm' id='btnDocRefresh'>刷新</button></div><div class='doc-list' id='docList'>加载中…</div></div>" +
      "<div class='action-row'>" +
        "<button class='btn btn-sm' data-act='open'>打开文件夹</button>" +
        "<button class='btn btn-sm' data-act='copy'>复制路径</button>" +
        "<button class='btn btn-sm' data-act='init'>预设初始化</button>" +
        "<button class='btn btn-sm' data-act='compliance'>合规检查</button>" +
        (proj.imported ? "" : "<button class='btn btn-sm btn-danger' data-act='remove'>移除管理</button>") +
      "</div>";
    $("panel-overview").querySelectorAll("[data-act]").forEach((btn) => {
      btn.addEventListener("click", () => handleOverviewAction(btn.dataset.act));
    });
    const gitRefresh = $("btnGitRefresh");
    if (gitRefresh) gitRefresh.addEventListener("click", () => loadGitStatus(S.current.id));
    const docRefresh = $("btnDocRefresh");
    if (docRefresh) docRefresh.addEventListener("click", () => loadDocuments(S.current.id));
    loadGitStatus(proj.id);
    loadDocuments(proj.id);
  }

  async function loadGitStatus(id) {
    const body = $("gitBody");
    if (!body) return;
    body.innerHTML = "加载中…";
    try {
      const st = await api("/api/projects/" + encodeURIComponent(id) + "/git-status");
      if (!st.has_git) {
        body.innerHTML = "<div class='git-row'><span class='git-dot no'></span><span>该项目未初始化 git（可点上方「预设初始化」）</span></div>";
        return;
      }
      let chg = "";
      if (st.dirty && st.files.length) {
        chg = "<div class='chg-list'>" + st.files.slice(0, 8).map((f) => "<div class='chg-item'>" + esc(f) + "</div>").join("") +
          (st.files.length > 8 ? "<div class='chg-item'>… 共 " + st.files.length + " 项变更</div>" : "") + "</div>";
      }
      body.innerHTML =
        "<div class='git-row'><span class='git-dot " + (st.dirty ? "dirty" : "clean") + "'></span>" +
        (st.dirty ? "<span class='git-txt-warn'>工作区有 " + st.files.length + " 项变更</span>" : "<span>工作区干净</span>") + "</div>" +
        (st.head ? "<div class='git-row'><span class='k'>最新提交</span><span class='v mono'>" + esc(st.head) + "</span></div>" : "") +
        chg;
    } catch (err) {
      body.innerHTML = "<div class='git-row'>读取失败：" + esc(err.message) + "</div>";
    }
  }

  async function openPath(path) {
    if (!S.current) return;
    try {
      await api("/api/projects/" + encodeURIComponent(S.current.id) + "/open-file", { method: "POST", body: { path: path } });
    } catch (err) { toast(err.message, "err"); }
  }

  async function revealPath(path) {
    if (!S.current) return;
    try {
      await api("/api/projects/" + encodeURIComponent(S.current.id) + "/reveal-file", { method: "POST", body: { path: path } });
    } catch (err) { toast(err.message, "err"); }
  }

  function bindPathActions(scope) {
    scope.querySelectorAll("[data-open]").forEach((btn) => btn.addEventListener("click", () => openPath(btn.dataset.open)));
    scope.querySelectorAll("[data-reveal]").forEach((btn) => btn.addEventListener("click", () => revealPath(btn.dataset.reveal)));
  }

  async function loadDocuments(id) {
    const list = $("docList");
    if (!list) return;
    list.innerHTML = "加载中…";
    try {
      const docs = await api("/api/projects/" + encodeURIComponent(id) + "/documents");
      if (!docs.length) {
        list.innerHTML = "<div class='git-row'><span>未找到计划书/企划书等文档（支持 README、计划书、企划书、方案、设计、需求等）</span></div>";
        return;
      }
      list.innerHTML = docs.map((d) =>
        "<div class='doc-item'><span class='doc-name'>" + esc(d.name) + "</span>" +
        "<span class='spacer'></span>" +
        "<button class='btn btn-sm' data-open='" + esc(d.path) + "'>打开</button>" +
        "<button class='btn btn-sm' data-reveal='" + esc(d.path) + "'>位置</button></div>"
      ).join("");
      bindPathActions(list);
    } catch (err) {
      list.innerHTML = "<div class='git-row'>读取失败：" + esc(err.message) + "</div>";
    }
  }

  async function handleOverviewAction(act) {
    if (!S.current) return;
    const id = S.current.id;
    if (act === "open") {
      try { await api("/api/projects/" + encodeURIComponent(id) + "/open", { method: "POST" }); }
      catch (err) { toast(err.message, "err"); }
    } else if (act === "copy") {
      try {
        await navigator.clipboard.writeText(S.current.path);
        toast("路径已复制");
      } catch (e) { toast("复制失败", "err"); }
    } else if (act === "init") {
      if (!window.confirm("对「" + S.current.title + "」执行预设初始化？将按类型生成骨架文件（覆盖同名文件）并 git init。")) return;
      try {
        await api("/api/projects/" + encodeURIComponent(id) + "/init", { method: "POST", body: { description: S.current.description, git: true } });
        toast("预设初始化完成");
        await refresh();
        openDrawer(id);
      } catch (err) { toast(err.message, "err"); }
    } else if (act === "compliance") {
      showTab("compliance");
    } else if (act === "remove") {
      if (!window.confirm("仅从 ProjectDock 移除管理（不会删除文件夹），继续？")) return;
      try {
        await api("/api/projects/" + encodeURIComponent(id), { method: "DELETE" });
        toast("已移除管理");
        closeDrawer();
        await refresh();
      } catch (err) { toast(err.message, "err"); }
    }
  }

  /* ============ 合规检查 ============ */
  async function renderCompliance() {
    if (!S.current) return;
    const panel = $("panel-compliance");
    if (!panel) return;
    if (!S.compliance) {
      panel.innerHTML = "<div class='build-log'>加载合规检查中…</div>";
      try {
        S.compliance = await api("/api/projects/" + encodeURIComponent(S.current.id) + "/compliance");
      } catch (err) {
        panel.innerHTML = "<div class='build-log'>加载失败：" + esc(err.message) + "</div>";
        return;
      }
    }
    const c = S.compliance;
    let html = "";
    html += "<div class='ver-block'><div class='ver-head'><h4>项目合规 · " + esc(c.type) + "</h4>" +
      "<button class='btn btn-sm' id='btnComplianceRefresh'>刷新</button></div>" +
      "<div class='overview-hero' style='margin-bottom:12px'>" +
      (c.compliant
        ? "<div class='ov-version ok-text'>合规 ✓</div><div class='ov-sub'>已满足「" + esc(c.type) + "」类型的必需规范</div>"
        : "<div class='ov-version warn-text'>待整改 " + (c.summary.total - c.summary.passed) + " 项</div>" +
          "<div class='ov-sub'>必需项通过 " + c.summary.passed + "/" + c.summary.total + "；建议项未完成 " + c.summary.suggestions + " 项</div>") +
      "</div>";

    html += "<div class='ver-block'><div class='ver-head'><h4>管理规范（" + esc(c.type) + "）</h4></div>" +
      "<div class='cl-entry'><div class='g-title'>必需项</div><ul>" +
      c.standard.required.map((r) => "<li>" + esc(r) + "</li>").join("") + "</ul>" +
      (c.standard.suggested.length ? "<div class='g-title' style='margin-top:6px'>建议项</div><ul>" + c.standard.suggested.map((r) => "<li>" + esc(r) + "</li>").join("") + "</ul>" : "") +
      (c.standard.dirs.length ? "<div class='g-title' style='margin-top:6px'>预设目录结构</div><div class='dirs-line'>" +
        c.standard.dirs.map((d) => "<span class='dir-chip'>" + esc(d) + "</span>").join("") + "</div>" : "") +
      "</div></div>";

    html += "<div class='ver-block'><div class='ver-head'><h4>检查结果</h4></div>";
    html += c.checks.map((ch) =>
      "<div class='cmp-row'><span class='cmp-ico " + (ch.ok ? "ok" : "no") + "'>" + (ch.ok ? "✓" : "✗") + "</span>" +
      "<span class='cmp-label'>" + esc(ch.label) + (ch.required ? "" : " <span class='sug'>建议</span>") + "</span>" +
      "<span class='spacer'></span><span class='cmp-detail'>" + esc(ch.detail) + "</span></div>"
    ).join("");
    html += "</div>";

    if (c.actions.length) {
      html += "<div class='ver-block'><div class='ver-head'><h4>一键合规修复</h4></div><div class='cmp-actions'>";
      html += c.actions.map((a) =>
        "<label class='check cmp-action'><input type='checkbox' data-key='" + esc(a.key) + "'" + (a.destructive ? "" : " checked") + ">" +
        "<span><b>" + esc(a.label) + "</b>" + (a.destructive ? "<span class='warn-text'> ⚠ 需确认（移动文件）</span>" : "") +
        "<div class='cmp-act-detail'>" + esc(a.detail) + "</div></span></label>"
      ).join("");
      html += "<div class='cmp-note'>本工具不会删除任何文件；归档动作为移动文件，默认不勾选，勾选后仍需确认。若需删除内容，请通过 AI 助手或手动操作。</div>";
      html += "<div class='action-row'><button class='btn btn-sm btn-primary' id='btnComplianceFix'>执行已勾选修复</button></div>";
      html += "<div id='cmpLogBox'></div>";
      html += "</div>";
    }

    panel.innerHTML = html;
    const ref = $("btnComplianceRefresh");
    if (ref) ref.addEventListener("click", () => { S.compliance = null; renderCompliance(); });
    const fix = $("btnComplianceFix");
    if (fix) fix.addEventListener("click", runComplianceFix);
  }

  async function runComplianceFix() {
    if (!S.current || !S.compliance) return;
    const panel = $("panel-compliance");
    const keys = Array.from(panel.querySelectorAll("input[data-key]:checked")).map((el) => el.dataset.key);
    if (!keys.length) { toast("请先勾选要执行的修复动作", "err"); return; }
    const destructive = keys.filter((k) => { const a = S.compliance.actions.find((x) => x.key === k); return a && a.destructive; });
    if (destructive.length && !window.confirm("以下动作会移动文件（不删除任何文件）：\n" + destructive.join("、") + "\n\n确认执行？")) return;
    const box = $("cmpLogBox");
    if (!box) return;
    box.innerHTML = "<div class='build-status'>执行中…</div>";
    try {
      const res = await api("/api/projects/" + encodeURIComponent(S.current.id) + "/compliance/fix", {
        method: "POST", body: { actions: keys, confirm: true },
      });
      box.innerHTML = res.results.map((r) =>
        "<div class='build-status " + (r.ok ? "ok" : "err") + "'>" + (r.ok ? "✓ " : "✗ ") + esc(r.message || r.key) + "</div>"
      ).join("");
      S.compliance = null;
      await renderCompliance();
      await refresh();
    } catch (err) {
      box.innerHTML = "<div class='build-status err'>执行失败：" + esc(err.message) + "</div>";
    }
  }

  /* ============ 版本与构建 ============ */
  function renderVersions() {
    if (!S.current) return;
    const versions = S.versions || { version: null, changelog: [], artifacts: { versions: [], dist: [] }, has_versions_dir: false, has_dist_dir: false };
    const id = S.current.id;
    let html = "";
    html += "<div style='display:flex;justify-content:flex-end;margin-bottom:12px'><button class='btn btn-primary btn-sm' id='btnReleaseWizard'>发布向导</button></div>";
    html += "<div class='ver-block'><div class='ver-head'><h4>当前版本</h4></div>" +
      "<div class='overview-hero' style='margin-bottom:0'>" +
        (versions.version ? "<div class='ov-version'>v" + esc(versions.version) + "</div>" : "<div class='ov-sub'>项目根目录没有 VERSION 文件</div>") +
      "</div></div>";

    html += "<div class='ver-block'><div class='ver-head'><h4>更新日志</h4></div>";
    if (versions.changelog.length) {
      html += "<div class='changelog'>" + versions.changelog.map((e) =>
        "<div class='cl-entry'><h5>" + esc(e.version) + "</h5>" +
        (e.date ? "<div class='cl-date'>" + esc(e.date) + "</div>" : "") +
        (e.groups || []).map((g) =>
          "<div class='cl-group'><div class='g-title'>" + esc(g.title) + "</div><ul>" +
          (g.items || []).map((it) => "<li>" + esc(it) + "</li>").join("") + "</ul></div>"
        ).join("") + "</div>"
      ).join("") + "</div>";
    } else {
      html += "<div class='build-log'>没有找到 CHANGELOG.md</div>";
    }
    html += "</div>";

    const artifacts = versions.artifacts || { versions: [], dist: [], latest: [] };
    const latest = artifacts.latest || [];
    html += "<div class='ver-block'><div class='ver-head'><h4>构建产物</h4></div>";
    if (!latest.length && !artifacts.versions.length && !artifacts.dist.length) {
      html += "<div class='build-log'>没有发现 versions/ 或 dist/ 构建产物</div>";
    } else {
      if (latest.length) {
        html += "<div class='ver-head latest-head'><h4>最新构建</h4><span class='latest-note'>按修改时间排序（版本目录 + 根 dist）</span></div>";
        if (artifacts.root_dist_newer) {
          html += "<div class='note-warn'>⚠ 根目录 dist/ 存在比已归档版本更新的构建（未归档）</div>";
        }
        html += latest.map((f) =>
          "<div class='artifact'><span class='a-name'>" + esc(f.name) + "</span>" +
          (f.source === "dist" ? "<span class='src-badge unarchived'>未归档</span>" : "<span class='src-badge archived'>" + esc(f.version || "") + "</span>") +
          "<span class='a-size'>" + fmtSize(f.size) + "</span><span class='spacer'></span>" +
          "<button class='btn btn-sm' data-open='" + esc(f.path) + "'>打开</button>" +
          "<button class='btn btn-sm' data-reveal='" + esc(f.path) + "'>位置</button>" +
          "<button class='btn btn-sm' data-copy='" + esc(f.path) + "'>复制</button></div>"
        ).join("");
      }
      artifacts.versions.forEach((v) => {
        html += "<div class='cl-entry'><h5>" + esc(v.name) + (v.has_src ? " · 含源码快照" : "") + "</h5>" +
          "<div class='artifact'><span class='a-name'>版本目录</span><span class='spacer'></span>" +
          "<button class='btn btn-sm' data-open='" + esc(v.path) + "'>打开文件夹</button>" +
          "<button class='btn btn-sm' data-reveal='" + esc(v.path) + "'>位置</button></div>";
        if (v.artifacts.length) {
          html += v.artifacts.map((f) =>
            "<div class='artifact'><span class='a-name'>" + esc(f.name) + "</span><span class='a-size'>" + fmtSize(f.size) + "</span>" +
            "<span class='spacer'></span>" +
            "<button class='btn btn-sm' data-open='" + esc(f.path) + "'>打开</button>" +
            "<button class='btn btn-sm' data-reveal='" + esc(f.path) + "'>位置</button>" +
            "<button class='btn btn-sm' data-copy='" + esc(f.path) + "'>复制</button></div>"
          ).join("");
        } else {
          html += "<div class='build-log' style='margin-top:6px'>（无 dist 产物）</div>";
        }
        html += "</div>";
      });
      if (artifacts.dist.length) {
        html += "<div class='ver-head latest-head'><h4>未归档构建（项目根目录 dist/）</h4>" +
          "<button class='btn btn-sm' id='btnGoCompliance'>去合规归档</button></div>";
        html += artifacts.dist.map((f) =>
          "<div class='artifact'><span class='a-name'>" + esc(f.name) + "</span><span class='a-size'>" + fmtSize(f.size) + "</span>" +
          "<span class='spacer'></span>" +
          "<button class='btn btn-sm' data-open='" + esc(f.path) + "'>打开</button>" +
          "<button class='btn btn-sm' data-reveal='" + esc(f.path) + "'>位置</button>" +
          "<button class='btn btn-sm' data-copy='" + esc(f.path) + "'>复制</button></div>"
        ).join("");
      }
    }
    html += "</div>";

    html += "<div class='ver-block'><div class='ver-head'><h4>构建脚本</h4></div>";
    if (!S.builds.length) {
      html += "<div class='build-log'>没有发现构建脚本（build*.py / 打包.bat）</div>";
    } else {
      html += S.builds.map((b) =>
        "<div class='artifact'><span class='a-name'>" + esc(b.name) + "</span><span class='spacer'></span>" +
        "<button class='btn btn-sm btn-primary' data-build='" + esc(b.name) + "'>运行构建</button></div>"
      ).join("");
    }
    html += "<div id='buildLogBox'></div></div>";

    const panel = $("panel-versions");
    panel.innerHTML = html;
    bindPathActions(panel);
    const goComp = $("btnGoCompliance");
    if (goComp) goComp.addEventListener("click", () => showTab("compliance"));
    panel.querySelectorAll("[data-copy]").forEach((btn) => {
      btn.addEventListener("click", () => {
        navigator.clipboard.writeText(btn.dataset.copy);
        toast("已复制：" + btn.dataset.copy);
      });
    });
    panel.querySelectorAll("[data-build]").forEach((btn) => {
      btn.addEventListener("click", () => runBuild(btn.dataset.build));
    });
    const wizard = $("btnReleaseWizard");
    if (wizard) wizard.addEventListener("click", openReleaseModal);
  }

  async function runBuild(script) {
    if (!S.current) return;
    const box = $("buildLogBox");
    box.innerHTML = "<div class='build-log'></div><div class='build-status'>构建中…</div>";
    const log = box.querySelector(".build-log");
    const status = box.querySelector(".build-status");
    let jobId = null;
    try {
      const res = await api("/api/projects/" + encodeURIComponent(S.current.id) + "/build", {
        method: "POST", body: { script: script },
      });
      jobId = res.job_id;
    } catch (err) {
      log.textContent += "\n" + err.message;
      status.textContent = "启动失败";
      status.className = "build-status err";
      return;
    }
    const scrollLog = () => { box.scrollTop = box.scrollHeight; };
    streamEvents("/api/jobs/" + jobId + "/stream", (data) => {
      if (data.type === "line") { log.textContent += data.text + "\n"; scrollLog(); }
      if (data.type === "end") {
        status.textContent = data.status === "done" ? "构建完成 ✓" : "构建失败：" + (data.error || "");
        status.className = "build-status " + (data.status === "done" ? "ok" : "err");
      }
    }, (err) => {
      if (err && !status.textContent) { status.textContent = "连接中断"; status.className = "build-status err"; }
    });
  }

  /* ============ 发布向导 ============ */
  function bumpVersion(v, part) {
    const m = String(v || "").replace(/^v/, "").match(/^(\d+)\.(\d+)\.(\d+)/);
    if (!m) return "0.1.0";
    let a = parseInt(m[1], 10), b = parseInt(m[2], 10), c = parseInt(m[3], 10);
    if (part === "major") { a += 1; b = 0; c = 0; }
    else if (part === "minor") { b += 1; c = 0; }
    else { c += 1; }
    return a + "." + b + "." + c;
  }

  function openReleaseModal() {
    const form = $("releaseForm");
    const current = S.current.version || "0.1.0";
    form.elements.current.value = current;
    form.elements.version.value = bumpVersion(current, "patch");
    form.elements.changelog.value = "";
    form.elements.push.checked = true;
    const sel = form.elements.build;
    sel.innerHTML = "<option value=''>不构建</option>" + S.builds.map((b) => "<option value='" + esc(b.name) + "'>" + esc(b.name) + "</option>").join("");
    $("releaseLogBox").innerHTML = "";
    openModal("release");
  }

  async function startRelease(ev) {
    ev.preventDefault();
    const form = ev.target;
    const body = {
      version: form.elements.version.value.trim(),
      changelog: form.elements.changelog.value.trim(),
      build_script: form.elements.build.value || null,
      push: form.elements.push.checked,
    };
    const box = $("releaseLogBox");
    box.innerHTML = "<div class='build-log'></div><div class='build-status'>发布中…</div>";
    const log = box.querySelector(".build-log");
    const status = box.querySelector(".build-status");
    form.querySelectorAll("input, select, textarea, button").forEach((el) => { el.disabled = true; });
    let jobId;
    try {
      const res = await api("/api/projects/" + encodeURIComponent(S.current.id) + "/release", { method: "POST", body: body });
      jobId = res.job_id;
    } catch (err) {
      status.textContent = "启动失败：" + err.message;
      status.className = "build-status err";
      form.querySelectorAll("input, select, textarea, button").forEach((el) => { el.disabled = false; });
      return;
    }
    streamEvents("/api/jobs/" + jobId + "/stream", (data) => {
      if (data.type === "line") { log.textContent += data.text + "\n"; box.scrollTop = box.scrollHeight; }
      if (data.type === "end") {
        status.textContent = data.status === "done" ? "发布完成 ✓" : "发布失败：" + (data.error || "");
        status.className = "build-status " + (data.status === "done" ? "ok" : "err");
        form.querySelectorAll("input, select, textarea, button").forEach((el) => { el.disabled = false; });
      }
    }, () => {
      form.querySelectorAll("input, select, textarea, button").forEach((el) => { el.disabled = false; });
    });
  }

  /* ============ AI 聊天 ============ */
  function fillAgentSelect() {
    const sel = $("agentSelect");
    sel.innerHTML = "";
    S.agents.forEach((a) => {
      const opt = document.createElement("option");
      opt.value = a.name;
      opt.textContent = a.label;
      sel.appendChild(opt);
    });
    if (S.settings.agent) sel.value = S.settings.agent;
  }

  function appendChatMessage(kind, text) {
    const wrap = $("chatMsgs");
    const el = document.createElement("div");
    el.className = "msg " + kind;
    el.textContent = text;
    wrap.appendChild(el);
    wrap.scrollTop = wrap.scrollHeight;
    return el;
  }

  async function sendChat() {
    if (S.chatRunning || !S.current) return;
    const input = $("chatInput");
    const prompt = input.value.trim();
    if (!prompt) return;
    input.value = "";
    appendChatMessage("user", prompt);
    const agent = $("agentSelect").value;
    const aiEl = appendChatMessage("ai", "");
    aiEl.classList.add("running");
    S.chatRunning = true;
    $("chatSend").disabled = true;
    $("chatInput").disabled = true;
    try {
      const res = await api("/api/agent/run", {
        method: "POST",
        body: { project_id: S.current.id, prompt: prompt, agent: agent },
      });
      aiEl.textContent = "";
      streamEvents("/api/jobs/" + res.job_id + "/stream", (data) => {
        if (data.type === "line") {
          aiEl.textContent = (aiEl.textContent ? aiEl.textContent + "\n" : "") + data.text;
          aiEl.classList.remove("running");
          $("chatMsgs").scrollTop = $("chatMsgs").scrollHeight;
        }
        if (data.type === "end") {
          aiEl.classList.remove("running");
          if (!aiEl.textContent && data.error) aiEl.textContent = "（任务失败：" + data.error + "）";
          S.chatRunning = false;
          $("chatSend").disabled = false;
          $("chatInput").disabled = false;
        }
      }, () => {
        if (!aiEl.textContent) aiEl.textContent = "（任务已结束，无输出）";
        aiEl.classList.remove("running");
        S.chatRunning = false;
        $("chatSend").disabled = false;
        $("chatInput").disabled = false;
      });
    } catch (err) {
      aiEl.textContent = "（启动失败：" + err.message + "）";
      aiEl.classList.remove("running");
      S.chatRunning = false;
      $("chatSend").disabled = false;
      $("chatInput").disabled = false;
    }
  }

  /* ============ 模态 ============ */
  function fillTypeSelects() {
    const opts = S.presets.map((p) => "<option value='" + esc(p.type) + "'>" + esc(p.label) + "</option>").join("");
    $("newType").innerHTML = opts;
    $("importType").innerHTML = opts;
    $("newType").onchange = updatePresetHint;
    updatePresetHint();
  }

  function updatePresetHint() {
    const p = S.presets.find((x) => x.type === $("newType").value);
    if (!p) return;
    $("presetHint").textContent = p.description + "（文件：" + (p.files.length ? p.files.join("、") : "目录结构") + (p.git ? "，含 git init" : "，不初始化 git") + "）";
  }

  function openModal(name) {
    const el = $(name + "Backdrop");
    el.hidden = false;
    requestAnimationFrame(() => {
      Spring.popIn(el.querySelector(".modal"));
      el.style.opacity = "1";
    });
  }

  function closeModal(name) {
    const el = $(name + "Backdrop");
    Spring.popOut(el.querySelector(".modal"), { onComplete: () => { el.hidden = true; } });
    el.style.opacity = "0";
  }

  /* ============ 设置 ============ */
  function openSettings() {
    const form = $("settingsForm");
    form.elements.root.value = S.settings.root;
    form.elements.agent.value = S.settings.agent;
    form.elements.theme.value = S.settings.theme;
    form.elements.github_auto.checked = !!S.settings.github_auto;
    form.elements.github_visibility.value = S.settings.github_visibility || "private";
    form.elements.backup.checked = !!S.settings.backup;
    openModal("settings");
  }

  async function saveSettings(ev) {
    ev.preventDefault();
    const form = ev.target;
    try {
      S.settings = await api("/api/settings", {
        method: "PUT",
        body: {
          root: form.elements.root.value,
          agent: form.elements.agent.value,
          theme: form.elements.theme.value,
          github_auto: form.elements.github_auto.checked,
          github_visibility: form.elements.github_visibility.value,
          backup: form.elements.backup.checked,
        },
      });
      applyTheme(S.settings.theme);
      closeModal("settings");
      toast("设置已保存");
      await refresh();
    } catch (err) { toast(err.message, "err"); }
  }

  /* ============ 自定义类型 ============ */
  async function openTypesModal() {
    S.types = await api("/api/types");
    renderTypesList();
    openModal("types");
  }

  function renderTypesList() {
    const custom = S.types.filter((t) => t.custom);
    $("customTypesList").innerHTML = custom.length
      ? custom.map((t) =>
        "<div class='artifact'><span class='a-name'>" + esc(t.label) + "（" + esc(t.name) + "）</span>" +
        "<span class='a-size'>" + Object.keys(t.files).length + " 个文件 / " + (t.dirs.length ? esc(t.dirs.join("、")) : "无目录") + "</span>" +
        "<span class='spacer'></span><button class='btn btn-sm btn-danger' data-del='" + esc(t.name) + "'>删除</button></div>"
      ).join("")
      : "<div class='build-log'>暂无自定义类型。内置类型：软件 / 网站 / 游戏 / PPT / 文稿 / 脚本 / 其他</div>";
    $("customTypesList").querySelectorAll("[data-del]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        if (!window.confirm("删除自定义类型「" + btn.dataset.del + "」？已创建的项目不受影响。")) return;
        try {
          await api("/api/types/" + encodeURIComponent(btn.dataset.del), { method: "DELETE" });
          toast("已删除类型");
          await refreshPresets();
          openTypesModal();
        } catch (err) { toast(err.message, "err"); }
      });
    });
  }

  function parseFilesText(text) {
    const files = {};
    String(text).split(/^={3,}\s*$/m).forEach((block) => {
      const lines = block.split("\n");
      const name = lines.shift().trim();
      if (name) files[name] = lines.join("\n");
    });
    return files;
  }

  async function addType(ev) {
    ev.preventDefault();
    const form = ev.target;
    const dirs = form.elements.dirs.value.split(/[,，]/).map((s) => s.trim()).filter(Boolean);
    const body = {
      name: form.elements.name.value.trim(),
      label: form.elements.label.value.trim() || undefined,
      description: form.elements.description.value.trim(),
      dirs: dirs,
      files: parseFilesText(form.elements.files.value),
      git: form.elements.git.checked,
    };
    if (!body.name) return toast("请填写类型名称", "err");
    try {
      await api("/api/types", { method: "POST", body: body });
      toast("已添加类型 " + body.name);
      form.reset();
      form.elements.git.checked = true;
      await refreshPresets();
      openTypesModal();
    } catch (err) { toast(err.message, "err"); }
  }

  async function refreshPresets() {
    S.presets = await api("/api/presets");
    fillTypeSelects();
    renderSidebar();
  }

  /* ============ 新建 / 导入 ============ */
  async function createProject(ev) {
    ev.preventDefault();
    const form = ev.target;
    const body = {
      name: form.elements.name.value.trim(),
      type: form.elements.type.value,
      description: form.elements.description.value.trim(),
      preset: form.elements.preset.checked,
      github: form.elements.github.checked,
    };
    if (!body.name) return toast("请填写项目名称", "err");
    try {
      const created = await api("/api/projects", { method: "POST", body: body });
      closeModal("new");
      toast("已创建 " + created.name);
      form.reset();
      form.elements.preset.checked = true;
      form.elements.github.checked = !!S.settings.github_auto;
      await refresh();
      openDrawer(created.id);
      if (created.github && !created.github.ok) toast("GitHub：" + created.github.message, "err");
      else if (created.github) toast("GitHub：" + created.github.message);
    } catch (err) { toast(err.message, "err"); }
  }

  async function importProject(ev) {
    ev.preventDefault();
    const form = ev.target;
    const body = {
      path: form.elements.path.value.trim(),
      type: form.elements.type.value,
      description: form.elements.description.value.trim(),
    };
    try {
      const imported = await api("/api/projects/import", { method: "POST", body: body });
      closeModal("import");
      toast("已导入 " + imported.name);
      form.reset();
      await refresh();
    } catch (err) { toast(err.message, "err"); }
  }

  /* ============ 工具 ============ */
  async function refresh() {
    S.projects = await api("/api/projects");
    renderSidebar();
    renderGrid();
  }

  function toast(msg, kind) {
    const el = document.createElement("div");
    el.className = "toast " + (kind || "ok");
    el.textContent = msg;
    $("toasts").appendChild(el);
    Spring.enter(el, { distance: 14, stiffness: 240, damping: 24 });
    setTimeout(() => {
      Spring.popOut(el, { onComplete: () => el.remove() });
    }, 2400);
  }

  /* ============ 事件 ============ */
  function bindEvents() {
    $("btnNewProject").addEventListener("click", () => {
      $("newForm").elements.github.checked = !!S.settings.github_auto;
      openModal("new");
    });
    $("btnImport").addEventListener("click", () => openModal("import"));
    $("btnSettings").addEventListener("click", openSettings);
    $("btnManageTypes").addEventListener("click", openTypesModal);
    $("searchInput").addEventListener("input", (e) => { S.search = e.target.value; renderGrid(); });
    $("btnDrawerClose").addEventListener("click", closeDrawer);
    $("btnOpenFolder").addEventListener("click", () => handleOverviewAction("open"));
    $("btnCopyPath").addEventListener("click", () => handleOverviewAction("copy"));
    $("backdrop").addEventListener("click", closeDrawer);
    document.querySelectorAll(".tab").forEach((el) => el.addEventListener("click", () => showTab(el.dataset.tab)));
    document.querySelectorAll("[data-close]").forEach((el) => el.addEventListener("click", () => closeModal(el.dataset.close)));
    $("newForm").addEventListener("submit", createProject);
    $("importForm").addEventListener("submit", importProject);
    $("settingsForm").addEventListener("submit", saveSettings);
    $("typesForm").addEventListener("submit", addType);
    $("releaseForm").addEventListener("submit", startRelease);
    document.querySelectorAll("[data-bump]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const form = $("releaseForm");
        form.elements.version.value = bumpVersion(form.elements.current.value, btn.dataset.bump);
      });
    });
    $("chatSend").addEventListener("click", sendChat);
    $("chatInput").addEventListener("keydown", (e) => { if (e.key === "Enter") sendChat(); });
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
      if (S.settings && S.settings.theme === "system") applyTheme("system");
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        if (!$("drawer").hidden) closeDrawer();
        ["new", "import", "settings", "types", "release"].forEach((n) => { if (!$(n + "Backdrop").hidden) closeModal(n); });
      }
    });
  }

  init().catch((err) => toast("初始化失败：" + err.message, "err"));
})();
