"""
Persistent application settings (loaded folders, etc.).

Stored as JSON in ~/.modular-terrain-planner/settings.json so the last
session's folders are automatically restored on next launch.
"""
import json
import sys
from pathlib import Path
from typing import List


class AppSettings:
    _DIR  = Path.home() / ".modular-terrain-planner"
    _FILE = _DIR / "settings.json"
    _MAX_FOLDERS = 20

    _DEFAULT_PAN_SPEED = 0.008

    def __init__(self) -> None:
        self.recent_folders: List[str] = []
        self.pan_speed: float = self._DEFAULT_PAN_SPEED
        self.theme: str = "auto"  # "auto" | "light" | "dark"

    @staticmethod
    def _system_theme() -> str:
        """Return 'dark' if Windows is set to dark mode, else 'light'."""
        if sys.platform == "win32":
            try:
                import winreg
                key = winreg.OpenKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
                )
                val, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
                winreg.CloseKey(key)
                return "light" if val else "dark"
            except Exception:
                pass
        return "light"

    # ------------------------------------------------------------------
    # Load / save
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Load settings from disk; silently ignores missing / corrupt file."""
        try:
            if self._FILE.exists():
                data = json.loads(self._FILE.read_text(encoding="utf-8"))
                self.recent_folders = [str(f) for f in data.get("recent_folders", [])]
                self.pan_speed = float(data.get("pan_speed", self._DEFAULT_PAN_SPEED))
                if "theme" in data:
                    self.theme = str(data["theme"])
        except Exception:
            pass

    def save(self) -> None:
        """Persist current settings to disk; silently ignores write errors."""
        try:
            self._DIR.mkdir(parents=True, exist_ok=True)
            data = {"recent_folders": self.recent_folders, "pan_speed": self.pan_speed,
                    "theme": self.theme}
            self._FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Folder helpers
    # ------------------------------------------------------------------

    def add_folder(self, folder: str) -> None:
        """Record a folder as recently used and persist immediately."""
        if folder in self.recent_folders:
            self.recent_folders.remove(folder)
        self.recent_folders.insert(0, folder)
        self.recent_folders = self.recent_folders[: self._MAX_FOLDERS]
        self.save()

    def remove_folder(self, folder: str) -> None:
        """Remove a folder from the recent list and persist immediately."""
        self.recent_folders = [f for f in self.recent_folders if f != folder]
        self.save()
