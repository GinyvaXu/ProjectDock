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

  function cardHTML(p, i) {
    return "<div class='card' data-id='" + esc(p.id) + "' style='opacity:0'>" +
      "<div class='card-top'>" +
        "<span class='badge " + esc(p.type) + "'>" + esc(p.type) + "</span>" +
        (p.version ? "<span class='card-version'>v" + esc(p.version) + "</span>" : "") +
      "</div>" +
      "<h3 class='card-title'>" + esc(p.title) + "</h3>" +
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
    $("empty").hidden = list.length > 0;
    grid.innerHTML = "";
    if (!list.length) return;
    const frag = document.createDocumentFragment();
    list.forEach((p, i) => {
      const el = document.createElement("div");
      el.innerHTML = cardHTML(p, i);
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
    S.currentTab = "overview";
    $("drawerName").textContent = proj.title;
    $("drawerType").textContent = proj.type;
    $("drawerType").className = "badge " + esc(proj.type);
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
      Spring.fadeIn(backdrop);
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
    document.querySelectorAll(".panel").forEach((el) => el.classList.remove("active"));
    $("panel-" + tab).classList.add("active");
    if (tab === "versions" && S.versions) renderVersions();
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
        (proj.created_at ? "<div class='meta-row'><span class='k'>纳入时间</span><span class='v'>" + esc(proj.created_at) + "</span></div>" : "") +
      "</div>" +
      "<div class='action-row'>" +
        "<button class='btn btn-sm' data-act='open'>打开文件夹</button>" +
        "<button class='btn btn-sm' data-act='copy'>复制路径</button>" +
        "<button class='btn btn-sm' data-act='init'>预设初始化</button>" +
        (proj.imported ? "" : "<button class='btn btn-sm btn-danger' data-act='remove'>移除管理</button>") +
      "</div>";
    $("panel-overview").querySelectorAll("[data-act]").forEach((btn) => {
      btn.addEventListener("click", () => handleOverviewAction(btn.dataset.act));
    });
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

  /* ============ 版本与构建 ============ */
  function renderVersions() {
    if (!S.current) return;
    const versions = S.versions || { version: null, changelog: [], artifacts: { versions: [], dist: [] }, has_versions_dir: false, has_dist_dir: false };
    const id = S.current.id;
    let html = "";
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

    html += "<div class='ver-block'><div class='ver-head'><h4>构建产物</h4></div>";
    if (!versions.artifacts.versions.length && !versions.artifacts.dist.length) {
      html += "<div class='build-log'>没有发现 versions/ 或 dist/ 构建产物</div>";
    } else {
      versions.artifacts.versions.forEach((v) => {
        html += "<div class='cl-entry'><h5>" + esc(v.name) + (v.has_src ? " · 含源码快照" : "") + "</h5>";
        if (v.artifacts.length) {
          html += v.artifacts.map((f) =>
            "<div class='artifact'><span class='a-name'>" + esc(f.name) + "</span><span class='a-size'>" + fmtSize(f.size) + "</span>" +
            "<span class='spacer'></span><button class='btn btn-sm' data-copy='" + esc(f.path) + "'>复制路径</button></div>"
          ).join("");
        } else {
          html += "<div class='build-log' style='margin-top:6px'>（无 dist 产物）</div>";
        }
        html += "</div>";
      });
      versions.artifacts.dist.forEach((f) => {
        html += "<div class='artifact'><span class='a-name'>" + esc(f.name) + "</span><span class='a-size'>" + fmtSize(f.size) + "</span>" +
          "<span class='spacer'></span><button class='btn btn-sm' data-copy='" + esc(f.path) + "'>复制路径</button></div>";
      });
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
    panel.querySelectorAll("[data-copy]").forEach((btn) => {
      btn.addEventListener("click", () => {
        navigator.clipboard.writeText(btn.dataset.copy);
        toast("已复制：" + btn.dataset.copy);
      });
    });
    panel.querySelectorAll("[data-build]").forEach((btn) => {
      btn.addEventListener("click", () => runBuild(btn.dataset.build));
    });
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
    streamEvents("/api/jobs/" + jobId + "/stream", (data) => {
      if (data.type === "line") log.textContent += data.text + "\n";
      if (data.type === "end") {
        status.textContent = data.status === "done" ? "构建完成 ✓" : "构建失败：" + (data.error || "");
        status.className = "build-status " + (data.status === "done" ? "ok" : "err");
      }
    }, (err) => {
      if (err && !status.textContent) { status.textContent = "连接中断"; status.className = "build-status err"; }
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
    let jobId = null;
    try {
      const res = await api("/api/agent/run", {
        method: "POST",
        body: { project_id: S.current.id, prompt: prompt, agent: agent },
      });
      jobId = res.job_id;
      aiEl.textContent = "";
      streamEvents("/api/jobs/" + jobId + "/stream", (data) => {
        if (data.type === "line") {
          aiEl.textContent = (aiEl.textContent ? aiEl.textContent + "\n" : "") + data.text;
          aiEl.classList.remove("running");
          $("chatMsgs").scrollTop = $("chatMsgs").scrollHeight;
        }
        if (data.type === "end") {
          aiEl.classList.remove("running");
          if (!aiEl.textContent && data.error) aiEl.textContent = "（任务失败：" + data.error + "）";
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
    $("newType").addEventListener("change", updatePresetHint);
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
    $("settingsForm").elements.root.value = S.settings.root;
    $("settingsForm").elements.agent.value = S.settings.agent;
    $("settingsForm").elements.theme.value = S.settings.theme;
    openModal("settings");
  }

  async function saveSettings(ev) {
    ev.preventDefault();
    const form = ev.target;
    try {
      S.settings = await api("/api/settings", {
        method: "PUT",
        body: { root: form.elements.root.value, agent: form.elements.agent.value, theme: form.elements.theme.value },
      });
      applyTheme(S.settings.theme);
      closeModal("settings");
      toast("设置已保存");
      await refresh();
    } catch (err) { toast(err.message, "err"); }
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
    };
    if (!body.name) return toast("请填写项目名称", "err");
    try {
      const created = await api("/api/projects", { method: "POST", body: body });
      closeModal("new");
      toast("已创建 " + created.name);
      form.reset();
      await refresh();
      openDrawer(created.id);
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
    $("btnNewProject").addEventListener("click", () => openModal("new"));
    $("btnImport").addEventListener("click", () => openModal("import"));
    $("btnSettings").addEventListener("click", openSettings);
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
    $("chatSend").addEventListener("click", sendChat);
    $("chatInput").addEventListener("keydown", (e) => { if (e.key === "Enter") sendChat(); });
    window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
      if (S.settings && S.settings.theme === "system") applyTheme("system");
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        if (!$("drawer").hidden) closeDrawer();
        ["new", "import", "settings"].forEach((n) => { if (!$(n + "Backdrop").hidden) closeModal(n); });
      }
    });
  }

  init().catch((err) => toast("初始化失败：" + err.message, "err"));
})();
