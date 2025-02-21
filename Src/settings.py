# 21.02.25

import json
from pathlib import Path

class SettingsManager:
    """Manages application settings with JSON persistence"""
    def __init__(self):
        self.settings_file = Path("settings.json")
        self.default_settings = {
            "last_color": "#7e57c2",
            "last_brightness": 75,
            "power_state": False,
            "window_geometry": None,
            "auto_connect": False,
            "last_device": None,
            "last_effect": None,
            "last_effect_speed": 50,
            "last_hsv": (180, 100, 100)  # Default HSV values
        }
        self.settings = self.default_settings.copy()
        
    def load_settings(self):
        try:
            if self.settings_file.exists():
                with open(self.settings_file, 'r') as f:
                    self.settings.update(json.load(f))
        except Exception as e:
            print(f"Settings error: {e}")
            self.reset_settings()

    def save_settings(self):
        try:
            with open(self.settings_file, 'w') as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            print(f"Settings error: {e}")

    def reset_settings(self):
        self.settings = self.default_settings.copy()

def normalize_uuid(uuid_str: str) -> str:
    """Normalize BLE UUID to 4-character format"""
    return uuid_str.lower().replace("-", "")[4:8]