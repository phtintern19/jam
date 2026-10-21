"""Framework-neutral validators for generic result data shapes.

These templates do not implement a sport's official rules. Tournament
standings/progression should consume results only after an authorized
confirmation transaction.
"""
from dataclasses import dataclass
import math
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class MatchResult:
    status: str
    participants: list
    winner_id: Optional[str]
    draw: bool
    score: Dict[str, Any]
    verification_status: str = "pending"


class ResultValidationError(ValueError):
    pass


def _nonnegative_number(value):
    return (not isinstance(value, bool) and isinstance(value, (int, float))
            and (not isinstance(value, float) or math.isfinite(value)) and value >= 0)


def _participants(result):
    people = result.get("participants")
    if not isinstance(people, list) or len(people) < 2:
        raise ResultValidationError("At least two participants are required")
    ids = [p.get("id") for p in people if isinstance(p, dict)]
    if len(ids) != len(people) or any(isinstance(value, bool) or not isinstance(value, (int, str)) or not value for value in ids) or len(set(ids)) != len(ids):
        raise ResultValidationError("Participants must have unique non-empty IDs")
    return people, ids


def validate_points(result):
    people, ids = _participants(result)
    scores = result.get("score")
    if not isinstance(scores, dict) or set(scores) != set(ids):
        raise ResultValidationError("A numeric score is required for each participant")
    if any(not _nonnegative_number(value) for value in scores.values()):
        raise ResultValidationError("Scores must be non-negative numbers")
    top = max(scores.values())
    leaders = [pid for pid, score in scores.items() if score == top]
    draw = len(leaders) > 1
    winner = result.get("winner_id")
    if winner is None and not draw:
        winner = leaders[0]
    if winner is not None and (draw or winner not in ids or winner != leaders[0]):
        raise ResultValidationError("Winner does not match the submitted scores")
    if draw and winner is not None:
        raise ResultValidationError("A tied points result cannot declare a winner")
    return MatchResult("completed", people, winner, draw, scores, result.get("verification_status", "pending"))


def validate_placement(result):
    people, ids = _participants(result)
    placements = result.get("score")
    if not isinstance(placements, dict) or set(placements) != set(ids):
        raise ResultValidationError("A placement is required for each participant")
    values = list(placements.values())
    if any(isinstance(v, bool) or not isinstance(v, int) or v < 1 for v in values):
        raise ResultValidationError("Placements must be positive integers")
    first = min(values)
    leaders = [pid for pid, place in placements.items() if place == first]
    winner = result.get("winner_id")
    if winner is None and len(leaders) == 1:
        winner = leaders[0]
    if winner is not None and winner not in leaders:
        raise ResultValidationError("Winner must have the best placement")
    return MatchResult("completed", people, winner, len(leaders) > 1, placements, result.get("verification_status", "pending"))


def validate_series(result):
    people, ids = _participants(result)
    games = result.get("score")
    if not isinstance(games, list) or not games:
        raise ResultValidationError("Series score must contain at least one game/map")
    wins = {pid: 0 for pid in ids}
    for game in games:
        if not isinstance(game, dict) or game.get("winner_id") not in ids:
            raise ResultValidationError("Each game/map must name a participant winner")
        wins[game["winner_id"]] += 1
    best = max(wins.values())
    leaders = [pid for pid, count in wins.items() if count == best]
    winner = result.get("winner_id")
    if winner is None and len(leaders) == 1:
        winner = leaders[0]
    if winner is not None and (len(leaders) != 1 or winner != leaders[0]):
        raise ResultValidationError("Series winner does not match game/map wins")
    return MatchResult("completed", people, winner, len(leaders) > 1, {"games": games, "wins": wins}, result.get("verification_status", "pending"))


def validate_sets(result):
    return validate_series(result)


def validate_win_draw_loss(result):
    people, ids = _participants(result)
    outcome = result.get("score")
    if not isinstance(outcome, dict) or outcome.get("outcome") not in {"win", "draw"}:
        raise ResultValidationError("Outcome must explicitly be win or draw")
    if outcome["outcome"] == "draw":
        if result.get("winner_id") is not None:
            raise ResultValidationError("Draw cannot declare a winner")
        return MatchResult("completed", people, None, True, outcome, result.get("verification_status", "pending"))
    if result.get("winner_id") not in ids:
        raise ResultValidationError("A valid participant winner is required")
    return MatchResult("completed", people, result["winner_id"], False, outcome, result.get("verification_status", "pending"))


def validate_timed_distance(result):
    people, ids = _participants(result)
    scores = result.get("score")
    if not isinstance(scores, dict) or set(scores) != set(ids):
        raise ResultValidationError("A measurement is required for each participant")
    if any(not _nonnegative_number(v) for v in scores.values()):
        raise ResultValidationError("Measurements must be non-negative numbers")
    measurement_type, unit = result.get("measurement_type"), result.get("unit")
    if not isinstance(measurement_type, str) or not measurement_type.strip() or len(measurement_type) > 80:
        raise ResultValidationError("measurement_type must be a non-empty string of at most 80 characters")
    if not isinstance(unit, str) or not unit.strip() or len(unit) > 30:
        raise ResultValidationError("unit must be a non-empty string of at most 30 characters")
    direction = result.get("ranking", "lower_wins")
    if direction not in {"lower_wins", "higher_wins"}:
        raise ResultValidationError("ranking must be lower_wins or higher_wins")
    best = min(scores.values()) if direction == "lower_wins" else max(scores.values())
    leaders = [pid for pid, value in scores.items() if value == best]
    winner = result.get("winner_id")
    if winner is None and len(leaders) == 1:
        winner = leaders[0]
    if winner is not None and (len(leaders) != 1 or winner != leaders[0]):
        raise ResultValidationError("Winner does not match the measured result")
    return MatchResult("completed", people, winner, len(leaders) > 1, scores, result.get("verification_status", "pending"))


SCORING_TEMPLATES = {
    "points": validate_points, "placement": validate_placement,
    "series": validate_series, "sets": validate_sets,
    "win_draw_loss": validate_win_draw_loss, "timed_distance": validate_timed_distance,
}


def validate_result(template, result):
    validator = SCORING_TEMPLATES.get(template)
    if validator is None:
        raise ResultValidationError(f"Unknown or unimplemented scoring template: {template}")
    return validator(result)
