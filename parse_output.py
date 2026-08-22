#!/usr/bin/env python3
"""Parse the scraped club pages in output/*.md into a structured JSON dataset.

Each markdown file contains one club:
  - 基本信息 table: NO., Name, Leader, Leadership Team, Category, Room,
    Students, Period, Space
  - 社团介绍: free-text description
  - 负责人: leader/teacher contact lines
  - 活动信息: day / time / classroom

Web links and storage-space stats are intentionally omitted.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

BASE = Path(__file__).parent
OUTPUT_DIR = BASE / "output"
OUTPUT_JSON = BASE / "clubs_parsed.json"

SKIP_FILES = {"社团信息.md"}


def latest_files_by_no() -> list[Path]:
    """Return the newest markdown file per numeric NO prefix (old crawls may
    linger alongside the latest one)."""
    by_no: dict[str, list[Path]] = {}
    for md_path in OUTPUT_DIR.glob("*.md"):
        if md_path.name in SKIP_FILES:
            continue
        m = re.match(r"(\d+)-", md_path.name)
        if not m:
            continue
        by_no.setdefault(m.group(1), []).append(md_path)

    picked: list[Path] = []
    for no in sorted(by_no, key=int):
        candidates = by_no[no]
        picked.append(max(candidates, key=lambda p: p.stat().st_mtime))
    return picked


def parse_period(value: str) -> tuple[str, str]:
    """'Thursday Period12' -> ('thursday', 'period12')."""
    parts = value.split()
    day = ""
    period = ""
    for p in parts:
        low = p.lower()
        if low in {
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        }:
            day = low
        elif low.startswith("period"):
            period = low[:8]  # period11 / period12
        elif low == "lunchtime":
            period = "lunchtime"
        elif "lunch" in low:
            period = "lunchtime"
    return day, period


def parse_club(md_path: Path) -> dict:
    text = md_path.read_text(encoding="utf-8")
    lines = text.splitlines()

    club: dict = {
        "no": "",
        "name": "",
        "leadership_team": "",
        "category": "",
        "room": "",
        "member_count": 0,
        "day": "",
        "period": "",
        "description": "",
    }

    in_basic = False
    in_intro = False
    intro: list[str] = []
    period_raw = ""

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            section = stripped[3:].strip()
            in_basic = section == "基本信息"
            if section == "社团介绍":
                in_intro = True
                intro = []
            else:
                in_intro = False
            continue

        if in_basic and stripped.startswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if len(cells) == 2:
                key, value = cells
                if key == "NO.":
                    club["no"] = value
                elif key == "Name":
                    club["name"] = value
                elif key == "Leadership Team":
                    club["leadership_team"] = value
                elif key == "Category":
                    club["category"] = re.sub(r"\s+", " ", value).strip()
                elif key == "Room":
                    club["room"] = value
                elif key == "Students":
                    try:
                        club["member_count"] = int(value)
                    except ValueError:
                        club["member_count"] = 0
                elif key == "Period":
                    period_raw = value

        if in_intro:
            if stripped.startswith("|") or stripped.startswith("## "):
                if intro and not stripped.startswith("|"):
                    break
                if stripped.startswith("|"):
                    continue
            if stripped and not stripped.startswith("|"):
                intro.append(stripped)

    club["description"] = " ".join(intro).strip()
    club["day"], club["period"] = parse_period(period_raw)
    return club


def main() -> None:
    clubs: list[dict] = []
    for md_path in latest_files_by_no():
        club = parse_club(md_path)
        if not club["no"] or not club["name"]:
            print(f"WARN: skipped {md_path.name} (no/no-name)")
            continue
        clubs.append(club)

    clubs.sort(key=lambda c: int(c["no"]))
    OUTPUT_JSON.write_text(
        json.dumps(clubs, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    no_intro = [c["no"] for c in clubs if not c["description"]]
    print(f"Parsed {len(clubs)} clubs -> {OUTPUT_JSON}")
    if no_intro:
        print(f"WARN: clubs without description: {no_intro}")
    missing_fields = []
    for c in clubs:
        for field in ("leadership_team", "category", "room", "day", "period"):
            if not c[field]:
                missing_fields.append((c["no"], field))
    if missing_fields:
        print(f"WARN: missing fields: {missing_fields}")


if __name__ == "__main__":
    main()
