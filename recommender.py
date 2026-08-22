"""Club recommendation engine.

Score = club coverage: the fraction of a club's CLUB_TAG_POINTS (20) that the
user's selected tags cover. Each club tag contributes its hierarchy weight
(deeper tags weigh more, same-depth tags weigh the same) times the strength of
its best relationship to a user tag (1.0 exact, 0.5 parent/child, 0.25
grand-related, 0 unrelated). This keeps the hierarchy meaningful: hitting a
club's deepest/most important tag scores ~1/2 or more, while hitting only
shallow tags scores much less, no matter how many tags the user picked.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from config import (
    CLUB_TAG_POINTS,
    EXCLUDED_CLUB_NOS,
    HIERARCHY_PARENT_CHILD,
    MAX_USER_TAGS,
    MEETING_PERIODS,
    METADATA_COLUMNS,
    MIN_ACTIVE_MEMBER_COUNT,
    MIN_FINAL_SCORE,
    MIN_RESULTS,
    POPULARITY_TIERS,
    SIMILARITY_PRECISION_WEIGHT,
    SIMILARITY_RECALL_WEIGHT,
    TOP_N_RESULTS,
    USER_TAG_POINTS,
    WEEKDAYS,
)
from tag_hierarchy import PARENT_MAP, display_name, hierarchy_coefficient

BASE = Path(__file__).parent

@dataclass
class Club:
    no: str
    name: str
    category: str
    description: str
    member_count: int
    day: str
    period: str
    room: str
    tags: dict[str, int]  # tag -> weight (sums to CLUB_TAG_POINTS)

    @property
    def meeting_slot(self) -> str:
        return f"{self.day}:{self.period}"


@dataclass
class MatchDetail:
    user_tag: str
    club_tag: str
    coefficient: float
    contribution: float


@dataclass
class Recommendation:
    club: Club
    similarity: float
    precision: float
    recall: float
    matched_weight: float
    matched_club_tags: set[str]
    popularity_multiplier: float
    final_score: float
    matches: list[MatchDetail] = field(default_factory=list)

    @property
    def final_score_pct(self) -> float:
        return self.final_score * 100

    @property
    def matching_tag_labels(self) -> list[str]:
        seen: set[str] = set()
        labels: list[str] = []
        for m in sorted(self.matches, key=lambda x: -x.contribution):
            if m.coefficient >= 1.0:
                label = display_name(m.user_tag)
            elif m.user_tag != m.club_tag:
                label = f"{display_name(m.user_tag)} → {display_name(m.club_tag)}"
            else:
                label = display_name(m.user_tag)
            if label not in seen:
                seen.add(label)
                labels.append(label)
        return labels

    def explanation(self) -> str:
        labels = self.matching_tag_labels
        if not labels:
            return "No strong tag overlap with your selected interests."
        if len(labels) == 1:
            tag_text = labels[0]
        elif len(labels) == 2:
            tag_text = f"{labels[0]} and {labels[1]}"
        else:
            tag_text = ", ".join(labels[:-1]) + f", and {labels[-1]}"
        strength = "strongly" if self.similarity >= 0.5 else "moderately"
        return f"Matched {strength} because of {tag_text}."


def normalize_tag(tag: str) -> str:
    """Map user input to canonical tag names used in the dataset and hierarchy."""
    cleaned = tag.strip().replace(" ", "_")
    lower = cleaned.lower()
    for known in PARENT_MAP:
        if known.lower() == lower:
            return known
    return lower


def distribute_user_weights(
    tags: list[str],
    weight_mults: dict[str, float] | None = None,
    total: int = USER_TAG_POINTS,
) -> dict[str, int]:
    if not tags:
        return {}
    if len(tags) > MAX_USER_TAGS:
        raise ValueError(f"Select at most {MAX_USER_TAGS} tags (got {len(tags)})")
    # Selection order does not matter: split the points evenly.
    base, remainder = divmod(total, len(tags))
    weights = [base + (1 if i < remainder else 0) for i in range(len(tags))]
    mults = weight_mults or {}
    scaled: dict[str, int] = {}
    for tag, weight in zip(tags, weights):
        scaled[tag] = max(0, round(weight * mults.get(tag, 1.0)))
    if sum(scaled.values()) == 0 and tags:
        scaled[tags[0]] = 1
    return scaled


def popularity_multiplier(member_count: int) -> float:
    for threshold, multiplier in POPULARITY_TIERS:
        if member_count >= threshold:
            return multiplier
    return 1.0


def load_clubs(csv_path: Path | None = None) -> list[Club]:
    csv_path = csv_path or BASE / "clubs_weighted.csv"
    clubs: list[Club] = []

    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        tag_columns = [c for c in reader.fieldnames or [] if c not in METADATA_COLUMNS]

        for row in reader:
            if row["no"] in EXCLUDED_CLUB_NOS:
                continue
            tags = {tag: int(row[tag]) for tag in tag_columns if int(row[tag]) > 0}
            clubs.append(
                Club(
                    no=row["no"],
                    name=row["name"],
                    category=row["category"],
                    description=row["description"],
                    member_count=int(row["member_count"]),
                    day=row.get("day") or "unknown",
                    period=row.get("period", "unknown"),
                    room=row.get("room", ""),
                    tags=tags,
                )
            )
    return clubs


def filter_clubs(
    clubs: list[Club],
    blocked_slots: list[str] | None = None,
    blocked_periods: list[str] | None = None,
) -> list[Club]:
    """Drop inactive clubs and clubs that meet during user-blocked day/period slots."""
    blocked = set(normalize_blocked_slots(blocked_slots or []))
    if blocked_periods:
        blocked.update(
            f"{day}:{period}"
            for day in WEEKDAYS
            for period in normalize_blocked_periods(blocked_periods)
        )
    eligible: list[Club] = []
    for club in clubs:
        if MIN_ACTIVE_MEMBER_COUNT > 0 and club.member_count <= MIN_ACTIVE_MEMBER_COUNT:
            continue
        if blocked and club.meeting_slot in blocked:
            continue
        eligible.append(club)
    return eligible


def normalize_blocked_period(s: str) -> str:
    cleaned = s.strip().lower().replace(" ", "").replace("-", "")
    aliases = {
        "period11": "period11",
        "p11": "period11",
        "11": "period11",
        "period12": "period12",
        "p12": "period12",
        "12": "period12",
        "lunchtime": "lunchtime",
        "lunch": "lunchtime",
    }
    if cleaned in aliases:
        return aliases[cleaned]
    raise ValueError(
        f"Unknown period {s!r}. Choose from: {', '.join(MEETING_PERIODS)}"
    )


def normalize_blocked_periods(periods: list[str]) -> list[str]:
    return [normalize_blocked_period(p) for p in periods]


def normalize_blocked_slot(s: str) -> str:
    """Normalize a day+period slot such as 'monday:period11'."""
    cleaned = s.strip().lower().replace(" ", "")
    if ":" not in cleaned:
        raise ValueError(
            f"Unknown slot {s!r}. Use weekday:period, e.g. monday:period11"
        )
    day_part, period_part = cleaned.split(":", 1)
    day_aliases = {
        "mon": "monday",
        "tue": "tuesday",
        "wed": "wednesday",
        "thu": "thursday",
        "fri": "friday",
    }
    day = day_aliases.get(day_part, day_part)
    if day not in WEEKDAYS:
        raise ValueError(f"Unknown weekday {day_part!r}. Choose from: {', '.join(WEEKDAYS)}")
    period = normalize_blocked_period(period_part)
    return f"{day}:{period}"


def normalize_blocked_slots(slots: list[str]) -> list[str]:
    return [normalize_blocked_slot(s) for s in slots]


def score_club(club: Club, user_tags: dict[str, int]) -> Recommendation:
    """Score a club by how much of its 20 tag points the user covers.

    For each club tag, take its best relationship strength to any user tag and
    multiply by the tag's weight. Matched points / 20 is the precision (club
    coverage) and the primary score. Recall (user coverage) is kept as an
    informational tiebreaker; user-side weights stay order-independent.
    """
    matched_points = 0.0
    matches: list[MatchDetail] = []
    for club_tag, club_weight in club.tags.items():
        best_user_tag: str | None = None
        best_strength = 0.0
        for user_tag in user_tags:
            strength = hierarchy_coefficient(user_tag, club_tag)
            if strength > best_strength:
                best_strength = strength
                best_user_tag = user_tag
        if best_strength > 0 and best_user_tag is not None:
            matched_points += club_weight * best_strength
            matches.append(
                MatchDetail(
                    best_user_tag,
                    club_tag,
                    best_strength,
                    club_weight * best_strength,
                )
            )

    precision = matched_points / CLUB_TAG_POINTS if club.tags else 0.0

    recall = 0.0
    for user_tag, user_weight in user_tags.items():
        best_strength = max(
            (hierarchy_coefficient(user_tag, club_tag) for club_tag in club.tags),
            default=0.0,
        )
        recall += user_weight * best_strength
    recall = recall / USER_TAG_POINTS if user_tags else 0.0

    # Only direct branch relationships (exact or parent/child) are highlighted;
    # sibling credit (0.25) still counts toward the score.
    matched_club_tags = {
        m.club_tag for m in matches if m.coefficient >= HIERARCHY_PARENT_CHILD
    }

    pop = popularity_multiplier(club.member_count)
    final_score = precision * pop

    return Recommendation(
        club=club,
        similarity=precision,
        precision=precision,
        recall=recall,
        matched_weight=matched_points,
        matched_club_tags=matched_club_tags,
        popularity_multiplier=pop,
        final_score=final_score,
        matches=matches,
    )


def recommend(
    user_tag_names: list[str],
    clubs: list[Club] | None = None,
    top_n: int = TOP_N_RESULTS,
    blocked_slots: list[str] | None = None,
    blocked_periods: list[str] | None = None,
    min_score: float = MIN_FINAL_SCORE,
    min_results: int = MIN_RESULTS,
    tag_weight_mults: dict[str, float] | None = None,
) -> list[Recommendation]:
    if clubs is None:
        clubs = load_clubs()

    normalized = [normalize_tag(t) for t in user_tag_names]
    mults = {normalize_tag(k): v for k, v in (tag_weight_mults or {}).items()}
    user_tags = distribute_user_weights(normalized, mults)
    eligible = filter_clubs(clubs, blocked_slots, blocked_periods)

    results = [score_club(club, user_tags) for club in eligible]
    results.sort(key=lambda r: (-r.final_score, -r.recall, r.club.name))

    if len(results) <= top_n:
        picked = results
    else:
        cutoff = results[top_n - 1].final_score
        if cutoff > 0:
            # Include every club tied with the cutoff score (ties share a rank).
            picked = [r for r in results if r.final_score >= cutoff]
        else:
            picked = results[:top_n]

    if len(picked) < min_results:
        seen = {id(r) for r in picked}
        picked = picked + [r for r in results if id(r) not in seen][: min_results - len(picked)]
    return picked


def format_results(results: list[Recommendation]) -> str:
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append("TOP CLUB RECOMMENDATIONS")
    lines.append("=" * 72)

    for i, rec in enumerate(results, 1):
        lines.append(f"\n{i}. {rec.club.name}")
        lines.append(f"   Final Score: {rec.final_score_pct:.1f}%")
        lines.append(f"   Members: {rec.club.member_count}")
        lines.append(f"   Meeting time: {rec.club.day} · {rec.club.period}")
        lines.append(
            f"   Similarity: {rec.similarity * 100:.1f}% "
            f"(precision {rec.precision * 100:.1f}%, recall {rec.recall * 100:.1f}%)"
        )
        lines.append(f"   Popularity multiplier: ×{rec.popularity_multiplier:.2f}")
        match_labels = rec.matching_tag_labels
        lines.append(f"   Matching tags: {', '.join(match_labels) if match_labels else 'None'}")
        lines.append(f"   {rec.explanation()}")

    lines.append("\n" + "=" * 72)
    return "\n".join(lines)
