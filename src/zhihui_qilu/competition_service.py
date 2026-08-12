"""Competition data service for local JSON storage."""

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class Competition(BaseModel):
    """Competition data model."""
    id: str = Field(default_factory=lambda: str(uuid4())[:8])
    name: str
    category: str
    level: str = "国家级"
    organizer: str = ""
    website: str = ""
    description: str = ""
    teamSize: str = "个人"
    time: str = ""
    registrationDeadline: str = ""
    difficulty: str = "中"
    skills: list[str] = Field(default_factory=list)
    awards: list[str] = Field(default_factory=list)
    tips: str = ""
    isActive: bool = True
    createdAt: str = ""
    updatedAt: str = ""


class CompetitionService:
    """Service for managing competition data with local JSON storage."""

    def __init__(self, data_dir: str | Path = "./data") -> None:
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._file_path = self._data_dir / "competitions.json"
        self._ensure_file()

    def _ensure_file(self) -> None:
        """Ensure the competitions file exists."""
        if not self._file_path.exists():
            self._file_path.write_text("[]", encoding="utf-8")

    def _load(self) -> list[dict[str, Any]]:
        """Load competitions from JSON file."""
        try:
            content = self._file_path.read_text(encoding="utf-8")
            return json.loads(content) if content.strip() else []
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _save(self, competitions: list[dict[str, Any]]) -> None:
        """Save competitions to JSON file."""
        self._file_path.write_text(
            json.dumps(competitions, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

    def get_all(self) -> list[dict[str, Any]]:
        """Get all competitions."""
        return self._load()

    def get_by_id(self, competition_id: str) -> dict[str, Any] | None:
        """Get competition by ID."""
        competitions = self._load()
        return next((c for c in competitions if c.get("id") == competition_id), None)

    def get_by_category(self, category: str) -> list[dict[str, Any]]:
        """Get competitions by category."""
        competitions = self._load()
        return [c for c in competitions if c.get("category") == category]

    def create(self, data: dict[str, Any]) -> dict[str, Any]:
        """Create a new competition."""
        from datetime import datetime
        competitions = self._load()
        now = datetime.now().isoformat()
        
        competition = {
            "id": data.get("id", str(uuid4())[:8]),
            "name": data.get("name", ""),
            "category": data.get("category", ""),
            "level": data.get("level", "国家级"),
            "organizer": data.get("organizer", ""),
            "website": data.get("website", ""),
            "description": data.get("description", ""),
            "teamSize": data.get("teamSize", "个人"),
            "time": data.get("time", ""),
            "registrationDeadline": data.get("registrationDeadline", ""),
            "difficulty": data.get("difficulty", "中"),
            "skills": data.get("skills", []),
            "awards": data.get("awards", []),
            "tips": data.get("tips", ""),
            "isActive": data.get("isActive", True),
            "createdAt": now,
            "updatedAt": now,
        }
        
        competitions.append(competition)
        self._save(competitions)
        return competition

    def update(self, competition_id: str, data: dict[str, Any]) -> dict[str, Any] | None:
        """Update an existing competition."""
        from datetime import datetime
        competitions = self._load()
        
        for i, comp in enumerate(competitions):
            if comp.get("id") == competition_id:
                now = datetime.now().isoformat()
                competitions[i] = {
                    **comp,
                    **data,
                    "id": competition_id,
                    "updatedAt": now,
                }
                self._save(competitions)
                return competitions[i]
        
        return None

    def delete(self, competition_id: str) -> bool:
        """Delete a competition."""
        competitions = self._load()
        original_len = len(competitions)
        competitions = [c for c in competitions if c.get("id") != competition_id]
        
        if len(competitions) < original_len:
            self._save(competitions)
            return True
        return False

    def import_from_json(self, json_path: str | Path) -> int:
        """Import competitions from a JSON file."""
        json_path = Path(json_path)
        if not json_path.exists():
            return 0
        
        try:
            content = json_path.read_text(encoding="utf-8")
            new_competitions = json.loads(content)
            
            if not isinstance(new_competitions, list):
                return 0
            
            existing = self._load()
            existing_ids = {c.get("id") for c in existing}
            
            imported = 0
            for comp in new_competitions:
                if comp.get("id") not in existing_ids:
                    from datetime import datetime
                    comp["createdAt"] = datetime.now().isoformat()
                    comp["updatedAt"] = datetime.now().isoformat()
                    existing.append(comp)
                    imported += 1
            
            self._save(existing)
            return imported
        except (json.JSONDecodeError, Exception):
            return 0

    def get_categories(self) -> list[str]:
        """Get all unique categories."""
        competitions = self._load()
        return sorted(set(c.get("category", "") for c in competitions if c.get("category")))

    def search(self, keyword: str) -> list[dict[str, Any]]:
        """Search competitions by keyword."""
        competitions = self._load()
        keyword_lower = keyword.lower()
        
        results = []
        for comp in competitions:
            searchable = [
                comp.get("name", ""),
                comp.get("category", ""),
                comp.get("description", ""),
                comp.get("organizer", ""),
                " ".join(comp.get("skills", [])),
            ]
            if any(keyword_lower in str(field).lower() for field in searchable):
                results.append(comp)
        
        return results