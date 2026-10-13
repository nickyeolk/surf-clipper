"""T001 (d): serve a review copy with HTTP Range from WSL2 and measure seek latency in a browser.

Usage: python scripts/spikes/t001_seek_server.py artifacts/spikes/t001/review.mp4
Then open http://localhost:8765/ in a Windows browser; results appear on the page and at /results.
"""

from __future__ import annotations

import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

VIDEO = Path(sys.argv[1]).resolve()
app = FastAPI()
results: dict[str, object] = {}

PAGE = """<!doctype html><meta charset=utf-8><title>Seek test</title>
<style>body{font:14px system-ui;margin:16px}video{width:640px;display:block}</style>
<video id=v src="/video.mp4" muted preload=auto></video><pre id=out>running…</pre>
<script>
const v = document.getElementById('v'), out = document.getElementById('out');
// Visible page: time until the frame is presented. Hidden page (no rendering): time until the
// seek completes with decoded data (readyState >= 2), a slightly optimistic proxy.
const frame = () => document.hidden
  ? new Promise(r => v.addEventListener('seeked', function h() {
      if (v.readyState >= 2) { v.removeEventListener('seeked', h); r(); }
      else v.addEventListener('canplay', r, {once: true}); }, {once: true}))
  : new Promise(r => v.requestVideoFrameCallback((_, m) => r(m)));
async function seekTo(t) {
  const t0 = performance.now(); const f = frame(); v.currentTime = t; await f;
  return performance.now() - t0;
}
(async () => {
  await new Promise(r => v.readyState >= 1 ? r() : v.addEventListener('loadedmetadata', r, {once:true}));
  const dur = v.duration, seeks = [], fwd = [], back = [];
  for (let i = 0; i < 20; i++) seeks.push(await seekTo(Math.random() * (dur - 5)));
  const fps = 30, base = dur * 0.4;
  await seekTo(base);
  for (let i = 1; i <= 10; i++) fwd.push(await seekTo(base + i / fps));
  for (let i = 9; i >= 0; i--) back.push(await seekTo(base + i / fps));
  const st = a => { const s = [...a].sort((x,y)=>x-y);
    return {median: s[s.length>>1].toFixed(0), max: s[s.length-1].toFixed(0)}; };
  const res = {duration_s: dur.toFixed(0), random_seek_ms: st(seeks),
               step_forward_ms: st(fwd), step_back_ms: st(back),
               mode: document.hidden ? 'hidden (seeked+decoded)' : 'visible (frame presented)',
               ua: navigator.userAgent};
  out.textContent = JSON.stringify(res, null, 2);
  fetch('/results', {method:'POST', headers:{'content-type':'application/json'}, body: JSON.stringify(res)});
})();
</script>"""


@app.get("/")
def page() -> HTMLResponse:
    return HTMLResponse(PAGE)


@app.get("/video.mp4")
def video() -> FileResponse:
    return FileResponse(VIDEO, media_type="video/mp4")


@app.post("/results")
async def post_results(request: Request) -> dict[str, str]:
    results.update(await request.json())
    return {"ok": "1"}


@app.get("/results")
def get_results() -> JSONResponse:
    return JSONResponse(results)


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")
