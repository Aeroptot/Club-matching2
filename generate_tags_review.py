#!/usr/bin/env python3
"""Generate a human-readable markdown listing of every club and its tags."""

from pathlib import Path

from generate_club_tags import CLUB_TAGS, load_clubs
from tag_hierarchy import display_name

BASE = Path(__file__).parent
OUTPUT = BASE / "clubs_tags_review.md"


def main() -> None:
    clubs = load_clubs()
    lines = [
        "# 社团 Tag 一览",
        "",
        f"共 {len(clubs)} 个社团，按 NO. 排序。Tag 使用可读名称；如有社团无 tag 会标注「未分配」。",
        "",
        "| NO | Name | Category | Tags |",
        "| --- | --- | --- | --- |",
    ]
    for club in clubs:
        no = club["no"]
        tags = CLUB_TAGS.get(no, [])
        tag_text = (
            ", ".join(display_name(t) for t in tags)
            if tags
            else "**未分配**"
        )
        name = club["name"].replace("|", "\\|")
        category = club["category"].replace("|", "\\|")
        lines.append(f"| {no} | {name} | {category} | {tag_text} |")
    lines.append("")
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUTPUT} ({len(clubs)} clubs)")


if __name__ == "__main__":
    main()
