"""Database-backed tournament generation and progression helpers."""
from datetime import datetime

import models


class TournamentError(ValueError):
    pass


def knockout_bracket(entrant_ids):
    """Return every bracket node, including explicit first-round byes."""
    entrants = list(entrant_ids)
    if len(entrants) < 2:
        raise TournamentError("At least two active entrants are required")
    size = 1 << (len(entrants) - 1).bit_length()
    bye_count = size - len(entrants)
    first_round = []
    cursor = 0
    for match_no in range(1, size // 2 + 1):
        if match_no <= bye_count:
            first_round.append((entrants[cursor], None))
            cursor += 1
        else:
            first_round.append((entrants[cursor], entrants[cursor + 1]))
            cursor += 2
    rounds = []
    for round_no in range(1, size.bit_length()):
        count = size >> round_no
        fixtures = []
        for match_no in range(1, count + 1):
            if round_no == 1:
                a, b = first_round[match_no - 1]
            else:
                a = b = None
            fixtures.append({"round_number": round_no, "match_number": match_no,
                             "participant_1": a, "participant_2": b,
                             "is_bye": round_no == 1 and (a is None) != (b is None),
                             "empty": round_no == 1 and a is None and b is None})
        rounds.append(fixtures)
    return rounds


def round_robin_fixtures(entrant_ids):
    """Circle-method schedule, with a None opponent representing a bye."""
    entrants = list(entrant_ids)
    if len(entrants) < 2:
        raise TournamentError("At least two active entrants are required")
    slots = entrants + ([None] if len(entrants) % 2 else [])
    fixed = slots[0]
    rotating = slots[1:]
    rounds = []
    for _ in range(len(slots) - 1):
        row = [fixed] + rotating
        fixtures = []
        for i in range(len(row) // 2):
            left, right = row[i], row[-1 - i]
            if left is not None or right is not None:
                fixtures.append((left, right))
        rounds.append(fixtures)
        rotating = [rotating[-1]] + rotating[:-1]
    return rounds


def _active_entrants(db, tournament):
    return db.query(models.TournamentParticipant).filter_by(
        tournament_id=tournament.tournament_id, status="registered"
    ).order_by(models.TournamentParticipant.tournament_participant_id).all()


def generate_schedule(db, tournament):
    """Create fixtures once, atomically, then activate the tournament."""
    if tournament.status not in ("registration", "ready"):
        raise TournamentError("Tournament must be open or ready before schedule generation")
    existing = db.query(models.CompetitionMatch.match_id).filter_by(tournament_id=tournament.tournament_id).first()
    if existing:
        raise TournamentError("Fixtures have already been generated")
    entrants = _active_entrants(db, tournament)
    if len(entrants) < tournament.min_participants:
        raise TournamentError("Tournament does not meet its minimum participant count")
    ids = [p.tournament_participant_id for p in entrants]
    if tournament.format == "single_elimination":
        plans = knockout_bracket(ids)
    elif tournament.format == "round_robin":
        plans = round_robin_fixtures(ids)
    elif tournament.format == "multi_entrant":
        plans = []
    else:
        raise TournamentError("Unsupported tournament format")
    if tournament.format == "single_elimination":
        match_map = {}
        for fixtures in plans:
            for plan in fixtures:
                match = models.CompetitionMatch(
                    tournament_id=tournament.tournament_id,
                    round_number=plan["round_number"], match_number=plan["match_number"],
                    status="cancelled" if plan["empty"] else "pending", is_bye=plan["is_bye"])
                db.add(match)
                db.flush()
                match_map[(plan["round_number"], plan["match_number"])] = match
                sides = [plan["participant_1"], plan["participant_2"]]
                for side_no, participant_id in enumerate(sides, start=1):
                    db.add(models.CompetitionMatchSide(match_id=match.match_id, side_number=side_no,
                                                       tournament_participant_id=participant_id))
                if plan["is_bye"]:
                    match.status = "completed"
                    match.result_status = "confirmed"
                    match.winner_participant_id = plan["participant_1"] or plan["participant_2"]
                    match.confirmed_at = datetime.utcnow()
            db.flush()
        # Apply all first-round byes to their pre-created next-round node.
        for plan in plans[0]:
            if plan["is_bye"]:
                winner_id = plan["participant_1"] or plan["participant_2"]
                parent = match_map[(2, (plan["match_number"] + 1) // 2)]
                side_no = 1 if plan["match_number"] % 2 else 2
                side = db.query(models.CompetitionMatchSide).filter_by(match_id=parent.match_id, side_number=side_no).one()
                side.tournament_participant_id = winner_id
                if parent.status == "pending":
                    parent.status = "scheduled"
        for fixtures in plans:
            for plan in fixtures:
                match = match_map[(plan["round_number"], plan["match_number"])]
                if match.status == "pending" and plan["round_number"] == 1:
                    match.status = "scheduled"
    elif tournament.format == "round_robin":
        for round_no, fixtures in enumerate(plans, start=1):
            for match_no, pair in enumerate(fixtures, start=1):
                a, b = pair
                bye = a is None or b is None
                match = models.CompetitionMatch(
                    tournament_id=tournament.tournament_id, round_number=round_no,
                    match_number=match_no, status="completed" if bye else "scheduled",
                    result_status="confirmed" if bye else "none", is_bye=bye,
                    winner_participant_id=a or b if bye else None,
                    confirmed_at=datetime.utcnow() if bye else None)
                db.add(match)
                db.flush()
                db.add_all([
                    models.CompetitionMatchSide(match_id=match.match_id, side_number=1, tournament_participant_id=a),
                    models.CompetitionMatchSide(match_id=match.match_id, side_number=2, tournament_participant_id=b),
                ])
    else:
        match = models.CompetitionMatch(tournament_id=tournament.tournament_id,
            round_number=1, match_number=1, status="scheduled")
        db.add(match)
        db.flush()
        for side_number, participant_id in enumerate(ids, start=1):
            db.add(models.CompetitionMatchSide(match_id=match.match_id, side_number=side_number,
                                               tournament_participant_id=participant_id))
    tournament.status = "in_progress"
    db.flush()
    return db.query(models.CompetitionMatch).filter_by(tournament_id=tournament.tournament_id).order_by(
        models.CompetitionMatch.round_number, models.CompetitionMatch.match_number).all()


def match_sides(db, match):
    sides = db.query(models.CompetitionMatchSide).filter_by(match_id=match.match_id).order_by(
        models.CompetitionMatchSide.side_number).all()
    return sides


def progress_match(db, tournament, match, winner_id):
    """Advance a confirmed knockout winner; mark the tournament complete at final."""
    if tournament.format == "single_elimination":
        total_rounds = (len(_active_entrants(db, tournament)) - 1).bit_length()
        if match.round_number >= total_rounds:
            tournament.status = "completed"
            return
        parent_no = (match.match_number + 1) // 2
        parent = db.query(models.CompetitionMatch).filter_by(
            tournament_id=tournament.tournament_id,
            round_number=match.round_number + 1, match_number=parent_no).with_for_update().one()
        side_no = 1 if match.match_number % 2 else 2
        side = db.query(models.CompetitionMatchSide).filter_by(match_id=parent.match_id, side_number=side_no).with_for_update().one()
        if side.tournament_participant_id not in (None, winner_id):
            raise TournamentError("Conflicting participant already advanced into this bracket slot")
        side.tournament_participant_id = winner_id
        if parent.status == "pending":
            parent.status = "scheduled"
    else:
        outstanding = db.query(models.CompetitionMatch.match_id).filter(
            models.CompetitionMatch.tournament_id == tournament.tournament_id,
            models.CompetitionMatch.is_bye.is_(False),
            models.CompetitionMatch.status != "completed",
        ).first()
        if outstanding is None:
            tournament.status = "completed"


def standings(db, tournament):
    if tournament.format != "round_robin":
        raise TournamentError("Standings are available for round-robin tournaments only")
    rows = {}
    for entrant in _active_entrants(db, tournament):
        rows[entrant.tournament_participant_id] = {"participant_id": entrant.tournament_participant_id,
            "played": 0, "wins": 0, "draws": 0, "losses": 0, "points": 0}
    matches = db.query(models.CompetitionMatch).filter_by(
        tournament_id=tournament.tournament_id, result_status="confirmed", is_bye=False).all()
    win_points = (tournament.rules_config or {}).get("win_points", 3)
    draw_points = (tournament.rules_config or {}).get("draw_points", 1)
    loss_points = (tournament.rules_config or {}).get("loss_points", 0)
    for match in matches:
        sides = match_sides(db, match)
        ids = [s.tournament_participant_id for s in sides]
        if any(pid not in rows for pid in ids):
            continue
        for pid in ids:
            rows[pid]["played"] += 1
        if match.is_draw:
            for pid in ids:
                rows[pid]["draws"] += 1
                rows[pid]["points"] += draw_points
        else:
            for pid in ids:
                if pid == match.winner_participant_id:
                    rows[pid]["wins"] += 1
                    rows[pid]["points"] += win_points
                else:
                    rows[pid]["losses"] += 1
                    rows[pid]["points"] += loss_points
    return sorted(rows.values(), key=lambda row: (-row["points"], -row["wins"], row["participant_id"]))
