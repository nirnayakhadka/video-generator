# ========================================
# STEP 5: VIDEO GENERATOR
# Uses D-ID API to generate final video
# from the approved script
# ========================================

import os
import time
import requests
import json
import base64
from dotenv import load_dotenv

load_dotenv()

DID_API_BASE = "https://api.d-id.com"


def generate_video(script: str, job_id: str) -> dict:
    print(f"\n[STEP 5] 🎬 Starting video generation (Job: {job_id[:8]})")

    did_key = os.getenv("DID_API_KEY", "")

    if did_key and did_key != "your-did-key-here":
        return _generate_via_did(script, job_id, did_key)
    else:
        return _simulate_video_generation(script, job_id)


def _generate_via_did(script: str, job_id: str, api_key: str) -> dict:
    try:
        # D-ID uses Basic auth with base64 encoded key
        encoded_key = base64.b64encode(f"{api_key}:".encode()).decode()
        headers = {
            "Authorization": f"Basic {encoded_key}",
            "Content-Type": "application/json"
        }

        voiceover_text = extract_voiceover_text(script)

        payload = {
            "script": {
                "type": "text",
                "input": voiceover_text,
                "provider": {
                    "type": "microsoft",
                    "voice_id": "en-US-JennyNeural"
                }
            },
            "source_url": "https://clips-presenters.d-id.com/amy/image.png",
            "config": {
                "fluent": True,
                "pad_audio": 0.0
            }
        }

        print("[STEP 5] 📤 Submitting video job to D-ID...")

        response = requests.post(
            f"{DID_API_BASE}/talks",
            headers=headers,
            json=payload,
            timeout=30
        )

        if response.status_code not in [200, 201]:
            raise Exception(f"D-ID API error: {response.status_code} - {response.text}")

        data = response.json()
        talk_id = data.get("id")

        if not talk_id:
            raise Exception("No talk id returned from D-ID")

        print(f"[STEP 5] ⏳ Video submitted. ID: {talk_id}")
        print("[STEP 5]    Waiting for video to render (1-2 minutes)...")

        return _poll_did_status(talk_id, job_id, headers)

    except Exception as e:
        print(f"[STEP 5] ❌ D-ID video generation failed: {e}")
        return _simulate_video_generation(script, job_id)


def _poll_did_status(talk_id: str, job_id: str,
                      headers: dict, max_wait: int = 300) -> dict:
    start = time.time()
    poll_interval = 10

    while time.time() - start < max_wait:
        try:
            response = requests.get(
                f"{DID_API_BASE}/talks/{talk_id}",
                headers=headers,
                timeout=15
            )

            data = response.json()
            status = data.get("status")

            print(f"[STEP 5] 🔄 Video status: {status}")

            if status == "done":
                video_url = data.get("result_url")
                print(f"[STEP 5] ✅ Video ready: {video_url}")
                video_path = download_video(video_url, job_id)
                return {
                    "success": True,
                    "video_url": video_url,
                    "video_path": video_path,
                    "video_id": talk_id,
                    "error": None
                }

            elif status == "error":
                raise Exception(f"D-ID video failed: {data.get('error')}")

            time.sleep(poll_interval)

        except requests.exceptions.RequestException as e:
            print(f"[STEP 5] ⚠️  Poll error: {e}")
            time.sleep(poll_interval)

    raise Exception("Video generation timed out")


def download_video(url: str, job_id: str) -> str:
    os.makedirs("output", exist_ok=True)
    path = f"output/video_{job_id[:8]}.mp4"

    print(f"[STEP 5] 📥 Downloading video to {path}...")

    response = requests.get(url, stream=True, timeout=120)
    with open(path, "wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

    size_mb = os.path.getsize(path) / (1024 * 1024)
    print(f"[STEP 5] ✅ Video downloaded: {path} ({size_mb:.1f} MB)")
    return path


def _simulate_video_generation(script: str, job_id: str) -> dict:
    print("\n[STEP 5] 🎬 SIMULATING VIDEO GENERATION (No D-ID key configured)")

    for i in range(1, 6):
        print(f"[STEP 5] 🔄 Rendering video... {i*20}%")
        time.sleep(1)

    os.makedirs("output", exist_ok=True)
    output_path = f"output/video_{job_id[:8]}_SIMULATED.txt"
    voiceover = extract_voiceover_text(script)

    with open(output_path, "w") as f:
        f.write(f"SIMULATED VIDEO\nJob: {job_id[:8]}\n\nSCRIPT:\n{script}\n\nVOICEOVER:\n{voiceover}")

    print(f"[STEP 5] ✅ Simulation saved: {output_path}")
    return {
        "success": True,
        "video_url": "SIMULATED",
        "video_path": output_path,
        "video_id": f"sim_{job_id[:8]}",
        "simulated": True,
        "error": None
    }


def extract_voiceover_text(script: str) -> str:
    lines = script.split("\n")
    voiceover_parts = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("Voiceover:"):
            text = stripped.replace("Voiceover:", "").strip()
            voiceover_parts.append(text)

    result = " ".join(voiceover_parts)
    return result if result else script[:1000]