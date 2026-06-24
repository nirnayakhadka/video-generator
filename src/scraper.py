# ========================================
# STEP 1: SCRAPER
# Scrapes LeftClickTech services page
# and returns clean structured text
# ========================================

import requests
from bs4 import BeautifulSoup
import re


def scrape_website(url: str) -> dict:
    """
    Scrapes the given URL and returns clean structured text.
    
    Args:
        url: Website URL to scrape
        
    Returns:
        dict with 'success', 'content', 'title', 'error'
    """
    print(f"\n[STEP 1] 🌐 Scraping website: {url}")

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }

        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Remove unwanted tags
        for tag in soup(["script", "style", "nav", "footer",
                          "header", "meta", "noscript", "iframe"]):
            tag.decompose()

        # Get page title
        title = soup.find("title")
        page_title = title.get_text(strip=True) if title else "LeftClickTech"

        # Extract main content
        main_content = ""

        # Try to find main content areas
        content_tags = soup.find_all(
            ["main", "article", "section", "div"],
            class_=re.compile(
                r"(content|service|main|about|feature|card|text|body)",
                re.I
            )
        )

        if content_tags:
            for tag in content_tags:
                text = tag.get_text(separator=" ", strip=True)
                if len(text) > 100:  # Only meaningful content
                    main_content += text + "\n\n"
        else:
            # Fallback: get all body text
            body = soup.find("body")
            if body:
                main_content = body.get_text(separator=" ", strip=True)

        # Clean the text
        main_content = clean_text(main_content)

        # Limit to avoid token overflow (keep first 3000 chars)
        if len(main_content) > 3000:
            main_content = main_content[:3000] + "..."

        print(f"[STEP 1] ✅ Scraped {len(main_content)} characters from {page_title}")

        return {
            "success": True,
            "title": page_title,
            "content": main_content,
            "url": url,
            "error": None
        }

    except requests.exceptions.RequestException as e:
        print(f"[STEP 1] ❌ Scraping failed: {e}")
        # Return fallback content if scraping fails
        return {
            "success": False,
            "title": "LeftClickTech",
            "content": get_fallback_content(),
            "url": url,
            "error": str(e)
        }


def clean_text(text: str) -> str:
    """Clean and normalize scraped text."""
    # Remove multiple spaces
    text = re.sub(r" +", " ", text)
    # Remove multiple newlines
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Remove very short lines (likely navigation items)
    lines = [line.strip() for line in text.split("\n")]
    lines = [line for line in lines if len(line) > 20]
    return "\n".join(lines).strip()


def get_fallback_content() -> str:
    """Fallback content if scraping fails."""
    return """
    LeftClickTech - IT Services & Solutions
    
    Services:
    - Cloud Infrastructure & Migration
    - Cybersecurity & Compliance (GDPR ready)
    - Managed IT Services
    - Digital Transformation Consulting
    - Software Development & Integration
    - 24/7 Technical Support
    
    Trusted by 200+ companies across Europe.
    GDPR compliant. ISO certified.
    Visit: leftclicktech.ai
    """


# Test the scraper standalone
if __name__ == "__main__":
    result = scrape_website("https://leftclicktech.ai/service/")
    print("\n--- SCRAPED CONTENT ---")
    print(result["content"][:500])
