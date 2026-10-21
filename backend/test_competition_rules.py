import unittest

from competition_rules import ResultValidationError, validate_result
from sports_catalog import catalog_records, upgrade_and_seed_catalog
from database import Base
from sqlalchemy import create_engine, func, inspect, text
from sqlalchemy.orm import sessionmaker
import models


class CatalogTests(unittest.TestCase):
    def test_catalog_is_broad_and_slugs_are_unique(self):
        records = catalog_records()
        slugs = [record["slug"] for record in records]
        self.assertGreaterEqual(len(set(slugs)), 100)
        self.assertEqual(len(slugs), len(set(slugs)))

    def test_repeat_seed_is_idempotent_and_preserves_existing_id(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        sessions = sessionmaker(bind=engine)
        db = sessions()
        legacy = models.Sport(name="Football")
        db.add(legacy)
        db.commit()
        legacy_id = legacy.sport_id
        legacy.is_active = False
        db.commit()
        db.close()
        upgrade_and_seed_catalog(engine, sessions)
        upgrade_and_seed_catalog(engine, sessions)
        db = sessions()
        self.assertEqual(db.query(models.Sport).filter_by(name="Football").count(), 1)
        self.assertEqual(db.query(models.Sport).filter_by(name="Football").one().sport_id, legacy_id)
        self.assertFalse(db.query(models.Sport).filter_by(name="Football").one().is_active)
        self.assertGreaterEqual(db.query(func.count(models.Sport.sport_id)).scalar(), 100)
        db.close()
        engine.dispose()

    def test_legacy_sports_schema_is_upgraded_additively_and_repeatably(self):
        engine = create_engine("sqlite:///:memory:")
        with engine.begin() as connection:
            connection.execute(text("""
                CREATE TABLE sports (
                    sport_id INTEGER PRIMARY KEY,
                    name VARCHAR(50) NOT NULL UNIQUE,
                    description TEXT,
                    icon_class VARCHAR(50),
                    is_active BOOLEAN NOT NULL DEFAULT 1,
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """))
            connection.execute(text("INSERT INTO sports (sport_id, name) VALUES (41, 'Football')"))
        Base.metadata.create_all(engine)
        sessions = sessionmaker(bind=engine)
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO event_sports (event_id, sport_id) VALUES (777, 41)"))

        upgrade_and_seed_catalog(engine, sessions)
        first_columns = {column["name"] for column in inspect(engine).get_columns("sports")}
        upgrade_and_seed_catalog(engine, sessions)

        expected = {column.name for column in models.Sport.__table__.columns}
        self.assertTrue(expected.issubset(first_columns))
        self.assertEqual(first_columns, {column["name"] for column in inspect(engine).get_columns("sports")})
        db = sessions()
        football = db.query(models.Sport).filter_by(name="Football").one()
        self.assertEqual(football.sport_id, 41)
        self.assertEqual(db.query(models.Sport).filter_by(name="Football").count(), 1)
        with engine.connect() as connection:
            self.assertEqual(connection.execute(text(
                "SELECT event_id, sport_id FROM event_sports WHERE sport_id = 41"
            )).one(), (777, 41))
        self.assertIsNotNone(football.slug)
        self.assertGreaterEqual(db.query(func.count(models.Sport.sport_id)).scalar(), 100)
        db.close()
        engine.dispose()


class ResultTemplateTests(unittest.TestCase):
    def test_representative_generic_result_envelopes(self):
        # These exercise data shapes, not official sport rules.
        for template, score, winner in [
            ("points", {"red": 2, "blue": 1}, "red"),  # football / cricket / carrom score summaries
            ("win_draw_loss", {"outcome": "draw"}, None),  # chess
            ("series", [{"winner_id": "red"}, {"winner_id": "red"}], "red"),  # esport maps
        ]:
            result = validate_result(template, {
                "participants": [{"id": "red"}, {"id": "blue"}],
                "score": score, "winner_id": winner,
            })
            self.assertEqual(result.winner_id, winner)

    def test_invalid_score_and_unknown_template_are_rejected(self):
        with self.assertRaises(ResultValidationError):
            validate_result("points", {"participants": [{"id": "a"}, {"id": "b"}], "score": {"a": -1, "b": 0}})
        with self.assertRaises(ResultValidationError):
            validate_result("custom_game_rules", {})


if __name__ == "__main__":
    unittest.main()
