import json, os
from datetime import datetime
HISTORY_FILE = "history.json"
class HistoryService:
    @staticmethod
    def save_session(mode, topic, response):
        data = {"timestamp": datetime.now().isoformat(), "mode": mode, "topic": topic, "response": response}
        history = []
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r") as f:
                try: history = json.load(f)
                except: history = []
        history.append(data)
        with open(HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=4)
    @staticmethod
    def get_history():
        if os.path.exists(HISTORY_FILE):
            with open(HISTORY_FILE, "r") as f:
                try: return json.load(f)
                except: return []
        return []
