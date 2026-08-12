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
    view: "grid",
    console: null,
    drawerSeq: 0,
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
    const [settings, presets, agents, projects, health, types] = await Promise.all([
      api("/api/settings"), api("/api/presets"), api("/api/agents"), api("/api/projects"),
      api("/api/health"), api("/api/types"),
    ]);
    S.settings = settings;
    S.presets = presets;
    S.agents = agents;
    S.projects = projects;
    S.types = types;
    S.appVersion = health.version;
    $("appVersion").textContent = "v" + health.version;
    checkUpdateSilent();
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
    if (S.view !== "grid") showGrid();
    renderGrid();
  }

  /* ============ 抽屉 ============ */
  async function openDrawer(id) {
    const proj = S.projects.find((p) => p.id === id);
    if (!proj) return;
    const seq = ++S.drawerSeq;
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
    renderDrawerTabs(proj.type);
    showTab("overview");
    renderOverview(proj);
    showDrawer();
    loadVersionsData();
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

  function tabsFor(type) {
    const t = S.types.find((x) => x.name === type);
    if (t && Array.isArray(t.tabs) && t.tabs.length) return t.tabs;
    return ["overview", "versions", "compliance", "ai", "ailog"];
  }

  function renderDrawerTabs(type) {
    const wrap = $("drawerTabs");
    const t = S.types.find((x) => x.name === type) || { tab_labels: {} };
    wrap.innerHTML = tabsFor(type).map((key) =>
      "<button class='tab' data-tab='" + esc(key) + "'>" + esc(t.tab_labels[key] || key) + "</button>"
    ).join("");
  }

  function showTab(tab) {
    S.currentTab = tab;
    document.querySelectorAll(".tab").forEach((el) => el.classList.toggle("active", el.dataset.tab === tab));
    document.querySelectorAll(".panel").forEach((el) => el.classList.remove("active", "panel-in"));
    const panel = $("panel-" + tab);
    panel.classList.add("active");
    void panel.offsetWidth;
    panel.classList.add("panel-in");
    if (tab === "versions") {
      if (S.versions === null && !S.versionsLoading) loadVersionsData();
      renderVersions();
    }
    if (tab === "compliance") renderCompliance();
    if (tab === "docs") renderDocs();
    if (tab === "ailog") renderAILog();
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
      "<div class='git-panel'><div class='git-head'><h4>备份管理</h4><button class='btn btn-sm' id='btnBackupNow'>立即备份</button></div><div class='git-body' id='backupList'>加载中…</div></div>" +
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
    const backupBtn = $("btnBackupNow");
    if (backupBtn) backupBtn.addEventListener("click", createBackupNow);
    loadGitStatus(proj.id);
    loadDocuments(proj.id);
    loadBackups(proj.id);
  }

  /* 备份管理 */
  async function loadBackups(id) {
    const body = $("backupList");
    if (!body) return;
    const seq = S.drawerSeq;
    body.innerHTML = "加载中…";
    try {
      const list = await api("/api/projects/" + encodeURIComponent(id) + "/backups");
      if (seq !== S.drawerSeq || !S.current || S.current.id !== id) return;
      if (!list.length) {
        body.innerHTML = "<div class='git-row'><span>暂无备份（AI 任务/发布前会自动创建快照到 versions/backups/）</span></div>";
        return;
      }
      body.innerHTML = list.map((b) =>
        "<div class='artifact' style='margin:4px 0'><span class='a-name'>" + esc(b.name) + "</span>" +
        "<span class='a-size'>" + fmtSize(b.size) + "</span><span class='spacer'></span>" +
        "<button class='btn btn-sm' data-restore='" + esc(b.name) + "'>恢复</button>" +
        "<button class='btn btn-sm btn-danger' data-delbackup='" + esc(b.name) + "'>删除</button></div>"
      ).join("");
      body.querySelectorAll("[data-restore]").forEach((btn) => btn.addEventListener("click", () => restoreBackupNow(btn.dataset.restore)));
      body.querySelectorAll("[data-delbackup]").forEach((btn) => btn.addEventListener("click", () => deleteBackupNow(btn.dataset.delbackup)));
    } catch (err) {
      body.innerHTML = "<div class='git-row'>读取失败：" + esc(err.message) + "</div>";
    }
  }

  async function createBackupNow() {
    if (!S.current) return;
    const btn = $("btnBackupNow");
    if (btn) btn.disabled = true;
    try {
      const r = await api("/api/projects/" + encodeURIComponent(S.current.id) + "/backups", { method: "POST", body: {} });
      toast("已创建备份 " + r.name);
      loadBackups(S.current.id);
    } catch (err) { toast(err.message, "err"); }
    finally { if (btn) btn.disabled = false; }
  }

  async function restoreBackupNow(name) {
    if (!S.current) return;
    if (!window.confirm("从备份「" + name + "」恢复将覆盖当前项目文件（会自动先留一个安全快照）。确定继续？")) return;
    try {
      const r = await api("/api/projects/" + encodeURIComponent(S.current.id) + "/backups/restore", { method: "POST", body: { name: name, confirm: true } });
      toast("已恢复 " + r.restored + " 个文件" + (r.skipped.length ? "（跳过 " + r.skipped.length + " 项）" : ""));
      loadBackups(S.current.id);
    } catch (err) { toast(err.message, "err"); }
  }

  async function deleteBackupNow(name) {
    if (!S.current) return;
    if (!window.confirm("删除备份「" + name + "」？此操作不可恢复。")) return;
    try {
      await api("/api/projects/" + encodeURIComponent(S.current.id) + "/backups/" + encodeURIComponent(name), { method: "DELETE" });
      toast("已删除备份");
      loadBackups(S.current.id);
    } catch (err) { toast(err.message, "err"); }
  }

  async function loadGitStatus(id) {
    const body = $("gitBody");
    if (!body) return;
    const seq = S.drawerSeq;
    body.innerHTML = "加载中…";
    try {
      const st = await api("/api/projects/" + encodeURIComponent(id) + "/git-status");
      if (seq !== S.drawerSeq || !S.current || S.current.id !== id) return;
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
    const seq = S.drawerSeq;
    list.innerHTML = "加载中…";
    try {
      const docs = await api("/api/projects/" + encodeURIComponent(id) + "/documents");
      if (seq !== S.drawerSeq || !S.current || S.current.id !== id) return;
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

  /* ============ 文稿版本 / AI 日志 / 总控台 ============ */
  async function renderDocs() {
    if (!S.current) return;
    const seq = S.drawerSeq;
    const pid = S.current.id;
    const panel = $("panel-docs");
    if (!panel) return;
    panel.innerHTML = "<div class='build-log'>加载文稿…</div>";
    try {
      const docs = await api("/api/projects/" + encodeURIComponent(pid) + "/documents?scope=all");
      if (seq !== S.drawerSeq || !S.current || S.current.id !== pid) return;
      if (!docs.length) {
        panel.innerHTML = "<div class='build-log'>未找到文档（支持 docx/doc/pdf/pptx/xlsx/md/txt）</div>";
        return;
      }
      const groups = {};
      docs.forEach((d) => { (groups[d.group] = groups[d.group] || []).push(d); });
      let html = "";
      Object.keys(groups).forEach((g) => {
        html += "<div class='ver-block'><div class='ver-head'><h4>" + esc(g) + " <span class='latest-note'>" + groups[g].length + " 个</span></h4></div>";
        html += groups[g].map((d) =>
          "<div class='artifact'><span class='a-name'>" + esc(d.name) + "</span>" +
          "<span class='a-size'>" + fmtSize(d.size) + "</span><span class='spacer'></span>" +
          "<button class='btn btn-sm' data-open='" + esc(d.path) + "'>打开</button>" +
          "<button class='btn btn-sm' data-reveal='" + esc(d.path) + "'>位置</button></div>"
        ).join("");
        html += "</div>";
      });
      panel.innerHTML = html;
      bindPathActions(panel);
    } catch (err) {
      panel.innerHTML = "<div class='build-log'>加载失败：" + esc(err.message) + "</div>";
    }
  }

  async function renderAILog() {
    if (!S.current) return;
    const seq = S.drawerSeq;
    const pid = S.current.id;
    const panel = $("panel-ailog");
    if (!panel) return;
    panel.innerHTML = "<div class='ver-block'><div class='ver-head'><h4>AI 操作日志</h4><button class='btn btn-sm' id='btnAILogRefresh'>刷新</button></div><div class='build-log'>加载中…</div></div>";
    try {
      const logs = await api("/api/projects/" + encodeURIComponent(pid) + "/ai-logs");
      if (seq !== S.drawerSeq || !S.current || S.current.id !== pid) return;
      const box = panel.querySelector(".build-log");
      if (!logs.length) {
        box.innerHTML = "（暂无 AI 操作日志）";
      } else {
        box.className = "ai-timeline";
        box.innerHTML = "";
        logs.forEach((e) => {
          const cls = e.result === "done" ? "ok" : (e.result === "failed" ? "err" : "run");
          box.innerHTML +=
            "<div class='ai-entry'><div class='ai-head'><span class='git-dot " + (e.result === "done" ? "clean" : e.result === "failed" ? "dirty" : e.result === "run" ? "run" : "no") + "'></span>" +
            "<span class='ai-agent'>" + esc(e.agent || "?") + "</span>" +
            "<span class='ai-ts'>" + esc((e.ts || "").replace("T", " ").slice(0, 19)) + "</span>" +
            "<span class='spacer'></span><span class='ai-result " + cls + "'>" + esc(e.result) + "</span></div>" +
            "<div class='ai-action'>" + esc(e.action || "") + "</div>" +
            (e.summary ? "<div class='ai-summary'>" + esc(e.summary) + "</div>" : "") +
            ((e.details || e.backup || Object.keys(e.git || {}).length) ?
              "<details class='ai-detail'><summary>详情</summary><div>" +
              (e.details ? "<div>" + esc(e.details) + "</div>" : "") +
              (e.backup ? "<div class='mono'>备份：" + esc(e.backup) + "</div>" : "") +
              (e.git && e.git.head ? "<div class='mono'>Git：" + esc(e.git.head) + "，变更 " + esc(e.git.changed || 0) + " 项</div>" : "") +
              "</div></details>" : "");
        });
      }
      const ref = $("btnAILogRefresh");
      if (ref) ref.addEventListener("click", renderAILog);
    } catch (err) {
      const box = panel.querySelector(".build-log");
      if (box) box.innerHTML = "加载失败：" + esc(err.message);
    }
  }

  function showConsole() {
    S.view = "console";
    document.querySelectorAll(".nav-item").forEach((el) => el.classList.remove("active"));
    $("btnConsole").classList.add("active");
    $("grid").hidden = true;
    $("empty").hidden = true;
    $("console").hidden = false;
    renderConsole();
  }

  function showGrid() {
    S.view = "grid";
    document.querySelectorAll(".nav-item").forEach((el) => el.classList.remove("active"));
    document.querySelectorAll(".nav-item[data-filter]").forEach((el) => el.classList.toggle("active", el.dataset.filter === S.filter));
    $("console").hidden = true;
    $("grid").hidden = false;
    renderGrid();
  }

  async function renderConsole() {
    const box = $("console");
    if (!box) return;
    box.innerHTML = "<div class='build-log'>加载总控台…</div>";
    try {
      const data = await api("/api/console");
      S.console = data;
      let html = "<div class='console-head'><h3>总控台</h3><button class='btn btn-sm' id='btnConsoleRefresh'>刷新</button></div>";
      html += "<div class='console-grid'>";

      html += "<div class='c-card'><div class='ver-head'><h4>运行中任务</h4><span class='latest-note'>" + data.running_jobs.length + " 个</span></div>";
      html += data.running_jobs.length
        ? data.running_jobs.map((j) => "<div class='ai-entry'><span class='git-dot run'></span><span>" + esc(j.label) + "</span></div>").join("")
        : "<div class='git-row'><span>当前没有运行中的任务</span></div>";
      html += "</div>";

      html += "<div class='c-card c-wide'><div class='ver-head'><h4>最近 AI 操作</h4></div>";
      if (!data.activity.length) {
        html += "<div class='git-row'><span>还没有任何 AI 操作日志</span></div>";
      } else {
        html += data.activity.map((e) =>
          "<div class='ai-entry'><span class='git-dot " + (e.result === "done" ? "clean" : e.result === "failed" ? "dirty" : e.result === "run" ? "run" : "no") + "'></span>" +
          "<span class='ai-ts'>" + esc((e.ts || "").replace("T", " ").slice(0, 16)) + "</span>" +
          "<span class='ai-agent'>" + esc(e.project || "") + "</span>" +
          "<span class='ai-action' title='" + esc(e.action || "") + "'>" + esc(e.action || "") + "</span>" +
          "<span class='spacer'></span><span class='ai-result " + (e.result === "done" ? "ok" : e.result === "failed" ? "err" : "run") + "'>" + esc(e.result) + "</span></div>"
        ).join("");
      }
      html += "</div>";

      html += "<div class='c-card c-wide'><div class='ver-head'><h4>项目状态</h4><span class='latest-note'>" + data.projects.length + " 个</span></div>";
      html += "<div class='proj-table'>" + data.projects.map((pj) =>
        "<div class='proj-row' data-pid='" + esc(pj.id) + "'><span class='badge " + esc(pj.type) + "'>" + esc(pj.type) + "</span>" +
        "<span class='proj-title'>" + esc(pj.title) + "</span>" +
        (pj.version ? "<span class='proj-ver'>v" + esc(pj.version) + "</span>" : "<span class='proj-ver dim'>—</span>") +
        (pj.compliant ? "<span class='src-badge archived'>合规</span>" : "<span class='src-badge unarchived'>待整改</span>") +
        (pj.has_git ? "<span class='git-ok'>git</span>" : "<span class='git-no'>git</span>") + "</div>"
      ).join("") + "</div>";
      html += "</div>";

      html += "<div class='c-card'><div class='ver-head'><h4>批量下指令</h4></div>";
      html += "<div class='batch-projects'>" + data.projects.map((pj) =>
        "<label class='check'><input type='checkbox' class='batch-pick' value='" + esc(pj.id) + "'><span>" + esc(pj.title) + "</span></label>"
      ).join("") + "</div>";
      html += "<textarea id='batchPrompt' class='batch-prompt' rows='3' placeholder='对选中的项目下达统一指令…'></textarea>";
      html += "<div class='action-row'><button class='btn btn-sm btn-primary' id='btnBatchRun'>向选中项目下达</button></div>";
      html += "<div id='batchLog'></div>";
      html += "</div>";

      html += "</div>";
      box.innerHTML = html;
      const ref = $("btnConsoleRefresh");
      if (ref) ref.addEventListener("click", renderConsole);
      box.querySelectorAll(".proj-row").forEach((row) => {
        row.addEventListener("click", () => openDrawer(row.dataset.pid));
      });
      const batch = $("btnBatchRun");
      if (batch) batch.addEventListener("click", runBatch);
    } catch (err) {
      box.innerHTML = "<div class='build-log'>加载失败：" + esc(err.message) + "</div>";
    }
  }

  async function runBatch() {
    const ids = Array.from(document.querySelectorAll(".batch-pick:checked")).map((el) => el.value);
    if (!ids.length) { toast("请先选择至少一个项目", "err"); return; }
    const prompt = $("batchPrompt").value.trim();
    if (!prompt) { toast("请输入指令", "err"); return; }
    const log = $("batchLog");
    if (!log) return;
    log.innerHTML = "<div class='build-status'>正在启动 " + ids.length + " 个任务…</div>";
    try {
      const res = await api("/api/agent/batch", { method: "POST", body: { project_ids: ids, prompt: prompt } });
      log.innerHTML = "<div class='build-status ok'>已启动 " + res.jobs.length + " 个任务（失败 " + res.jobs.filter((j) => j.error).length + "），可到各项目「AI 日志」查看</div>";
      toast("批量任务已启动");
      setTimeout(() => renderConsole(), 3000);
    } catch (err) {
      log.innerHTML = "<div class='build-status err'>失败：" + esc(err.message) + "</div>";
    }
  }

  /* ============ 合规检查 ============ */
  async function renderCompliance() {
    if (!S.current) return;
    const seq = S.drawerSeq;
    const pid = S.current.id;
    const panel = $("panel-compliance");
    if (!panel) return;
    if (!S.compliance) {
      panel.innerHTML = "<div class='build-log'>加载合规检查中…</div>";
      try {
        S.compliance = await api("/api/projects/" + encodeURIComponent(pid) + "/compliance");
        if (seq !== S.drawerSeq || !S.current || S.current.id !== pid) return;
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
    const id = S.current.id;
    const panel = $("panel-versions");
    if (S.versions === null) {
      panel.innerHTML =
        "<div class='ver-block'><div class='ver-head'><h4>版本信息</h4></div>" +
        "<div class='build-log'>" + (S.versionsFailed ? "版本信息加载失败（" + esc(S.versionsError || "") + "），请重试。" : "正在加载版本信息…") + "</div>" +
        (S.versionsFailed ? "<button class='btn btn-sm' id='btnRetryVersions' style='margin-top:8px'>重新加载</button>" : "") +
        "</div>";
      const retry = $("btnRetryVersions");
      if (retry) retry.addEventListener("click", () => { S.versionsFailed = false; renderVersions(); loadVersionsData(); });
      return;
    }
    const versions = S.versions || { version: null, changelog: [], artifacts: { versions: [], dist: [] }, has_versions_dir: false, has_dist_dir: false };
    const verBlock = (title, inner, openDefault) =>
      "<div class='ver-block collapsible" + (openDefault ? "" : " collapsed") + "'>" +
        "<div class='ver-head' role='button' tabindex='0'><span class='caret'>▶</span><h4>" + title + "</h4></div>" +
        "<div class='ver-body'><div class='ver-body-inner'>" + inner + "</div></div>" +
      "</div>";

    let html = "";
    html += "<div style='display:flex;justify-content:flex-end;gap:8px;margin-bottom:12px'>" +
      "<button class='btn btn-sm' id='btnToggleAll'>全部展开</button>" +
      "<button class='btn btn-primary btn-sm' id='btnReleaseWizard'>发布向导</button></div>";

    html += verBlock("当前版本",
      "<div class='overview-hero' style='margin-bottom:0'>" +
        (versions.version ? "<div class='ov-version'>v" + esc(versions.version) + "</div>" : "<div class='ov-sub'>项目根目录没有 VERSION 文件</div>") +
      "</div>", true);

    let clHtml = "";
    if (versions.changelog.length) {
      clHtml = "<div class='changelog'>" + versions.changelog.map((e) =>
        "<div class='cl-entry'><h5>" + esc(e.version) + "</h5>" +
        (e.date ? "<div class='cl-date'>" + esc(e.date) + "</div>" : "") +
        (e.groups || []).map((g) =>
          "<div class='cl-group'><div class='g-title'>" + esc(g.title) + "</div><ul>" +
          (g.items || []).map((it) => "<li>" + esc(it) + "</li>").join("") + "</ul></div>"
        ).join("") + "</div>"
      ).join("") + "</div>";
    } else {
      clHtml = "<div class='build-log'>没有找到 CHANGELOG.md</div>";
    }
    html += verBlock("更新日志", clHtml, false);

    const artifacts = versions.artifacts || { versions: [], dist: [], latest: [] };
    const latest = artifacts.latest || [];
    let artHtml = "";
    if (!latest.length && !artifacts.versions.length && !artifacts.dist.length) {
      artHtml = "<div class='build-log'>没有发现 versions/ 或 dist/ 构建产物</div>";
    } else {
      if (latest.length) {
        artHtml += "<div class='ver-head latest-head'><h4>最新构建</h4><span class='latest-note'>按修改时间排序（版本目录 + 根 dist）</span></div>";
        if (artifacts.root_dist_newer) {
          artHtml += "<div class='note-warn'>⚠ 根目录 dist/installer/build 存在比已归档版本更新的构建（未归档）</div>";
        }
        artHtml += latest.map((f) =>
          "<div class='artifact'><span class='a-name'>" + esc(f.name) + "</span>" +
          (f.source === "versions" ? "<span class='src-badge archived'>" + esc(f.version || "") + "</span>" : "<span class='src-badge unarchived'>未归档</span>") +
          "<span class='a-size'>" + fmtSize(f.size) + "</span><span class='spacer'></span>" +
          "<button class='btn btn-sm' data-open='" + esc(f.path) + "'>打开</button>" +
          "<button class='btn btn-sm' data-reveal='" + esc(f.path) + "'>位置</button>" +
          "<button class='btn btn-sm' data-copy='" + esc(f.path) + "'>复制</button></div>"
        ).join("");
      }
      artifacts.versions.forEach((v) => {
        artHtml += "<div class='cl-entry'><h5>" + esc(v.name) + (v.has_src ? " · 含源码快照" : "") + "</h5>" +
          "<div class='artifact'><span class='a-name'>版本目录</span><span class='spacer'></span>" +
          "<button class='btn btn-sm' data-open='" + esc(v.path) + "'>打开文件夹</button>" +
          "<button class='btn btn-sm' data-reveal='" + esc(v.path) + "'>位置</button></div>";
        if (v.artifacts.length) {
          artHtml += v.artifacts.map((f) =>
            "<div class='artifact'><span class='a-name'>" + esc(f.name) + "</span><span class='a-size'>" + fmtSize(f.size) + "</span>" +
            "<span class='spacer'></span>" +
            "<button class='btn btn-sm' data-open='" + esc(f.path) + "'>打开</button>" +
            "<button class='btn btn-sm' data-reveal='" + esc(f.path) + "'>位置</button>" +
            "<button class='btn btn-sm' data-copy='" + esc(f.path) + "'>复制</button></div>"
          ).join("");
        } else {
          artHtml += "<div class='build-log' style='margin-top:6px'>（无 dist 产物）</div>";
        }
        artHtml += "</div>";
      });
      if (artifacts.dist.length) {
        artHtml += "<div class='ver-head latest-head'><h4>未归档构建（项目根目录 dist/installer/build）</h4>" +
          "<button class='btn btn-sm' id='btnGoCompliance'>去合规归档</button></div>";
        artHtml += artifacts.dist.map((f) =>
          "<div class='artifact'><span class='a-name'>" + esc(f.name) + "</span><span class='a-size'>" + fmtSize(f.size) + "</span>" +
          "<span class='spacer'></span>" +
          "<button class='btn btn-sm' data-open='" + esc(f.path) + "'>打开</button>" +
          "<button class='btn btn-sm' data-reveal='" + esc(f.path) + "'>位置</button>" +
          "<button class='btn btn-sm' data-copy='" + esc(f.path) + "'>复制</button></div>"
        ).join("");
      }
    }
    html += verBlock("构建产物", artHtml, false);

    let buildHtml = "";
    if (!S.builds.length) {
      buildHtml = "<div class='build-log'>没有发现构建脚本（build*.py / 打包.bat）</div>";
    } else {
      buildHtml = S.builds.map((b) =>
        "<div class='artifact'><span class='a-name'>" + esc(b.name) + "</span><span class='spacer'></span>" +
        "<button class='btn btn-sm btn-primary' data-build='" + esc(b.name) + "'>运行构建</button></div>"
      ).join("");
    }
    buildHtml += "<div id='buildLogBox'></div>";
    html += verBlock("构建脚本", buildHtml, false);

    panel.innerHTML = html;
    bindPathActions(panel);
    // 折叠/展开
    panel.querySelectorAll(".ver-block.collapsible > .ver-head").forEach((h) => {
      const toggle = () => h.parentElement.classList.toggle("collapsed");
      h.addEventListener("click", toggle);
      h.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); }
      });
    });
    const toggleAll = $("btnToggleAll");
    if (toggleAll) toggleAll.addEventListener("click", () => {
      const anyCollapsed = panel.querySelectorAll(".ver-block.collapsible.collapsed").length > 0;
      panel.querySelectorAll(".ver-block.collapsible").forEach((b) => b.classList.toggle("collapsed", !anyCollapsed));
      toggleAll.textContent = anyCollapsed ? "全部折叠" : "全部展开";
    });
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

  async function loadVersionsData() {
    if (!S.current || S.versionsLoading) return;
    S.versionsLoading = true;
    S.versionsFailed = false;
    S.versionsError = "";
    const id = S.current.id;
    const seq = S.drawerSeq;
    try {
      const [versions, builds] = await Promise.all([
        api("/api/projects/" + encodeURIComponent(id) + "/versions"),
        api("/api/projects/" + encodeURIComponent(id) + "/builds"),
      ]);
      if (seq !== S.drawerSeq || !S.current || S.current.id !== id) return;
      S.versions = versions;
      S.builds = builds;
      if (S.currentTab === "versions") renderVersions();
    } catch (err) {
      if (seq !== S.drawerSeq || !S.current || S.current.id !== id) return;
      S.versions = null;
      S.versionsFailed = true;
      S.versionsError = err.message;
      toast("加载版本信息失败：" + err.message, "err");
      if (S.currentTab === "versions") renderVersions();
    } finally {
      if (seq === S.drawerSeq) S.versionsLoading = false;
    }
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

  /* 安全 Markdown 渲染（先 HTML 转义再套格式，杜绝 XSS） */
  function inlineMd(s) {
    s = esc(s);
    s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
    s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
    s = s.replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
    s = s.replace(/~~([^~]+)~~/g, "<del>$1</del>");
    s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, function (m, txt, url) {
      const safe = String(url).replace(/["'<>]/g, "");
      return "<a href='" + safe + "' target='_blank' rel='noopener'>" + txt + "</a>";
    });
    return s;
  }

  function mdToHtml(src) {
    const lines = String(src || "").split("\n");
    let html = "";
    let inCode = false, codeBuf = [];
    const flushCode = () => {
      if (codeBuf.length) html += "<pre><code>" + esc(codeBuf.join("\n")) + "</code></pre>";
      codeBuf = [];
    };
    lines.forEach((line) => {
      const fence = line.match(/^```(\w*)\s*$/);
      if (fence) {
        if (inCode) { inCode = false; flushCode(); }
        else { flushCode(); inCode = true; }
        return;
      }
      if (inCode) { codeBuf.push(line); return; }
      const h = line.match(/^(#{1,6})\s+(.*)$/);
      if (h) { html += "<h" + h[1].length + ">" + inlineMd(h[2]) + "</h" + h[1].length + ">"; return; }
      if (/^(-{3,}|\*{3,}|_{3,})$/.test(line.trim())) { html += "<hr>"; return; }
      const li = line.match(/^\s*([-*+])\s+(.*)$/);
      if (li) { html += "<li>" + inlineMd(li[2]) + "</li>"; return; }
      const ol = line.match(/^\s*\d+[.)]\s+(.*)$/);
      if (ol) { html += "<li class='md-ol'>" + inlineMd(ol[1]) + "</li>"; return; }
      if (!line.trim()) return;
      html += "<p>" + inlineMd(line) + "</p>";
    });
    if (inCode) flushCode();
    return html;
  }

  function appendChatMessage(kind, text) {
    const wrap = $("chatMsgs");
    const el = document.createElement("div");
    if (kind === "user") {
      el.className = "msg user";
      el.textContent = text;
    } else {
      el.className = "msg ai md-mode";
      el.innerHTML =
        "<div class='agent-status' hidden><span class='st-dot'></span><span class='st-txt'></span></div>" +
        "<div class='md'></div>" +
        "<div class='msg-actions'><button class='msg-copy' title='复制这段回复'>⧉ 复制</button></div>";
      el.dataset.raw = "";
    }
    wrap.appendChild(el);
    wrap.scrollTop = wrap.scrollHeight;
    return el;
  }

  function agentLabel(name) {
    const a = (S.agents || []).find((x) => x.name === name);
    return a ? a.label : name;
  }

  function setAIStatus(el, text) {
    const st = el.querySelector(".agent-status");
    if (!st) return;
    if (text) {
      st.hidden = false;
      st.querySelector(".st-txt").textContent = text;
    } else {
      st.hidden = true;
    }
  }

  function setAIText(el, text) {
    el.dataset.raw = text;
    const md = el.querySelector(".md");
    if (md) md.innerHTML = mdToHtml(text);
    const btn = el.querySelector(".msg-copy");
    if (btn) btn.onclick = () => {
      navigator.clipboard.writeText(text).then(() => toast("已复制回复"), () => toast("复制失败", "err"));
    };
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
    setAIStatus(aiEl, "正在连接 " + agentLabel(agent) + " …");
    S.chatRunning = true;
    $("chatSend").disabled = true;
    $("chatInput").disabled = true;
    let raw = "";
    try {
      const res = await api("/api/agent/run", {
        method: "POST",
        body: { project_id: S.current.id, prompt: prompt, agent: agent },
      });
      streamEvents("/api/jobs/" + res.job_id + "/stream", (data) => {
        if (data.type === "status") {
          setAIStatus(aiEl, data.text);
          aiEl.classList.remove("running");
        } else if (data.type === "line") {
          setAIStatus(aiEl, "");
          raw = raw ? raw + "\n" + data.text : data.text;
          setAIText(aiEl, raw);
          aiEl.classList.remove("running");
          $("chatMsgs").scrollTop = $("chatMsgs").scrollHeight;
        }
        if (data.type === "end") {
          aiEl.classList.remove("running");
          setAIStatus(aiEl, "");
          if (!raw && data.error) setAIText(aiEl, "（任务失败：" + data.error + "）");
          S.chatRunning = false;
          $("chatSend").disabled = false;
          $("chatInput").disabled = false;
        }
      }, () => {
        if (!raw) setAIText(aiEl, "（任务已结束，无输出）");
        aiEl.classList.remove("running");
        setAIStatus(aiEl, "");
        S.chatRunning = false;
        $("chatSend").disabled = false;
        $("chatInput").disabled = false;
      });
    } catch (err) {
      setAIText(aiEl, "（启动失败：" + err.message + "）");
      aiEl.classList.remove("running");
      setAIStatus(aiEl, "");
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
  function renderTypeTabsEditor() {
    const wrap = $("typeTabsEditor");
    if (!wrap || !S.types.length) return;
    const tabLabels = S.types[0].tab_labels || {};
    const keys = Object.keys(tabLabels);
    const always = ["overview", "ailog"];
    wrap.innerHTML = "";
    S.types.forEach((t) => {
      const block = document.createElement("div");
      block.className = "tt-type";
      const title = document.createElement("div");
      title.className = "tt-title";
      title.textContent = (t.custom ? "（自定义）" : "") + " " + t.label;
      block.appendChild(title);
      const grid = document.createElement("div");
      grid.className = "tt-grid";
      keys.forEach((key) => {
        const locked = always.indexOf(key) >= 0;
        const on = locked || (Array.isArray(t.tabs) && t.tabs.indexOf(key) >= 0);
        const label = document.createElement("label");
        label.className = "tt-check" + (locked ? " locked" : "");
        const cb = document.createElement("input");
        cb.type = "checkbox";
        cb.name = "tab_" + t.name + "_" + key;
        cb.checked = on;
        cb.disabled = locked;
        label.appendChild(cb);
        const span = document.createElement("span");
        span.textContent = tabLabels[key] || key;
        label.appendChild(span);
        grid.appendChild(label);
      });
      block.appendChild(grid);
      wrap.appendChild(block);
    });
  }

  function openSettings() {
    const form = $("settingsForm");
    form.elements.root.value = S.settings.root;
    form.elements.agent.value = S.settings.agent;
    form.elements.theme.value = S.settings.theme;
    form.elements.github_auto.checked = !!S.settings.github_auto;
    form.elements.github_visibility.value = S.settings.github_visibility || "private";
    form.elements.backup.checked = !!S.settings.backup;
    const policy = S.settings.confirm_policy || {};
    ["push", "delete", "github_create", "release", "archive"].forEach((k) => {
      const el = form.elements["policy_" + k];
      if (el) el.checked = policy[k] !== false;
    });
    form.elements.update_repo.value = S.settings.update_repo || "GinyvaXu/ProjectDock";
    const cur = $("updateCurrent");
    if (cur) cur.textContent = S.appVersion || "";
    renderTypeTabsEditor();
    openModal("settings");
  }

  async function saveSettings(ev) {
    ev.preventDefault();
    const form = ev.target;
    const tabLabels = (S.types.length && S.types[0].tab_labels) || {};
    const keys = Object.keys(tabLabels);
    const typeTabs = {};
    S.types.forEach((t) => {
      const checked = [];
      keys.forEach((key) => {
        const cb = form.elements["tab_" + t.name + "_" + key];
        if (cb && cb.checked) checked.push(key);
      });
      if (checked.length) typeTabs[t.name] = checked;
    });
    const confirmPolicy = {};
    ["push", "delete", "github_create", "release", "archive"].forEach((k) => {
      confirmPolicy[k] = !!form.elements["policy_" + k].checked;
    });
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
          type_tabs: typeTabs,
          confirm_policy: confirmPolicy,
          update_repo: form.elements.update_repo.value.trim(),
        },
      });
      applyTheme(S.settings.theme);
      closeModal("settings");
      toast("设置已保存");
      S.types = await api("/api/types");
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

  /* ============ 软件更新 ============ */
  async function checkUpdateSilent() {
    try {
      const r = await api("/api/update/check");
      if (r && r.update_available) {
        toast("发现新版本 v" + r.latest + "，可在设置中更新", "ok");
      }
    } catch (err) { /* 静默失败 */ }
  }

  async function checkUpdate() {
    const status = $("updateStatus");
    const actions = $("updateActions");
    if (!status) return;
    status.className = "update-status";
    status.textContent = "正在检查更新…";
    try {
      const r = await api("/api/update/check");
      if (r.status === "unknown") {
        status.textContent = "无法检查更新（未安装 gh 或仓库不可达）";
        actions.hidden = true;
        return;
      }
      if (!r.update_available) {
        status.textContent = "已是最新版本 v" + esc(r.current) + (r.latest ? "（最新 v" + esc(r.latest) + "）" : "");
        actions.hidden = true;
        return;
      }
      status.textContent = "发现新版本 v" + esc(r.latest);
      $("updateInfo").innerHTML = "<div class='build-log'>" + esc((r.notes || "（无更新说明）").slice(0, 2000)) + "</div>";
      actions.hidden = false;
    } catch (err) {
      status.textContent = "检查更新失败：" + esc(err.message);
      actions.hidden = true;
    }
  }

  async function downloadAndInstall() {
    const status = $("updateStatus");
    const actions = $("updateActions");
    status.textContent = "正在下载安装包…";
    try {
      const dl = await api("/api/update/download", { method: "POST", body: {} });
      status.textContent = "已下载 " + fmtSize(dl.size) + "，正在启动安装…";
      await api("/api/update/install", { method: "POST", body: { path: dl.path } });
      status.textContent = "安装程序已启动，应用即将自动关闭。完成后请从桌面快捷方式重新打开。";
      actions.hidden = true;
      setTimeout(() => { try { window.close(); } catch (e) { /* ignore */ } }, 900);
    } catch (err) {
      status.textContent = "更新失败：" + esc(err.message);
    }
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
    $("btnCheckUpdate").addEventListener("click", checkUpdate);
    $("btnDownloadUpdate").addEventListener("click", downloadAndInstall);
    $("searchInput").addEventListener("input", (e) => { S.search = e.target.value; renderGrid(); });
    $("btnDrawerClose").addEventListener("click", closeDrawer);
    $("btnOpenFolder").addEventListener("click", () => handleOverviewAction("open"));
    $("btnCopyPath").addEventListener("click", () => handleOverviewAction("copy"));
    $("backdrop").addEventListener("click", closeDrawer);
    $("drawerTabs").addEventListener("click", (e) => {
      const btn = e.target.closest(".tab");
      if (btn) showTab(btn.dataset.tab);
    });
    $("btnConsole").addEventListener("click", showConsole);
    document.querySelectorAll(".nav-item[data-filter]").forEach((el) => {
      el.addEventListener("click", () => setFilter(el.dataset.filter));
    });
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
