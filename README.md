

One prompt → Full AI-generated video. Automatically.
Built with **FastAPI** · Deployable on **Render** in minutes.

---

## Project Structure

```
ai-content-automator/
├── main.py                  ← FastAPI app (Render entry point)
├── render.yaml              ← Render deployment config
├── requirements.txt
├── .env.example
└── src/
    ├── scraper.py           ← Step 1: Scrape website
    ├── script_generator.py  ← Steps 2&3: Claude writes script
    ├── email_approval.py    ← Step 4: Email + wait for approval
    ├── video_generator.py   ← Step 5: HeyGen generates video
    ├── webhook_server.py    ← FastAPI server (background mode)
    ├── pipeline.py          ← CLI pipeline runner
    └── demo.py              ← Demo mode (auto-approves)
```

---

## Quick Start (Local)

```bash
# 1. Install
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env — add at minimum: ANTHROPIC_API_KEY

# 3. Run (local dev with auto-reload)
uvicorn main:app --reload

# Open http://localhost:8000
# Swagger docs at http://localhost:8000/docs
```

---

## Deploy to Render

### Option A — render.yaml (Recommended)



```

### Option B — Manual Render Setup

| Setting | Value |
|---------|-------|
| Runtime | Python |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `uvicorn main:app --host 0.0.0.0 --port $PORT` |
| Health Check | `/health` |

### Environment Variables (set in Render dashboard)

| Variable | Required | Where to get |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | ✅ Yes | console.anthropic.com |
| `APP_URL` | ✅ Yes | Your Render URL e.g. `https://ai-automator.onrender.com` |
| `SENDGRID_API_KEY` | Optional | sendgrid.com (free tier) |
| `SENDER_EMAIL` | Optional | Your sending email |
| `REVIEWER_EMAIL` | Optional | Reviewer's email |
| `HEYGEN_API_KEY` | Optional | app.heygen.com/settings |

---

## API Usage

### Start the Pipeline
```bash
curl -X POST https://YOUR-APP.onrender.com/run \
  -H "Content-Type: application/json" \
  -d '{"prompt": "Generate a service intro video for LeftClickTech European market"}'
```



### Check Job Status
```bash
curl https://YOUR-APP.onrender.com/status/abc12345
```

### Approve / Reject (reviewer clicks email link)
```
GET /approve/{job_id}  → shows success page, triggers video generation
GET /reject/{job_id}   → shows rejection page, stops pipeline
```

---

## The Pipeline

```
POST /run  →  [background task starts]
               │
               ▼
         1. SCRAPE leftclicktech.ai/services
               │
               ▼
         2. SEED Claude with scraped data
               │
               ▼
         3. WRITE Script (Claude AI)
               │
               ▼
         4. EMAIL reviewer with approve/reject links
               │  ← pipeline pauses here
               ▼ (on approve click)
         5. GENERATE Video (HeyGen API)
               │
               ▼
            MP4 video saved to output/
```

---

## Flask vs FastAPI — Why FastAPI?

| Feature | Flask | FastAPI ✅ |
|---------|-------|-----------|
| Speed | Sync | Async (faster) |
| Auto API docs | ❌ | ✅ Swagger at /docs |
| Background tasks | Manual threads | Built-in `BackgroundTasks` |
| Type validation | Manual | Automatic (Pydantic) |
| Render compatible | ✅ | ✅ |
| Modern Python | Old style | Modern async/await |

---

## Demo Mode (No email/video keys needed)

```bash
cd src
python demo.py
# Auto-approves after 5 seconds — perfect for presentations
```
