"""
Persistent application settings (loaded folders, etc.).

Stored as JSON in ~/.modular-terrain-planner/settings.json so the last
session's folders are automatically restored on next launch.
"""
import json
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
        except Exception:
            pass

    def save(self) -> None:
        """Persist current settings to disk; silently ignores write errors."""
        try:
            self._DIR.mkdir(parents=True, exist_ok=True)
            data = {"recent_folders": self.recent_folders, "pan_speed": self.pan_speed}
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
