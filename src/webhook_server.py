# ========================================
# FASTAPI WEBHOOK SERVER
# Replaces Flask — faster, async, auto-docs
# Deploy-ready for Render
# ========================================

import os
import threading
import uvicorn
from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from email_approval import set_approval_status, approval_store

app = FastAPI(
    title="AI Content Generation Automator",
    description="Automated pipeline: Scrape → Script → Approve → Video",
    version="1.0.0"
)

# ----------------------------------------
# HTML Pages
# ----------------------------------------
APPROVED_HTML = """
<html><head><title>Approved</title>
<style>
  body{font-family:Arial,sans-serif;display:flex;justify-content:center;
       align-items:center;height:100vh;margin:0;background:#f0f9f0;}
  .box{text-align:center;padding:48px;background:white;border-radius:16px;
       box-shadow:0 4px 24px rgba(0,0,0,0.1);}
  .icon{font-size:72px;} h1{color:#28a745;} p{color:#666;}
</style></head>
<body><div class="box">
  <div class="icon">✅</div>
  <h1>Script Approved!</h1>
  <p>Video generation has started automatically.</p>
  <p>Job: <strong>{job_id}</strong></p>
</div></body></html>
"""

REJECTED_HTML = """
<html><head><title>Rejected</title>
<style>
  body{font-family:Arial,sans-serif;display:flex;justify-content:center;
       align-items:center;height:100vh;margin:0;background:#fff0f0;}
  .box{text-align:center;padding:48px;background:white;border-radius:16px;
       box-shadow:0 4px 24px rgba(0,0,0,0.1);}
  .icon{font-size:72px;} h1{color:#dc3545;} p{color:#666;}
</style></head>
<body><div class="box">
  <div class="icon">❌</div>
  <h1>Script Rejected</h1>
  <p>The job has been cancelled.</p>
  <p>Job: <strong>{job_id}</strong></p>
</div></body></html>
"""

# ----------------------------------------
# Routes
# ----------------------------------------

@app.get("/", response_class=HTMLResponse)
def root():
    return """
    <html><head><title>AI Content Automator</title>
    <style>body{font-family:Arial,sans-serif;max-width:700px;margin:60px auto;padding:20px;}
    h1{color:#333;} code{background:#f4f4f4;padding:2px 6px;border-radius:4px;}
    .badge{display:inline-block;background:#28a745;color:white;padding:4px 12px;
           border-radius:20px;font-size:14px;}</style></head>
    <body>
      <h1>🤖 AI Content Generation Automator</h1>
      <p><span class="badge">Running</span></p>
      <h3>Endpoints</h3>
      <ul>
        <li><code>POST /run</code> — Start the full pipeline</li>
        <li><code>GET /approve/{job_id}</code> — Approve a script</li>
        <li><code>GET /reject/{job_id}</code> — Reject a script</li>
        <li><code>GET /status/{job_id}</code> — Check job status</li>
        <li><code>GET /docs</code> — Interactive API docs (Swagger)</li>
      </ul>
    </body></html>
    """


@app.post("/run")
async def run_pipeline_endpoint(body: dict, background_tasks: BackgroundTasks):
    """
    Start the full 5-step content generation pipeline.

    Body: { "prompt": "Generate a video for LeftClickTech European market" }
    """
    prompt = body.get("prompt", "").strip()
    if not prompt:
        return JSONResponse(
            status_code=400,
            content={"error": "prompt is required"}
        )

    # Import here to avoid circular imports
    from pipeline import run_pipeline
    from email_approval import generate_job_id

    job_id = generate_job_id()

    # Run pipeline in background so API returns immediately
    background_tasks.add_task(run_pipeline, prompt)

    return {
        "message": "Pipeline started",
        "job_id": job_id,
        "prompt": prompt,
        "status": "running",
        "docs": "/docs",
        "check_status": f"/status/{job_id}"
    }


@app.get("/approve/{job_id}", response_class=HTMLResponse)
def approve(job_id: str):
    """Reviewer clicks this link to approve the script."""
    set_approval_status(job_id, "approved")
    return APPROVED_HTML.format(job_id=job_id[:8])


@app.get("/reject/{job_id}", response_class=HTMLResponse)
def reject(job_id: str):
    """Reviewer clicks this link to reject the script."""
    set_approval_status(job_id, "rejected")
    return REJECTED_HTML.format(job_id=job_id[:8])


@app.get("/status/{job_id}")
def get_status(job_id: str):
    """Check the approval status of a job."""
    status = approval_store.get(job_id, "pending")
    return {
        "job_id": job_id,
        "status": status,
        "message": {
            "pending":  "Waiting for reviewer approval",
            "approved": "Script approved — video generating",
            "rejected": "Script rejected by reviewer"
        }.get(status, "Unknown")
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "AI Content Automator"}


# ----------------------------------------
# Start server in background thread
# ----------------------------------------
def start_server(port: int = 5000):
    """Start FastAPI/uvicorn in background thread (non-blocking)."""
    print(f"\n[WEBHOOK] 🚀 Starting FastAPI server on port {port}...")

    def run():
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")

    t = threading.Thread(target=run, daemon=True)
    t.start()
    print(f"[WEBHOOK] ✅ FastAPI running at http://localhost:{port}")
    print(f"[WEBHOOK] 📖 API docs at  http://localhost:{port}/docs")
    return t


# ----------------------------------------
# Run directly (for Render deployment)
# ----------------------------------------
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info")
