# ========================================
# STEP 2 & 3: SEED + SCRIPT GENERATOR
# Feeds scraped data to Claude and
# generates a professional video script
# ========================================



from groq import Groq
import os
from dotenv import load_dotenv

load_dotenv()


def generate_script(scraped_content: dict, user_prompt: str) -> dict:
    """
    Takes scraped company data + user prompt and generates a video script.
    
    Args:
        scraped_content: dict from scraper (title, content, url)
        user_prompt: original user prompt e.g. "Generate intro video for European market"
        
    Returns:
        dict with 'success', 'script', 'error'
    """
    print(f"\n[STEP 2] 🧠 Seeding Claude with company data...")
    print(f"[STEP 3] ✍️  Generating video script...")

    try:
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))

        # ----------------------------------------
        # STEP 2: Seed = company data in the prompt
        # STEP 3: Script = Claude writes the script
        # ----------------------------------------
        prompt = f"""
You are a professional video script writer specializing in B2B technology companies.

============================
COMPANY INFORMATION (Source: {scraped_content.get('url', 'leftclicktech.ai')})
============================
{scraped_content.get('content', '')}

============================
USER REQUEST
============================
{user_prompt}

============================
YOUR TASK
============================
Write a professional 45-60 second video script for the above company.

The script MUST follow this exact format:

[SCENE 1 - 0:00 to 0:08]
Visual: [describe what viewers see on screen]
Voiceover: [exact words spoken]

[SCENE 2 - 0:08 to 0:18]
Visual: [describe what viewers see on screen]
Voiceover: [exact words spoken]

[SCENE 3 - 0:18 to 0:30]
Visual: [describe what viewers see on screen]
Voiceover: [exact words spoken]

[SCENE 4 - 0:30 to 0:45]
Visual: [describe what viewers see on screen]
Voiceover: [exact words spoken]

[SCENE 5 - 0:45 to 0:55]
Visual: [describe what viewers see on screen]
Voiceover: [exact words spoken]

[SCENE 6 - 0:55 to 1:00]
Visual: Logo animation with tagline
Voiceover: [closing call to action]

RULES:
- Use professional, confident language
- Tailor tone and references to the target market mentioned in the request
- Mention specific services from the company data
- End with a clear call to action
- Keep voiceover natural and conversational
- Do NOT add any text outside the scene format above
"""
       
        client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",   # or "llama3-70b-8192" for better quality
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1500,
        )
        script = response.choices[0].message.content.strip()
        print(f"[STEP 3] ✅ Script generated ({len(script)} characters)")

        return {
            "success": True,
            "script": script,
            "error": None
        }

    except Exception as e:
        print(f"[STEP 3] ❌ Script generation failed: {e}")
        return {
            "success": False,
            "script": None,
            "error": str(e)
        }


def extract_voiceover(script: str) -> str:
    """
    Extracts only the voiceover lines from the full script.
    Used to send to video generation API.
    """
    lines = script.split("\n")
    voiceover_lines = []

    for line in lines:
        if line.strip().startswith("Voiceover:"):
            text = line.replace("Voiceover:", "").strip()
            voiceover_lines.append(text)

    return " ".join(voiceover_lines)


# Test standalone
if __name__ == "__main__":
    test_content = {
        "title": "LeftClickTech",
        "content": "LeftClickTech provides cloud, cybersecurity, and managed IT services.",
        "url": "https://leftclicktech.ai/service/"
    }
    test_prompt = "Generate a service introduction video targeting the European market."

    result = generate_script(test_content, test_prompt)
    if result["success"]:
        print("\n--- GENERATED SCRIPT ---")
        print(result["script"])
