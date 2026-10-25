"""Project library: each analysis is a project saved as one JSON file.

Projects live in the user's data folder (`projects/<id>.dnproj`) and are listed in the lobby.
A project can be exported to, or imported from, any location as the same single file.
Pure Python (no Qt), like the engine.
"""
from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from .. import __version__
from .mrv import default_db_path

SUFFIX = ".dnproj"
FORMAT = 1
STEPS = 6


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


@dataclass
class Project:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = ""
    created: str = field(default_factory=now)
    updated: str = field(default_factory=now)
    step: int = 0                      # current step (0-based)
    reached: int = 0                   # furthest step unlocked
    view: str = "eu"
    ship: dict | None = None           # {"imo", "year", "name", "type"}
    inputs: dict = field(default_factory=dict)
    summary: dict = field(default_factory=dict)   # figures shown on the lobby card
    format: int = FORMAT
    app_version: str = __version__

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, d: dict) -> Project:
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


def default_dir() -> Path:
    env = os.environ.get("NAVIGATOR_PROJECTS")
    return Path(env) if env else default_db_path().parent / "projects"


class ProjectStore:
    def __init__(self, folder: Path | None = None):
        self.folder = Path(folder) if folder else default_dir()
        self.folder.mkdir(parents=True, exist_ok=True)

    def path(self, pid: str) -> Path:
        return self.folder / f"{pid}{SUFFIX}"

    def list(self) -> list[Project]:
        out = []
        for p in self.folder.glob(f"*{SUFFIX}"):
            try:
                out.append(Project.from_dict(json.loads(p.read_text(encoding="utf-8"))))
            except (OSError, ValueError, TypeError):
                continue                    # a damaged file must not hide the others
        return sorted(out, key=lambda x: x.updated, reverse=True)

    def load(self, pid: str) -> Project:
        return Project.from_dict(json.loads(self.path(pid).read_text(encoding="utf-8")))

    def save(self, project: Project) -> None:
        project.updated = now()
        tmp = self.path(project.id).with_suffix(".tmp")
        tmp.write_text(project.to_json(), encoding="utf-8")
        tmp.replace(self.path(project.id))

    def delete(self, pid: str) -> None:
        self.path(pid).unlink(missing_ok=True)

    def duplicate(self, pid: str, name: str) -> Project:
        p = self.load(pid)
        p.id, p.name, p.created = uuid.uuid4().hex[:12], name, now()
        self.save(p)
        return p

    def export(self, pid: str, target: Path) -> Path:
        target = Path(target)
        if target.suffix != SUFFIX:
            target = target.with_suffix(SUFFIX)
        target.write_text(self.load(pid).to_json(), encoding="utf-8")
        return target

    def import_file(self, source: Path) -> Project:
        """Import a project file; it gets a new id if one with the same id already exists."""
        p = Project.from_dict(json.loads(Path(source).read_text(encoding="utf-8")))
        if self.path(p.id).exists():
            p.id = uuid.uuid4().hex[:12]
        self.save(p)
        return p
