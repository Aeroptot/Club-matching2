"""Tag hierarchy tree and relationship matching."""

from __future__ import annotations

from config import (
    HIERARCHY_EXACT,
    HIERARCHY_GRANDRELATED,
    HIERARCHY_PARENT_CHILD,
    HIERARCHY_UNRELATED,
    HIERARCHY_WEIGHT_SPREAD,
)

# Nested hierarchy: parent -> {child: subtree, ...}
# Tags not listed here are standalone roots (match only themselves).
TAG_TREE: dict[str, dict] = {
    "STEM": {
        "math": {},
        "biology": {},
        "chemistry": {},
        "physics": {},
        "astronomy": {},
        "medicine": {
            "forensic_science": {},
        },
        "environment": {
            "meteorology": {},
            "geology": {},
        },
        "experiments": {},
        "research": {},
        "engineering": {
            "robotics": {},
            "aerospace": {},
            "drones": {},
            "hands_on": {},
        },
        "computer_science": {
            "programming": {},
            "algorithms": {},
            "web_development": {},
            "game_development": {},
            "cybersecurity": {},
            "data_science": {},
            "AI": {
                "machine_learning": {},
            },
        },
        "technology": {},
    },
    "social_sciences": {
        "economics": {},
        "psychology": {},
        "anthropology": {},
        "politics": {},
        "linguistics": {},
        "debate": {},
        "law": {},
        "geography": {},
        "gender_studies": {},
    },
    "humanities": {
        "philosophy": {},
        "history": {},
        "literature": {},
        "writing": {},
        "academic": {},
        "religion": {},
    },
    "business": {
        "finance": {},
        "investment": {},
        "entrepreneurship": {},
    },
    "creative_arts": {
        "visual_arts": {},
        "photography": {},
        "design": {},
        "3d_modeling": {},
        "fashion": {},
        "craftsmanship": {},
    },
    "performing_arts": {
        "music": {},
        "dance": {},
        "theater": {},
        "magic": {},
        "voice_acting": {},
    },
    "media": {
        "film": {},
        "journalism": {},
        "anime": {},
    },
    "sports": {
        "fitness": {
            "running": {},
        },
        "team_sports": {
            "football": {},
            "basketball": {},
            "baseball": {},
            "volleyball": {},
            "frisbee": {},
            "dodgeball": {},
            "tchoukball": {},
            "cheerleading": {},
        },
        "racquet_sports": {
            "badminton": {},
            "tennis": {},
            "table_tennis": {},
            "pickleball": {},
        },
        "martial_arts": {
            "fencing": {},
        },
        "outdoor_sports": {
            "climbing": {},
            "cycling": {},
        },
        "winter_sports": {
            "skiing": {},
            "figure_skating": {},
        },
        "water_sports": {
            "rowing": {},
            "scuba_diving": {},
            "swimming": {},
        },
        "equestrian": {},
        "billiards": {},
        "motorsport": {
            "rc_racing": {},
        },
        "golf": {},
    },
    "volunteer": {
        "teaching": {},
        "charity": {},
        "community_service": {},
        "animal_welfare": {},
        "peer_support": {},
    },
    "health": {
        "mental_health": {},
        "wellness": {},
        "nutrition": {},
        "yoga": {},
    },
    "gaming": {
        "board_games": {
            "mahjong": {},
        },
        "strategy": {},
        "rhythm_games": {},
        "tcg": {},
    },
    "culture": {
        "chinese_culture": {},
        "language_learning": {},
    },
    "hobbies": {
        "speedcubing": {},
        "coffee": {},
    },
    "competition": {},
    "academic_support": {},
    "personal_growth": {},
}


def _build_parent_map(
    tree: dict[str, dict], parent: str | None = None, out: dict[str, str | None] | None = None
) -> dict[str, str | None]:
    if out is None:
        out = {}
    for node, children in tree.items():
        out[node] = parent
        if children:
            _build_parent_map(children, node, out)
    return out


PARENT_MAP: dict[str, str | None] = _build_parent_map(TAG_TREE)


def hierarchy_depth(tag: str) -> int:
    """Depth of a tag in the tree (roots are depth 1)."""
    depth = 1
    current = tag
    while PARENT_MAP.get(current) is not None:
        current = PARENT_MAP[current]  # type: ignore[assignment]
        depth += 1
    return depth


def ancestor_chain(tag: str) -> list[str]:
    """Return [tag, parent, grandparent, ...]."""
    chain = [tag]
    current = tag
    while PARENT_MAP.get(current) is not None:
        current = PARENT_MAP[current]  # type: ignore[assignment]
        chain.append(current)
    return chain


def hierarchy_distance(tag_a: str, tag_b: str) -> int | None:
    """Shortest path distance in the hierarchy tree, or None if unrelated."""
    if tag_a == tag_b:
        return 0
    chain_a = ancestor_chain(tag_a)
    chain_b = ancestor_chain(tag_b)
    best: int | None = None
    for i, ancestor in enumerate(chain_a):
        if ancestor in chain_b:
            j = chain_b.index(ancestor)
            distance = i + j
            if distance <= 2 and (best is None or distance < best):
                best = distance
    return best


def hierarchy_coefficient(tag_a: str, tag_b: str) -> float:
    distance = hierarchy_distance(tag_a, tag_b)
    if distance is None:
        return HIERARCHY_UNRELATED
    if distance == 0:
        return HIERARCHY_EXACT
    if distance == 1:
        return HIERARCHY_PARENT_CHILD
    if distance == 2:
        return HIERARCHY_GRANDRELATED
    return HIERARCHY_UNRELATED


def display_name(tag: str) -> str:
    """Human-readable tag label."""
    special = {
        "AI": "AI",
        "STEM": "STEM",
        "anime": "Anime",
        "rc_racing": "RC Racing",
        "3d_modeling": "3D Modeling",
        "tcg": "TCG",
    }
    if tag in special:
        return special[tag]
    return tag.replace("_", " ").title()


def all_known_tags() -> set[str]:
    return set(PARENT_MAP.keys())


def _fill_subtree_depth(tree: dict, out: dict) -> int:
    """Fill SUBTREE_DEPTH: tag -> levels from the tag down to its deepest
    leaf, including the tag itself (leaves are 1)."""
    max_below = 0
    for node, children in tree.items():
        below = _fill_subtree_depth(children, out)
        out[node] = below + 1
        max_below = max(max_below, below + 1)
    return max_below


SUBTREE_DEPTH: dict[str, int] = {}
_fill_subtree_depth(TAG_TREE, SUBTREE_DEPTH)


def hierarchy_position(tag: str) -> float:
    """Relative position of a tag in its own branch: 0.0 = beginning,
    1.0 = end. The end of a 2-layer branch and the end of a 4-layer branch
    both return 1.0, so their weights are identical."""
    depth = hierarchy_depth(tag)
    deepest = depth - 1 + SUBTREE_DEPTH.get(tag, 1)
    if deepest <= 1:
        return 1.0
    return (depth - 1) / (deepest - 1)


def hierarchy_relative_weight(tag: str) -> float:
    """Weight of a tag by its position in its own branch. Every hierarchy
    begins at weight 1 and ends at HIERARCHY_WEIGHT_SPREAD regardless of how
    many layers it has."""
    return HIERARCHY_WEIGHT_SPREAD ** hierarchy_position(tag)
