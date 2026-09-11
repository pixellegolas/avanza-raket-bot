
import requests, os
class TelegramNotifier:
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN", "8752642455:AAEpGTSis6YVij46PrePRZnLqWbQ7OBCZvM")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID", "1033208239")
    def send(self, message: str):
        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            requests.post(url, json={"chat_id": self.chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10)
        except Exception as e:
            print(e)
