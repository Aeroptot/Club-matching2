"""Configurable constants for the club recommendation engine."""

# Total tag points assigned to each club and user profile.
CLUB_TAG_POINTS = 20
USER_TAG_POINTS = 20
MAX_USER_TAGS = 10

# Hierarchy match coefficients (relationship strength).
# Each step away from an exact match halves the weight (1.0 → 0.5 → 0.25).
HIERARCHY_EXACT = 1.0
HIERARCHY_PARENT_CHILD = 0.5
HIERARCHY_GRANDRELATED = 0.25
HIERARCHY_UNRELATED = 0.0

# Club tag weights by absolute hierarchy depth: depth 1 -> 1, 2 -> 4,
# 3 -> 12, 4 -> 24. Deeper (more niche) tags weigh more; tags at the same
# depth weigh the same regardless of how long their branch is.
DEPTH_WEIGHT_TIERS: dict[int, int] = {1: 1, 2: 4, 3: 12, 4: 24}

# Quiz "None" selections use the parent tag at this fraction of normal weight.
NONE_TAG_WEIGHT_MULTIPLIER = 0.7

# Clubs excluded from recommendations and data exports.
EXCLUDED_CLUB_NOS: set[str] = set()

# Similarity blend: Precision vs Recall.
SIMILARITY_PRECISION_WEIGHT = 0.7
SIMILARITY_RECALL_WEIGHT = 0.3

# Popularity multipliers by member count (inclusive lower bound -> multiplier).
# Member counts are not considered this term (clubs just started), so the
# multiplier is neutral; the count is still shown in club details.
POPULARITY_TIERS: list[tuple[int, float]] = [
    (0, 1.00),
]

TOP_N_RESULTS = 10

# Return at least this many clubs when possible (may include scores <= MIN_FINAL_SCORE).
MIN_RESULTS = 10

# Clubs with this many members or fewer are treated as inactive and excluded.
# Set to 0 so no club is filtered by member count this term.
MIN_ACTIVE_MEMBER_COUNT = 0

# Prefer clubs whose final score exceeds this threshold (0–1 scale).
MIN_FINAL_SCORE = 0.50

WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday")
MEETING_PERIODS = ("period11", "period12", "lunchtime")

# Column names in the weighted CSV that are not tags.
METADATA_COLUMNS = {
    "no",
    "name",
    "category",
    "description",
    "member_count",
    "day",
    "period",
    "room",
}
