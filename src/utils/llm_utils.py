# src/utils/llm_utils.py

import os
import json
import requests
from fastapi import HTTPException

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_URL = os.getenv(
    "GEMINI_CHAT_URL",
    "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
)

def call_gemini(prompt: str) -> str:
    if not GEMINI_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="GEMINI_API_KEY is not set in environment variables.",
        )

    headers = {
        "Content-Type": "application/json",
        "X-goog-api-key": GEMINI_API_KEY,
    }

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt}
                ]
            }
        ]
    }

    resp = requests.post(GEMINI_URL, headers=headers, json=payload)

    if resp.status_code != 200:
        raise HTTPException(
            status_code=500,
            detail=f"Gemini API error: {resp.status_code} {resp.text}",
        )

    try:
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected Gemini response: {json.dumps(resp.json())[:500]}",
        )
