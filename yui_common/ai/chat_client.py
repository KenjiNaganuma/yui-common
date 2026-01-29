# yui_common/ai/chat_client.py
import os
import requests

class YuiAIChatClient:
    def __init__(self, base_url=None):
        self.base_url = base_url or os.getenv("YUI_AI_BASE_URL")
        if not self.base_url:
            raise RuntimeError("YUI_AI_BASE_URL is not set")

    def chat(self, messages, temperature=0.3):
        r = requests.post(
            f"{self.base_url}/chat/",
            json={
                "messages": messages,
                "temperature": temperature
            },
            timeout=60
        )
        r.raise_for_status()
        return r.json()["content"]
