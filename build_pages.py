#!/usr/bin/env python3
"""Build static site for GitHub Pages (docs/ and repo root)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from config import (
    CLUB_TAG_POINTS,
    HIERARCHY_EXACT,
    HIERARCHY_GRANDRELATED,
    HIERARCHY_PARENT_CHILD,
    MAX_USER_TAGS,
    MIN_ACTIVE_MEMBER_COUNT,
    MIN_FINAL_SCORE,
    MIN_RESULTS,
    NONE_TAG_WEIGHT_MULTIPLIER,
    POPULARITY_TIERS,
    SIMILARITY_PRECISION_WEIGHT,
    SIMILARITY_RECALL_WEIGHT,
    TOP_N_RESULTS,
    USER_TAG_POINTS,
)
from recommender import load_clubs
from tag_hierarchy import PARENT_MAP, TAG_TREE, all_known_tags, display_name
from tag_quiz import TOP_LEVEL

BASE = Path(__file__).parent
DOCS = BASE / "docs"
ROOT = BASE
STATIC = BASE / "static"
SITE_FILES = ("index.html", "styles.css", "app.js", "engine.js")


def _write_data(data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)

    clubs = load_clubs()
    clubs_payload = [
        {
            "no": c.no,
            "name": c.name,
            "category": c.category,
            "description": c.description,
            "member_count": c.member_count,
            "day": c.day,
            "period": c.period,
            "room": c.room,
            "tags": c.tags,
        }
        for c in clubs
    ]

    site_payload = {
        "config": {
            "CLUB_TAG_POINTS": CLUB_TAG_POINTS,
            "USER_TAG_POINTS": USER_TAG_POINTS,
            "MAX_USER_TAGS": MAX_USER_TAGS,
            "HIERARCHY_EXACT": HIERARCHY_EXACT,
            "HIERARCHY_PARENT_CHILD": HIERARCHY_PARENT_CHILD,
            "HIERARCHY_GRANDRELATED": HIERARCHY_GRANDRELATED,
            "NONE_TAG_WEIGHT_MULTIPLIER": NONE_TAG_WEIGHT_MULTIPLIER,
            "MIN_ACTIVE_MEMBER_COUNT": MIN_ACTIVE_MEMBER_COUNT,
            "MIN_FINAL_SCORE": MIN_FINAL_SCORE,
            "MIN_RESULTS": MIN_RESULTS,
            "TOP_N_RESULTS": TOP_N_RESULTS,
            "SIMILARITY_PRECISION_WEIGHT": SIMILARITY_PRECISION_WEIGHT,
            "SIMILARITY_RECALL_WEIGHT": SIMILARITY_RECALL_WEIGHT,
            "POPULARITY_TIERS": POPULARITY_TIERS,
        },
        "parentMap": PARENT_MAP,
        "tagTree": TAG_TREE,
        "topLevel": TOP_LEVEL,
        "tags": [
            {"id": tag, "label": display_name(tag)}
            for tag in sorted(all_known_tags(), key=lambda t: display_name(t).lower())
        ],
    }

    (data_dir / "clubs.json").write_text(
        json.dumps(clubs_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (data_dir / "site.json").write_text(
        json.dumps(site_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _deploy_docs(target: Path, data_dir: Path) -> None:
    if target.exists():
        for item in target.iterdir():
            if item.name == "data":
                continue
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()
    else:
        target.mkdir(parents=True)

    for name in SITE_FILES:
        shutil.copy2(STATIC / name, target / name)

    (target / ".nojekyll").touch()
    _ensure_engine_script(target / "index.html")


def _deploy_root(target: Path, data_dir: Path) -> None:
    for name in SITE_FILES:
        shutil.copy2(STATIC / name, target / name)

    data_target = target / "data"
    if data_target.exists():
        shutil.rmtree(data_target)
    shutil.copytree(data_dir, data_target)

    (target / ".nojekyll").touch()
    _ensure_engine_script(target / "index.html")


def _ensure_engine_script(index_path: Path) -> None:
    index = index_path.read_text(encoding="utf-8")
    if "engine.js" not in index:
        index = index.replace(
            '<script src="app.js"></script>',
            '<script src="engine.js"></script>\n  <script src="app.js"></script>',
        )
        index_path.write_text(index, encoding="utf-8")


def build_pages() -> Path:
    data_dir = DOCS / "data"
    _write_data(data_dir)
    _deploy_docs(DOCS, data_dir)
    _deploy_root(ROOT, data_dir)
    return DOCS


if __name__ == "__main__":
    path = build_pages()
    print(f"Built GitHub Pages site at {path} and repo root")
