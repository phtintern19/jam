"""Authenticated Flask endpoints for the shared tournament engine."""
from datetime import datetime, timezone
import math

from flask import jsonify, request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import StaleDataError

import models
from competition_rules import ResultValidationError, validate_result
from tournament_engine import TournamentError, generate_schedule, match_sides, progress_match, standings


def _role(user):
    value = getattr(user.user_type, "value", user.user_type)
    return str(value).split(".")[-1]


def _admin(user):
    return _role(user) == "admin"


def _manage(user, tournament):
    return _admin(user) or user.user_id == tournament.created_by


def _audit_tournament(db, tournament_id, actor_id, action, details=None):
    db.add(models.TournamentAudit(tournament_id=tournament_id, actor_id=actor_id,
                                  action=action, details=details or {}))


def _iso(value):
    return value.isoformat() if value else None


def _participant_dict(db, entrant):
    if not entrant:
        return None
    if entrant.participant_type == "individual":
        person = db.query(models.Player).filter_by(player_id=entrant.player_id).first()
        label = person.full_name if person else f"Player {entrant.player_id}"
        return {"participant_id": entrant.tournament_participant_id, "type": "individual", "id": entrant.player_id, "name": label}
    team = db.query(models.Team).filter_by(team_id=entrant.team_id).first()
    return {"participant_id": entrant.tournament_participant_id, "type": "team", "id": entrant.team_id,
            "name": team.team_name if team else f"Team {entrant.team_id}"}


def _match_dict(db, match):
    sides = match_sides(db, match)
    participants = []
    for side in sides:
        entrant = db.query(models.TournamentParticipant).filter_by(
            tournament_participant_id=side.tournament_participant_id).first() if side.tournament_participant_id else None
        participants.append({"slot": side.side_number, "participant": _participant_dict(db, entrant)})
    return {"match_id": match.match_id, "tournament_id": match.tournament_id,
            "round": match.round_number, "match_number": match.match_number,
            "status": match.status, "result_status": match.result_status, "is_bye": match.is_bye,
            "participants": participants, "winner_participant_id": match.winner_participant_id,
            "is_draw": match.is_draw, "score": match.score_data, "scheduled_at": _iso(match.scheduled_at),
            "venue": match.venue, "confirmed_at": _iso(match.confirmed_at)}


def _tournament_dict(db, tournament, include_matches=False):
    sport = db.query(models.Sport).filter_by(sport_id=tournament.sport_id).first()
    entrants = db.query(models.TournamentParticipant).filter_by(tournament_id=tournament.tournament_id).all()
    payload = {"tournament_id": tournament.tournament_id, "name": tournament.name,
               "sport": {"sport_id": tournament.sport_id, "name": sport.name if sport else None,
                         "slug": sport.slug if sport else None},
               "event_id": tournament.event_id, "format": tournament.format,
               "participant_type": tournament.participant_type, "scoring_template": tournament.scoring_template,
               "status": tournament.status, "min_participants": tournament.min_participants,
               "max_participants": tournament.max_participants, "participant_count": sum(p.status == "registered" for p in entrants),
               "allow_draws": tournament.allow_draws, "rules_config": tournament.rules_config or {},
               "starts_at": _iso(tournament.starts_at), "venue": tournament.venue,
               "created_by": tournament.created_by, "created_at": _iso(tournament.created_at)}
    if include_matches:
        matches = db.query(models.CompetitionMatch).filter_by(tournament_id=tournament.tournament_id).order_by(
            models.CompetitionMatch.round_number, models.CompetitionMatch.match_number).all()
        payload["matches"] = [_match_dict(db, match) for match in matches]
        payload["participants"] = [{**_participant_dict(db, p), "status": p.status} for p in entrants]
    return payload


def _parse_datetime(value):
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValueError("scheduled_at must be an ISO 8601 string")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed
    except ValueError as exc:
        raise ValueError("scheduled_at must be an ISO 8601 datetime") from exc


def register_tournament_routes(app, get_current_user, session_factory):
    def db_session():
        return session_factory()

    def serialize_error(message, status=400):
        return jsonify({"success": False, "error": message}), status

    def request_object():
        payload = request.get_json(silent=True)
        return payload if isinstance(payload, dict) else None

    def can_manage(user, tournament):
        return _manage(user, tournament)

    def active_tournament_participant(db, tournament, match, user):
        participant_ids = {side.tournament_participant_id for side in match_sides(db, match) if side.tournament_participant_id}
        if not participant_ids:
            return None
        if _admin(user) or _manage(user, tournament):
            return True
        if tournament.participant_type == "individual":
            own = db.query(models.TournamentParticipant).filter_by(
                tournament_id=tournament.tournament_id, player_id=getattr(user.player, "player_id", None), status="registered").first()
            return own if own and own.tournament_participant_id in participant_ids else None
        owner_user_id = user.parent_user_id if _role(user) in {"team_manager", "team_analyst"} else user.user_id
        team_ids = [row[0] for row in db.query(models.Team.team_id).join(models.TeamOwner).filter(
            models.TeamOwner.user_id == owner_user_id).all()]
        own = db.query(models.TournamentParticipant).filter(
            models.TournamentParticipant.tournament_id == tournament.tournament_id,
            models.TournamentParticipant.team_id.in_(team_ids),
            models.TournamentParticipant.status == "registered").first() if team_ids else None
        return own if own and own.tournament_participant_id in participant_ids else None

    @app.route("/api/tournaments", methods=["GET", "POST"])
    def tournaments_collection():
        db = db_session()
        try:
            if request.method == "GET":
                query = db.query(models.Tournament)
                if request.args.get("sport_id", type=int):
                    query = query.filter_by(sport_id=request.args.get("sport_id", type=int))
                if request.args.get("status"):
                    query = query.filter_by(status=request.args["status"])
                tournaments = query.order_by(models.Tournament.created_at.desc()).limit(200).all()
                return jsonify({"success": True, "tournaments": [_tournament_dict(db, t) for t in tournaments]})

            user = get_current_user()
            data = request_object()
            if data is None:
                return serialize_error("Request body must be a JSON object")
            name = data.get("name")
            if not isinstance(name, str) or not name.strip() or len(name.strip()) > 160:
                return serialize_error("name is required and must be at most 160 characters")
            sport_id = data.get("sport_id")
            if type(sport_id) is not int or sport_id < 1:
                return serialize_error("sport_id must be a positive integer")
            sport = db.query(models.Sport).filter_by(sport_id=sport_id, is_active=True, tier=1).first()
            if not sport:
                return serialize_error("An active Tier 1 sport_id is required", 404)
            fmt = data.get("format")
            supported_formats = sport.competition_formats or []
            if not isinstance(supported_formats, list) or fmt not in {"single_elimination", "round_robin", "multi_entrant"} or fmt not in supported_formats:
                return serialize_error("This sport does not have that competition format enabled", 400)
            participant_type = data.get("participant_type")
            if participant_type not in {"individual", "team"}:
                return serialize_error("participant_type must be individual or team")
            if sport.participation_format not in {"both", participant_type}:
                return serialize_error("This sport is not configured for that participant type")
            template = data.get("scoring_template") or sport.scoring_template
            from competition_rules import SCORING_TEMPLATES
            if not template or template not in SCORING_TEMPLATES or (sport.scoring_template and template != sport.scoring_template):
                return serialize_error("A supported scoring template must be configured for this sport")
            allow_draws = data.get("allow_draws", fmt == "round_robin")
            if not isinstance(allow_draws, bool) or (allow_draws and fmt not in {"round_robin", "multi_entrant"}):
                return serialize_error("Draws are supported only for round-robin or multi-entrant tournaments")
            minimum = data.get("min_participants", 2)
            maximum = data.get("max_participants", 64)
            if type(minimum) is not int or type(maximum) is not int or minimum < 2 or maximum < minimum or maximum > 512:
                return serialize_error("Participant limits must satisfy 2 <= minimum <= maximum <= 512")
            if fmt in {"round_robin", "multi_entrant"} and maximum > 128:
                return serialize_error("Round-robin and multi-entrant tournaments are limited to 128 entrants in this phase")
            event_id = data.get("event_id")
            if event_id is not None:
                if type(event_id) is not int or event_id < 1:
                    return serialize_error("event_id must be a positive integer")
                event = db.query(models.Event).filter_by(event_id=event_id).first()
                if not event:
                    return serialize_error("Event not found", 404)
                if not _admin(user) and event.creator_id != user.user_id:
                    return serialize_error("Only the event organizer can link its event", 403)
                linked_sport_ids = {linked.sport_id for linked in event.sports}
                if ((event.sport_id and event.sport_id != sport.sport_id) or
                        (linked_sport_ids and sport.sport_id not in linked_sport_ids)):
                    return serialize_error("Tournament sport must match the linked event sport")
            rules = data.get("rules_config") or {}
            if not isinstance(rules, dict):
                return serialize_error("rules_config must be an object")
            for key in ("win_points", "draw_points", "loss_points"):
                if key in rules and (type(rules[key]) not in (int, float) or rules[key] < 0 or
                                     (isinstance(rules[key], float) and not math.isfinite(rules[key]))):
                    return serialize_error(f"{key} must be a non-negative number")
            venue = data.get("venue")
            if venue is not None and (not isinstance(venue, str) or len(venue) > 255):
                return serialize_error("venue must be a string of at most 255 characters")
            tournament = models.Tournament(name=name.strip(), sport_id=sport.sport_id, event_id=event_id,
                created_by=user.user_id, format=fmt, participant_type=participant_type,
                scoring_template=template, min_participants=minimum, max_participants=maximum,
                allow_draws=allow_draws, rules_config=rules, starts_at=_parse_datetime(data.get("starts_at")),
                venue=venue)
            db.add(tournament)
            db.flush()
            _audit_tournament(db, tournament.tournament_id, user.user_id, "created", {"name": tournament.name})
            db.commit()
            return jsonify({"success": True, "tournament": _tournament_dict(db, tournament)}), 201
        except ValueError as exc:
            db.rollback()
            return serialize_error(str(exc))
        except (IntegrityError, StaleDataError):
            db.rollback()
            return serialize_error("Tournament data conflicted with a concurrent update", 409)
        finally:
            db.close()

    @app.route("/api/tournaments/sports", methods=["GET"])
    def tournament_sports():
        """Return only active Tier 1 sports for tournament creation."""
        db = db_session()
        try:
            sports = db.query(models.Sport).filter_by(tier=1, is_active=True).order_by(models.Sport.name).all()
            return jsonify({"success": True, "sports": [{
                "sport_id": sport.sport_id,
                "name": sport.name,
                "tier": sport.tier,
                "competition_formats": sport.competition_formats or [],
                "scoring_template": sport.scoring_template,
                "participation_format": sport.participation_format,
            } for sport in sports]})
        finally:
            db.close()

    @app.route("/api/tournaments/<int:tournament_id>", methods=["GET", "PUT"])
    def tournament_detail(tournament_id):
        db = db_session()
        try:
            query = db.query(models.Tournament).filter_by(tournament_id=tournament_id)
            if request.method == "PUT":
                query = query.with_for_update()
            tournament = query.first()
            if not tournament:
                return serialize_error("Tournament not found", 404)
            if request.method == "GET":
                return jsonify({"success": True, "tournament": _tournament_dict(db, tournament)})
            user = get_current_user()
            if not can_manage(user, tournament):
                return serialize_error("Only the tournament organizer can edit it", 403)
            if tournament.status not in {"draft", "registration"}:
                return serialize_error("Tournament settings are locked after registration closes", 409)
            data = request_object()
            if data is None:
                return serialize_error("Request body must be a JSON object")
            for field in ("name", "venue"):
                if field in data:
                    if field == "name" and (not isinstance(data[field], str) or not data[field].strip() or len(data[field]) > 160):
                        return serialize_error("name must be a non-empty string of at most 160 characters")
                    setattr(tournament, field, data[field].strip() if isinstance(data[field], str) else data[field])
            if "starts_at" in data:
                tournament.starts_at = _parse_datetime(data["starts_at"])
            if "venue" in data and data["venue"] is not None and (not isinstance(data["venue"], str) or len(data["venue"]) > 255):
                return serialize_error("venue must be a string of at most 255 characters")
            if "max_participants" in data:
                maximum = data["max_participants"]
                current = db.query(models.TournamentParticipant).filter_by(tournament_id=tournament_id, status="registered").count()
                if type(maximum) is not int or maximum < current or maximum < tournament.min_participants or maximum > 512:
                    return serialize_error("max_participants must cover registered entrants and be at most 512")
                if tournament.format in {"round_robin", "multi_entrant"} and maximum > 128:
                    return serialize_error("This tournament format is limited to 128 entrants")
                tournament.max_participants = maximum
            _audit_tournament(db, tournament_id, user.user_id, "updated", {"fields": sorted(data.keys())})
            db.commit()
            return jsonify({"success": True, "tournament": _tournament_dict(db, tournament)})
        except ValueError as exc:
            db.rollback()
            return serialize_error(str(exc))
        except StaleDataError:
            db.rollback()
            return serialize_error("Tournament changed concurrently; reload and retry", 409)
        finally:
            db.close()

    @app.route("/api/tournaments/<int:tournament_id>/open", methods=["POST"])
    def open_tournament(tournament_id):
        return _transition_tournament(tournament_id, "registration")

    @app.route("/api/tournaments/<int:tournament_id>/ready", methods=["POST"])
    def ready_tournament(tournament_id):
        return _transition_tournament(tournament_id, "ready")

    @app.route("/api/tournaments/<int:tournament_id>/cancel", methods=["POST"])
    def cancel_tournament(tournament_id):
        return _transition_tournament(tournament_id, "cancelled")

    def _transition_tournament(tournament_id, target):
        db = db_session()
        try:
            user = get_current_user()
            tournament = db.query(models.Tournament).filter_by(tournament_id=tournament_id).with_for_update().first()
            if not tournament:
                return serialize_error("Tournament not found", 404)
            if not can_manage(user, tournament):
                return serialize_error("Only the tournament organizer can change its state", 403)
            transitions = {"registration": {"draft"}, "ready": {"registration"}, "cancelled": {"draft", "registration", "ready", "in_progress"}}
            if tournament.status not in transitions[target]:
                return serialize_error(f"Cannot transition {tournament.status} to {target}", 409)
            count = db.query(models.TournamentParticipant).filter_by(tournament_id=tournament_id, status="registered").count()
            if target == "ready" and count < tournament.min_participants:
                return serialize_error("Tournament has fewer than its minimum required entrants", 409)
            previous = tournament.status
            tournament.status = target
            if target == "cancelled":
                db.query(models.CompetitionMatch).filter(
                    models.CompetitionMatch.tournament_id == tournament_id,
                    models.CompetitionMatch.status.notin_(["completed", "cancelled"]),
                ).update({models.CompetitionMatch.status: "cancelled"}, synchronize_session="fetch")
            _audit_tournament(db, tournament_id, user.user_id, "state_changed", {"from": previous, "to": target})
            db.commit()
            return jsonify({"success": True, "tournament": _tournament_dict(db, tournament)})
        except StaleDataError:
            db.rollback()
            return serialize_error("Tournament changed concurrently; retry", 409)
        finally:
            db.close()

    @app.route("/api/tournaments/<int:tournament_id>/participants", methods=["GET", "POST"])
    def tournament_participants(tournament_id):
        db = db_session()
        try:
            query = db.query(models.Tournament).filter_by(tournament_id=tournament_id)
            if request.method == "POST":
                query = query.with_for_update()
            tournament = query.first()
            if not tournament:
                return serialize_error("Tournament not found", 404)
            if request.method == "GET":
                entrants = db.query(models.TournamentParticipant).filter_by(tournament_id=tournament_id).all()
                return jsonify({"success": True, "participants": [{**_participant_dict(db, p), "status": p.status} for p in entrants]})
            user = get_current_user()
            if tournament.status != "registration":
                return serialize_error("Registration is not open", 409)
            data = request_object()
            if data is None:
                return serialize_error("Request body must be a JSON object")
            entity_id = data.get("participant_id")
            if type(entity_id) is not int or entity_id < 1:
                return serialize_error("participant_id must be a positive integer")
            if tournament.participant_type == "individual":
                entity = db.query(models.Player).filter_by(player_id=entity_id, is_active=True).first()
                if not entity:
                    return serialize_error("Active player not found", 404)
                authorized = _manage(user, tournament) or entity.user_id == user.user_id
                kwargs = {"player_id": entity_id, "team_id": None}
            else:
                entity = db.query(models.Team).filter_by(team_id=entity_id, status="active").first()
                if not entity:
                    return serialize_error("Active team not found", 404)
                owner_user_id = user.parent_user_id if _role(user) in {"team_manager", "team_analyst"} else user.user_id
                authorized = _manage(user, tournament) or entity.owner.user_id == owner_user_id
                kwargs = {"player_id": None, "team_id": entity_id}
            if not authorized:
                return serialize_error("You cannot register this participant", 403)
            if tournament.event_id:
                if tournament.participant_type == "team" and entity.event_id != tournament.event_id:
                    return serialize_error("Team must belong to the tournament event")
                if tournament.participant_type == "individual" and not db.query(models.player_events).filter_by(
                        player_id=entity_id, event_id=tournament.event_id).first():
                    return serialize_error("Player must be registered for the tournament event")
            count = db.query(models.TournamentParticipant).filter_by(tournament_id=tournament_id, status="registered").count()
            if count >= tournament.max_participants:
                return serialize_error("Tournament has reached its participant capacity", 409)
            participant = models.TournamentParticipant(tournament_id=tournament_id,
                participant_type=tournament.participant_type, **kwargs)
            db.add(participant)
            db.flush()
            _audit_tournament(db, tournament_id, user.user_id, "participant_registered",
                              {"participant_id": participant.tournament_participant_id})
            db.commit()
            return jsonify({"success": True, "participant": {**_participant_dict(db, participant), "status": participant.status}}), 201
        except IntegrityError:
            db.rollback()
            return serialize_error("Participant is already registered", 409)
        finally:
            db.close()

    @app.route("/api/tournaments/<int:tournament_id>/participants/<int:participant_id>/withdraw", methods=["POST"])
    def withdraw_participant(tournament_id, participant_id):
        db = db_session()
        try:
            user = get_current_user()
            tournament = db.query(models.Tournament).filter_by(tournament_id=tournament_id).with_for_update().first()
            participant = db.query(models.TournamentParticipant).filter_by(
                tournament_id=tournament_id, tournament_participant_id=participant_id).first()
            if not tournament or not participant:
                return serialize_error("Tournament or participant not found", 404)
            if tournament.status != "registration":
                return serialize_error("Participants can withdraw only during registration", 409)
            own = ((participant.player_id and getattr(user.player, "player_id", None) == participant.player_id) or
                   (participant.team_id and participant.team and participant.team.owner.user_id in {user.user_id, user.parent_user_id}))
            if not own and not can_manage(user, tournament):
                return serialize_error("You cannot withdraw this participant", 403)
            participant.status = "withdrawn"
            participant.withdrawn_at = datetime.utcnow()
            _audit_tournament(db, tournament_id, user.user_id, "participant_withdrawn",
                              {"participant_id": participant_id})
            db.commit()
            return jsonify({"success": True, "status": participant.status})
        finally:
            db.close()

    @app.route("/api/tournaments/<int:tournament_id>/start", methods=["POST"])
    def start_tournament(tournament_id):
        db = db_session()
        try:
            user = get_current_user()
            tournament = db.query(models.Tournament).filter_by(tournament_id=tournament_id).with_for_update().first()
            if not tournament:
                return serialize_error("Tournament not found", 404)
            if not can_manage(user, tournament):
                return serialize_error("Only the tournament organizer can generate fixtures", 403)
            matches = generate_schedule(db, tournament)
            _audit_tournament(db, tournament_id, user.user_id, "fixtures_generated",
                              {"match_count": len(matches), "format": tournament.format})
            db.commit()
            return jsonify({"success": True, "status": tournament.status, "match_count": len(matches),
                            "matches": [_match_dict(db, match) for match in matches[:100]]}), 201
        except TournamentError as exc:
            db.rollback()
            return serialize_error(str(exc), 409)
        except (IntegrityError, StaleDataError):
            db.rollback()
            return serialize_error("Fixture generation conflicted with another request", 409)
        finally:
            db.close()

    @app.route("/api/tournaments/<int:tournament_id>/matches", methods=["GET"])
    def tournament_matches(tournament_id):
        db = db_session()
        try:
            if not db.query(models.Tournament.tournament_id).filter_by(tournament_id=tournament_id).first():
                return serialize_error("Tournament not found", 404)
            limit = min(max(request.args.get("limit", 100, type=int) or 100, 1), 200)
            offset = max(request.args.get("offset", 0, type=int) or 0, 0)
            query = db.query(models.CompetitionMatch).filter_by(tournament_id=tournament_id).order_by(
                models.CompetitionMatch.round_number, models.CompetitionMatch.match_number)
            total = query.count()
            matches = query.offset(offset).limit(limit).all()
            return jsonify({"success": True, "total": total, "limit": limit, "offset": offset,
                            "matches": [_match_dict(db, match) for match in matches]})
        finally:
            db.close()

    @app.route("/api/matches/<int:match_id>", methods=["GET", "PUT"])
    def match_detail(match_id):
        db = db_session()
        try:
            match = db.query(models.CompetitionMatch).filter_by(match_id=match_id).first()
            if not match:
                return serialize_error("Match not found", 404)
            if request.method == "GET":
                return jsonify({"success": True, "match": _match_dict(db, match)})
            user = get_current_user()
            tournament = db.query(models.Tournament).filter_by(tournament_id=match.tournament_id).first()
            if not can_manage(user, tournament):
                return serialize_error("Only the tournament organizer can schedule matches", 403)
            if tournament.status != "in_progress":
                return serialize_error("Matches can be scheduled only while the tournament is in progress", 409)
            if match.status in {"completed", "cancelled"}:
                return serialize_error("Completed or cancelled matches cannot be rescheduled", 409)
            data = request_object()
            if data is None:
                return serialize_error("Request body must be a JSON object")
            if "scheduled_at" in data:
                match.scheduled_at = _parse_datetime(data["scheduled_at"])
            if "venue" in data:
                if data["venue"] is not None and (not isinstance(data["venue"], str) or len(data["venue"]) > 255):
                    return serialize_error("venue must be a string of at most 255 characters")
                match.venue = data["venue"]
            if match.status == "pending" and all(s.tournament_participant_id for s in match_sides(db, match)):
                match.status = "scheduled"
            db.commit()
            return jsonify({"success": True, "match": _match_dict(db, match)})
        except ValueError as exc:
            db.rollback()
            return serialize_error(str(exc))
        finally:
            db.close()

    @app.route("/api/matches/<int:match_id>/transition", methods=["POST"])
    def transition_match(match_id):
        db = db_session()
        try:
            user = get_current_user()
            match = db.query(models.CompetitionMatch).filter_by(match_id=match_id).with_for_update().first()
            if not match:
                return serialize_error("Match not found", 404)
            tournament = db.query(models.Tournament).filter_by(tournament_id=match.tournament_id).with_for_update().first()
            if not can_manage(user, tournament):
                return serialize_error("Only the tournament organizer can change match state", 403)
            if tournament.status != "in_progress":
                return serialize_error("Tournament is not in progress", 409)
            data = request_object()
            if data is None:
                return serialize_error("Request body must be a JSON object")
            target = data.get("status")
            transitions = {"scheduled": {"in_progress", "postponed", "cancelled"},
                           "postponed": {"scheduled", "cancelled"},
                           "in_progress": {"postponed", "cancelled"}}
            if target not in transitions.get(match.status, set()):
                return serialize_error(f"Cannot transition {match.status} to {target}", 409)
            if target == "in_progress" and not all(s.tournament_participant_id for s in match_sides(db, match)):
                return serialize_error("Both participant slots must be filled before a match starts", 409)
            match.status = target
            db.commit()
            return jsonify({"success": True, "match": _match_dict(db, match)})
        finally:
            db.close()

    @app.route("/api/matches/<int:match_id>/results", methods=["POST", "PUT"])
    def submit_match_result(match_id):
        db = db_session()
        try:
            user = get_current_user()
            match = db.query(models.CompetitionMatch).filter_by(match_id=match_id).with_for_update().first()
            if not match:
                return serialize_error("Match not found", 404)
            tournament = db.query(models.Tournament).filter_by(tournament_id=match.tournament_id).with_for_update().first()
            finalized_correction = request.method == "PUT" and match.result_status == "confirmed"
            if tournament.status != "in_progress" and not (finalized_correction and tournament.status == "completed"):
                return serialize_error("Tournament is not in progress", 409)
            if request.method == "PUT":
                if not can_manage(user, tournament):
                    return serialize_error("Only the tournament organizer can correct a result", 403)
            elif not active_tournament_participant(db, tournament, match, user):
                return serialize_error("Only the tournament organizer or a match participant may submit a result", 403)
            allowed = {"none", "rejected"} if request.method == "POST" else {"pending", "confirmed"}
            if match.result_status not in allowed:
                return serialize_error("A result is already awaiting confirmation or has been finalized", 409)
            if match.is_bye or (not finalized_correction and match.status in {"completed", "cancelled", "postponed", "pending"}):
                return serialize_error("This match cannot accept a result in its current state", 409)
            data = request_object()
            if data is None:
                return serialize_error("Request body must be a JSON object")
            sides = match_sides(db, match)
            ids = [str(s.tournament_participant_id) for s in sides]
            payload = {"participants": [{"id": value} for value in ids], "score": data.get("score")}
            supplied_winner = data.get("winner_participant_id")
            if supplied_winner is not None:
                if str(supplied_winner) not in ids:
                    return serialize_error("winner_participant_id must identify a match participant")
                payload["winner_id"] = str(supplied_winner)
            for key in ("measurement_type", "unit", "ranking"):
                if key in data:
                    payload[key] = data[key]
            try:
                validated = validate_result(tournament.scoring_template, payload)
            except ResultValidationError as exc:
                return serialize_error(str(exc))
            if validated.draw and (not tournament.allow_draws or tournament.format == "single_elimination"):
                return serialize_error("This tournament configuration does not allow drawn matches")
            old_winner_id = match.winner_participant_id
            new_winner_id = int(validated.winner_id) if validated.winner_id is not None else None
            if finalized_correction and tournament.format == "single_elimination":
                total_rounds = (db.query(models.TournamentParticipant).filter_by(
                    tournament_id=tournament.tournament_id, status="registered").count() - 1).bit_length()
                if match.round_number < total_rounds:
                    parent = db.query(models.CompetitionMatch).filter_by(tournament_id=tournament.tournament_id,
                        round_number=match.round_number + 1,
                        match_number=(match.match_number + 1) // 2).with_for_update().first()
                    if not parent or parent.status in {"in_progress", "completed", "cancelled"} or parent.result_status != "none":
                        return serialize_error("This result can no longer be corrected because the next match has progressed", 409)
                    side_no = 1 if match.match_number % 2 else 2
                    parent_side = db.query(models.CompetitionMatchSide).filter_by(
                        match_id=parent.match_id, side_number=side_no).with_for_update().one()
                    if parent_side.tournament_participant_id != old_winner_id:
                        return serialize_error("Bracket advancement is inconsistent; result correction was stopped", 409)
                    if new_winner_id is None:
                        return serialize_error("Knockout corrections must determine a winner")
                    parent_side.tournament_participant_id = new_winner_id
            match.winner_participant_id = new_winner_id
            match.is_draw = validated.draw
            match.score_data = {"template": tournament.scoring_template, "score": validated.score,
                                **{k: payload[k] for k in ("measurement_type", "unit", "ranking") if k in payload}}
            if request.method == "PUT":
                reason = data.get("reason")
                if not isinstance(reason, str) or not reason.strip() or len(reason) > 2000:
                    return serialize_error("A correction reason of at most 2000 characters is required")
                action, audit_reason = "corrected", reason.strip()
                if finalized_correction:
                    match.confirmed_by = user.user_id
                    match.confirmed_at = datetime.utcnow()
                else:
                    match.submitted_by = user.user_id
            else:
                match.result_status = "pending"
                match.submitted_by = user.user_id
                action, audit_reason = "submitted", None
            db.add(models.MatchResultAudit(match_id=match.match_id, actor_id=user.user_id,
                action=action, reason=audit_reason, score_data=match.score_data))
            db.commit()
            return jsonify({"success": True, "result_status": match.result_status,
                            "match": _match_dict(db, match)}), 202
        except (StaleDataError, IntegrityError):
            db.rollback()
            return serialize_error("Result submission conflicted with a concurrent update", 409)
        finally:
            db.close()

    @app.route("/api/matches/<int:match_id>/confirm", methods=["POST"])
    def confirm_match_result(match_id):
        db = db_session()
        try:
            user = get_current_user()
            match = db.query(models.CompetitionMatch).filter_by(match_id=match_id).with_for_update().first()
            if not match:
                return serialize_error("Match not found", 404)
            tournament = db.query(models.Tournament).filter_by(tournament_id=match.tournament_id).with_for_update().first()
            if tournament.status != "in_progress":
                return serialize_error("Tournament is not in progress", 409)
            if not can_manage(user, tournament):
                return serialize_error("Only the tournament organizer can confirm a result", 403)
            if match.result_status != "pending":
                return serialize_error("There is no pending result to confirm", 409)
            if not match.is_draw and not match.winner_participant_id:
                return serialize_error("A winner is required before this result can be finalized")
            match.result_status = "confirmed"
            match.status = "completed"
            match.confirmed_by = user.user_id
            match.confirmed_at = datetime.utcnow()
            db.add(models.MatchResultAudit(match_id=match.match_id, actor_id=user.user_id,
                action="confirmed", score_data=match.score_data))
            progress_match(db, tournament, match, match.winner_participant_id)
            db.commit()
            return jsonify({"success": True, "tournament_status": tournament.status,
                            "match": _match_dict(db, match)})
        except TournamentError as exc:
            db.rollback()
            return serialize_error(str(exc), 409)
        except (StaleDataError, IntegrityError):
            db.rollback()
            return serialize_error("Result confirmation conflicted with another update", 409)
        finally:
            db.close()

    @app.route("/api/matches/<int:match_id>/reject", methods=["POST"])
    def reject_match_result(match_id):
        db = db_session()
        try:
            user = get_current_user()
            match = db.query(models.CompetitionMatch).filter_by(match_id=match_id).with_for_update().first()
            if not match:
                return serialize_error("Match not found", 404)
            tournament = db.query(models.Tournament).filter_by(tournament_id=match.tournament_id).with_for_update().first()
            if tournament.status != "in_progress":
                return serialize_error("Tournament is not in progress", 409)
            if not can_manage(user, tournament):
                return serialize_error("Only the tournament organizer can reject a result", 403)
            if match.result_status != "pending":
                return serialize_error("There is no pending result to reject", 409)
            data = request_object()
            if data is None:
                return serialize_error("Request body must be a JSON object")
            reason = data.get("reason")
            if not isinstance(reason, str) or not reason.strip() or len(reason) > 2000:
                return serialize_error("A rejection reason of at most 2000 characters is required")
            match.result_status = "rejected"
            db.add(models.MatchResultAudit(match_id=match.match_id, actor_id=user.user_id,
                action="rejected", reason=reason.strip(), score_data=match.score_data))
            db.commit()
            return jsonify({"success": True, "result_status": match.result_status})
        finally:
            db.close()

    @app.route("/api/tournaments/<int:tournament_id>/standings", methods=["GET"])
    def tournament_standings(tournament_id):
        db = db_session()
        try:
            tournament = db.query(models.Tournament).filter_by(tournament_id=tournament_id).first()
            if not tournament:
                return serialize_error("Tournament not found", 404)
            try:
                rows = standings(db, tournament)
            except TournamentError as exc:
                return serialize_error(str(exc), 409)
            return jsonify({"success": True, "standings": rows})
        finally:
            db.close()

    @app.route("/api/tournaments/<int:tournament_id>/history", methods=["GET"])
    def tournament_history(tournament_id):
        db = db_session()
        try:
            if not db.query(models.Tournament.tournament_id).filter_by(tournament_id=tournament_id).first():
                return serialize_error("Tournament not found", 404)
            entries = db.query(models.TournamentAudit).filter_by(tournament_id=tournament_id).order_by(
                models.TournamentAudit.created_at, models.TournamentAudit.audit_id).all()
            history = [{"action": entry.action, "actor_id": entry.actor_id,
                "details": entry.details or {}, "created_at": _iso(entry.created_at)} for entry in entries]
            match_entries = db.query(models.MatchResultAudit).join(models.CompetitionMatch).filter(
                models.CompetitionMatch.tournament_id == tournament_id).all()
            history.extend({"action": entry.action, "actor_id": entry.actor_id, "match_id": entry.match_id,
                "details": {"reason": entry.reason, "score": entry.score_data}, "created_at": _iso(entry.created_at)}
                for entry in match_entries)
            history.sort(key=lambda item: item["created_at"] or "")
            return jsonify({"success": True, "history": history})
        finally:
            db.close()
