import requests
import base64
import json

class AIChatAPI:
    def __init__(self):
        self.base_url = ""
        self.api_key = ""
        self.model = ""
        self.prompt = ""
        self.proxy = None
        self.extra_params = {}

    def set_config(self, base_url, api_key, model, prompt, proxy=None, extra_params=None):
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.prompt = prompt
        self.proxy = {"http": proxy, "https": proxy} if proxy else None
        self.extra_params = extra_params if extra_params else {}

    def call_api(self, text_content=None, image_path=None):
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        
        messages = []
        # System prompt
        if self.prompt:
            messages.append({"role": "system", "content": self.prompt})
        
        # User content
        content = []
        if text_content:
            content.append({"type": "text", "text": text_content})
        
        if image_path:
            with open(image_path, "rb") as image_file:
                base64_image = base64.b64encode(image_file.read()).decode('utf-8')
            content.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{base64_image}"
                }
            })
        
        if not content:
            return "Error: No content provided"
            
        messages.append({"role": "user", "content": content})

        payload = {
            "model": self.model,
            "messages": messages,
            **self.extra_params
        }

        try:
            response = requests.post(self.base_url, headers=headers, json=payload, proxies=self.proxy, timeout=30)
            response.raise_for_status()
            result = response.json()
            return result['choices'][0]['message']['content']
        except Exception as e:
            return f"API Error: {str(e)}"