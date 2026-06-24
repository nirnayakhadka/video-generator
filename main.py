# ========================================
# RENDER ENTRY POINT
# uvicorn main:app --host 0.0.0.0 --port $PORT
# ========================================

import os
import sys
import json
import asyncio

sys.path.insert(0, "src")

from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
import uvicorn

from scraper import scrape_website
from script_generator import generate_script
from email_approval import (
    send_approval_email, wait_for_approval,
    generate_job_id, set_approval_status,
    save_job, load_job, approval_store
)
from video_generator import generate_video

app = FastAPI(
    title="AI Content Generation Automator",
    description="One prompt → Full AI-generated video.",
    version="2.0.0"
)

# ─────────────────────────────────────────
# In-memory job progress store
# ─────────────────────────────────────────
# structure: { job_id: { "step": int, "label": str, "pct": int, "status": str,
#                        "script": str, "video_url": str, "video_path": str,
#                        "prompt": str, "error": str } }
job_store: dict = {}

def update_progress(job_id: str, pct: int, label: str, status: str = "running", **kwargs):
    if job_id not in job_store:
        job_store[job_id] = {}
    job_store[job_id].update({"pct": pct, "label": label, "status": status, **kwargs})


# ─────────────────────────────────────────
# Background Pipeline
# ─────────────────────────────────────────
async def run_pipeline_background(prompt: str, job_id: str):
    try:
        update_progress(job_id, 5, "Scraping website…", prompt=prompt)

        target_url = os.getenv("TARGET_URL", "https://leftclicktech.ai/service/")
        scraped = scrape_website(target_url)

        update_progress(job_id, 20, "Generating script with AI…")

        script_result = generate_script(scraped, prompt)
        if not script_result["success"]:
            update_progress(job_id, 0, f"Script failed: {script_result['error']}", status="error", error=script_result['error'])
            return

        script = script_result["script"]
        update_progress(job_id, 40, "Awaiting your approval…", status="awaiting_approval", script=script)

        send_approval_email(script, prompt, job_id)
        approval = await wait_for_approval(job_id, timeout_seconds=int(os.getenv("APPROVAL_TIMEOUT", "300")))

        if not approval["approved"]:
            update_progress(job_id, 0, approval["message"], status="rejected")
            return

        update_progress(job_id, 60, "Generating video…")

        # Simulate progress ticks during video generation
        async def tick_progress():
            for pct in [65, 70, 75, 80, 85, 90]:
                await asyncio.sleep(8)
                if job_store.get(job_id, {}).get("status") == "running":
                    update_progress(job_id, pct, "Rendering video frames…")

        tick_task = asyncio.create_task(tick_progress())

        loop = asyncio.get_event_loop()
        video_result = await loop.run_in_executor(None, generate_video, script, job_id)
        tick_task.cancel()

        if not video_result["success"]:
            update_progress(job_id, 0, f"Video failed: {video_result.get('error')}", status="error")
            return

        update_progress(
            job_id, 100, "Video ready!",
            status="done",
            video_url=video_result.get("video_url"),
            video_path=video_result.get("video_path"),
            simulated=video_result.get("simulated", False)
        )

        save_job(job_id, {**job_store[job_id], "job_id": job_id})

    except Exception as e:
        update_progress(job_id, 0, f"Unexpected error: {e}", status="error", error=str(e))


# ─────────────────────────────────────────
# SSE Progress Stream
# ─────────────────────────────────────────
@app.get("/progress/{job_id}")
async def progress_stream(job_id: str):
    async def event_gen():
        last = None
        for _ in range(300):  # max ~5 min at 1s poll
            state = job_store.get(job_id, {})
            payload = json.dumps(state)
            if payload != last:
                yield f"data: {payload}\n\n"
                last = payload
            if state.get("status") in ("done", "error", "rejected"):
                break
            await asyncio.sleep(1)
        yield "data: {\"status\":\"timeout\"}\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ─────────────────────────────────────────
# Video Proxy (serve local mp4 if simulated URL)
# ─────────────────────────────────────────
@app.get("/video/{job_id}")
async def serve_video(job_id: str):
    state = job_store.get(job_id, {})
    path = state.get("video_path", "")
    if path and path.endswith(".mp4") and os.path.exists(path):
        def iter_file():
            with open(path, "rb") as f:
                while chunk := f.read(65536):
                    yield chunk
        return StreamingResponse(iter_file(), media_type="video/mp4")
    return JSONResponse({"error": "Video not available"}, status_code=404)


# ─────────────────────────────────────────
# API Routes
# ─────────────────────────────────────────
@app.post("/run")
async def run_pipeline(body: dict, background_tasks: BackgroundTasks):
    prompt = body.get("prompt", "").strip()
    if not prompt:
        return JSONResponse(status_code=400, content={"error": "prompt is required"})

    job_id = generate_job_id()
    job_store[job_id] = {"pct": 0, "label": "Starting…", "status": "running", "prompt": prompt}
    background_tasks.add_task(run_pipeline_background, prompt, job_id)

    return {"success": True, "job_id": job_id}


@app.get("/approve/{job_id}", response_class=HTMLResponse)
def approve(job_id: str):
    set_approval_status(job_id, "approved")
    return f"""<html><head><title>Approved</title>
<style>body{{font-family:Arial;display:flex;justify-content:center;align-items:center;
height:100vh;margin:0;background:#0a1a0a;color:#e0e0e0;}}
.box{{text-align:center;padding:48px;background:#111f11;border:1px solid #1a3a1a;border-radius:16px;}}
.icon{{font-size:72px;margin-bottom:16px;}} h1{{color:#4ade80;margin-bottom:8px;}}
p{{color:#888;}} a{{color:#4ade80;text-decoration:none;}}</style></head>
<body><div class="box"><div class="icon">✅</div>
<h1>Script Approved</h1>
<p>Video generation has started.<br>Job: <strong>{job_id[:8]}</strong></p>
</div></body></html>"""


@app.get("/reject/{job_id}", response_class=HTMLResponse)
def reject(job_id: str):
    set_approval_status(job_id, "rejected")
    return f"""<html><head><title>Rejected</title>
<style>body{{font-family:Arial;display:flex;justify-content:center;align-items:center;
height:100vh;margin:0;background:#1a0a0a;color:#e0e0e0;}}
.box{{text-align:center;padding:48px;background:#1f1111;border:1px solid #3a1a1a;border-radius:16px;}}
.icon{{font-size:72px;margin-bottom:16px;}} h1{{color:#f87171;margin-bottom:8px;}}
p{{color:#888;}}</style></head>
<body><div class="box"><div class="icon">❌</div>
<h1>Script Rejected</h1>
<p>Pipeline cancelled.<br>Job: <strong>{job_id[:8]}</strong></p>
</div></body></html>"""


@app.get("/status/{job_id}")
def get_status(job_id: str):
    return job_store.get(job_id, {"status": "not_found"})


@app.get("/health")
def health():
    return {"status": "ok", "version": "2.0.0"}


# ─────────────────────────────────────────
# Frontend HTML
# ─────────────────────────────────────────
HOME_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>AI Content Automator</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:        #0c0c14;
    --surface:   #13131f;
    --surface2:  #1a1a2e;
    --border:    #252540;
    --border2:   #32325a;
    --accent:    #7c6af7;
    --accent2:   #a78bfa;
    --green:     #4ade80;
    --red:       #f87171;
    --amber:     #fbbf24;
    --text:      #e4e4f0;
    --muted:     #6b6b8a;
    --mono:      'JetBrains Mono', monospace;
  }

  html { scroll-behavior: smooth; }

  body {
    font-family: 'Inter', sans-serif;
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    line-height: 1.6;
  }

  /* ── Layout ── */
  .container { max-width: 780px; margin: 0 auto; padding: 0 24px 80px; }

  /* ── Header ── */
  header {
    padding: 48px 0 40px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 40px;
  }
  .logo {
    display: flex; align-items: center; gap: 12px; margin-bottom: 8px;
  }
  .logo-icon {
    width: 36px; height: 36px; border-radius: 10px;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    display: flex; align-items: center; justify-content: center;
    font-size: 18px; flex-shrink: 0;
  }
  .logo h1 { font-size: 1.25rem; font-weight: 600; letter-spacing: -0.02em; color: #fff; }
  .tagline { color: var(--muted); font-size: 0.9rem; margin-left: 48px; }

  /* ── Pipeline steps legend ── */
  .steps-legend {
    display: flex; gap: 0; margin-bottom: 36px;
    border: 1px solid var(--border); border-radius: 12px; overflow: hidden;
  }
  .step-pill {
    flex: 1; padding: 10px 6px; text-align: center; font-size: 0.72rem;
    color: var(--muted); border-right: 1px solid var(--border);
    background: var(--surface);
  }
  .step-pill:last-child { border-right: none; }
  .step-pill .s-icon { font-size: 1.1rem; display: block; margin-bottom: 2px; }
  .step-pill .s-label { display: block; }

  /* ── Input card ── */
  .card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 16px;
    padding: 28px;
    margin-bottom: 24px;
  }
  .card-title {
    font-size: 0.75rem; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.08em; color: var(--muted); margin-bottom: 14px;
  }

  textarea {
    width: 100%; background: var(--bg); border: 1px solid var(--border2);
    color: var(--text); border-radius: 10px; padding: 14px 16px;
    font-family: inherit; font-size: 0.95rem; resize: vertical;
    min-height: 88px; line-height: 1.5; transition: border-color .2s;
    outline: none;
  }
  textarea:focus { border-color: var(--accent); }
  textarea::placeholder { color: var(--muted); }

  .run-btn {
    width: 100%; margin-top: 14px;
    background: linear-gradient(135deg, var(--accent), var(--accent2));
    color: #fff; border: none; padding: 14px;
    border-radius: 10px; font-size: 0.95rem; font-weight: 600;
    cursor: pointer; letter-spacing: 0.01em; transition: opacity .15s, transform .1s;
  }
  .run-btn:hover:not(:disabled) { opacity: 0.9; }
  .run-btn:active:not(:disabled) { transform: scale(0.99); }
  .run-btn:disabled { opacity: 0.5; cursor: not-allowed; }

  /* ── Job panel ── */
  .job-panel { display: none; }
  .job-panel.visible { display: block; }

  /* progress bar */
  .progress-wrap {
    background: var(--surface2); border-radius: 8px; height: 8px;
    overflow: hidden; margin: 16px 0 8px;
  }
  .progress-bar {
    height: 100%; border-radius: 8px; width: 0%;
    background: linear-gradient(90deg, var(--accent), var(--accent2));
    transition: width .6s cubic-bezier(.4,0,.2,1);
  }
  .progress-meta {
    display: flex; justify-content: space-between;
    font-size: 0.8rem; color: var(--muted);
  }
  .progress-label { }
  .progress-pct { font-family: var(--mono); font-weight: 500; }

  /* status badge */
  .badge {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 4px 10px; border-radius: 99px; font-size: 0.75rem;
    font-weight: 500; margin-bottom: 16px;
  }
  .badge.running  { background: rgba(124,106,247,.15); color: var(--accent2); border: 1px solid rgba(124,106,247,.3); }
  .badge.approval { background: rgba(251,191,36,.12); color: var(--amber); border: 1px solid rgba(251,191,36,.25); }
  .badge.done     { background: rgba(74,222,128,.12); color: var(--green); border: 1px solid rgba(74,222,128,.25); }
  .badge.error    { background: rgba(248,113,113,.12); color: var(--red); border: 1px solid rgba(248,113,113,.25); }
  .badge.rejected { background: rgba(248,113,113,.12); color: var(--red); border: 1px solid rgba(248,113,113,.25); }
  .dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
  .dot.pulse { animation: pulse 1.4s ease-in-out infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.3} }

  /* ── Approval section ── */
  .approval-section { display: none; }
  .approval-section.visible { display: block; }

  .script-box {
    background: var(--bg); border: 1px solid var(--border);
    border-radius: 10px; padding: 18px 20px; font-size: 0.84rem;
    line-height: 1.7; color: #c4c4d8; max-height: 320px; overflow-y: auto;
    white-space: pre-wrap; font-family: var(--mono); margin-bottom: 18px;
  }
  .script-box::-webkit-scrollbar { width: 4px; }
  .script-box::-webkit-scrollbar-track { background: transparent; }
  .script-box::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 4px; }

  .approval-btns { display: flex; gap: 12px; }
  .btn-approve, .btn-reject {
    flex: 1; padding: 13px; border: none; border-radius: 10px;
    font-size: 0.95rem; font-weight: 600; cursor: pointer;
    transition: opacity .15s, transform .1s;
  }
  .btn-approve { background: rgba(74,222,128,.15); color: var(--green); border: 1px solid rgba(74,222,128,.3); }
  .btn-approve:hover { background: rgba(74,222,128,.25); }
  .btn-reject  { background: rgba(248,113,113,.10); color: var(--red); border: 1px solid rgba(248,113,113,.25); }
  .btn-reject:hover  { background: rgba(248,113,113,.2); }
  .btn-approve:active, .btn-reject:active { transform: scale(0.98); }

  /* ── Video section ── */
  .video-section { display: none; margin-top: 20px; }
  .video-section.visible { display: block; }

  video {
    width: 100%; border-radius: 12px; background: #000;
    border: 1px solid var(--border); display: block;
  }
  .video-label {
    font-size: 0.78rem; color: var(--muted); margin-top: 8px;
    font-family: var(--mono);
  }

  /* simulated video placeholder */
  .sim-box {
    background: var(--surface2); border: 1px dashed var(--border2);
    border-radius: 12px; padding: 40px; text-align: center;
  }
  .sim-box .sim-icon { font-size: 40px; margin-bottom: 12px; }
  .sim-box p { color: var(--muted); font-size: 0.88rem; line-height: 1.6; }
  .sim-box .sim-path { font-family: var(--mono); color: var(--accent2); font-size: 0.8rem; margin-top: 8px; }

  /* ── Divider ── */
  .divider { border: none; border-top: 1px solid var(--border); margin: 36px 0; }

  /* ── History ── */
  #history-section { display: none; }
  #history-section.visible { display: block; }
  .section-title {
    font-size: 0.75rem; font-weight: 600; text-transform: uppercase;
    letter-spacing: 0.08em; color: var(--muted); margin-bottom: 16px;
  }
  .history-list { display: flex; flex-direction: column; gap: 10px; }
  .history-item {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 12px; padding: 16px 20px;
    display: flex; justify-content: space-between; align-items: flex-start;
    gap: 16px;
  }
  .history-item:hover { border-color: var(--border2); }
  .h-left { flex: 1; min-width: 0; }
  .h-prompt {
    font-size: 0.9rem; color: var(--text); font-weight: 500;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
    margin-bottom: 4px;
  }
  .h-meta { font-size: 0.76rem; color: var(--muted); font-family: var(--mono); }
  .h-badge {
    font-size: 0.72rem; font-weight: 600; padding: 3px 8px;
    border-radius: 6px; white-space: nowrap; flex-shrink: 0;
  }
  .h-badge.done     { background: rgba(74,222,128,.12); color: var(--green); }
  .h-badge.error    { background: rgba(248,113,113,.12); color: var(--red); }
  .h-badge.rejected { background: rgba(248,113,113,.12); color: var(--red); }
  .h-badge.running  { background: rgba(124,106,247,.12); color: var(--accent2); }
  .h-badge.awaiting_approval { background: rgba(251,191,36,.1); color: var(--amber); }

  /* scrollbar global */
  ::-webkit-scrollbar { width: 6px; height: 6px; }
  ::-webkit-scrollbar-track { background: transparent; }
  ::-webkit-scrollbar-thumb { background: var(--border2); border-radius: 3px; }
</style>
</head>
<body>
<div class="container">

  <!-- Header -->
  <header>
    <div class="logo">
      <div class="logo-icon">🤖</div>
      <h1>AI Content Automator</h1>
    </div>
    <p class="tagline">One prompt → scrape → AI script → approve → generated video</p>
  </header>

  <!-- Pipeline legend -->
  <div class="steps-legend">
    <div class="step-pill"><span class="s-icon">🌐</span><span class="s-label">Scrape</span></div>
    <div class="step-pill"><span class="s-icon">🧠</span><span class="s-label">Script</span></div>
    <div class="step-pill"><span class="s-icon">✅</span><span class="s-label">Approve</span></div>
    <div class="step-pill"><span class="s-icon">🎬</span><span class="s-label">Generate</span></div>
    <div class="step-pill"><span class="s-icon">▶️</span><span class="s-label">Watch</span></div>
  </div>

  <!-- Prompt card -->
  <div class="card">
    <p class="card-title">New Job</p>
    <textarea id="prompt-input" placeholder="Generate a service introduction video of LeftClickTech catering to the European market."></textarea>
    <button class="run-btn" id="run-btn" onclick="startPipeline()">▶  Start Pipeline</button>
  </div>

  <!-- Active job panel -->
  <div class="job-panel" id="job-panel">
    <div class="card">
      <p class="card-title">Current Job — <span id="job-id-label" style="font-family:var(--mono);color:var(--accent2)"></span></p>

      <span class="badge running" id="status-badge"><span class="dot pulse"></span> <span id="status-text">Starting…</span></span>

      <div class="progress-wrap">
        <div class="progress-bar" id="progress-bar"></div>
      </div>
      <div class="progress-meta">
        <span class="progress-label" id="progress-label">Initialising pipeline</span>
        <span class="progress-pct" id="progress-pct">0%</span>
      </div>

      <!-- Approval UI -->
      <div class="approval-section" id="approval-section" style="margin-top:22px;">
        <p class="card-title" style="margin-bottom:12px;">Generated Script — Review &amp; Decide</p>
        <div class="script-box" id="script-box"></div>
        <div class="approval-btns">
          <button class="btn-approve" onclick="decide('approve')">✅ &nbsp;Approve — Generate Video</button>
          <button class="btn-reject"  onclick="decide('reject')">❌ &nbsp;Reject — Cancel Job</button>
        </div>
      </div>

      <!-- Video -->
      <div class="video-section" id="video-section">
        <div id="video-container"></div>
      </div>
    </div>
  </div>

  <hr class="divider" id="history-divider" style="display:none">

  <!-- History -->
  <div id="history-section">
    <p class="section-title">Previous Jobs</p>
    <div class="history-list" id="history-list"></div>
  </div>

</div>

<script>
// ──────────────────────────────────────────────────────
// State
// ──────────────────────────────────────────────────────
let currentJobId = null;
let currentEs    = null;
const history    = JSON.parse(localStorage.getItem('job_history') || '[]');

// ──────────────────────────────────────────────────────
// Start pipeline
// ──────────────────────────────────────────────────────
async function startPipeline() {
  const prompt = document.getElementById('prompt-input').value.trim();
  if (!prompt) { alert('Enter a prompt first.'); return; }

  const btn = document.getElementById('run-btn');
  btn.disabled = true;
  btn.textContent = '⏳  Starting…';

  // Close any existing SSE
  if (currentEs) { currentEs.close(); currentEs = null; }

  const res  = await fetch('/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ prompt })
  });
  const data = await res.json();

  if (!data.success) {
    alert('Failed to start: ' + (data.error || 'unknown error'));
    btn.disabled = false; btn.textContent = '▶  Start Pipeline';
    return;
  }

  currentJobId = data.job_id;
  showJobPanel(currentJobId, prompt);
  listenToProgress(currentJobId, prompt);
}

// ──────────────────────────────────────────────────────
// Show job panel
// ──────────────────────────────────────────────────────
function showJobPanel(jobId, prompt) {
  document.getElementById('job-panel').classList.add('visible');
  document.getElementById('job-id-label').textContent = jobId.slice(0, 8);
  setProgress(0, 'Starting pipeline…', 'running');
  document.getElementById('approval-section').classList.remove('visible');
  document.getElementById('video-section').classList.remove('visible');
}

// ──────────────────────────────────────────────────────
// SSE listener
// ──────────────────────────────────────────────────────
function listenToProgress(jobId, prompt) {
  const es = new EventSource(`/progress/${jobId}`);
  currentEs = es;

  es.onmessage = (e) => {
    const state = JSON.parse(e.data);
    const status = state.status || 'running';
    const pct    = state.pct   || 0;
    const label  = state.label || '';

    setProgress(pct, label, status);

    // Show script for approval
    if (status === 'awaiting_approval' && state.script) {
      showApproval(state.script);
    }

    // Hide approval once decision is made
    if (status === 'running' && pct > 40) {
      document.getElementById('approval-section').classList.remove('visible');
    }

    // Done → show video
    if (status === 'done') {
      showVideo(jobId, state);
      pushHistory(jobId, prompt, 'done');
      enableNewJob();
      es.close();
    }

    // Terminal failures
    if (status === 'error' || status === 'rejected' || status === 'timeout') {
      pushHistory(jobId, prompt, status);
      enableNewJob();
      es.close();
    }
  };

  es.onerror = () => { es.close(); };
}

// ──────────────────────────────────────────────────────
// UI helpers
// ──────────────────────────────────────────────────────
function setProgress(pct, label, status) {
  document.getElementById('progress-bar').style.width  = pct + '%';
  document.getElementById('progress-pct').textContent  = pct + '%';
  document.getElementById('progress-label').textContent = label;
  document.getElementById('status-text').textContent   = statusLabel(status);

  const badge = document.getElementById('status-badge');
  badge.className = 'badge ' + status;
  const dot = badge.querySelector('.dot');
  dot.className = 'dot' + (['running','awaiting_approval'].includes(status) ? ' pulse' : '');
}

function statusLabel(s) {
  return {
    running:           'Running',
    awaiting_approval: 'Awaiting approval',
    done:              'Complete',
    error:             'Failed',
    rejected:          'Rejected',
    timeout:           'Timed out'
  }[s] || s;
}

function showApproval(script) {
  document.getElementById('script-box').textContent = script;
  document.getElementById('approval-section').classList.add('visible');
}

async function decide(action) {
  if (!currentJobId) return;
  document.getElementById('approval-section').classList.remove('visible');

  // Hit the approve/reject endpoint
  await fetch(`/${action}/${currentJobId}`);

  if (action === 'approve') {
    setProgress(60, 'Generating video…', 'running');
  } else {
    setProgress(0, 'Script rejected — pipeline cancelled.', 'rejected');
  }
}

function showVideo(jobId, state) {
  const sec = document.getElementById('video-section');
  sec.classList.add('visible');
  const container = document.getElementById('video-container');

  if (state.simulated) {
    container.innerHTML = `
      <div class="sim-box">
        <div class="sim-icon">🎬</div>
        <p>Video generated in <strong>simulation mode</strong>.<br>
        Configure a D-ID API key to produce real videos.</p>
        <p class="sim-path">${state.video_path || ''}</p>
      </div>`;
  } else {
    // Real video — try inline player, fall back to URL
    const src = state.video_url && state.video_url !== 'SIMULATED'
      ? state.video_url
      : `/video/${jobId}`;
    container.innerHTML = `
      <video controls autoplay muted playsinline src="${src}"></video>
      <p class="video-label">${src}</p>`;
  }
}

function enableNewJob() {
  const btn = document.getElementById('run-btn');
  btn.disabled = false;
  btn.textContent = '▶  Start New Job';
}

// ──────────────────────────────────────────────────────
// History
// ──────────────────────────────────────────────────────
function pushHistory(jobId, prompt, status) {
  // Remove if already exists (re-push on update)
  const idx = history.findIndex(h => h.jobId === jobId);
  if (idx > -1) history.splice(idx, 1);

  history.unshift({ jobId, prompt, status, ts: new Date().toISOString() });
  if (history.length > 20) history.pop();
  localStorage.setItem('job_history', JSON.stringify(history));
  renderHistory();
}

function renderHistory() {
  if (history.length === 0) return;
  document.getElementById('history-section').classList.add('visible');
  document.getElementById('history-divider').style.display = 'block';

  const list = document.getElementById('history-list');
  list.innerHTML = history.map(h => {
    const short  = h.jobId.slice(0, 8);
    const time   = new Date(h.ts).toLocaleString();
    const labels = { done:'Done', error:'Failed', rejected:'Rejected',
                     running:'In progress', awaiting_approval:'Awaiting approval' };
    return `<div class="history-item">
      <div class="h-left">
        <div class="h-prompt" title="${esc(h.prompt)}">${esc(h.prompt)}</div>
        <div class="h-meta">${short} &nbsp;·&nbsp; ${time}</div>
      </div>
      <span class="h-badge ${h.status}">${labels[h.status] || h.status}</span>
    </div>`;
  }).join('');
}

function esc(s) {
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// ──────────────────────────────────────────────────────
// Init
// ──────────────────────────────────────────────────────
renderHistory();
</script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def home():
    return HOME_HTML


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)