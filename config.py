import os
import json
import copy

SETTINGS_FILE = "settings.json"

# 默认全局配置
DEFAULT_GLOBAL_CONFIG = {
    "api_url": "https://api.openai.com/v1/chat/completions",
    "api_key": "sk-xxx",
    "model": "gpt-4o",
    "prompt": "请翻译以下内容：",
    "proxy": "",
    "custom_params": "{}",
    "ocr_engine": "tesseract",
    "ocr_lang": "eng+jpn",
    "tesseract_path": r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    "window_style": {
        "font_size": 12,
        "top_opacity": 0.9,
        "hover_opacity": 1.0,
        "text_color": "#000000",
        "text_bg_color": "#FFFFFFCC",
        "text_border_color": "#FF0000",
        "enable_text_border": False,
        "auto_save_state": True,
        "top_bg_color": "#2B2B2B"
    },
    "auto_mode": {
        "enabled": False, 
        "interval":5,
        "interrupt_on_manual": True
    },
    "paddle": {
        "close_on_exit": True
    },
    "close_to_tray": True
}

# 默认窗口配置
DEFAULT_WINDOW_CONFIG = {
    "window_style": {
        "width": 400,
        "height": 300,
        "lock_size": False
    },
    "region": {"x": 0, "y": 0, "w": 1920, "h": 1080},
    "shortcuts": {
        "screenshot": "ctrl+alt+q",
        "translate_area": "ctrl+alt+t",
        "retry": "ctrl+alt+r",
        "toggle_indicator": "ctrl+alt+e",
        "select_area": "ctrl+alt+a"
    },
    "show_indicator": True,
    "win_pos": {"x": 100, "y": 100}
}

class SettingsManager:
    def __init__(self):
        self.data = {}
        self.load()

    def load(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
                    if 'global' not in self.data:
                        self.data['global'] = DEFAULT_GLOBAL_CONFIG.copy()
                    g = self.data['global']
                    for key, val in DEFAULT_GLOBAL_CONFIG.items():
                        if key not in g: g[key] = val
                    if 'shortcuts' in g: del g['shortcuts']
                    ws = g.setdefault('window_style', {})
                    for key, val in DEFAULT_GLOBAL_CONFIG['window_style'].items():
                        if key not in ws: ws[key] = val
                    if 'windows' not in self.data:
                        self.data['windows'] = []
                        if 'profiles' in self.data:
                            for p in self.data['profiles']:
                                new_w = DEFAULT_WINDOW_CONFIG.copy()
                                new_w['shortcuts'] = p.get('shortcuts', DEFAULT_WINDOW_CONFIG['shortcuts']).copy()
                                if 'region' in p: new_w['region'] = p['region']
                                if 'window_style' in p: new_w['window_style'] = p['window_style']
                                self.data['windows'].append(new_w)
                            if 'profiles' in self.data: del self.data['profiles']
                        if not self.data['windows']:
                            self.data['windows'].append(copy.deepcopy(DEFAULT_WINDOW_CONFIG))
                    for w in self.data['windows']:
                        if 'window_style' not in w: w['window_style'] = {}
                        ws_local = w['window_style']
                        if 'width' not in ws_local: ws_local['width'] = DEFAULT_WINDOW_CONFIG['window_style']['width']
                        if 'height' not in ws_local: ws_local['height'] = DEFAULT_WINDOW_CONFIG['window_style']['height']
                        if 'lock_size' not in ws_local: ws_local['lock_size'] = False
                        if 'shortcuts' not in w: w['shortcuts'] = DEFAULT_WINDOW_CONFIG['shortcuts'].copy()
                        if 'region' not in w: w['region'] = DEFAULT_WINDOW_CONFIG['region']
                        if 'show_indicator' not in w: w['show_indicator'] = DEFAULT_WINDOW_CONFIG['show_indicator']
                        if 'win_pos' not in w: w['win_pos'] = DEFAULT_WINDOW_CONFIG['win_pos']
            except Exception as e:
                print(f"Config Load Error: {e}")
                self.data = {'global': DEFAULT_GLOBAL_CONFIG.copy(), 'windows': [copy.deepcopy(DEFAULT_WINDOW_CONFIG)]}
        else:
            self.data = {'global': DEFAULT_GLOBAL_CONFIG.copy(), 'windows': [copy.deepcopy(DEFAULT_WINDOW_CONFIG)]}
        self.save()

    def save(self):
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=4, ensure_ascii=False)