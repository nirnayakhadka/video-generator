# ========================================
# STEP 4: EMAIL APPROVAL (Human-in-the-Loop)
# Sends script to reviewer via email
# Waits for approve/reject via webhook
# ========================================

import os
import time
import uuid
import json
import threading
from datetime import datetime
from dotenv import load_dotenv
import asyncio
load_dotenv()

# Global state to track approval status
approval_store = {}


# ----------------------------------------
# Send Approval Email
# ----------------------------------------
def send_approval_email(script: str, user_prompt: str, job_id: str) -> dict:
    """
    Sends the draft script to reviewer for approval.
    
    Args:
        script: The generated video script
        user_prompt: Original user request
        job_id: Unique job identifier
        
    Returns:
        dict with 'success', 'message', 'error'
    """
    print(f"\n[STEP 4] 📧 Sending approval email (Job ID: {job_id})")

    app_url = os.getenv("APP_URL", "http://localhost:8000")
    approve_url = f"{app_url}/approve/{job_id}"
    reject_url  = f"{app_url}/reject/{job_id}"

    email_body = f"""
Hello Reviewer,

A new video script has been generated and requires your approval.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 ORIGINAL REQUEST
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{user_prompt}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎬 GENERATED SCRIPT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
{script}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
YOUR DECISION
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✅ APPROVE (proceed to video generation):
{approve_url}

❌ REJECT (cancel the job):
{reject_url}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Job ID: {job_id}
Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

This is an automated message from the AI Content Automator.
"""

    # Try SendGrid first, fallback to console simulation
    sendgrid_key = os.getenv("SENDGRID_API_KEY", "")

    if sendgrid_key and sendgrid_key != "SG.your-sendgrid-key-here":
        return _send_via_sendgrid(email_body, job_id, approve_url, reject_url)
    else:
        return _simulate_email(email_body, job_id, approve_url, reject_url)


def _send_via_sendgrid(body: str, job_id: str,
                        approve_url: str, reject_url: str) -> dict:
    """Send email using SendGrid API."""
    try:
        import sendgrid
        from sendgrid.helpers.mail import Mail

        sg = sendgrid.SendGridAPIClient(
            api_key=os.getenv("SENDGRID_API_KEY")
        )

        message = Mail(
            from_email=os.getenv("SENDER_EMAIL"),
            to_emails=os.getenv("REVIEWER_EMAIL"),
            subject=f"[APPROVAL NEEDED] Video Script - Job {job_id[:8]}",
            plain_text_content=body
        )

        response = sg.send(message)

        if response.status_code in [200, 201, 202]:
            print(f"[STEP 4] ✅ Email sent to {os.getenv('REVIEWER_EMAIL')}")
            print(f"[STEP 4] 🔗 Approve: {approve_url}")
            print(f"[STEP 4] 🔗 Reject:  {reject_url}")
            return {"success": True, "message": "Email sent via SendGrid", "error": None}
        else:
            raise Exception(f"SendGrid returned status {response.status_code}")

    except Exception as e:
        print(f"[STEP 4] ⚠️  SendGrid failed: {e}, falling back to simulation")
        return _simulate_email(body, job_id, approve_url, reject_url)


def _simulate_email(body: str, job_id: str,
                     approve_url: str, reject_url: str) -> dict:
    """Simulate email sending for demo/testing purposes."""
    print("\n" + "="*60)
    print("📧 EMAIL SIMULATION (No SendGrid key configured)")
    print("="*60)
    print(f"TO:      {os.getenv('REVIEWER_EMAIL', 'reviewer@example.com')}")
    print(f"SUBJECT: [APPROVAL NEEDED] Video Script - Job {job_id[:8]}")
    print("-"*60)
    print(body[:800] + "..." if len(body) > 800 else body)
    print("="*60)
    print(f"\n✅ APPROVE URL: {approve_url}")
    print(f"❌ REJECT  URL: {reject_url}")
    print("="*60 + "\n")

    return {
        "success": True,
        "message": "Email simulated (check console above)",
        "approve_url": approve_url,
        "reject_url": reject_url,
        "error": None
    }


# ----------------------------------------
# Wait for Approval
# ----------------------------------------


async def wait_for_approval(job_id: str, timeout_seconds: int = 300) -> dict:
    print(f"\n[STEP 4] ⏳ Waiting for reviewer approval (timeout: {timeout_seconds}s)...")
    print(f"[STEP 4]    Job ID: {job_id}")

    start_time = time.time()

    while time.time() - start_time < timeout_seconds:
        status = approval_store.get(job_id)

        if status == "approved":
            print("[STEP 4] ✅ Script APPROVED by reviewer!")
            return {"approved": True, "message": "Approved by reviewer"}

        elif status == "rejected":
            print("[STEP 4] ❌ Script REJECTED by reviewer.")
            return {"approved": False, "message": "Rejected by reviewer"}

        await asyncio.sleep(3)  # ← non-blocking

    print("[STEP 4] ⏰ Approval timed out.")
    return {"approved": False, "message": "Approval timed out"}
def set_approval_status(job_id: str, status: str):
    """Called by Flask webhook to set approve/reject."""
    approval_store[job_id] = status
    print(f"[APPROVAL] Job {job_id} marked as: {status.upper()}")


def generate_job_id() -> str:
    """Generate a unique job ID."""
    return str(uuid.uuid4())


# ----------------------------------------
# Save job state to file (for persistence)
# ----------------------------------------
def save_job(job_id: str, data: dict):
    """Save job data to JSON file."""
    os.makedirs("output", exist_ok=True)
    path = f"output/job_{job_id}.json"
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_job(job_id: str) -> dict:
    """Load job data from JSON file."""
    path = f"output/job_{job_id}.json"
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {}
