"""Load regulatory parameters from sourced JSON files (see docs/decisions/0002).

File format::

    {
      "name": "eu_ets_maritime",
      "sources": {"ec_faq": {"title": "...", "url": "...", "checked": "2026-10-24"}},
      "values": {
        "phase_in": {"value": {"2024": 0.4}, "source": "ec_faq"},
        "gwp_ch4":  {"value": 28, "source": "ipcc_ar5", "status": "verify", "note": "..."}
      }
    }

A file with the same name in a user override directory replaces individual values and
adds sources, so a rule change never needs a new build.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
VERIFIED, VERIFY = "verified", "verify"


@dataclass(frozen=True)
class Source:
    id: str
    title: str
    url: str = ""
    checked: str = ""


@dataclass(frozen=True)
class Param:
    key: str
    value: Any
    source: str
    status: str = VERIFIED
    note: str = ""


class ParamSet:
    def __init__(self, name: str, sources: dict[str, Source], values: dict[str, Param], origin: list[Path]):
        self.name = name
        self.sources = sources
        self.values = values
        self.origin = origin

    def __getitem__(self, key: str) -> Any:
        return self.values[key].value

    def param(self, key: str) -> Param:
        return self.values[key]

    def source_of(self, key: str) -> Source:
        return self.sources[self.values[key].source]

    def unverified(self) -> list[Param]:
        return [p for p in self.values.values() if p.status != VERIFIED]

    def validate(self) -> list[str]:
        """Problems that make the file unusable for a thesis: values without a known source."""
        errs = []
        for p in self.values.values():
            if p.source not in self.sources:
                errs.append(f"{self.name}.{p.key}: unknown source '{p.source}'")
            if p.status not in (VERIFIED, VERIFY):
                errs.append(f"{self.name}.{p.key}: invalid status '{p.status}'")
        return errs


def _read(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def load(name: str, *, base_dir: Path | None = None, override_dir: Path | None = None) -> ParamSet:
    base_dir = base_dir or CONFIG_DIR / "regulation"
    path = base_dir / f"{name}.json"
    raw = _read(path)
    origin = [path]
    sources_raw = dict(raw.get("sources", {}))
    values_raw = dict(raw.get("values", {}))
    if override_dir is not None:
        user = override_dir / f"{name}.json"
        if user.exists():
            u = _read(user)
            sources_raw.update(u.get("sources", {}))
            values_raw.update(u.get("values", {}))
            origin.append(user)
    sources = {sid: Source(id=sid, **s) for sid, s in sources_raw.items()}
    values = {k: Param(key=k, value=v["value"], source=v["source"], status=v.get("status", VERIFIED),
                       note=v.get("note", "")) for k, v in values_raw.items()}
    ps = ParamSet(raw.get("name", name), sources, values, origin)
    errs = ps.validate()
    if errs:
        raise ValueError("; ".join(errs))
    return ps


def available(base_dir: Path | None = None) -> list[str]:
    base_dir = base_dir or CONFIG_DIR / "regulation"
    return sorted(p.stem for p in base_dir.glob("*.json"))
