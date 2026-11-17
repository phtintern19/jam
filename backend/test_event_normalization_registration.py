import unittest
import sys
import os
import uuid
import random
from datetime import datetime, timezone

# Add backend directory to sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal, engine, Base
import models
import sport_configuration
from app import app, calculate_player_score

class EventNormalizationRegistrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        Base.metadata.create_all(bind=engine)
        cls.client = app.test_client()

    def setUp(self):
        self.db = SessionLocal()

    def tearDown(self):
        self.db.close()

    def test_registration_config_includes_normalization_thresholds_and_custom_panels(self):
        """Verify GET /api/events/<event_id>/registration-config returns normalization threshold values."""
        unique_id = uuid.uuid4().hex[:8]
        sport_name = f"Squash League {unique_id}"
        # Create a test sport with custom normalization thresholds and a custom panel
        sport = models.Sport(
            name=sport_name,
            category="Racquet",
            is_active=True,
            evaluation_rules={
                "enabled": True,
                "scoring_method": "weighted",
                "fields": [
                    {"key": "matches_played", "label": "Matches Played", "type": "integer", "default_threshold": 60, "direction": "higher", "unit": "matches"},
                    {"key": "win_rate", "label": "Win Rate", "type": "decimal", "default_threshold": 80, "direction": "higher", "unit": "%"}
                ],
                "evaluation_weights": {"matches_played": 50, "win_rate": 50},
                "normalization_thresholds": {
                    "matches_played": 60,
                    "win_rate": 80,
                    "stamina_score": 95
                },
                "normalization_panels": [
                    {
                        "name": "Stamina Score",
                        "key": "stamina_score",
                        "type": "integer",
                        "unit": "pts",
                        "value": 95
                    }
                ]
            }
        )
        self.db.add(sport)
        self.db.commit()
        self.db.refresh(sport)

        now = datetime.now(timezone.utc)
        # Create an event for this sport
        event = models.Event(
            title=f"Squash Open {unique_id}",
            start_date=now,
            end_date=now,
            location="Main Arena",
            creator_id=1,
            sport_id=sport.sport_id,
            event_config={
                "evaluation_rules": sport.evaluation_rules
            },
            status="upcoming",
            is_live=True
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)

        # Query /api/events/<event_id>/registration-config
        res = self.client.get(f"/api/events/{event.event_id}/registration-config")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()

        self.assertEqual(data["event_id"], event.event_id)
        self.assertEqual(data["sport_name"], sport_name)

        fields_by_key = {f["key"]: f for f in data["fields"]}
        
        # Verify base normalization threshold fields
        self.assertIn("matches_played", fields_by_key)
        self.assertEqual(fields_by_key["matches_played"]["maximum"], 60)
        self.assertEqual(fields_by_key["matches_played"]["unit"], "matches")
        self.assertEqual(fields_by_key["matches_played"]["type"], "integer")

        self.assertIn("win_rate", fields_by_key)
        self.assertEqual(fields_by_key["win_rate"]["maximum"], 80)
        self.assertEqual(fields_by_key["win_rate"]["unit"], "%")

        # Verify custom panel added to Normalization Thresholds is also included!
        self.assertIn("stamina_score", fields_by_key)
        self.assertEqual(fields_by_key["stamina_score"]["maximum"], 95)
        self.assertEqual(fields_by_key["stamina_score"]["label"], "Stamina Score")
        self.assertEqual(fields_by_key["stamina_score"]["unit"], "pts")
        self.assertEqual(fields_by_key["stamina_score"]["type"], "integer")

    def test_existing_esports_event_registration_config(self):
        """Test with event 3 (Esports) from existing database."""
        res = self.client.get("/api/events/3/registration-config")
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertEqual(data["sport_name"], "Esports")
        field_keys = [f["key"] for f in data["fields"]]
        self.assertIn("matches_played", field_keys)
        self.assertIn("wins", field_keys)
        self.assertIn("win_rate", field_keys)
        self.assertIn("rating", field_keys)

        # Check maximums match normalization thresholds
        for field in data["fields"]:
            if field["key"] == "matches_played":
                self.assertEqual(field["maximum"], 500)
            elif field["key"] == "wins":
                self.assertEqual(field["maximum"], 300)
            elif field["key"] == "win_rate":
                self.assertEqual(field["maximum"], 100)
            elif field["key"] == "rating":
                self.assertEqual(field["maximum"], 5000)

    def test_calculate_player_score_with_normalization_thresholds(self):
        """Verify calculate_player_score accurately evaluates performance against normalization thresholds."""
        rules = {
            "enabled": True,
            "scoring_method": "weighted",
            "fields": [
                {"key": "matches_played", "label": "Matches", "type": "integer", "direction": "higher", "default_threshold": 100},
                {"key": "runs", "label": "Runs", "type": "integer", "direction": "higher", "default_threshold": 500}
            ],
            "evaluation_weights": {"matches_played": 40, "runs": 60},
            "normalization_thresholds": {"matches_max": 100, "runs_max": 500}
        }
        score = calculate_player_score({"matches_played": 50, "runs": 250}, rules)
        self.assertEqual(score, 50.0)

        score_100 = calculate_player_score({"matches_played": 100, "runs": 500}, rules)
        self.assertEqual(score_100, 100.0)

    def test_player_registration_with_normalization_fields_submits_cleanly(self):
        """Verify POST /register/player accepts normalization fields and assigns score."""
        unique_id = uuid.uuid4().hex[:8]
        sport_name = f"TestSport {unique_id}"
        sport = models.Sport(
            name=sport_name,
            category="General",
            is_active=True,
            evaluation_rules={
                "enabled": True,
                "scoring_method": "weighted",
                "fields": [
                    {"key": "matches_played", "label": "Matches Played", "type": "integer", "default_threshold": 100, "direction": "higher"},
                    {"key": "score_metric", "label": "Score Metric", "type": "integer", "default_threshold": 200, "direction": "higher"}
                ],
                "evaluation_weights": {"matches_played": 50, "score_metric": 50},
                "normalization_thresholds": {
                    "matches_played": 100,
                    "score_metric": 200
                },
                "normalization_panels": [
                    {"name": "Skill Rating", "key": "skill_rating", "type": "integer", "unit": "pts", "value": 100}
                ]
            }
        )
        self.db.add(sport)
        self.db.commit()
        self.db.refresh(sport)

        now = datetime.now(timezone.utc)
        event = models.Event(
            title=f"Test Event {unique_id}",
            start_date=now,
            end_date=now,
            location="Stadium A",
            creator_id=1,
            sport_id=sport.sport_id,
            base_prices={"Diamond": 50000, "Platinum": 30000, "Gold": 20000, "Silver": 10000},
            event_config={
                "evaluation_rules": sport.evaluation_rules,
                "categories_config": [
                    {"name": "Diamond", "base_price": 50000, "min_score": 80, "max_score": 100},
                    {"name": "Platinum", "base_price": 30000, "min_score": 60, "max_score": 80},
                    {"name": "Gold", "base_price": 20000, "min_score": 40, "max_score": 60},
                    {"name": "Silver", "base_price": 10000, "min_score": 0, "max_score": 40}
                ]
            },
            status="upcoming",
            is_live=True
        )
        self.db.add(event)
        self.db.commit()
        self.db.refresh(event)

        unique_phone = f"9{random.randint(100000000, 999999999)}"
        reg_payload = {
            "firstName": "John",
            "lastName": "Doe",
            "email": f"player_{unique_id}@example.com",
            "password": "Password123!",
            "confirmPassword": "Password123!",
            "phone": unique_phone,
            "dateOfBirth": "2000-01-01",
            "gender": "male",
            "eventId": event.event_id,
            "terms_accepted": True,
            "sportProfiles": {
                sport_name.lower(): {
                    "matches_played": 50,
                    "score_metric": 100,
                    "skill_rating": 80
                }
            }
        }
        res = self.client.post("/register/player", json=reg_payload)
        self.assertEqual(res.status_code, 201)
        data = res.get_json()
        self.assertTrue(data.get("success", False))

if __name__ == "__main__":
    unittest.main()
