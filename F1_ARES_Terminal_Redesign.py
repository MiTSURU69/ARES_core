"""
ARES Web Frontend Server + Auto Token Generator
"""
import os
import http.server
import socketserver
import threading
import webbrowser
import time
import json
from livekit_api import AccessToken, VideoGrants

PORT = 3000
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

# --- FILL THESE IN ---
LIVEKIT_API_KEY = "APIB4tej5UNRWuB"
LIVEKIT_API_SECRET = "J9HeNaMZ8Iu6Zk1mRfCCSfqq29heJRwDvIsvVMgYxKqD"
LIVEKIT_URL = "wss://ares-core-1s45sexy.livekit.cloud"
# ---------------------

def generate_token():
    token = AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
    token.with_identity("priyangshu")
    token.with_name("Boss")
    token.with_grants(VideoGrants(room_join=True, room="ares-room"))
    return token.to_jwt()

class AresHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=STATIC_DIR, **kwargs)

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == "/token":
            token = generate_token()
            response = json.dumps({"url": LIVEKIT_URL, "token": token}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(response)
        else:
            super().do_GET()

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        super().end_headers()

def open_browser():
    time.sleep(0.8)
    webbrowser.open(f"http://localhost:{PORT}")

def main():
    os.makedirs(STATIC_DIR, exist_ok=True)
    print(f"""
╔══════════════════════════════════════════════════════╗
║  ARES · Web Frontend · v4.2                          ║
║  UI:    http://localhost:{PORT}                        ║
║  Token: http://localhost:{PORT}/token (auto-generated)║
╚══════════════════════════════════════════════════════╝
    """)
    with socketserver.TCPServer(("", PORT), AresHandler) as httpd:
        httpd.allow_reuse_address = True
        threading.Thread(target=open_browser, daemon=True).start()
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nARES UI server shutting down.")

if __name__ == "__main__":
    main()