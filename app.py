
from flask import Flask, jsonify, send_from_directory
import os, requests

app = Flask(__name__, static_folder='static')

# Telegram config from env or hardcoded
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8752642455:AAEpGTSis6YVij46PrePRZnLqWbQ7OBCZvM")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "1033208239")

@app.route("/")
def index():
    # Serve dashboard if exists, else simple page
    try:
        return send_from_directory('static', 'index.html')
    except Exception as e:
        return f"<h1>Avanza Bot Live</h1><p>Dashboard saknas men API funkar: {e}</p><a href='/api/test-telegram'>Testa Telegram</a>"

@app.route("/manifest.json")
def manifest():
    return send_from_directory('static', 'manifest.json')

@app.route("/icon-192.png")
def icon192():
    return send_from_directory('static', 'icon-192.png')

@app.route("/icon-512.png")
def icon512():
    return send_from_directory('static', 'icon-512.png')

@app.route("/api/status")
def status():
    return jsonify({"status": "Bot online", "budget": "500kr", "telegram": "konfigurerad"})

@app.route("/api/health")
def health():
    return jsonify({"ok": True})

@app.route("/api/test-telegram")
def test_telegram():
    try:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": "✅ TEST - Din Avanza-bot funkar! Telegram ar korrekt kopplad. Budget: 500kr/dag. Du far larm har 09-11.",
            "parse_mode": "Markdown"
        }
        r = requests.post(url, json=payload, timeout=15)
        print(f"Telegram send: {r.status_code} {r.text}")
        if r.status_code == 200:
            return jsonify({"ok": True, "message": "Test skickat! Kolla Telegram - du ska ha fått meddelande nu."})
        else:
            return jsonify({"ok": False, "error": f"Telegram API {r.status_code}: {r.text}"}), 500
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
