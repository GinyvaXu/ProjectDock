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
    logoRev: 0,
    _iconChoice: null,
    chatRunning: false,
    _chatRunning: {},
    chatSessions: {},
    consoleChatProject: null,
    consoleChatFull: false,
    view: "grid",
    viewMode: "grid",
    sort: "pinned",
    console: null,
    drawerSeq: 0,
    unmanaged: [],
    namingStyles: null,
  };

  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const fmtSize = (n) => (n == null ? "" : n >= 1048576 ? (n / 1048576).toFixed(1) + " MB" : n >= 1024 ? (n / 1024).toFixed(1) + " KB" : n + " B");
  const TYPE_ICONS = { "软件": "💻", "网站": "🌐", "游戏": "🎮", "PPT": "📊", "文稿": "📄", "脚本": "🐍", "其他": "📁",
    "文档加工": "📚", "资料系统": "🗃️", "本地应用": "🧰", "克隆仓库": "🐙", "工具脚本": "🔧" };
  const SCHEME_LABELS = { semver: "语义化版本", archive: "日期归档", upstream: "上游只读", none: "不追踪版本" };
  const schemeLabel = (s) => SCHEME_LABELS[s] || s || "";
  const typeIcon = (p) => TYPE_ICONS[p.type] || "📁";
  function logoHTML(p) {
    const emoji = "<span class='logo-fallback'>" + typeIcon(p) + "</span>";
    if (!p.has_logo) return emoji;
    return "<span class='logo-wrap'>" + emoji +
      "<img class='proj-logo' src='/api/projects/" + encodeURIComponent(p.id) + "/logo?v=" + (S.logoRev || 0) + "' alt='' onerror='this.remove()'></span>";
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
    S.viewMode = (typeof localStorage !== "undefined" && localStorage.getItem("pd.view")) || "grid";
    S.view = S.viewMode;
    S.sort = (typeof localStorage !== "undefined" && localStorage.getItem("pd.sort")) || "pinned";
    S.appVersion = health.version;
    $("appVersion").textContent = "v" + health.version;
    checkUpdateSilent();
    applyTheme(settings.theme);
    fillTypeSelects();
    fillAgentSelect();
    renderSidebar();
    renderGrid();
    loadUnmanaged();
    bindEvents();
    updateViewButtons();
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
    const sort = S.sort || "pinned";
    const byName = (a, b) => String(a.title || "").localeCompare(String(b.title || ""), "zh-Hans-CN");
    return list.slice().sort((a, b) => {
      if (sort === "pinned") return (b.pinned ? 1 : 0) - (a.pinned ? 1 : 0) || byName(a, b);
      if (sort === "name") return byName(a, b);
      if (sort === "type") return String(a.type || "").localeCompare(String(b.type || ""), "zh-Hans-CN") || byName(a, b);
      if (sort === "updated") return String(b.updated_at || "").localeCompare(String(a.updated_at || ""));
      if (sort === "created") return String(b.created_at || "").localeCompare(String(a.created_at || ""));
      return 0;
    });
  }

  function cardHTML(p) {
    return "<div class='card" + (p.pinned ? " pinned-card" : "") + "' data-id='" + esc(p.id) + "' style='opacity:0'>" +
      "<div class='card-head'>" +
        "<button class='pin-btn" + (p.pinned ? " on" : "") + "' data-pin='" + esc(p.id) + "' title='" + (p.pinned ? "取消置顶" : "置顶") + "'>📌</button>" +
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

  function rowHTML(p) {
    return "<div class='proj-row" + (p.pinned ? " pinned-row" : "") + "' data-id='" + esc(p.id) + "' style='opacity:0'>" +
      "<button class='pin-btn" + (p.pinned ? " on" : "") + "' data-pin='" + esc(p.id) + "' title='" + (p.pinned ? "取消置顶" : "置顶") + "'>📌</button>" +
      "<span class='row-logo type-" + esc(p.type) + "'>" + logoHTML(p) + "</span>" +
      "<div class='row-main'>" +
        "<div class='row-top'>" +
          "<span class='row-title'>" + esc(p.title) + "</span>" +
          "<span class='badge " + esc(p.type) + "'>" + esc(p.type) + "</span>" +
          (p.compliant ? "" : "<span class='badge badge-warn' title='未达标项目管理规范'>⚠ 未合规</span>") +
          (p.version ? "<span class='row-version'>v" + esc(p.version) + "</span>" : "") +
        "</div>" +
        "<div class='row-desc'>" + esc(p.description || "（暂无描述）") + "</div>" +
      "</div>" +
      "<div class='row-meta'>" +
        "<span class='row-path'>" + esc(p.id) + "</span>" +
        (p.has_git ? "<span class='git-ok'>git ✓</span>" : "<span class='git-no'>git</span>") +
        (p.updated_at ? "<span class='row-updated'>更新 " + esc((p.updated_at || "").replace("T", " ").slice(0, 10)) + "</span>" : "") +
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
    const listMode = S.view === "list";
    grid.classList.toggle("list-mode", listMode);
    const pinned = list.filter((p) => p.pinned);
    const rest = list.filter((p) => !p.pinned);
    let idx = 0;
    const addSection = (label, items) => {
      if (!items.length) return;
      if (label) {
        const lab = document.createElement("div");
        lab.className = "section-label";
        lab.innerHTML = "<span>" + esc(label) + "</span><span class='section-count'>" + items.length + "</span>";
        frag.appendChild(lab);
      }
      items.forEach((p) => {
        const el = document.createElement("div");
        el.innerHTML = listMode ? rowHTML(p) : cardHTML(p);
        const card = el.firstElementChild;
        card.addEventListener("click", (ev) => { if (ev.target.closest(".pin-btn")) return; openDrawer(p.id); });
        const pinBtn = card.querySelector(".pin-btn");
        if (pinBtn) pinBtn.addEventListener("click", (ev) => { ev.stopPropagation(); togglePin(p.id, pinBtn); });
        frag.appendChild(card);
        Spring.enter(card, { delay: Math.min(idx * 40, 320), distance: 22 });
        idx += 1;
      });
    };
    if (S.sort === "pinned") {
      addSection("📌 置顶", pinned);
      addSection("全部项目", rest);
    } else {
      addSection("", list);
    }
    grid.appendChild(frag);
  }

  /* ============ 未纳管文件夹 ============ */
  async function loadUnmanaged() {
    try {
      S.unmanaged = await api("/api/projects/unmanaged");
    } catch (err) {
      S.unmanaged = [];
    }
    renderUnmanaged();
  }

  function renderUnmanaged() {
    const box = $("unmanagedBox");
    if (!box) return;
    const list = S.unmanaged || [];
    if (!list.length || S.view === "console") {
      box.hidden = true;
      box.innerHTML = "";
      return;
    }
    box.hidden = false;
    box.innerHTML =
      "<div class='unmanaged-head'><span>📂 未纳管文件夹</span><span class='section-count'>" + list.length + "</span>" +
      "<span style='font-weight:400;color:var(--text-3)'>不符合当前命名风格，可一键导入管理</span></div>" +
      list.map((u) =>
        "<div class='unmanaged-row'><span class='u-name'>" + esc(u.name) + "</span>" +
        "<span class='u-path'>" + esc(u.path) + "</span><span class='spacer'></span>" +
        "<button class='btn btn-sm btn-primary' data-import-path='" + esc(u.path) + "'>导入管理</button></div>"
      ).join("");
    box.querySelectorAll("[data-import-path]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const row = btn.closest(".unmanaged-row");
        const name = row ? (row.querySelector(".u-name") || {}).textContent : "";
        btn.disabled = true;
        try {
          await api("/api/projects/import", { method: "POST", body: { path: btn.dataset.importPath, type: "其他", description: "" } });
          toast("已导入：" + name);
          await refresh();
        } catch (err) {
          btn.disabled = false;
          toast(err.message, "err");
        }
      });
    });
  }

  function setFilter(type) {
    S.filter = type;
    document.querySelectorAll(".nav-item").forEach((el) => {
      el.classList.toggle("active", el.dataset.filter === type);
    });
    if (S.view === "console") showGrid();
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
    renderChatPresets();
    renderChat(S.current.id, "chatMsgs");
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
    if (tab === "github") renderGithub();
    if (tab === "techstack") renderTechstack();
    if (tab === "ai") renderChatPresets();
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
        "<button class='btn btn-sm' data-act='icon'>设置图标</button>" +
        "<button class='btn btn-sm' data-act='edit'>编辑信息</button>" +
        "<button class='btn btn-sm" + (proj.pinned ? " btn-pinned" : "") + "' data-act='pin'>" + (proj.pinned ? "取消置顶" : "置顶") + "</button>" +
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
    } else if (act === "icon") {
      openIconModal();
    } else if (act === "edit") {
      openEditModal();
    } else if (act === "pin") {
      togglePin(id, null, true);
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

  async function togglePin(id, btn, fromOverview) {
    try {
      const res = await api("/api/projects/" + encodeURIComponent(id) + "/pin", { method: "POST" });
      const p = S.projects.find((x) => x.id === id);
      if (p) p.pinned = res.pinned;
      if (btn) {
        btn.classList.toggle("on", res.pinned);
        btn.title = res.pinned ? "取消置顶" : "置顶";
      }
      if (fromOverview) {
        const meta = document.querySelector('#panel-overview [data-act="pin"]');
        if (meta) {
          meta.textContent = res.pinned ? "取消置顶" : "置顶";
          meta.classList.toggle("btn-pinned", res.pinned);
        }
      }
      renderGrid();
      toast(res.pinned ? "已置顶" : "已取消置顶");
    } catch (err) { toast(err.message, "err"); }
  }

  /* ============ 项目信息编辑 ============ */
  function openEditModal() {
    if (!S.current) return;
    const form = $("editForm");
    if (!form) return;
    form.elements.name.value = S.current.title || "";
    form.elements.description.value = S.current.description || "";
    const sel = $("editType");
    sel.innerHTML = S.presets.map((p) => "<option value='" + esc(p.type) + "'>" + esc(p.label) + "</option>").join("");
    sel.value = S.current.type;
    if (form.elements.version_scheme) {
      form.elements.version_scheme.value = S.current.version_scheme_set || "";
    }
    openModal("edit");
  }

  async function saveEdit(ev) {
    ev.preventDefault();
    if (!S.current) return;
    const form = ev.target;
    const payload = {
      name: form.elements.name.value.trim(),
      type: form.elements.type.value,
      description: form.elements.description.value.trim(),
      version_scheme: form.elements.version_scheme ? form.elements.version_scheme.value : "",
    };
    if (!payload.name) { toast("项目名称不能为空", "err"); return; }
    const oldId = S.current.id;
    try {
      const updated = await api("/api/projects/" + encodeURIComponent(oldId), { method: "PUT", body: payload });
      toast("项目信息已更新");
      closeModal("edit");
      await refresh();
      if (updated && updated.id) openDrawer(updated.id);
    } catch (err) { toast(err.message, "err"); }
  }

  /* ============ GitHub 仓库管理 ============ */
  function ghBadge(ok, text) {
    return "<span class='ai-badge' style='" + (ok ? "" : "background:rgba(255,59,48,.12);color:#ff3b30;") + "'>" + esc(text) + "</span>";
  }

  function fixReadmeImages(md, owner, repo, branch) {
    const base = "https://raw.githubusercontent.com/" + owner + "/" + repo + "/" + branch + "/";
    let out = String(md || "").replace(/!\[([^\]]*)\]\(([^)]+)\)/g, function (m, alt, url) {
      const u = String(url).trim();
      if (/^(https?:|data:)/.test(u)) return m;
      const safe = u.replace(/["'<>]/g, "").replace(/^\.\//, "");
      return "![" + alt + "](" + base + safe + ")";
    });
    out = out.replace(/<img\b[^>]*\bsrc=["']([^"'#]+)["'][^>]*>/gi, function (m, url) {
      const u = String(url).trim();
      if (/^(https?:|data:|blob:)/.test(u)) return m;
      const safe = u.replace(/["'<>]/g, "").replace(/^\.\//, "");
      return m.split(url).join(base + safe);
    });
    return out;
  }

  async function renderGithub() {
    if (!S.current) return;
    const seq = S.drawerSeq;
    const pid = S.current.id;
    const panel = $("panel-github");
    if (!panel) return;
    panel.innerHTML = "<div class='gh-box'><div class='gh-loading'>加载 GitHub 信息…</div></div>";
    try {
      const data = await api("/api/projects/" + encodeURIComponent(pid) + "/github");
      if (seq !== S.drawerSeq || !S.current || S.current.id !== pid) return;
      let html = "<div class='gh-box'>";
      if (!data.auth.logged_in) {
        html += "<div class='gh-login'><span class='gh-login-ico'>🐙</span><div>尚未登录 GitHub</div>" +
          "<div style='font-size:12.5px;color:var(--text-3)'>登录后即可查看远程仓库、README、提交记录与发行版。</div>" +
          "<button class='btn btn-sm btn-primary' id='btnGhGoSettings'>去设置登录</button></div>";
      } else {
        const u = data.auth.user || {};
        html += "<div class='gh-card'><div class='gh-user'>" +
          (u.avatar_url ? "<img src='" + esc(u.avatar_url) + "' alt=''>" : "<span class='logo-fallback'>🐙</span>") +
          "<div><div class='gh-uname'>" + esc(u.login || "") + "</div>" +
          "<div class='gh-usrc'>" + esc(data.auth.source === "token" ? "令牌登录" : "gh 命令行登录") + "</div></div>" +
          "<span class='spacer'></span><button class='btn btn-sm' id='btnGhRefresh'>刷新</button></div>";
        if (!data.remote.url) {
          html += "<div class='gh-card'><h4>尚未关联远程仓库</h4>" +
            "<div class='gh-remote-row'><span>当前项目没有配置 origin。可一键创建并推送，或手动填写远程地址。</span></div>" +
            "<div class='action-row' style='margin-top:10px'>" +
            "<button class='btn btn-sm btn-primary' id='btnGhCreate'>创建仓库并推送</button>" +
            "<select id='ghCreateVis'><option value='private'>私有</option><option value='public'>公开</option></select></div>" +
            "<div class='gh-set-remote'><input id='ghRemoteInput' placeholder='https://github.com/owner/repo.git' spellcheck='false'>" +
            "<button class='btn btn-sm' id='btnGhSetRemote'>设置远程</button></div></div>";
        } else {
          const repo = data.repo || {};
          html += "<div class='gh-card'><h4>" + esc(data.remote.owner + "/" + data.remote.repo) + "</h4>";
          if (repo.error) {
            html += "<div class='gh-err'>仓库信息读取失败：" + esc(repo.error) + "</div>";
          } else if (repo.full_name) {
            html += "<div class='gh-meta'>" +
              "<div class='gm'>可见性</div><div class='gv'>" + (repo.private ? "私有" : "公开") + "</div>" +
              "<div class='gm'>默认分支</div><div class='gv'>" + esc(repo.default_branch || "main") + "</div>" +
              "<div class='gm'>语言</div><div class='gv'>" + esc(repo.language || "—") + "</div>" +
              "<div class='gm'>最近推送</div><div class='gv'>" + esc((repo.pushed_at || "").slice(0, 10) || "—") + "</div>" +
              "<div class='gm'>Stars / Forks</div><div class='gv'>" + repo.stargazers + " / " + repo.forks + "</div>" +
              "<div class='gm'>Issues</div><div class='gv'>" + repo.issues + "</div></div>";
          }
          html += "<div class='action-row' style='margin-top:10px'>" +
            "<button class='btn btn-sm btn-primary' id='btnGhOpen'>打开远程仓库</button>" +
            "<button class='btn btn-sm' id='btnGhReleases'>发行版</button></div></div>";
          html += "<div class='gh-card'><div class='action-row' style='margin:0 0 8px'><h4 style='margin:0'>README</h4><span class='spacer'></span>" +
            "<button class='btn btn-sm' id='btnGhReadme'>加载 / 刷新</button></div>" +
            "<div class='gh-readme' id='ghReadmeBox'><div class='gh-loading'>点击上方按钮加载远程 README</div></div></div>";
          html += "<div class='gh-card'><h4>最近提交</h4><div id='ghCommitsBox'><div class='gh-loading'>加载中…</div></div></div>";
          html += "<div class='gh-card'><h4>发行版 Releases</h4><div id='ghReleasesBox'><div class='gh-loading'>点击「发行版」加载</div></div></div>";
        }
      }
      html += "</div>";
      panel.innerHTML = html;
      bindGithubActions(pid, data);
      if (data.remote.url && data.auth.logged_in) loadGhCommits(pid);
    } catch (err) {
      panel.innerHTML = "<div class='gh-box'><div class='gh-err'>加载失败：" + esc(err.message) + "</div></div>";
    }
  }

  function bindGithubActions(pid, data) {
    const go = $("btnGhGoSettings");
    if (go) go.addEventListener("click", openSettings);
    const ref = $("btnGhRefresh");
    if (ref) ref.addEventListener("click", renderGithub);
    const openBtn = $("btnGhOpen");
    if (openBtn && data.repo && data.repo.html_url) {
      openBtn.addEventListener("click", () => api("/api/open-url", { method: "POST", body: { url: data.repo.html_url } }).catch((e) => toast(e.message, "err")));
    }
    const createBtn = $("btnGhCreate");
    if (createBtn) createBtn.addEventListener("click", async () => {
      if (!window.confirm("将在 GitHub 创建仓库并推送当前分支到 origin，继续？")) return;
      const vis = ($("ghCreateVis") || {}).value || "private";
      try {
        const r = await api("/api/projects/" + encodeURIComponent(pid) + "/github/create", { method: "POST", body: { visibility: vis } });
        toast(r.message || "仓库已创建");
        renderGithub();
      } catch (err) { toast(err.message, "err"); }
    });
    const setRemote = $("btnGhSetRemote");
    if (setRemote) setRemote.addEventListener("click", async () => {
      const url = ($("ghRemoteInput") || {}).value || "";
      if (!url) { toast("请填写远程地址", "err"); return; }
      try {
        const r = await api("/api/projects/" + encodeURIComponent(pid) + "/github/set-remote", { method: "POST", body: { url: url } });
        toast(r.message || "已设置");
        renderGithub();
      } catch (err) { toast(err.message, "err"); }
    });
    const readmeBtn = $("btnGhReadme");
    if (readmeBtn) {
      const branch = (data.repo && data.repo.default_branch) || "main";
      readmeBtn.addEventListener("click", () => loadGhReadme(pid, branch));
    }
    const relBtn = $("btnGhReleases");
    if (relBtn) relBtn.addEventListener("click", () => loadGhReleases(pid));
  }

  async function loadGhReadme(pid, branch) {
    const box = $("ghReadmeBox");
    if (!box) return;
    box.innerHTML = "<div class='gh-loading'>加载 README…</div>";
    try {
      const r = await api("/api/projects/" + encodeURIComponent(pid) + "/github/readme");
      const br = branch || r.branch || "main";
      const text = fixReadmeImages(r.text, r.owner, r.repo, br);
      if (!text.trim()) { box.innerHTML = "<div class='gh-loading'>远程仓库没有 README</div>"; return; }
      box.innerHTML = mdToHtml(text);
    } catch (err) {
      box.innerHTML = "<div class='gh-err'>" + esc(err.message) + "</div>";
    }
  }

  async function loadGhCommits(pid) {
    const box = $("ghCommitsBox");
    if (!box) return;
    try {
      const r = await api("/api/projects/" + encodeURIComponent(pid) + "/github/commits");
      box.innerHTML = r.commits.length
        ? r.commits.map((c) => "<div class='gh-commit'><span class='ghc-msg'>" + esc(c.message) + "</span>" +
            "<span class='ghc-sha'>" + esc(c.sha) + "</span>" +
            "<span class='ghc-date'>" + esc((c.date || "").slice(0, 10)) + "</span></div>").join("")
        : "<div class='gh-loading'>暂无提交记录</div>";
    } catch (err) {
      box.innerHTML = "<div class='gh-err'>" + esc(err.message) + "</div>";
    }
  }

  async function loadGhReleases(pid) {
    const box = $("ghReleasesBox");
    if (!box) return;
    box.innerHTML = "<div class='gh-loading'>加载发行版…</div>";
    try {
      const r = await api("/api/projects/" + encodeURIComponent(pid) + "/github/releases");
      box.innerHTML = r.releases.length
        ? r.releases.map((x) => "<div class='gh-rel'><span class='ghr-tag'>" + esc(x.tag) + "</span>" +
            "<span class='ghr-date'>" + esc((x.published_at || "").slice(0, 10)) + "</span>" +
            (x.prerelease ? ghBadge(false, "预发布") : "") +
            "<span class='spacer'></span><button class='btn btn-sm' data-gh-url='" + esc(x.html_url) + "'>打开</button></div>").join("")
        : "<div class='gh-loading'>暂无发行版</div>";
      box.querySelectorAll("[data-gh-url]").forEach((b) => {
        b.addEventListener("click", () => api("/api/open-url", { method: "POST", body: { url: b.dataset.ghUrl } }).catch((e) => toast(e.message, "err")));
      });
    } catch (err) {
      box.innerHTML = "<div class='gh-err'>" + esc(err.message) + "</div>";
    }
  }

  /* ============ GitHub 设置登录 ============ */
  async function loadGithubAuth() {
    const box = $("ghAuthStatus");
    if (!box) return;
    box.innerHTML = "检测中…";
    try {
      const a = await api("/api/github/auth");
      const logout = $("btnGhLogout");
      const loginBtn = $("btnGhLogin");
      if (a.logged_in && a.user) {
        box.innerHTML = "✅ 已登录：<strong>" + esc(a.user.login) + "</strong>（" + (a.source === "token" ? "令牌" : "gh 命令行") + "）";
        if (logout) logout.hidden = false;
        if (loginBtn) loginBtn.disabled = false;
      } else {
        box.textContent = "未登录。可粘贴个人访问令牌，或使用 gh 命令行登录。";
        if (logout) logout.hidden = true;
      }
    } catch (err) {
      box.textContent = "检测失败：" + err.message;
    }
  }

  async function githubLogin() {
    const input = $("ghTokenInput");
    const token = (input.value || "").trim();
    if (!token) { toast("请先粘贴令牌", "err"); return; }
    try {
      const r = await api("/api/github/auth", { method: "POST", body: { token: token } });
      toast("已登录：" + r.user.login);
      input.value = "";
      await loadGithubAuth();
    } catch (err) { toast(err.message, "err"); }
  }

  async function githubLogout() {
    try {
      await api("/api/github/auth", { method: "DELETE" });
      toast("已退出登录");
      await loadGithubAuth();
    } catch (err) { toast(err.message, "err"); }
  }

  /* ============ AI 聊天：分类快捷指令 ============ */
  const PRESET_GROUPS = {
    "软件": [
      { icon: "🗂", label: "Git 与版本", items: [
        "帮我初始化 Git 并提交当前代码",
        "查看 Git 状态并汇报工作区概况",
        "整理版本归档到 versions/ 目录",
        "把当前版本构建产物归档并递增版本号",
      ]},
      { icon: "🔨", label: "构建与发布", items: [
        "构建 Debug 版本",
        "构建 Release 安装包（Setup）",
        "发布新版本（构建 + 归档 + GitHub Release）",
        "推送代码到 GitHub 远程仓库",
      ]},
      { icon: "📝", label: "文档", items: [
        "更新 CHANGELOG 并递增版本号",
        "更新 README 文档",
        "撰写/更新 TECHSTACK.md 技术栈文档（通读源码归纳核心功能）",
        "检查并补全项目文档（计划书/设计/需求）",
      ]},
      { icon: "🧪", label: "质量", items: [
        "审查代码并修复 Bug",
        "补充单元测试并全部跑通",
        "检查项目合规性并一键修复",
      ]},
      { icon: "🤖", label: "AI 协作", items: [
        "梳理项目当前状态并给出下一步计划",
        "分析项目文件夹结构并给出优化建议",
        "把本次开发过程写成 AI 操作日志",
      ]},
    ],
    "网站": [
      { icon: "🗂", label: "Git 与版本", items: [
        "帮我初始化 Git 并提交当前代码",
        "整理版本归档到 versions/ 目录",
        "推送代码到 GitHub 远程仓库",
      ]},
      { icon: "🔨", label: "前端构建", items: [
        "构建前端产物并检查输出",
        "构建并本地预览网站",
        "检查页面资源与打包配置",
      ]},
      { icon: "📝", label: "文档", items: [
        "更新 README 文档",
        "检查并补全网站说明文档",
      ]},
      { icon: "🤖", label: "AI 协作", items: [
        "梳理网站结构与当前进度",
        "分析页面结构并给出改进建议",
      ]},
    ],
    "游戏": [
      { icon: "🗂", label: "Git 与版本", items: [
        "帮我初始化 Git 并提交当前代码",
        "整理版本归档到 versions/ 目录",
        "推送代码到 GitHub 远程仓库",
      ]},
      { icon: "🔨", label: "资源与构建", items: [
        "构建当前游戏版本",
        "整理游戏资源素材",
        "检查并归档构建产物",
      ]},
      { icon: "📝", label: "文档", items: [
        "更新 README 与游戏说明",
        "整理玩法/设计文档",
      ]},
      { icon: "🤖", label: "AI 协作", items: [
        "梳理游戏开发进度",
        "分析关卡/数值并给出建议",
      ]},
    ],
    "脚本": [
      { icon: "🗂", label: "Git 与版本", items: [
        "帮我初始化 Git 并提交当前代码",
        "整理版本归档到 versions/ 目录",
        "推送代码到 GitHub 远程仓库",
      ]},
      { icon: "🔨", label: "运行与测试", items: [
        "运行脚本并检查输出",
        "补充参数校验与错误处理",
        "为脚本补充测试用例",
      ]},
      { icon: "📝", label: "文档", items: [
        "更新 README 与用法说明",
        "检查并补全脚本注释",
      ]},
      { icon: "🤖", label: "AI 协作", items: [
        "分析脚本逻辑并优化",
        "梳理脚本使用场景与依赖",
      ]},
    ],
    "PPT": [
      { icon: "🗂", label: "内容整理", items: [
        "整理演示文稿大纲",
        "按主题归类幻灯片素材",
        "检查幻灯片文字密度与排版",
      ]},
      { icon: "📦", label: "版本归档", items: [
        "归档各版本演示文稿到 versions/",
        "整理相关素材与参考资料",
      ]},
      { icon: "🤖", label: "AI 协作", items: [
        "梳理演示文稿结构与进度",
        "给出单页内容修改建议",
      ]},
    ],
    "文稿": [
      { icon: "🗂", label: "内容整理", items: [
        "按文件类型归类文档",
        "整理各版本文稿并排序",
        "生成文档目录索引",
      ]},
      { icon: "📦", label: "版本归档", items: [
        "归档各版本文稿到 versions/",
        "整理 backups 备份",
      ]},
      { icon: "🤖", label: "AI 协作", items: [
        "梳理文稿写作进度",
        "检查并补全文稿元信息",
      ]},
    ],
    "其他": [
      { icon: "🗂", label: "整理", items: [
        "整理项目文件结构",
        "按文件类型归类文件",
        "生成项目文件索引",
      ]},
      { icon: "📦", label: "版本归档", items: [
        "整理 versions/ 归档",
        "整理 backups 备份",
      ]},
      { icon: "🤖", label: "AI 协作", items: [
        "梳理项目当前状态",
        "检查并补全项目信息",
        "给出文件组织优化建议",
      ]},
    ],
  };
  function renderChatPresets() {
    const wrap = $("chatPresets");
    if (!wrap) return;
    const type = S.current ? S.current.type : "";
    const groups = PRESET_GROUPS[type] || PRESET_GROUPS["其他"];
    wrap.innerHTML = groups.map((g, gi) =>
      "<details class='preset-group'" + (gi === 0 ? " open" : "") + ">" +
        "<summary><span class='pg-ico'>" + esc(g.icon || "·") + "</span><span class='pg-label'>" + esc(g.label) + "</span>" +
        "<span class='pg-count'>" + g.items.length + "</span><span class='pg-caret'>▾</span></summary>" +
        "<div class='preset-chips'>" +
          g.items.map((t) => "<button class='preset-chip' data-prompt='" + esc(t) + "'>" + esc(t) + "</button>").join("") +
        "</div></details>"
    ).join("");
    wrap.querySelectorAll(".preset-chip").forEach((b) => {
      b.addEventListener("click", () => {
        const input = $("chatInput");
        if (!input) return;
        input.value = b.dataset.prompt;
        input.focus();
      });
    });
  }

  const ICON_SYMBOLS = [
    ["播放", 0], ["地球", 1], ["手柄", 2], ["图表", 3], ["文档", 4], ["终端", 5],
    ["菱形", 6], ["星星", 7], ["齿轮", 8], ["书本", 9], ["相机", 10], ["音符", 11],
  ];

  function openIconModal() {
    if (!S.current) return;
    const wrap = $("iconSymbols");
    wrap.innerHTML = ICON_SYMBOLS.map((pair) =>
      "<button class='icon-sym" + (S._iconChoice && S._iconChoice.symbol === pair[1] ? " active" : "") + "' data-sym='" + pair[1] + "'>" + pair[0] + "</button>"
    ).join("");
    const prev = $("iconPreview");
    if (S.current.has_logo) {
      prev.innerHTML = "<img src='/api/projects/" + encodeURIComponent(S.current.id) + "/logo?v=" + (S.logoRev || 0) + "' alt=''>";
    } else {
      prev.innerHTML = logoHTML(S.current);
    }
    S._iconChoice = { mode: "auto", symbol: null };
    $("btnIconApply").disabled = false;
    openModal("icon");
  }

  function setIconChoice(choice) {
    S._iconChoice = choice;
    $("btnIconApply").disabled = false;
    document.querySelectorAll("#iconSymbols .icon-sym").forEach((b) => {
      const on = choice.symbol !== undefined && choice.symbol !== null && parseInt(b.dataset.sym, 10) === choice.symbol;
      b.classList.toggle("active", on);
    });
  }

  async function applyIcon() {
    if (!S.current || !S._iconChoice) return;
    const btn = $("btnIconApply");
    const origText = btn ? btn.textContent : "";
    if (btn) { btn.disabled = true; btn.textContent = "生成中…"; }
    toast(S._iconChoice.mode === "upload" ? "正在保存图标…" : "正在生成图标…");
    try {
      await api("/api/projects/" + encodeURIComponent(S.current.id) + "/icon", {
        method: "POST", body: S._iconChoice,
      });
      S.logoRev = (S.logoRev || 0) + 1;
      const proj = S.projects.find((x) => x.id === S.current.id);
      if (proj) proj.has_logo = true;
      if (S.current) S.current.has_logo = true;
      closeModal("icon");
      const dl = $("drawerLogo");
      if (dl) dl.innerHTML = logoHTML(S.current);
      renderOverview(S.current);
      renderGrid();
      toast("图标已更新");
    } catch (err) { toast(err.message, "err"); }
    finally {
      if (btn) { btn.disabled = false; btn.textContent = origText; }
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
          const dot = e.result === "done" ? "clean" : e.result === "failed" ? "dirty" : e.result === "run" ? "run" : "no";
          const git = e.git || {};
          const gitParts = [];
          if (git.head) gitParts.push("HEAD " + git.head);
          if (git.branch) gitParts.push("分支 " + git.branch);
          if (git.changed != null) gitParts.push("变更 " + git.changed + " 项");
          if (git.added) gitParts.push("新增 " + git.added);
          if (git.commits != null) gitParts.push("提交 " + git.commits);
          box.innerHTML +=
            "<div class='ai-entry'><div class='ai-head'><span class='git-dot " + dot + "'></span>" +
            "<span class='ai-agent'>" + esc(agentLabel(e.agent) || e.agent || "?") + "</span>" +
            "<span class='ai-ts'>" + esc((e.ts || "").replace("T", " ").slice(0, 19)) + "</span>" +
            "<span class='spacer'></span>" +
            (e.source === "inapp" ? "<span class='ai-src'>应用内</span>" : "") +
            "<span class='ai-result " + cls + "'>" + esc(e.result) + "</span></div>" +
            "<div class='ai-action'>" + esc(e.action || "") + "</div>" +
            (e.summary ? "<div class='ai-summary'>" + esc(e.summary) + "</div>" : "") +
            "<div class='ai-more'>" +
            (e.source ? "<span class='ai-src'>来源：" + esc(e.source === "inapp" ? "应用内" : "外部 Agent") + "</span>" : "") +
            (e.backup ? "<span class='ai-src'>备份：" + esc(e.backup) + "</span>" : "") +
            (gitParts.length ? "<span class='ai-src'>Git：" + esc(gitParts.join(" · ")) + "</span>" : "") +
            "</div>" +
            ((e.details) ?
              "<details class='ai-detail'><summary>详情</summary><div>" + esc(e.details) + "</div></details>" : "");
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
    renderUnmanaged();
    renderConsole();
  }

  function showGrid() {
    S.view = S.viewMode === "list" ? "list" : "grid";
    document.querySelectorAll(".nav-item").forEach((el) => el.classList.remove("active"));
    document.querySelectorAll(".nav-item[data-filter]").forEach((el) => el.classList.toggle("active", el.dataset.filter === S.filter));
    $("console").hidden = true;
    $("grid").hidden = false;
    updateViewButtons();
    renderGrid();
    renderUnmanaged();
  }

  function setView(mode) {
    S.viewMode = mode;
    S.view = mode;
    if (typeof localStorage !== "undefined") localStorage.setItem("pd.view", mode);
    updateViewButtons();
    renderGrid();
  }

  function updateViewButtons() {
    document.querySelectorAll(".seg-btn").forEach((b) => {
      b.classList.toggle("active", b.dataset.view === S.view);
    });
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
          "<div class='console-act'><button class='ai-badge' data-pid='" + esc(e.project || "") + "' title='打开项目'>" + esc(e.project_title || e.project || "") + "</button>" +
          "<span class='ai-ts'>" + esc((e.ts || "").replace("T", " ").slice(0, 16)) + "</span>" +
          "<span class='ai-agent'>" + esc(e.agent || "") + "</span>" +
          "<span class='ai-result " + (e.result === "done" ? "ok" : e.result === "failed" ? "err" : "run") + "'>" + esc(e.result) + "</span></div>" +
          "<div class='ai-action' title='" + esc(e.action || "") + "'>" + esc(e.action || "") + "</div>" +
          (e.summary ? "<div class='ai-summary'>" + esc(e.summary) + "</div>" : "") +
          (e.details ? "<details class='ai-detail'><summary>详情</summary><div>" + esc(e.details) + "</div></details>" : "") +
          "</div>"
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

      html += "<div class='c-card c-chat" + (S.consoleChatFull ? " chat-full" : "") + "'><div class='ver-head'><h4>AI 助手对话</h4>" +
        "<span class='spacer'></span>" +
        "<select id='consoleAgentProject' class='console-proj-sel' title='切换对话项目'>" +
          data.projects.map((pj) => "<option value='" + esc(pj.id) + "'" + (S.consoleChatProject === pj.id ? " selected" : "") + ">" + esc(pj.title) + "</option>").join("") +
        "</select>" +
        "<select id='consoleAgentSelect' class='console-agent-sel' title='AI 后端'></select>" +
        "<button class='btn btn-sm' id='btnConsoleChatFull' title='对话窗口全屏/还原'>" + (S.consoleChatFull ? "⤢ 还原" : "⤢ 全屏") + "</button>" +
        "<button class='btn btn-sm' id='btnConsoleChatClear' title='清空该项目的对话记录'>清空</button></div>" +
        "<div class='console-chat'><div class='chat-msgs' id='consoleChatMsgs'></div>" +
        "<div class='chat-input'><input id='consoleChatInput' placeholder='向该项目的 AI 助手下达指令…' autocomplete='off'>" +
        "<button class='btn btn-primary' id='consoleChatSend'>发送</button></div></div>" +
        "</div>";

      html += "</div>";
      box.innerHTML = html;
      document.querySelector(".app").classList.toggle("chat-focus", !!S.consoleChatFull);
      const ref = $("btnConsoleRefresh");
      if (ref) ref.addEventListener("click", renderConsole);
      box.querySelectorAll(".proj-row").forEach((row) => {
        row.addEventListener("click", () => openDrawer(row.dataset.pid));
      });
      box.querySelectorAll(".ai-badge[data-pid]").forEach((b) => {
        b.addEventListener("click", () => openDrawer(b.dataset.pid));
      });
      const batch = $("btnBatchRun");
      if (batch) batch.addEventListener("click", runBatch);
      // 总控台 AI 助手对话
      const projSel = $("consoleAgentProject");
      const agentSel = $("consoleAgentSelect");
      if (agentSel) {
        S.agents.forEach((a) => {
          const o = document.createElement("option");
          o.value = a.name; o.textContent = a.label;
          if (a.name === S.settings.agent) o.selected = true;
          agentSel.appendChild(o);
        });
      }
      if (projSel) {
        const first = projSel.value || (projSel.options.length ? projSel.options[0].value : null);
        if (S.consoleChatProject && projSel.querySelector('[value="' + CSS.escape(S.consoleChatProject) + '"]')) projSel.value = S.consoleChatProject;
        else if (first) S.consoleChatProject = first;
        projSel.addEventListener("change", (e) => {
          S.consoleChatProject = e.target.value;
          renderChat(S.consoleChatProject, "consoleChatMsgs");
        });
      }
      if (S.consoleChatProject) renderChat(S.consoleChatProject, "consoleChatMsgs");
      const chatSend = $("consoleChatSend");
      if (chatSend) chatSend.addEventListener("click", () => sendChatFor("consoleChatMsgs", S.consoleChatProject, "consoleAgentSelect"));
      const chatInput = $("consoleChatInput");
      if (chatInput) chatInput.addEventListener("keydown", (e) => { if (e.key === "Enter") sendChatFor("consoleChatMsgs", S.consoleChatProject, "consoleAgentSelect"); });
      const fullBtn = $("btnConsoleChatFull");
      if (fullBtn) fullBtn.addEventListener("click", () => {
        S.consoleChatFull = !S.consoleChatFull;
        document.querySelector(".app").classList.toggle("chat-focus", S.consoleChatFull);
        fullBtn.textContent = S.consoleChatFull ? "⤢ 还原" : "⤢ 全屏";
      });
      const clearBtn = $("btnConsoleChatClear");
      if (clearBtn) clearBtn.addEventListener("click", () => {
        if (!S.consoleChatProject) return;
        S.chatSessions[S.consoleChatProject] = { msgs: [], history: [] };
        renderChat(S.consoleChatProject, "consoleChatMsgs");
        toast("已清空该项目对话记录");
      });
    } catch (err) {
      box.innerHTML = "<div class='build-log'>加载失败：" + esc(err.message) + "</div>";
    }
  }

  function appendBatchJob(log, pid, projMap, init) {
    const wrap = document.createElement("div");
    wrap.className = "batch-job";
    wrap.innerHTML =
      "<div class='batch-job-head'><span class='git-dot " + (init.status === "error" ? "dirty" : "run") + "'></span>" +
      "<span class='batch-job-title'>" + esc(projMap[pid] || pid) + "</span>" +
      "<span class='spacer'></span><span class='batch-job-status " + (init.status === "error" ? "err" : init.status === "done" ? "ok" : "") + "'>" + (init.status === "error" ? "启动失败" : "运行中") + "</span></div>" +
      "<div class='batch-job-statusline'></div>" +
      "<details class='batch-job-outwrap'><summary>输出</summary><pre class='batch-job-out'></pre></details>";
    if (init.error) wrap.querySelector(".batch-job-statusline").textContent = init.error;
    log.appendChild(wrap);
    return wrap;
  }

  async function runBatch() {
    const ids = Array.from(document.querySelectorAll(".batch-pick:checked")).map((el) => el.value);
    if (!ids.length) { toast("请先选择至少一个项目", "err"); return; }
    const prompt = $("batchPrompt").value.trim();
    if (!prompt) { toast("请输入指令", "err"); return; }
    const log = $("batchLog");
    if (!log) return;
    const projMap = {};
    S.projects.forEach((p) => { projMap[p.id] = p.title; });
    log.innerHTML = "<div class='build-status'>正在启动 " + ids.length + " 个任务…</div>";
    try {
      const res = await api("/api/agent/batch", { method: "POST", body: { project_ids: ids, prompt: prompt } });
      log.innerHTML = "";
      const states = {};
      res.jobs.forEach((j) => {
        if (j.error) {
          states[j.project_id] = "error";
          appendBatchJob(log, j.project_id, projMap, { status: "error", error: j.error });
          return;
        }
        states[j.project_id] = "running";
        const el = appendBatchJob(log, j.project_id, projMap, { status: "running" });
        const outBox = el.querySelector(".batch-job-out");
        const stLine = el.querySelector(".batch-job-statusline");
        streamEvents("/api/jobs/" + j.job_id + "/stream", (data) => {
          if (data.type === "status") { stLine.textContent = data.text; }
          else if (data.type === "line") {
            if (outBox) {
              outBox.textContent = outBox.textContent ? outBox.textContent + "\n" + data.text : data.text;
              outBox.scrollTop = outBox.scrollHeight;
            }
          }
          if (data.type === "end") {
            const head = el.querySelector(".batch-job-status");
            if (data.status === "done") { head.textContent = "完成"; head.className = "batch-job-status ok"; }
            else { head.textContent = "失败"; head.className = "batch-job-status err"; }
            stLine.textContent = data.error || "";
            states[j.project_id] = data.status;
          }
        }, () => {
          const head = el.querySelector(".batch-job-status");
          if (states[j.project_id] === "running") { head.textContent = "已结束"; head.className = "batch-job-status"; }
        });
      });
      toast("批量任务已启动，实时进度见下方");
      setTimeout(() => renderConsole(), 5000);
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
    const scheme = versions.scheme || "semver";
    const verBlock = (title, inner, openDefault) =>
      "<div class='ver-block collapsible" + (openDefault ? "" : " collapsed") + "'>" +
        "<div class='ver-head' role='button' tabindex='0'><span class='caret'>▶</span><h4>" + title + "</h4></div>" +
        "<div class='ver-body'><div class='ver-body-inner'>" + inner + "</div></div>" +
      "</div>";

    let html = "";
    html += "<div class='ver-head-row'>" +
      "<span class='ver-scheme-badge'>版本方案：" + esc(schemeLabel(scheme)) + "</span>" +
      "<span class='spacer'></span>" +
      "<button class='btn btn-sm' id='btnToggleAll'>全部展开</button>" +
      (scheme === "semver" ? "<button class='btn btn-primary btn-sm' id='btnReleaseWizard'>发布向导</button>" : "") +
      "</div>";

    let curInner;
    if (scheme === "archive") {
      curInner = "<div class='ov-sub'>日期归档型：版本以归档批次体现（archive/v&lt;序号&gt;_&lt;YYYYMMDD&gt;）</div>";
    } else if (scheme === "none") {
      curInner = "<div class='ov-sub'>该类型不追踪版本（可在「编辑信息」中切换版本方案）</div>";
    } else if (scheme === "upstream") {
      curInner = versions.version
        ? "<div class='ov-version'>v" + esc(versions.version) + "</div><div class='ov-sub'>上游仓库版本（只读展示）</div>"
        : "<div class='ov-sub'>上游仓库：未发现 VERSION 文件（只读展示）</div>";
    } else {
      curInner = versions.version ? "<div class='ov-version'>v" + esc(versions.version) + "</div>" : "<div class='ov-sub'>项目根目录没有 VERSION 文件</div>";
    }
    html += verBlock("当前版本", "<div class='overview-hero' style='margin-bottom:0'>" + curInner + "</div>", true);

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
      clHtml = "<div class='build-log'>" + ((scheme === "archive" || scheme === "none")
        ? "（本类型不追踪 CHANGELOG；归档批次见「构建产物」）" : "没有找到 CHANGELOG.md") + "</div>";
    }
    html += verBlock("更新日志", clHtml, false);

    const artifacts = versions.artifacts || { versions: [], dist: [], latest: [] };
    const latest = artifacts.latest || [];
    let artHtml = "";
    if (!latest.length && !artifacts.versions.length && !artifacts.dist.length) {
      artHtml = "<div class='build-log'>" + (scheme === "archive"
        ? "没有发现 archive/ 或 versions/ 归档目录" : "没有发现 versions/ 或 dist/ 构建产物") + "</div>";
    } else {
      if (latest.length) {
        artHtml += "<div class='ver-head latest-head'><h4>" + (scheme === "archive" ? "最新归档与交付物" : "最新构建") + "</h4>" +
          "<span class='latest-note'>按修改时间排序（" + (scheme === "archive" ? "归档目录 + dist" : "版本目录 + 根 dist") + "）</span></div>";
        if (artifacts.root_dist_newer) {
          artHtml += "<div class='note-warn'>⚠ 根目录 dist/installer/build 存在比已归档版本更新的构建（未归档）</div>";
        }
        artHtml += latest.map((f) => {
          let badge;
          if (f.source === "versions" || f.source === "archive") {
            badge = "<span class='src-badge archived'>" + esc(f.version || "") + "</span>";
          } else if (scheme === "archive") {
            badge = "<span class='src-badge'>交付物</span>";
          } else {
            badge = "<span class='src-badge unarchived'>未归档</span>";
          }
          return "<div class='artifact'><span class='a-name'>" + esc(f.name) + "</span>" + badge +
            "<span class='a-size'>" + fmtSize(f.size) + "</span><span class='spacer'></span>" +
            "<button class='btn btn-sm' data-open='" + esc(f.path) + "'>打开</button>" +
            "<button class='btn btn-sm' data-reveal='" + esc(f.path) + "'>位置</button>" +
            "<button class='btn btn-sm' data-copy='" + esc(f.path) + "'>复制</button></div>";
        }).join("");
      }
      artifacts.versions.forEach((v) => {
        artHtml += "<div class='cl-entry'><h5>" + esc(v.name) + (v.has_src ? " · 含源码快照" : "") + "</h5>" +
          "<div class='artifact'><span class='a-name'>" + (scheme === "archive" ? "归档目录" : "版本目录") + "</span><span class='spacer'></span>" +
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
          artHtml += "<div class='build-log' style='margin-top:6px'>" + (scheme === "archive" ? "（目录为空）" : "（无 dist 产物）") + "</div>";
        }
        artHtml += "</div>";
      });
      if (artifacts.dist.length) {
        const deliverable = scheme === "archive";
        artHtml += "<div class='ver-head latest-head'><h4>" + (deliverable ? "交付物（dist/）" : "未归档构建（项目根目录 dist/installer/build）") + "</h4>" +
          (deliverable ? "" : "<button class='btn btn-sm' id='btnGoCompliance'>去合规归档</button>") + "</div>";
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
    s = s.replace(/\[!\[([^\]]*)\]\(([^)]+)\)\]\(([^)]+)\)/g, function (m, alt, img, url) {
      const iu = String(img).replace(/["'<>]/g, "");
      const lu = String(url).replace(/["'<>]/g, "");
      return "<a href='" + lu + "' target='_blank' rel='noopener'><img class='md-img' src='" + iu + "' alt='" + esc(alt) + "' loading='lazy'></a>";
    });
    s = s.replace(/!\[([^\]]*)\]\(([^)]+)\)/g, function (m, alt, url) {
      const u = String(url).replace(/["'<>]/g, "");
      return "<img class='md-img' src='" + u + "' alt='" + esc(alt) + "' loading='lazy'>";
    });
    s = s.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, function (m, txt, url) {
      const safe = String(url).replace(/["'<>]/g, "");
      return "<a href='" + safe + "' target='_blank' rel='noopener'>" + txt + "</a>";
    });
    return s;
  }

  /* README 内嵌 HTML 白名单过滤（防 XSS，仅保留安全标签/属性） */
  function sanitizeHtml(raw) {
    const ALLOW_TAGS = new Set(["a","b","blockquote","br","code","del","details","div","em","h1","h2","h3","h4","h5","h6","hr","i","img","li","ol","p","pre","s","span","strong","sub","summary","sup","table","tbody","td","th","thead","tr","ul"]);
    const ALLOW_ATTRS = new Set(["href","src","alt","title","align","width","height","colspan","rowspan","target","rel","loading"]);
    const doc = new DOMParser().parseFromString(String(raw || ""), "text/html");
    const clean = (node) => {
      if (node.nodeType === 3) return node.nodeValue || "";
      if (node.nodeType !== 1) return "";
      const tag = node.tagName.toLowerCase();
      if (!ALLOW_TAGS.has(tag)) {
        let inner = "";
        [...node.childNodes].forEach((c) => { inner += clean(c); });
        return inner;
      }
      let attrs = "";
      [...node.attributes].forEach((a) => {
        const name = a.name.toLowerCase();
        if (!ALLOW_ATTRS.has(name)) return;
        const val = a.value.trim();
        if ((name === "href" || name === "src") && /^\s*(javascript:|vbscript:|data:text\/html)/i.test(val)) return;
        if (name === "href" && !/^(https?:|mailto:|#|\/)/i.test(val)) return;
        attrs += " " + name + '="' + esc(val) + '"';
      });
      let inner = "";
      [...node.childNodes].forEach((c) => { inner += clean(c); });
      return "<" + tag + attrs + ">" + inner + "</" + tag + ">";
    };
    return clean(doc.body);
  }

  function mdToHtml(src) {
    const lines = String(src || "").split("\n");
    let html = "";
    let inCode = false, codeBuf = [], codeLang = "";
    let pdChoice = null;
    let listBuf = [], listType = null;
    let tableBuf = [], inTable = false;
    let quoteBuf = [];
    let htmlBuf = null;
    const flushCode = () => {
      if (codeLang === "pdchoice") {
        try {
          const obj = JSON.parse(codeBuf.join("\n"));
          if (obj && typeof obj.question === "string" && Array.isArray(obj.options) && obj.options.length) pdChoice = obj;
        } catch (e) { pdChoice = null; }
      } else if (codeBuf.length) {
        html += "<pre><code>" + esc(codeBuf.join("\n")) + "</code></pre>";
      }
      codeBuf = [];
      codeLang = "";
    };
    const flushList = () => {
      if (!listBuf.length) return;
      const tag = listType === "ol" ? "ol" : "ul";
      html += "<" + tag + ">" + listBuf.join("") + "</" + tag + ">";
      listBuf = []; listType = null;
    };
    const flushTable = () => {
      if (!tableBuf.length) return;
      const rows = tableBuf;
      tableBuf = [];
      const head = rows[0].map((c) => "<th>" + inlineMd(c) + "</th>").join("");
      let body = "";
      rows.slice(2).forEach((r) => { body += "<tr>" + r.map((c) => "<td>" + inlineMd(c) + "</td>").join("") + "</tr>"; });
      html += "<div class='md-table-wrap'><table><thead><tr>" + head + "</tr></thead>" +
        (body ? "<tbody>" + body + "</tbody>" : "") + "</table></div>";
    };
    const flushQuote = () => {
      if (!quoteBuf.length) return;
      html += "<blockquote>" + quoteBuf.join("<br>") + "</blockquote>";
      quoteBuf = [];
    };
    const flushAll = () => {
      flushCode(); flushList(); flushTable(); flushQuote();
      if (htmlBuf) { html += sanitizeHtml(htmlBuf.buf.join("\n")); htmlBuf = null; }
    };
    const isTableLine = (l) => (String(l).match(/\|/g) || []).length >= 2;
    const isTableSep = (l) => /^\s*\|?[\s:|-]+\|?\s*$/.test(l) && l.indexOf("-") >= 0;
    const splitRow = (l) => String(l).trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
    lines.forEach((line) => {
      const fence = line.match(/^```(\w*)\s*$/);
      if (fence) {
        if (inCode) { inCode = false; flushCode(); }
        else { flushAll(); inCode = true; codeLang = fence[1] || ""; }
        return;
      }
      if (inCode) { codeBuf.push(line); return; }
      if (!line.trim()) { flushAll(); return; }
      const h = line.match(/^(#{1,6})\s+(.*)$/);
      if (h) { flushAll(); html += "<h" + h[1].length + ">" + inlineMd(h[2]) + "</h" + h[1].length + ">"; return; }
      if (/^(-{3,}|\*{3,}|_{3,})$/.test(line.trim())) { flushAll(); html += "<hr>"; return; }
      if (isTableLine(line)) {
        if (inTable && isTableSep(line)) return;
        if (inTable) { tableBuf.push(splitRow(line)); return; }
        flushAll();
        inTable = true;
        tableBuf.push(splitRow(line));
        return;
      }
      if (inTable) { flushTable(); inTable = false; }
      if (htmlBuf) {
        htmlBuf.buf.push(line);
        if (htmlBuf.buf.join(" ").indexOf("</" + htmlBuf.tag + ">") >= 0) {
          html += sanitizeHtml(htmlBuf.buf.join("\n"));
          htmlBuf = null;
        }
        return;
      }
      const open = line.match(/^\s*<([a-zA-Z][a-zA-Z0-9-]*)(\s[^>]*)?>\s*$/);
      if (open) {
        flushAll();
        if (line.indexOf("</" + open[1] + ">") >= 0 || /\/\s*>$/.test(line)) {
          html += sanitizeHtml(line);
        } else {
          htmlBuf = { tag: open[1], buf: [line] };
        }
        return;
      }
      const li = line.match(/^\s*([-*+])\s+(.*)$/);
      if (li) {
        if (listType !== "ul") { flushList(); listType = "ul"; }
        listBuf.push("<li>" + inlineMd(li[2]) + "</li>");
        return;
      }
      const ol = line.match(/^\s*\d+[.)]\s+(.*)$/);
      if (ol) {
        if (listType !== "ol") { flushList(); listType = "ol"; }
        listBuf.push("<li>" + inlineMd(ol[1]) + "</li>");
        return;
      }
      if (listType) flushList();
      const q = line.match(/^\s*>\s?(.*)$/);
      if (q) { quoteBuf.push(inlineMd(q[1])); return; }
      if (quoteBuf.length) flushQuote();
      html += "<p>" + inlineMd(line) + "</p>";
    });
    flushAll();
    if (pdChoice) {
      html += "<div class='choice-card'><div class='choice-q'>" + esc(pdChoice.question || "请选择") + "</div>" +
        "<div class='choice-opts'>" +
        pdChoice.options.map(function (o, i) {
          return "<button class='choice-btn' data-opt='" + i + "'>" + esc(o) + "</button>";
        }).join("") +
        "</div></div>";
    }
    return html;
  }

  function appendChatMessage(kind, text, wrapId) {
    const wrap = $(wrapId || "chatMsgs");
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

  /* 会话状态：每个项目独立的对话记录（msgs=展示，history=给 agent 的上下文） */
  function chatSession(pid) {
    if (!S.chatSessions[pid]) S.chatSessions[pid] = { msgs: [], history: [] };
    return S.chatSessions[pid];
  }

  function sessionHistory(pid) {
    return chatSession(pid).history.slice(-12);
  }

  function chatContextFor(wrapId) {
    if (wrapId === "chatMsgs") return { projectId: S.current ? S.current.id : null, agentSel: "agentSelect" };
    if (wrapId === "consoleChatMsgs") return { projectId: S.consoleChatProject, agentSel: "consoleAgentSelect" };
    return { projectId: null, agentSel: "agentSelect" };
  }

  function renderChat(pid, wrapId) {
    const wrap = $(wrapId);
    if (!wrap || !pid) return;
    const s = chatSession(pid);
    wrap.innerHTML = "";
    if (!s.msgs.length) {
      const hint = document.createElement("div");
      hint.className = "chat-hint";
      hint.textContent = "用自然语言向 AI 项目助手下达要求。任务将在当前项目目录中执行，输出实时回显；当 agent 需要你决策时，回复中会出现可点击的选项卡片。";
      wrap.appendChild(hint);
    }
    s.msgs.forEach((m) => {
      const el = appendChatMessage(m.kind, m.text, wrapId);
      if (m.kind === "ai") setAIText(el, m.text);
    });
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
    bindChoices(el, text);
    const btn = el.querySelector(".msg-copy");
    if (btn) btn.onclick = () => {
      navigator.clipboard.writeText(text).then(() => toast("已复制回复"), () => toast("复制失败", "err"));
    };
  }

  /* 解析回复中的 pdchoice 选择卡片并绑定选项点击 */
  function parseChoices(text) {
    const blocks = [];
    const re = /```pdchoice\s*\n([\s\S]*?)\s*```/g;
    let m;
    while ((m = re.exec(String(text || ""))) !== null) {
      try {
        const obj = JSON.parse(m[1]);
        if (obj && typeof obj.question === "string" && Array.isArray(obj.options) && obj.options.length) {
          blocks.push(obj);
        }
      } catch (e) { /* ignore malformed */ }
    }
    return blocks;
  }

  function bindChoices(el, text) {
    const blocks = parseChoices(text);
    if (!blocks.length) return;
    const wrap = el.closest(".chat-msgs");
    const wrapId = wrap ? wrap.id : "chatMsgs";
    const ctx = chatContextFor(wrapId);
    const cards = el.querySelectorAll(".choice-card");
    blocks.forEach((block, bi) => {
      const card = cards[bi];
      if (!card || card.dataset.bound === "1") return;
      card.dataset.bound = "1";
      card.querySelectorAll(".choice-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          if (S._chatRunning[wrapId]) { toast("当前任务运行中，请等待完成", "err"); return; }
          if (!ctx.projectId) { toast("未选择项目", "err"); return; }
          const idx = parseInt(btn.dataset.opt, 10);
          const label = block.options[idx];
          card.classList.add("answered");
          card.querySelectorAll(".choice-btn").forEach((b) => { b.disabled = true; });
          btn.classList.add("chosen");
          const selText = "【选择】" + (block.question || "") + "\n我选择：" + (label || "");
          runPrompt(wrapId, ctx.projectId, ctx.agentSel, selText);
        });
      });
    });
  }

  async function sendChat() {
    await sendChatFor("chatMsgs", S.current ? S.current.id : null, "agentSelect");
  }

  /* 通用发送：从输入框取词并交给 runPrompt */
  async function sendChatFor(wrapId, projectId, agentSelId) {
    if (!projectId) { toast("未选择项目", "err"); return; }
    const inputId = wrapId.replace("Msgs", "Input");
    const input = $(inputId);
    if (!input) return;
    const prompt = input.value.trim();
    if (!prompt) return;
    input.value = "";
    await runPrompt(wrapId, projectId, agentSelId, prompt);
  }

  /* 通用执行：追加用户消息 -> 携带会话历史调用 agent -> 流式回显 -> 存档 */
  async function runPrompt(wrapId, projectId, agentSelId, prompt, agentOverride) {
    if (S._chatRunning[wrapId] || !projectId || !prompt) return;
    const sendId = wrapId.replace("Msgs", "Send");
    const inputId = wrapId.replace("Msgs", "Input");
    const session = chatSession(projectId);
    const prior = sessionHistory(projectId);
    session.msgs.push({ kind: "user", text: prompt });
    session.history.push({ role: "user", text: prompt });
    appendChatMessage("user", prompt, wrapId);
    const agent = agentOverride || $(agentSelId || "agentSelect").value;
    const aiEl = appendChatMessage("ai", "", wrapId);
    aiEl.classList.add("running");
    setAIStatus(aiEl, "正在连接 " + agentLabel(agent) + " …");
    S._chatRunning[wrapId] = true;
    const sb = $(sendId), ib = $(inputId);
    if (sb) sb.disabled = true;
    if (ib) ib.disabled = true;
    let raw = "";
    const finish = () => {
      S._chatRunning[wrapId] = false;
      if (sb) sb.disabled = false;
      if (ib) ib.disabled = false;
    };
    try {
      const res = await api("/api/agent/run", {
        method: "POST",
        body: { project_id: projectId, prompt: prompt, agent: agent, history: prior },
      });
      streamEvents("/api/jobs/" + res.job_id + "/stream", (data) => {
        if (data.type === "status") {
          setAIStatus(aiEl, data.text);
          aiEl.classList.remove("running");
        } else if (data.type === "chunk") {
          setAIStatus(aiEl, "");
          raw += data.text;
          setAIText(aiEl, raw);
          aiEl.classList.remove("running");
          const w = $(wrapId);
          if (w) w.scrollTop = w.scrollHeight;
        } else if (data.type === "line") {
          setAIStatus(aiEl, "");
          raw = raw ? raw + "\n" + data.text : data.text;
          setAIText(aiEl, raw);
          aiEl.classList.remove("running");
          const w = $(wrapId);
          if (w) w.scrollTop = w.scrollHeight;
        }
        if (data.type === "end") {
          aiEl.classList.remove("running");
          setAIStatus(aiEl, "");
          if (!raw && data.error) { raw = "（任务失败：" + data.error + "）"; setAIText(aiEl, raw); }
          else if (!raw) { raw = "（任务已结束，无输出）"; setAIText(aiEl, raw); }
          session.msgs.push({ kind: "ai", text: raw });
          session.history.push({ role: "assistant", text: raw });
          finish();
        }
      }, () => {
        aiEl.classList.remove("running");
        setAIStatus(aiEl, "");
        if (!raw) { raw = "（任务已结束，无输出）"; setAIText(aiEl, raw); }
        session.msgs.push({ kind: "ai", text: raw });
        session.history.push({ role: "assistant", text: raw });
        finish();
      });
    } catch (err) {
      setAIText(aiEl, "（启动失败：" + err.message + "）");
      aiEl.classList.remove("running");
      setAIStatus(aiEl, "");
      finish();
    }
  }

  const TECHSTACK_PROMPT = "请分析当前项目（通读源码、README、CHANGELOG、依赖清单、构建配置等），在项目根目录撰写/更新 TECHSTACK.md 技术栈文档。格式：## 概览 表格（维度|内容：语言/运行时、主要框架、数据存储、前端、构建与打包、测试等）+ ## 核心功能实现（每个关键功能一个 ### 小节，含 **实现逻辑** 与 **技术手段** 两条要点）。要求详细但简明清晰、只写真实存在的内容；不要改动其他文件。完成后报告你分析了哪些文件、归纳了哪些功能。";

  async function renderTechstack() {
    if (!S.current) return;
    const seq = S.drawerSeq;
    const pid = S.current.id;
    const panel = $("panel-techstack");
    if (!panel) return;
    panel.innerHTML = "<div class='build-log'>加载技术栈…</div>";
    try {
      const data = await api("/api/projects/" + encodeURIComponent(pid) + "/techstack");
      if (seq !== S.drawerSeq || !S.current || S.current.id !== pid) return;
      let html = "<div class='ver-head'><h4>技术栈 · " + esc(S.current.title) + "</h4>" +
        "<span class='spacer'></span>" +
        "<button class='btn btn-sm' id='btnTsAi'>🤖 AI 撰写</button>" +
        "<button class='btn btn-sm' id='btnTsEdit'>" + (data.exists ? "编辑" : "填写") + "</button>" +
        "<button class='btn btn-sm' id='btnTsRefresh'>刷新</button></div>";
      if (!data.exists) {
        html += "<div class='ts-empty'>该项目还没有技术栈文档。<br>点击「🤖 AI 撰写」让 agent 分析项目自动填写，或点「填写」手动编写。</div>";
      } else {
        if (data.overview && data.overview.length) {
          html += "<div class='ts-overview'>" + data.overview.map((o) =>
            "<div class='ts-chip'><span class='ts-chip-label'>" + esc(o.label) + "</span><span class='ts-chip-value'>" + esc(o.value) + "</span></div>"
          ).join("") + "</div>";
        }
        if (data.features && data.features.length) {
          html += "<div class='ts-features'>" + data.features.map((f, i) =>
            "<div class='ts-card'><div class='ts-card-title'>" + (i + 1) + ". " + esc(f.title) + "</div>" +
            (f.logic.length ? "<div class='ts-row'><span class='ts-k'>实现逻辑</span><span class='ts-v'>" + f.logic.map(esc).join("<br>") + "</span></div>" : "") +
            (f.means.length ? "<div class='ts-row'><span class='ts-k'>技术手段</span><span class='ts-v'>" + f.means.map(esc).join("<br>") + "</span></div>" : "") +
            "</div>"
          ).join("") + "</div>";
        }
        if (!data.overview.length && !data.features.length) {
          html += "<div class='ts-raw'>" + mdToHtml(data.content || "") + "</div>";
        }
        html += "<details class='ai-detail'><summary>原文（Markdown）</summary><div class='ts-raw'>" + mdToHtml(data.content || "") + "</div></details>";
      }
      panel.innerHTML = html;
      const btnAi = $("btnTsAi");
      if (btnAi) btnAi.addEventListener("click", () => {
        if (!S.current) return;
        showTab("ai");
        runPrompt("chatMsgs", S.current.id, "agentSelect", TECHSTACK_PROMPT);
      });
      const btnEdit = $("btnTsEdit");
      if (btnEdit) btnEdit.addEventListener("click", () => openTsEditor(panel, pid));
      const btnRef = $("btnTsRefresh");
      if (btnRef) btnRef.addEventListener("click", renderTechstack);
    } catch (err) {
      panel.innerHTML = "<div class='build-log'>加载失败：" + esc(err.message) + "</div>";
    }
  }

  function openTsEditor(panel, pid) {
    const path = "/api/projects/" + encodeURIComponent(pid) + "/techstack";
    api(path).then((data) => {
      panel.innerHTML =
        "<div class='ver-head'><h4>编辑技术栈</h4><span class='spacer'></span>" +
        "<button class='btn btn-sm btn-primary' id='btnTsSave'>保存</button>" +
        "<button class='btn btn-sm' id='btnTsCancel'>取消</button></div>" +
        "<div class='ts-editor-hint'>格式：<code>## 概览</code> 表格（维度|内容）+ <code>## 核心功能实现</code>（每个功能一个 <code>###</code> 小节，含 <b>实现逻辑</b> / <b>技术手段</b> 两条要点）。可先点「AI 撰写」自动生成。</div>" +
        "<textarea id='tsEditor' class='ts-editor'>" + esc(data.content || "") + "</textarea>";
      const save = $("btnTsSave");
      if (save) save.addEventListener("click", async () => {
        const content = $("tsEditor").value;
        try {
          await api(path, { method: "PUT", body: { content: content } });
          toast("技术栈已保存");
          renderTechstack();
        } catch (err) { toast(err.message, "err"); }
      });
      const cancel = $("btnTsCancel");
      if (cancel) cancel.addEventListener("click", renderTechstack);
    }).catch((err) => toast(err.message, "err"));
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
    // AI 接入（API Key）
    const apiBase = $("apiBaseInput"), apiModel = $("apiModelInput"), apiKey = $("apiKeyInput");
    if (apiBase) apiBase.value = S.settings.api_base_url || "";
    if (apiModel) apiModel.value = S.settings.api_model || "";
    if (apiKey) {
      apiKey.value = "";
      apiKey.placeholder = S.settings.api_key_set ? "API Key：已配置（留空保持不变）" : "API Key（粘贴后保存）";
    }
    const aiSt = $("aiTestStatus");
    if (aiSt) aiSt.textContent = S.settings.api_configured ? "已配置 ✓" : "未配置";
    loadNamingStyleOptions();
    renderTypeTabsEditor();
    openModal("settings");
    loadGithubAuth();
  }

  /* ============ 命名规范风格（设置） ============ */
  function styleLabel(id) {
    if (!S.namingStyles) return id || "";
    if (id === "auto") return "自动识别";
    const s = (S.namingStyles.styles || []).find((x) => x.id === id);
    return s ? s.label : id;
  }

  function renderNamingHint() {
    const hint = $("namingStyleHint");
    const sel = $("namingStyleSelect");
    if (!hint || !sel || !S.namingStyles) return;
    const v = sel.value;
    if (v === "auto") {
      hint.textContent = "自动识别：按资料库现有项目文件夹选择风格（当前检测：" + styleLabel(S.namingStyles.detected) + "）。";
      return;
    }
    const s = (S.namingStyles.styles || []).find((x) => x.id === v);
    hint.textContent = s ? s.description + "；示例：" + s.example : "";
  }

  async function loadNamingStyleOptions() {
    const form = $("settingsForm");
    const sel = form.elements.naming_style;
    if (!sel) return;
    try {
      S.namingStyles = await api("/api/naming/styles");
    } catch (err) { return; }
    sel.innerHTML = "";
    const autoOpt = document.createElement("option");
    autoOpt.value = "auto";
    autoOpt.textContent = "自动识别（当前检测：" + styleLabel(S.namingStyles.detected) + "）";
    sel.appendChild(autoOpt);
    (S.namingStyles.styles || []).forEach((s) => {
      const o = document.createElement("option");
      o.value = s.id;
      o.textContent = s.label + "（示例：" + s.example + "）";
      sel.appendChild(o);
    });
    sel.value = S.settings.naming_style || "auto";
    renderNamingHint();
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
      const body = {
        root: form.elements.root.value,
        agent: form.elements.agent.value,
        theme: form.elements.theme.value,
        github_auto: form.elements.github_auto.checked,
        github_visibility: form.elements.github_visibility.value,
        backup: form.elements.backup.checked,
        type_tabs: typeTabs,
        confirm_policy: confirmPolicy,
        update_repo: form.elements.update_repo.value.trim(),
      };
      const nsEl = form.elements.naming_style;
      if (nsEl && nsEl.value) body.naming_style = nsEl.value;
      const ab = $("apiBaseInput"), am = $("apiModelInput"), ak = $("apiKeyInput");
      if (ab) body.api_base_url = ab.value.trim();
      if (am) body.api_model = am.value.trim();
      if (ak && ak.value.trim()) body.api_key = ak.value.trim();
      S.settings = await api("/api/settings", { method: "PUT", body });
      S.namingStyles = null;  // 风格可能变化（含自动识别结果），下次打开重新拉取
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
    const wantAi = !!(form.elements.ai_docs && form.elements.ai_docs.checked && S.settings.api_configured);
    const desc = body.description;
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
      if (wantAi) {
        setTimeout(() => {
          showTab("ai");
          const prompt = "请根据这个新项目的用途描述，为它生成/完善项目文档：\n「" + (desc || "（未填写描述，按目录现状推断）") + "」\n" +
            "要求：先查看目录现状；创建或完善 README.md（项目用途、目录结构、快速开始、约定），必要时补充 AGENTS.md；" +
            "用中文，不要编造未实现的内容；完成后简短报告。";
          runPrompt("chatMsgs", created.id, "agentSelect", prompt, "api");
        }, 400);
      }
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
    loadUnmanaged();
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
      const cb = $("newAiDocs");
      const hint = $("aiDocsHint");
      if (cb) {
        cb.checked = false;
        cb.disabled = !S.settings.api_configured;
        if (hint) {
          hint.hidden = false;
          hint.textContent = S.settings.api_configured
            ? "AI 文档：创建后自动读取目录并按用途描述生成/完善 README 等项目文档（API 直连，任务前自动备份）。"
            : "AI 文档：需先在「设置 → AI 接入」粘贴 API Key 后可用。";
        }
      }
      openModal("new");
    });
    $("btnImport").addEventListener("click", () => openModal("import"));
    $("btnSettings").addEventListener("click", openSettings);
    $("btnManageTypes").addEventListener("click", openTypesModal);
    $("btnCheckUpdate").addEventListener("click", checkUpdate);
    $("btnDownloadUpdate").addEventListener("click", downloadAndInstall);
    $("searchInput").addEventListener("input", (e) => { S.search = e.target.value; renderGrid(); });
    const viewSeg = $("viewSeg");
    if (viewSeg) viewSeg.addEventListener("click", (e) => {
      const b = e.target.closest(".seg-btn");
      if (b) setView(b.dataset.view);
    });
    const sortSel = $("sortSelect");
    if (sortSel) {
      sortSel.value = S.sort;
      sortSel.addEventListener("change", (e) => {
        S.sort = e.target.value;
        if (typeof localStorage !== "undefined") localStorage.setItem("pd.sort", S.sort);
        renderGrid();
      });
    }
    $("btnDrawerClose").addEventListener("click", closeDrawer);
    const fullBtn = $("btnDrawerFull");
    if (fullBtn) fullBtn.addEventListener("click", () => {
      const drawer = $("drawer");
      drawer.classList.toggle("full");
      fullBtn.textContent = drawer.classList.contains("full") ? "⛶" : "⤢";
    });
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
    // 图标设置
    const iconAuto = $("btnIconAuto");
    if (iconAuto) iconAuto.addEventListener("click", () => setIconChoice({ mode: "auto", symbol: null }));
    const iconSymbols = $("iconSymbols");
    if (iconSymbols) iconSymbols.addEventListener("click", (e) => {
      const b = e.target.closest(".icon-sym");
      if (b) setIconChoice({ mode: "auto", symbol: parseInt(b.dataset.sym, 10) });
    });
    const iconFile = $("iconFile");
    if (iconFile) iconFile.addEventListener("change", () => {
      const file = iconFile.files && iconFile.files[0];
      if (!file) return;
      if (file.size > 8 * 1024 * 1024) { toast("图片过大（>8MB）", "err"); return; }
      const reader = new FileReader();
      reader.onload = () => {
        setIconChoice({ mode: "upload", data: String(reader.result) });
        const prev = $("iconPreview");
        if (prev) prev.innerHTML = "<img src='" + reader.result + "' alt=''>";
        toast("已选择图片，点击「应用图标」保存");
      };
      reader.readAsDataURL(file);
    });
    const iconApply = $("btnIconApply");
    if (iconApply) iconApply.addEventListener("click", applyIcon);
    $("newForm").addEventListener("submit", createProject);
    $("importForm").addEventListener("submit", importProject);
    $("settingsForm").addEventListener("submit", saveSettings);
    const namingSel = $("namingStyleSelect");
    if (namingSel) namingSel.addEventListener("change", renderNamingHint);
    const aiTest = $("btnAiTest");
    if (aiTest) aiTest.addEventListener("click", async () => {
      const st = $("aiTestStatus");
      const ab = $("apiBaseInput"), ak = $("apiKeyInput");
      if (st) st.textContent = "测试中…";
      try {
        const res = await api("/api/ai/test", { method: "POST", body: {
          base_url: ab ? ab.value.trim() : "",
          api_key: ak && ak.value.trim() ? ak.value.trim() : "",
        }});
        if (st) st.textContent = "连接成功 ✓ 可用模型 " + (res.count || 0) + " 个" + (res.models && res.models.length ? "（如 " + res.models[0] + "）" : "");
      } catch (err) { if (st) st.textContent = "失败：" + err.message; }
    });
    const btnGhRefresh = $("btnGhRefresh");
    if (btnGhRefresh) btnGhRefresh.addEventListener("click", loadGithubAuth);
    const btnGhLogin = $("btnGhLogin");
    if (btnGhLogin) btnGhLogin.addEventListener("click", githubLogin);
    const btnGhLogout = $("btnGhLogout");
    if (btnGhLogout) btnGhLogout.addEventListener("click", githubLogout);
    const ghToken = $("ghTokenInput");
    if (ghToken) ghToken.addEventListener("keydown", (e) => { if (e.key === "Enter") githubLogin(); });
    const editForm = $("editForm");
    if (editForm) editForm.addEventListener("submit", saveEdit);
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




