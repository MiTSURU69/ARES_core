import requests
import os
import subprocess

SARVAM_API_KEY = os.getenv("SARVAM_API_KEY")

def sarvam_stt(audio_path):
    """Converts speech to text using Sarvam's multi-lingual model."""
    url = "https://api.sarvam.ai/speech-to-text"
    files = {"file": open(audio_path, "rb")}
    headers = {"api-subscription-key": SARVAM_API_KEY}
    
    try:
        response = requests.post(url, files=files, headers=headers)
        return response.json().get("transcript", "")
    except: return ""

def sarvam_tts(text):
    """Converts text to multi-lingual speech."""
    url = "https://api.sarvam.ai/text-to-speech"
    payload = {
        "inputs": [text],
        "target_language_code": "en-IN", # Supports hi-IN, kn-IN, etc.
        "speaker": "meera", # Elite Indian female voice
        "model": "bulbul:v1"
    }
    headers = {"Content-Type": "application/json", "api-subscription-key": SARVAM_API_KEY}
    
    try:
        res = requests.post(url, json=payload, headers=headers)
        with open("voice.wav", "wb") as f:
            f.write(res.content)
        subprocess.run(["mpv", "--no-video", "voice.wav"], stdout=subprocess.DEVNULL)
    except Exception as e:
        print(f"TTS Error: {e}")