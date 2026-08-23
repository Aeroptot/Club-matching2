"""Guided tag selection through a hierarchy of interest questions."""

from __future__ import annotations

from dataclasses import dataclass

from config import NONE_TAG_WEIGHT_MULTIPLIER

from tag_hierarchy import TAG_TREE, display_name

NONE_ID = "__none__"


def tag_added(tag: str, *, from_none: bool = False) -> dict:
    return {
        "tag": tag,
        "weight_mult": NONE_TAG_WEIGHT_MULTIPLIER if from_none else 1.0,
    }


TOP_LEVEL: dict[str, dict] = {
    "academic": {
        "label": "Academic & Learning",
        "prompt": "Which academic areas appeal to you? (choose one or more)",
        "branches": ["STEM", "humanities", "social_sciences", "business", "academic_support"],
    },
    "sports": {
        "label": "Sports & Fitness",
        "prompt": "What kind of sports interest you? (choose one or more)",
        # "sports" is the only child of this area, so skip it and show its
        # children directly (keeps the hierarchy intact, drops the one-option
        # layer).
        "branches": list(TAG_TREE["sports"].keys()),
    },
    "social": {
        "label": "Social, Arts & Lifestyle",
        "prompt": "Which social or creative areas fit you? (choose one or more)",
        "branches": [
            "creative_arts",
            "performing_arts",
            "media",
            "volunteer",
            "health",
            "gaming",
            "culture",
            "hobbies",
            "competition",
            "personal_growth",
        ],
    },
}


@dataclass
class QuizOption:
    id: str
    label: str
    tag: str | None = None
    is_none: bool = False


@dataclass
class QuizStep:
    step_id: str
    question: str
    options: list[QuizOption]
    multi_select: bool = True
    can_continue: bool = True
    phase: str = "root"
    none_parent_tag: str | None = None


def empty_session() -> dict:
    return {
        "phase": "root",
        "areas": [],
        "area_index": 0,
        "branch_queue": [],
        "drill_extra": [],
        "pending_drill_nodes": [],
    }


def _children(tag: str) -> list[str]:
    node: dict = TAG_TREE
    for part in _path_to_tag(tag):
        if part not in node:
            return []
        node = node[part]
    return list(node.keys())


def _collapse_singletons(tag: str) -> str:
    """Follow single-child chains down to a branching node or a leaf.

    A node whose only child is a leaf (e.g. motorsport -> rc_racing) never
    shows a one-option quiz layer: selecting it directly adds the leaf tag.
    """
    while True:
        kids = _children(tag)
        if len(kids) == 1:
            tag = kids[0]
        else:
            return tag


def _path_to_tag(tag: str) -> list[str]:
    from tag_hierarchy import PARENT_MAP

    chain = [tag]
    current = tag
    while PARENT_MAP.get(current) is not None:
        current = PARENT_MAP[current]  # type: ignore[assignment]
        chain.append(current)
    chain.reverse()
    return chain


def _option_for_tag(tag: str) -> QuizOption:
    return QuizOption(id=tag, label=display_name(tag), tag=tag if not _children(tag) else None)


def _none_option(parent_label: str) -> QuizOption:
    return QuizOption(
        id=NONE_ID,
        label=f"None — use {parent_label} instead",
        tag=None,
        is_none=True,
    )


def _drill_node(session: dict) -> str:
    if session["drill_extra"]:
        return session["drill_extra"][-1]
    return session["branch_queue"][0]


def _advance_to_next_area(session: dict, tags_added: list[str]) -> tuple[dict, list[str]]:
    session["area_index"] += 1
    if session["area_index"] >= len(session["areas"]):
        session["phase"] = "complete"
    else:
        session["phase"] = "branches"
    return session, tags_added


def _finish_current_branch(session: dict, tags_added: list[str]) -> tuple[dict, list[str]]:
    session["drill_extra"] = []
    session["pending_drill_nodes"] = []
    session["branch_queue"].pop(0)

    if session["branch_queue"]:
        return session, tags_added

    return _advance_to_next_area(session, tags_added)


def _start_next_pending_drill(session: dict, tags_added: list[str]) -> tuple[dict, list[str]]:
    pending = session.get("pending_drill_nodes") or []
    if pending:
        session["drill_extra"] = [pending.pop(0)]
        session["pending_drill_nodes"] = pending
        return session, tags_added
    return _finish_current_branch(session, tags_added)


def quiz_step_from_session(session: dict | None) -> QuizStep:
    session = session or empty_session()
    phase = session["phase"]

    if phase == "root":
        return QuizStep(
            step_id="root",
            question="What broad areas interest you? (choose one or more)",
            options=[
                QuizOption(id=key, label=meta["label"], tag=None)
                for key, meta in TOP_LEVEL.items()
            ]
            + [_none_option("nothing from this list")],
            phase="root",
        )

    if phase == "branches":
        area = session["areas"][session["area_index"]]
        return QuizStep(
            step_id=f"{area}:branches",
            question=TOP_LEVEL[area]["prompt"],
            options=[_option_for_tag(tag) for tag in TOP_LEVEL[area]["branches"]]
            + [_none_option(TOP_LEVEL[area]["label"])],
            phase="branches",
        )

    if phase == "drill":
        branch = session["branch_queue"][0]
        node = _drill_node(session)
        parent_label = display_name(node)
        if not session["drill_extra"]:
            question = f"Which {display_name(branch)} topics fit you? (choose one or more)"
        else:
            question = f"Which {parent_label} topics fit you? (choose one or more)"
        children = _children(node)
        return QuizStep(
            step_id=f"drill:{branch}:{'/'.join(session['drill_extra'])}",
            question=question,
            options=[_option_for_tag(child) for child in children]
            + [_none_option(parent_label)],
            none_parent_tag=node,
            phase="drill",
        )

    return QuizStep(
        step_id="complete",
        question="Questionnaire complete — generating your matches…",
        options=[],
        can_continue=False,
        multi_select=False,
        phase="complete",
    )


def _validate_none_only(selections: list[str]) -> None:
    if NONE_ID in selections and len(selections) > 1:
        raise ValueError('Choose "None" by itself, or pick other options (not both).')


def advance_quiz_continue(session: dict, selections: list[str]) -> tuple[dict, list[str]]:
    """Apply a multi-select Continue action. Returns (session, tags_added)."""
    session = dict(session)
    session["branch_queue"] = list(session.get("branch_queue", []))
    session["drill_extra"] = list(session.get("drill_extra", []))
    session["areas"] = list(session.get("areas", []))
    session["pending_drill_nodes"] = list(session.get("pending_drill_nodes", []))

    if not selections:
        raise ValueError("Select at least one option before continuing.")

    _validate_none_only(selections)
    phase = session["phase"]

    if NONE_ID in selections:
        if phase == "root":
            session["phase"] = "complete"
            return session, []
        if phase == "branches":
            return _advance_to_next_area(session, [])
        if phase == "drill":
            parent = _drill_node(session)
            return _start_next_pending_drill(session, [tag_added(parent, from_none=True)])

    if phase == "root":
        for area in selections:
            if area not in TOP_LEVEL:
                raise ValueError(f"Unknown area: {area}")
        session["areas"] = selections
        session["area_index"] = 0
        session["phase"] = "branches"
        return session, []

    if phase == "branches":
        area = session["areas"][session["area_index"]]
        valid = set(TOP_LEVEL[area]["branches"])
        for branch in selections:
            if branch not in valid:
                raise ValueError(f"Unknown branch: {branch}")
        drill_deeper = []
        leaf_tags = []
        for b in selections:
            eff = _collapse_singletons(b)
            if _children(eff):
                drill_deeper.append(eff)
            else:
                leaf_tags.append(eff)
        tags_added = [tag_added(b) for b in leaf_tags]
        session["branch_queue"] = drill_deeper
        session["drill_extra"] = []
        session["pending_drill_nodes"] = []
        if not drill_deeper:
            return _advance_to_next_area(session, tags_added)
        session["phase"] = "drill"
        return session, tags_added

    if phase == "drill":
        return _drill_continue(session, selections)

    raise ValueError("Continue is not available at this step.")


def _drill_continue(session: dict, selections: list[str]) -> tuple[dict, list[str]]:
    node = _drill_node(session)
    valid = set(_children(node))
    for sel in selections:
        if sel not in valid:
            raise ValueError(f"Invalid selection: {sel}")

    tags_added: list[dict] = []
    drill_deeper: list[str] = []

    for sel in selections:
        eff = _collapse_singletons(sel)
        if _children(eff):
            drill_deeper.append(eff)
        else:
            tags_added.append(tag_added(eff))

    if drill_deeper:
        session["drill_extra"] = [drill_deeper[0]]
        session["pending_drill_nodes"] = drill_deeper[1:] + session["pending_drill_nodes"]
        return session, tags_added

    return _start_next_pending_drill(session, tags_added)


def step_to_dict(step: QuizStep, session: dict | None = None) -> dict:
    return {
        "step_id": step.step_id,
        "question": step.question,
        "multi_select": step.multi_select,
        "can_continue": step.can_continue,
        "phase": step.phase,
        "none_parent_tag": step.none_parent_tag,
        "session": session or empty_session(),
        "options": [
            {
                "id": opt.id,
                "label": opt.label,
                "tag": opt.tag,
                "is_leaf": opt.tag is not None,
                "is_none": opt.is_none,
            }
            for opt in step.options
        ],
    }
