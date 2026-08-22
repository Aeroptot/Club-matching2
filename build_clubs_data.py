"""Build clubs_weighted.csv from parsed output pages and tag assignments."""

from __future__ import annotations

import csv
from pathlib import Path

from config import CLUB_TAG_POINTS
from generate_club_tags import CLUB_TAGS, TAG_VOCABULARY, load_clubs
from tag_hierarchy import hierarchy_depth

BASE = Path(__file__).parent

# Optional per-club weight overrides (must sum to CLUB_TAG_POINTS).
CLUB_WEIGHT_OVERRIDES: dict[str, dict[str, int]] = {}


def distribute_weights(tags: list[str], total: int = CLUB_TAG_POINTS) -> list[int]:
    """Weight tags by their position in the hierarchy.

    A tag's importance grows with its depth (specificity): tags at the same
    hierarchy level get equal weight, deeper/more specific tags get more.
    Weights sum to ``total`` using largest remainders.
    """
    if not tags:
        return []
    raw = [hierarchy_depth(t) for t in tags]
    raw_sum = sum(raw)
    exact = [total * w / raw_sum for w in raw]
    weights = [int(x) for x in exact]
    remainder = total - sum(weights)
    order = sorted(
        range(len(exact)),
        key=lambda i: (exact[i] - int(exact[i]), raw[i]),
        reverse=True,
    )
    for i in range(remainder):
        weights[order[i]] += 1
    return weights


def club_weighted_tags(club_no: str) -> dict[str, int]:
    if club_no in CLUB_WEIGHT_OVERRIDES:
        weights = CLUB_WEIGHT_OVERRIDES[club_no]
        if sum(weights.values()) != CLUB_TAG_POINTS:
            raise ValueError(
                f"Club {club_no} override weights must sum to {CLUB_TAG_POINTS}"
            )
        return weights
    tags = CLUB_TAGS.get(club_no, [])
    if not tags:
        return {}
    weights = distribute_weights(tags)
    return dict(zip(tags, weights))


def build_weighted_csv(output_path: Path | None = None) -> Path:
    output_path = output_path or BASE / "clubs_weighted.csv"
    clubs = load_clubs()

    # Include machine_learning in export columns (used in hierarchy / user selection).
    export_tags = sorted(set(TAG_VOCABULARY) | {"machine_learning"})
    fieldnames = [
        "no",
        "name",
        "category",
        "description",
        "member_count",
        "day",
        "period",
        "room",
    ] + export_tags

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for club in clubs:
            no = club["no"]
            weighted = club_weighted_tags(no)
            row = {
                "no": no,
                "name": club["name"],
                "category": club["category"],
                "description": club["description"],
                "member_count": club["member_count"],
                "day": club["day"],
                "period": club["period"],
                "room": club["room"],
            }
            for tag in export_tags:
                row[tag] = weighted.get(tag, 0)
            writer.writerow(row)

    return output_path


if __name__ == "__main__":
    path = build_weighted_csv()
    print(f"Wrote {path}")
