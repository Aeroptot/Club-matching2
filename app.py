#!/usr/bin/env python3
"""Simple web UI for the club recommendation engine."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from config import MAX_USER_TAGS, MEETING_PERIODS, MIN_FINAL_SCORE, MIN_RESULTS, WEEKDAYS
from recommender import load_clubs, recommend
from tag_hierarchy import all_known_tags, display_name
from tag_quiz import (
    advance_quiz_continue,
    empty_session,
    quiz_step_from_session,
    step_to_dict,
)

BASE = Path(__file__).parent
STATIC = BASE / "static"

DAY_LABELS = {
    "monday": "Mon",
    "tuesday": "Tue",
    "wednesday": "Wed",
    "thursday": "Thu",
    "friday": "Fri",
}

PERIOD_LABELS = {
    "period11": "Period 11",
    "period12": "Period 12",
    "lunchtime": "Lunch",
}


def recommendation_payload(rec) -> dict:
    matched = rec.matched_club_tags
    club_tags = [
        {"id": tag, "label": display_name(tag), "matched": tag in matched}
        for tag, _ in sorted(rec.club.tags.items(), key=lambda x: -x[1])
    ]
    return {
        "name": rec.club.name,
        "category": rec.club.category,
        "description": rec.club.description,
        "member_count": rec.club.member_count,
        "day": rec.club.day,
        "period": rec.club.period,
        "room": rec.club.room,
        "meeting_slot": rec.club.meeting_slot,
        "final_score_pct": round(rec.final_score_pct, 1),
        "above_threshold": rec.final_score >= MIN_FINAL_SCORE,
        "similarity_pct": round(rec.similarity * 100, 1),
        "popularity_multiplier": rec.popularity_multiplier,
        "club_tags": club_tags,
    }


class ClubHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return

    def _send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str) -> None:
        if not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        route = parsed.path

        if route in {"/", "/index.html"}:
            self._send_file(STATIC / "index.html", "text/html; charset=utf-8")
            return
        if route == "/app.js":
            self._send_file(STATIC / "app.js", "application/javascript; charset=utf-8")
            return
        if route == "/engine.js":
            self._send_file(STATIC / "engine.js", "application/javascript; charset=utf-8")
            return
        if route == "/styles.css":
            self._send_file(STATIC / "styles.css", "text/css; charset=utf-8")
            return
        if route == "/clubs.html":
            self._send_file(STATIC / "clubs.html", "text/html; charset=utf-8")
            return

        if route == "/api/clubs":
            clubs = load_clubs()
            self._send_json(
                [
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
            )
            return

        if route == "/api/tags":
            tags = sorted(all_known_tags(), key=lambda t: display_name(t).lower())
            self._send_json(
                {
                    "tags": [{"id": t, "label": display_name(t)} for t in tags],
                    "max_tags": MAX_USER_TAGS,
                }
            )
            return

        if route == "/api/slots":
            slots = []
            for day in WEEKDAYS:
                for period in MEETING_PERIODS:
                    slots.append(
                        {
                            "id": f"{day}:{period}",
                            "day": day,
                            "period": period,
                            "label": f"{DAY_LABELS[day]} · {PERIOD_LABELS[period]}",
                        }
                    )
            self._send_json({"days": list(WEEKDAYS), "periods": list(MEETING_PERIODS), "slots": slots})
            return

        if route == "/api/quiz":
            step = quiz_step_from_session(empty_session())
            self._send_json(step_to_dict(step, empty_session()))
            return

        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        data = self._read_json()

        if parsed.path == "/api/quiz":
            session = data.get("session") or empty_session()
            action = data.get("action")
            try:
                if action == "continue":
                    session, tags_added = advance_quiz_continue(
                        session, data.get("selections") or []
                    )
                elif action == "pick":
                    session, tags_added = advance_quiz_continue(
                        session, [data.get("pick", "")]
                    )
                elif action == "restart":
                    session = empty_session()
                    tags_added = []
                elif action == "status":
                    tags_added = []
                else:
                    self._send_json({"error": "Unknown quiz action."}, HTTPStatus.BAD_REQUEST)
                    return
            except ValueError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return

            step = quiz_step_from_session(session)
            payload = step_to_dict(step, session)
            payload["tags_added"] = tags_added
            self._send_json(payload)
            return

        if parsed.path == "/api/recommend":
            tags = data.get("tags") or []
            blocked_slots = data.get("blocked_slots") or []

            if not tags:
                self._send_json({"error": "Select at least one interest tag."}, HTTPStatus.BAD_REQUEST)
                return
            if len(tags) > MAX_USER_TAGS:
                self._send_json(
                    {"error": f"Select at most {MAX_USER_TAGS} tags."},
                    HTTPStatus.BAD_REQUEST,
                )
                return

            tag_weights = data.get("tag_weights") or {}

            try:
                results = recommend(
                    tags,
                    blocked_slots=blocked_slots,
                    tag_weight_mults=tag_weights,
                )
            except ValueError as exc:
                self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return

            above = sum(1 for r in results if r.final_score >= MIN_FINAL_SCORE)
            self._send_json(
                {
                    "count": len(results),
                    "above_threshold": above,
                    "min_results": MIN_RESULTS,
                    "tags": tags,
                    "blocked_slots": blocked_slots,
                    "results": [recommendation_payload(r) for r in results],
                }
            )
            return

        self.send_error(HTTPStatus.NOT_FOUND)


def main() -> None:
    if not (BASE / "clubs_weighted.csv").is_file():
        from build_clubs_data import build_weighted_csv

        build_weighted_csv()
    load_clubs()

    host = "127.0.0.1"
    port = 8765
    server = ThreadingHTTPServer((host, port), ClubHandler)
    print(f"Club matcher running at http://{host}:{port}")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    main()
