"""What to look for and what to do about a crop health screening's class, from a reviewed guidance file.

The file (`crop_guidance.json`) is versioned and records its reviewer. Until an agronomist has
reviewed it, treatment steps and chemical prevention are withheld: they name pesticide classes,
which must first be checked against what is registered in Pakistan (#15).
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel


class Guidance(BaseModel):
    name: str
    type: str
    symptoms: list[str]
    prevention: list[str]
    # Empty until the guidance file has a reviewer.
    treatment_steps: list[str]
    reviewed: bool
    version: str
    source: str


class CropGuidance:
    def __init__(self, path: Path) -> None:
        document = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {"classes": {}}
        self.version = document.get("version", "none")
        self.source = document.get("source", "")
        self.reviewed = document.get("status") == "reviewed" and bool(document.get("reviewer"))
        self._entries: dict[str, dict] = {}
        for class_id, entry in document["classes"].items():
            for key in (class_id, *entry.get("aliases", [])):
                self._entries[key] = entry

    def for_class(self, class_id: str) -> Guidance | None:
        entry = self._entries.get(class_id)
        if entry is None:
            return None
        return Guidance(
            name=entry["name"],
            type=entry["type"],
            symptoms=entry["symptoms"],
            prevention=entry["prevention"] + (entry.get("chemical_prevention", []) if self.reviewed else []),
            treatment_steps=entry["treatment_steps"] if self.reviewed else [],
            reviewed=self.reviewed,
            version=self.version,
            source=self.source,
        )
