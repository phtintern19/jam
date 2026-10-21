import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace

from flask import Flask
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models
from database import Base
from tournament_api import register_tournament_routes
from tournament_engine import knockout_bracket, round_robin_fixtures
from add_tournament_tables import upgrade as upgrade_tournament_tables


class FormatTests(unittest.TestCase):
    def test_knockout_odd_entrants_have_advancing_byes(self):
        bracket = knockout_bracket([1, 2, 3, 4, 5])
        first = bracket[0]
        self.assertEqual(sum(item["is_bye"] for item in first), 3)
        self.assertFalse(any(item["empty"] for item in first))
        self.assertEqual(len(bracket[-1]), 1)

    def test_round_robin_each_pair_once_and_odd_bye(self):
        fixtures = round_robin_fixtures([1, 2, 3, 4, 5])
        pairs = [frozenset(pair) for round_fixtures in fixtures for pair in round_fixtures if None not in pair]
        self.assertEqual(len(pairs), 10)
        self.assertEqual(len(set(pairs)), 10)
        self.assertTrue(all(sum(None in pair for pair in round_fixtures) == 1 for round_fixtures in fixtures))


class TournamentApiTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(self.engine)
        upgrade_tournament_tables(self.engine)
        upgrade_tournament_tables(self.engine)
        self.sessions = sessionmaker(bind=self.engine, expire_on_commit=False)
        db = self.sessions()
        self.sport = models.Sport(name="Test Football", slug="test-football", is_active=True,
            tier=1,
            participation_format="individual", competition_formats=["single_elimination", "round_robin"],
            scoring_template="points")
        db.add(self.sport)
        for player_id in range(1, 4):
            db.add(models.Player(user_id=100 + player_id, email=f"p{player_id}@example.test",
                password_hash="not-used", first_name=f"Player{player_id}", last_name="Test", is_active=True))
        db.commit()
        self.sport_id = self.sport.sport_id
        self.actor = SimpleNamespace(user_id=1, user_type="admin", parent_user_id=None, player=None)
        app = Flask(__name__)
        app.testing = True
        register_tournament_routes(app, lambda: self.actor, self.sessions)
        self.client = app.test_client()

    def tearDown(self):
        self.engine.dispose()

    def _create_tournament(self):
        response = self.client.post("/api/tournaments", json={"name": "Playoff", "sport_id": self.sport_id,
            "format": "single_elimination", "participant_type": "individual", "max_participants": 8})
        self.assertEqual(response.status_code, 201, response.json)
        return response.json["tournament"]["tournament_id"]

    def test_tournament_sport_list_contains_only_active_tier_one_sports(self):
        db = self.sessions()
        db.add_all([
            models.Sport(name="Other Tier", slug="other-tier", tier=2, is_active=True,
                participation_format="individual", competition_formats=["single_elimination"], scoring_template="points"),
            models.Sport(name="Inactive Tier One", slug="inactive-tier-one", tier=1, is_active=False,
                participation_format="individual", competition_formats=["single_elimination"], scoring_template="points"),
        ])
        db.commit()
        db.close()

        response = self.client.get("/api/tournaments/sports")
        self.assertEqual(response.status_code, 200)
        names = [sport["name"] for sport in response.json["sports"]]
        self.assertIn("Test Football", names)
        self.assertNotIn("Other Tier", names)
        self.assertNotIn("Inactive Tier One", names)
        self.assertTrue(all(sport["tier"] == 1 for sport in response.json["sports"]))

    def test_tournament_creation_rejects_non_tier_one_sport(self):
        db = self.sessions()
        sport = models.Sport(name="Tier Two Sport", slug="tier-two-sport", tier=2, is_active=True,
            participation_format="individual", competition_formats=["single_elimination"], scoring_template="points")
        db.add(sport)
        db.commit()
        sport_id = sport.sport_id
        db.close()

        response = self.client.post("/api/tournaments", json={"name": "Not Tier One", "sport_id": sport_id,
            "format": "single_elimination", "participant_type": "individual"})
        self.assertEqual(response.status_code, 404)
        self.assertIn("Tier 1", response.json["error"])

    def test_tournament_creation_accepts_active_tier_one_sport(self):
        response = self.client.post("/api/tournaments", json={"name": "Tier One Cup", "sport_id": self.sport_id,
            "format": "single_elimination", "participant_type": "individual"})
        self.assertEqual(response.status_code, 201, response.json)

    def test_tournament_creation_rejects_inactive_tier_one_sport(self):
        db = self.sessions()
        sport = models.Sport(name="Inactive Tier One", slug="inactive-tier-one", tier=1, is_active=False,
            participation_format="individual", competition_formats=["single_elimination"], scoring_template="points")
        db.add(sport)
        db.commit()
        sport_id = sport.sport_id
        db.close()

        response = self.client.post("/api/tournaments", json={"name": "Inactive Cup", "sport_id": sport_id,
            "format": "single_elimination", "participant_type": "individual"})
        self.assertEqual(response.status_code, 404)

    def test_lifecycle_byes_submission_confirmation_progression_and_duplicates(self):
        tournament_id = self._create_tournament()
        self.client.post(f"/api/tournaments/{tournament_id}/open")
        for player_id in (1, 2, 3):
            response = self.client.post(f"/api/tournaments/{tournament_id}/participants", json={"participant_id": player_id})
            self.assertEqual(response.status_code, 201, response.json)
        duplicate = self.client.post(f"/api/tournaments/{tournament_id}/participants", json={"participant_id": 1})
        self.assertEqual(duplicate.status_code, 409)
        started = self.client.post(f"/api/tournaments/{tournament_id}/start")
        self.assertEqual(started.status_code, 201, started.json)
        matches = started.json["matches"]
        self.assertEqual(len(matches), 3)
        first = next(item for item in matches if item["round"] == 1 and not item["is_bye"])
        pids = [str(side["participant"]["participant_id"]) for side in first["participants"]]

        self.actor = SimpleNamespace(user_id=999, user_type="player", parent_user_id=None, player=None)
        forbidden = self.client.post(f"/api/matches/{first['match_id']}/results", json={"score": {pids[0]: 1, pids[1]: 0}})
        self.assertEqual(forbidden.status_code, 403)

        player_id = first["participants"][0]["participant"]["id"]
        self.actor = SimpleNamespace(user_id=100 + player_id, user_type="player", parent_user_id=None,
            player=self._player(player_id))
        submitted = self.client.post(f"/api/matches/{first['match_id']}/results", json={"score": {pids[0]: 2, pids[1]: 1}})
        self.assertEqual(submitted.status_code, 202, submitted.json)
        self.assertEqual(self.client.post(f"/api/matches/{first['match_id']}/results", json={"score": {pids[0]: 2, pids[1]: 1}}).status_code, 409)

        self.actor = SimpleNamespace(user_id=1, user_type="admin", parent_user_id=None, player=None)
        finalized = self.client.post(f"/api/matches/{first['match_id']}/confirm", json={})
        self.assertEqual(finalized.status_code, 200, finalized.json)
        corrected = self.client.put(f"/api/matches/{first['match_id']}/results", json={
            "score": {pids[0]: 1, pids[1]: 2}, "reason": "Official score sheet correction"})
        self.assertEqual(corrected.status_code, 202, corrected.json)
        final = next(item for item in matches if item["round"] == 2)
        final = self.client.get(f"/api/matches/{final['match_id']}").json["match"]
        self.assertTrue(all(side["participant"] for side in final["participants"]))
        self.assertEqual(final["participants"][1]["participant"]["participant_id"], int(pids[1]))
        final_pids = [str(side["participant"]["participant_id"]) for side in final["participants"]]
        self.assertEqual(self.client.post(f"/api/matches/{final['match_id']}/results",
            json={"score": {final_pids[0]: 3, final_pids[1]: 1}}).status_code, 202)
        complete = self.client.post(f"/api/matches/{final['match_id']}/confirm", json={})
        self.assertEqual(complete.status_code, 200, complete.json)
        self.assertEqual(complete.json["tournament_status"], "completed")
        self.assertEqual(self.client.post(f"/api/matches/{final['match_id']}/confirm", json={}).status_code, 409)

    def test_invalid_format_and_tied_knockout_result_rejected(self):
        bad = self.client.post("/api/tournaments", json={"name": "Bad", "sport_id": self.sport_id,
            "format": "groups", "participant_type": "individual"})
        self.assertEqual(bad.status_code, 400)
        tournament_id = self._create_tournament()
        self.client.post(f"/api/tournaments/{tournament_id}/open")
        self.client.post(f"/api/tournaments/{tournament_id}/participants", json={"participant_id": 1})
        self.client.post(f"/api/tournaments/{tournament_id}/participants", json={"participant_id": 2})
        matches = self.client.post(f"/api/tournaments/{tournament_id}/start").json["matches"]
        match = matches[0]
        pids = [str(side["participant"]["participant_id"]) for side in match["participants"]]
        response = self.client.post(f"/api/matches/{match['match_id']}/results", json={"score": {pids[0]: 1, pids[1]: 1}})
        self.assertEqual(response.status_code, 400)

    def test_capacity_scoring_template_and_state_are_validated(self):
        invalid_capacity = self.client.post("/api/tournaments", json={"name": "Bad cap", "sport_id": self.sport_id,
            "format": "single_elimination", "participant_type": "individual", "min_participants": 10, "max_participants": 2})
        self.assertEqual(invalid_capacity.status_code, 400)
        invalid_template = self.client.post("/api/tournaments", json={"name": "Bad score", "sport_id": self.sport_id,
            "format": "single_elimination", "participant_type": "individual", "scoring_template": "made_up"})
        self.assertEqual(invalid_template.status_code, 400)
        tournament_id = self._create_tournament()
        self.assertEqual(self.client.post(f"/api/tournaments/{tournament_id}/ready").status_code, 409)

    def test_round_robin_fixtures_byes_and_confirmed_standings(self):
        response = self.client.post("/api/tournaments", json={"name": "League", "sport_id": self.sport_id,
            "format": "round_robin", "participant_type": "individual", "max_participants": 8})
        tournament_id = response.json["tournament"]["tournament_id"]
        self.client.post(f"/api/tournaments/{tournament_id}/open")
        for player_id in (1, 2, 3):
            self.client.post(f"/api/tournaments/{tournament_id}/participants", json={"participant_id": player_id})
        started = self.client.post(f"/api/tournaments/{tournament_id}/start")
        self.assertEqual(started.status_code, 201, started.json)
        matches = started.json["matches"]
        self.assertEqual(len(matches), 6)
        self.assertEqual(sum(match["is_bye"] for match in matches), 3)
        self.assertEqual(self.client.post(f"/api/tournaments/{tournament_id}/start").status_code, 409)
        for match in matches:
            if match["is_bye"]:
                continue
            self.assertEqual(self.client.post(f"/api/matches/{match['match_id']}/transition",
                json={"status": "postponed"}).status_code, 200)
            self.assertEqual(self.client.post(f"/api/matches/{match['match_id']}/transition",
                json={"status": "scheduled"}).status_code, 200)
            self.assertEqual(self.client.post(f"/api/matches/{match['match_id']}/transition",
                json={"status": "completed"}).status_code, 409)
            ids = [str(side["participant"]["participant_id"]) for side in match["participants"]]
            submitted = self.client.post(f"/api/matches/{match['match_id']}/results", json={"score": {ids[0]: 2, ids[1]: 0}})
            self.assertEqual(submitted.status_code, 202, submitted.json)
            self.assertEqual(self.client.post(f"/api/matches/{match['match_id']}/confirm", json={}).status_code, 200)
        standings_response = self.client.get(f"/api/tournaments/{tournament_id}/standings")
        self.assertEqual(standings_response.status_code, 200, standings_response.json)
        rows = standings_response.json["standings"]
        self.assertEqual(sum(row["played"] for row in rows), 6)
        self.assertEqual(sum(row["points"] for row in rows), 9)
        self.assertEqual(self.client.get(f"/api/tournaments/{tournament_id}/history").status_code, 200)

    def test_existing_event_sport_relationship_is_preserved(self):
        db = self.sessions()
        now = datetime.utcnow()
        event = models.Event(title="Existing auction", start_date=now, end_date=now + timedelta(days=1),
            location="Gym", creator_id=1, sport=self.sport)
        event.sports.append(self.sport)
        db.add(event)
        db.commit()
        event_id = event.event_id
        db.expire_all()
        saved = db.query(models.Event).filter_by(event_id=event_id).one()
        self.assertEqual(saved.sport.sport_id, self.sport_id)
        self.assertEqual([sport.sport_id for sport in saved.sports], [self.sport_id])
        db.close()

    def test_multi_entrant_placement_match_is_not_reduced_to_two_sides(self):
        db = self.sessions()
        sport = models.Sport(name="Test Race", slug="test-race", tier=1, is_active=True,
            participation_format="individual", competition_formats=["multi_entrant"], scoring_template="placement")
        db.add(sport)
        db.commit()
        sport_id = sport.sport_id
        db.close()
        response = self.client.post("/api/tournaments", json={"name": "Race Final", "sport_id": sport_id,
            "format": "multi_entrant", "participant_type": "individual"})
        self.assertEqual(response.status_code, 201, response.json)
        tournament_id = response.json["tournament"]["tournament_id"]
        self.client.post(f"/api/tournaments/{tournament_id}/open")
        for player_id in (1, 2, 3):
            self.client.post(f"/api/tournaments/{tournament_id}/participants", json={"participant_id": player_id})
        match = self.client.post(f"/api/tournaments/{tournament_id}/start").json["matches"][0]
        self.assertEqual(len(match["participants"]), 3)
        scores = {str(side["participant"]["participant_id"]): index for index, side in enumerate(match["participants"], 1)}
        submitted = self.client.post(f"/api/matches/{match['match_id']}/results", json={"score": scores})
        self.assertEqual(submitted.status_code, 202, submitted.json)
        confirmed = self.client.post(f"/api/matches/{match['match_id']}/confirm", json={})
        self.assertEqual(confirmed.json["tournament_status"], "completed")

    def _player(self, player_id):
        db = self.sessions()
        try:
            return db.query(models.Player).filter_by(player_id=player_id).one()
        finally:
            db.expunge_all()
            db.close()


if __name__ == "__main__":
    unittest.main()
