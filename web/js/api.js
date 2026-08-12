/**
 * api.js — 后端 API 封装（fetch + SSE）。
 */
(function (global) {
  "use strict";

  async function api(path, options) {
    options = options || {};
    const init = {
      method: options.method || "GET",
      headers: { "Content-Type": "application/json" },
    };
    if (options.body !== undefined) init.body = JSON.stringify(options.body);
    const resp = await fetch(path, init);
    if (!resp.ok) {
      let detail = resp.statusText;
      try {
        const j = await resp.json();
        if (j.detail) detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
      } catch (e) { /* ignore */ }
      throw new Error(detail);
    }
    return resp.json();
  }

  /** 订阅 SSE 事件流：onData({type,text,...})，结束时调用 onEnd。 */
  function streamEvents(url, onData, onEnd) {
    return fetch(url)
      .then(function (resp) {
        if (!resp.ok) throw new Error("stream failed: " + resp.status);
        const reader = resp.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buf = "";
        function pump() {
          return reader.read().then(function (res) {
            if (res.done) { if (onEnd) onEnd(); return; }
            buf += decoder.decode(res.value, { stream: true });
            const parts = buf.split("\n\n");
            buf = parts.pop();
            parts.forEach(function (part) {
              part.split("\n").forEach(function (line) {
                if (line.indexOf("data: ") === 0) {
                  try { onData(JSON.parse(line.slice(6))); } catch (e) { /* ignore */ }
                }
              });
            });
            return pump();
          });
        }
        return pump();
      })
      .catch(function (err) {
        if (onEnd) onEnd(err);
      });
  }

  global.API = { api, streamEvents };
})(window);
