# ========================================
# DEMO MODE - Full Pipeline Demo
# Auto-approves after 5 seconds
# Great for presentations!
# ========================================

import os
import sys
import time
import threading
from dotenv import load_dotenv

load_dotenv()


def run_demo():
    """Run the pipeline in demo mode with auto-approval."""

    print("\n" + "🌟"*30)
    print("\n  AI CONTENT GENERATION AUTOMATOR — DEMO MODE")
    print("\n" + "🌟"*30)
    print("\n  This demo auto-approves the script after 5 seconds.")
    print("  In production, a real human reviews and clicks Approve/Reject.\n")

    # Start the webhook server
    from webhook_server import start_server
    start_server(port=5000)
    time.sleep(1)

    # The prompt
    prompt = (
        "Generate a service introduction video of LeftClickTech "
        "catering to the European market."
    )

    # Import pipeline components
    from scraper import scrape_website
    from script_generator import generate_script
    from email_approval import (
        send_approval_email, generate_job_id,
        set_approval_status, save_job
    )
    from video_generator import generate_video

    job_id = generate_job_id()
    target_url = os.getenv("TARGET_URL", "https://leftclicktech.ai/service/")

    print(f"  Job ID: {job_id[:8]}")
    print(f"  Prompt: {prompt}\n")

    # ── STEP 1: SCRAPE ──────────────────────
    print("\n" + "─"*50)
    print("  STEP 1: SCRAPING WEBSITE")
    print("─"*50)
    scraped = scrape_website(target_url)
    print(f"  ✅ Got {len(scraped['content'])} characters of content")

    # ── STEP 2 & 3: SEED + SCRIPT ───────────
    print("\n" + "─"*50)
    print("  STEP 2 & 3: SEEDING + GENERATING SCRIPT")
    print("─"*50)
    script_result = generate_script(scraped, prompt)

    if not script_result["success"]:
        print(f"  ❌ Script generation failed: {script_result['error']}")
        sys.exit(1)

    script = script_result["script"]
    print("\n  📄 GENERATED SCRIPT:")
    print("─"*50)
    print(script)
    print("─"*50)

    # ── STEP 4: EMAIL (AUTO-APPROVE) ─────────
    print("\n" + "─"*50)
    print("  STEP 4: EMAIL APPROVAL")
    print("─"*50)
    send_approval_email(script, prompt, job_id)

    # Auto-approve after 5 seconds for demo
    print("\n  ⏳ [DEMO MODE] Auto-approving in 5 seconds...")
    print("     (In production, reviewer clicks email link)\n")

    def auto_approve():
        time.sleep(5)
        print("\n  🖱️  [DEMO] Simulating reviewer clicking APPROVE...")
        set_approval_status(job_id, "approved")

    threading.Thread(target=auto_approve, daemon=True).start()

    # Wait for approval
    from email_approval import wait_for_approval
    approval = wait_for_approval(job_id, timeout_seconds=30)

    if not approval["approved"]:
        print("  ❌ Not approved. Stopping.")
        sys.exit(1)

    print("  ✅ APPROVED! Proceeding to video generation...")

    # ── STEP 5: VIDEO GENERATION ─────────────
    print("\n" + "─"*50)
    print("  STEP 5: GENERATING VIDEO")
    print("─"*50)
    video_result = generate_video(script, job_id)

    # ── FINAL RESULT ──────────────────────────
    print("\n" + "🎉"*30)
    print("\n  PIPELINE COMPLETE!")
    print("\n" + "🎉"*30)
    print(f"\n  ✅ Script:     Generated successfully")
    print(f"  ✅ Approval:   Received")
    print(f"  ✅ Video:      {video_result.get('video_path', 'Generated')}")

    if video_result.get("simulated"):
        print("\n  ℹ️  Note: Video was simulated.")
        print("     Add HEYGEN_API_KEY to .env for real video generation.")

    print(f"\n  📁 Output files saved in: ./output/")
    print("\n" + "─"*50 + "\n")


if __name__ == "__main__":
    run_demo()
