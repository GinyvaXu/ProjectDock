/**
 * spring.js — 轻量弹簧动画引擎（参考 apple-design：从当前值起步、可打断、速度继承）。
 * 数值积分：a = ((goal - value) * k - v * c) / m
 */
(function (global) {
  "use strict";

  const REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function currentVal(el, key) {
    if (key === "opacity") {
      return el.style.opacity === "" ? 1 : parseFloat(el.style.opacity) || 0;
    }
    const t = el.style.transform || "";
    if (key === "tx") { const m = t.match(/translate3d\(([^,]+)px/); return m ? parseFloat(m[1]) : 0; }
    if (key === "ty") { const m = t.match(/translate3d\([^,]+,\s*([^,]+)px/); return m ? parseFloat(m[1]) : 0; }
    if (key === "scale") { const m = t.match(/scale\(([^)]+)\)/); return m ? parseFloat(m[1]) : 1; }
    return 0;
  }

  function applyValues(el, values) {
    const tx = values.tx || 0, ty = values.ty || 0, scale = values.scale != null ? values.scale : 1;
    el.style.transform = "translate3d(" + tx + "px, " + ty + "px, 0) scale(" + scale + ")";
    if (values.opacity != null) el.style.opacity = values.opacity;
  }

  /**
   * 弹簧动画到目标值。从当前显示值起步，因此随时可打断重定向。
   * target: { tx, ty, scale, opacity }
   */
  function springTo(el, target, opts) {
    opts = opts || {};
    const stiffness = opts.stiffness || 220;
    const damping = opts.damping || 26;
    const mass = opts.mass || 1;
    const maxDuration = opts.maxDuration || 1500;
    const onComplete = opts.onComplete || function () {};
    if (REDUCED) { applyValues(el, target); onComplete(); return function () {}; }

    const values = {}, vel = {};
    for (const key in target) { values[key] = currentVal(el, key); vel[key] = 0; }
    let start = 0, raf = 0, cancelled = false;

    function frame(now) {
      if (!start) start = now;
      const dt = Math.min((now - start) / 1000, 1 / 30);
      start = now;
      let moving = false;
      for (const key in target) {
        const goal = target[key];
        const acc = ((goal - values[key]) * stiffness - vel[key] * damping) / mass;
        vel[key] += acc * dt;
        values[key] += vel[key] * dt;
        if (Math.abs(goal - values[key]) > 0.001 || Math.abs(vel[key]) > 0.01) moving = true;
      }
      applyValues(el, values);
      if (moving && now - start < maxDuration) raf = requestAnimationFrame(frame);
      else { applyValues(el, target); if (!cancelled) onComplete(); }
    }
    raf = requestAnimationFrame(frame);
    return function cancel() { cancelled = true; cancelAnimationFrame(raf); };
  }

  /** 入场：从下方淡入 */
  function enter(el, opts) {
    opts = opts || {};
    if (REDUCED) { el.style.opacity = "1"; el.style.transform = ""; return; }
    el.style.opacity = "0";
    el.style.transform = "translate3d(0, " + (opts.distance || 26) + "px, 0) scale(" + (opts.scale || 0.985) + ")";
    const delay = opts.delay || 0;
    if (delay) {
      setTimeout(function () { springTo(el, { ty: 0, scale: 1, opacity: 1 }, opts); }, delay);
    } else {
      springTo(el, { ty: 0, scale: 1, opacity: 1 }, opts);
    }
  }

  /** 抽屉/面板滑入（从右侧） */
  function slideIn(el, opts) {
    opts = opts || {};
    if (REDUCED) { el.style.opacity = "1"; el.style.transform = ""; return; }
    el.style.opacity = "0";
    el.style.transform = "translate3d(" + (opts.from != null ? opts.from : 100) + "px, 0, 0)";
    springTo(el, { tx: 0, opacity: 1 }, opts);
  }

  function slideOut(el, opts) {
    opts = opts || {};
    if (REDUCED) { el.style.opacity = "0"; (opts.onComplete || function () {})(); return; }
    springTo(el, { tx: opts.to != null ? opts.to : 100, opacity: 0 }, opts);
  }

  /** 模态弹出（scale + 上移） */
  function popIn(el, opts) {
    opts = opts || {};
    if (REDUCED) { el.style.opacity = "1"; el.style.transform = ""; return; }
    el.style.opacity = "0";
    el.style.transform = "translate3d(0, -10px, 0) scale(0.94)";
    springTo(el, { ty: 0, scale: 1, opacity: 1 }, opts);
  }

  function popOut(el, opts) {
    opts = opts || {};
    if (REDUCED) { el.style.opacity = "0"; (opts.onComplete || function () {})(); return; }
    springTo(el, { scale: 0.96, opacity: 0 }, opts);
  }

  /** 简单淡入（减动效回退） */
  function fadeIn(el) { el.style.opacity = "1"; }

  global.Spring = { springTo, enter, slideIn, slideOut, popIn, popOut, fadeIn };
})(window);
