# ========================================
# MAIN PIPELINE ORCHESTRATOR
# Connects all 5 steps into one automated flow
#
# Usage:
#   python pipeline.py
#   python pipeline.py "Your custom prompt here"
# ========================================

import os
import sys
import json
import time
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import all pipeline steps
from scraper import scrape_website
from script_generator import generate_script
from email_approval import (
    send_approval_email,
    wait_for_approval,
    generate_job_id,
    save_job
)
from video_generator import generate_video
from webhook_server import start_server


def run_pipeline(user_prompt: str) -> dict:
    """
    Runs the complete 5-step AI Content Generation Pipeline.
    
    Args:
        user_prompt: Natural language prompt from user
        
    Returns:
        dict with final pipeline results
    """

    print("\n" + "="*65)
    print("   🤖 AI CONTENT GENERATION AUTOMATOR")
    print("="*65)
    print(f"   Prompt: {user_prompt}")
    print(f"   Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*65)

    # Generate unique job ID for this run
    job_id = generate_job_id()
    target_url = os.getenv("TARGET_URL", "https://leftclicktech.ai/service/")

    # Track job state
    job_data = {
        "job_id": job_id,
        "prompt": user_prompt,
        "started_at": datetime.now().isoformat(),
        "status": "running",
        "steps": {}
    }

    # ────────────────────────────────────────
    # STEP 1: SCRAPE
    # ────────────────────────────────────────
    print_step_header(1, "SCRAPE", "Extracting content from website")

    scraped = scrape_website(target_url)
    job_data["steps"]["scrape"] = {
        "success": scraped["success"],
        "chars": len(scraped.get("content", "")),
        "url": target_url
    }

    if not scraped["content"]:
        return fail_pipeline(job_data, "Scraping returned empty content")

    # ────────────────────────────────────────
    # STEP 2 & 3: SEED + SCRIPT GENERATION
    # ────────────────────────────────────────
    print_step_header(2, "SEED & SCRIPT", "Generating video script with Claude AI")

    script_result = generate_script(scraped, user_prompt)
    job_data["steps"]["script"] = {
        "success": script_result["success"],
        "error": script_result.get("error")
    }

    if not script_result["success"]:
        return fail_pipeline(job_data, f"Script generation failed: {script_result['error']}")

    script = script_result["script"]
    job_data["script"] = script

    print("\n[PREVIEW] 📄 Script Preview (first 300 chars):")
    print("-" * 50)
    print(script[:300] + "..." if len(script) > 300 else script)
    print("-" * 50)

    # ────────────────────────────────────────
    # STEP 4: EMAIL APPROVAL
    # ────────────────────────────────────────
    print_step_header(4, "EMAIL APPROVAL", "Sending script to reviewer")

    # Send the approval email
    email_result = send_approval_email(script, user_prompt, job_id)
    job_data["steps"]["email"] = {
        "success": email_result["success"],
        "message": email_result.get("message")
    }

    if not email_result["success"]:
        return fail_pipeline(job_data, "Failed to send approval email")

    # Wait for reviewer to click approve/reject
    approval_timeout = int(os.getenv("APPROVAL_TIMEOUT", "300"))
    approval = wait_for_approval(job_id, timeout_seconds=approval_timeout)

    job_data["steps"]["approval"] = {
        "approved": approval["approved"],
        "message": approval["message"]
    }

    if not approval["approved"]:
        job_data["status"] = "rejected"
        save_job(job_id, job_data)
        print(f"\n[PIPELINE] ❌ Pipeline stopped: {approval['message']}")
        return {
            "success": False,
            "job_id": job_id,
            "status": "rejected",
            "message": approval["message"],
            "script": script
        }

    # ────────────────────────────────────────
    # STEP 5: VIDEO GENERATION
    # ────────────────────────────────────────
    print_step_header(5, "VIDEO GENERATION", "Creating final video content")

    video_result = generate_video(script, job_id)
    job_data["steps"]["video"] = {
        "success": video_result["success"],
        "video_url": video_result.get("video_url"),
        "video_path": video_result.get("video_path"),
        "error": video_result.get("error")
    }

    if not video_result["success"]:
        return fail_pipeline(job_data, f"Video generation failed: {video_result['error']}")

    # ────────────────────────────────────────
    # PIPELINE COMPLETE
    # ────────────────────────────────────────
    job_data["status"] = "completed"
    job_data["completed_at"] = datetime.now().isoformat()
    save_job(job_id, job_data)

    print("\n" + "="*65)
    print("   🎉 PIPELINE COMPLETE!")
    print("="*65)
    print(f"   Job ID:     {job_id[:8]}")
    print(f"   Video Path: {video_result.get('video_path', 'N/A')}")
    print(f"   Video URL:  {video_result.get('video_url', 'N/A')}")
    print("="*65 + "\n")

    return {
        "success": True,
        "job_id": job_id,
        "status": "completed",
        "script": script,
        "video_url": video_result.get("video_url"),
        "video_path": video_result.get("video_path"),
        "simulated": video_result.get("simulated", False),
        "job_data": job_data
    }


# ────────────────────────────────────────
# Helper Functions
# ────────────────────────────────────────

def print_step_header(step_num: int, name: str, description: str):
    """Print a formatted step header."""
    print(f"\n{'─'*65}")
    print(f"  STEP {step_num}: {name}")
    print(f"  {description}")
    print(f"{'─'*65}")


def fail_pipeline(job_data: dict, error: str) -> dict:
    """Mark pipeline as failed and return error result."""
    job_data["status"] = "failed"
    job_data["error"] = error
    save_job(job_data["job_id"], job_data)
    print(f"\n[PIPELINE] ❌ FAILED: {error}")
    return {
        "success": False,
        "job_id": job_data["job_id"],
        "status": "failed",
        "error": error
    }


# ────────────────────────────────────────
# Entry Point
# ────────────────────────────────────────
if __name__ == "__main__":

    # Get prompt from command line or use default
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
    else:
        prompt = (
            "Generate a service introduction video of LeftClickTech "
            "catering to the European market."
        )

    # Start webhook server (for approve/reject links)
    start_server(port=5000)
    time.sleep(1)  # Give server a moment to start

    # Run the full pipeline
    result = run_pipeline(prompt)

    # Print final summary
    print("\n📊 FINAL RESULT:")
    print(json.dumps({
        "success": result.get("success"),
        "status": result.get("status"),
        "job_id": result.get("job_id", "")[:8],
        "video_path": result.get("video_path"),
        "video_url": result.get("video_url"),
        "simulated": result.get("simulated", False)
    }, indent=2))
