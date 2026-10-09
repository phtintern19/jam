"""Safely upgrade and seed the existing JAMRIG sports table from Tier 1 data."""
import json
import logging
from pathlib import Path

from sqlalchemy import inspect, text

from database import Base, SessionLocal, engine
import models

DATA_PATH = Path(__file__).with_name("sports_tier1_data.json")


def upgrade_and_seed_tier1_sports(db_engine=engine, session_factory=SessionLocal):
    """Add missing sport metadata columns and upsert workbook Tier 1 records.

    Existing sport IDs, event links, and sport-specific configuration are kept.
    Name matching is case-insensitive so legacy lowercase names are updated in
    place instead of creating duplicate sports.
    """
    Base.metadata.create_all(bind=db_engine)
    columns = {
        "category": "VARCHAR(150) NULL",
        "tier": "INTEGER NULL",
        "players_equipment": "TEXT NULL",
        "scoring_format": "TEXT NULL",
        "exact_rules": "TEXT NULL",
        # This existing Sport field is present in current MySQL deployments,
        # but may be absent from older local SQLite databases.
        "training_config": "JSON NULL",
    }
    existing = {column["name"] for column in inspect(db_engine).get_columns("sports")}
    with db_engine.begin() as connection:
        for name, definition in columns.items():
            if name not in existing:
                connection.execute(text(f"ALTER TABLE sports ADD COLUMN {name} {definition}"))
    indexes = {index["name"] for index in inspect(db_engine).get_indexes("sports")}
    if "ix_sports_tier" not in indexes:
        with db_engine.begin() as connection:
            connection.execute(text("CREATE INDEX ix_sports_tier ON sports (tier)"))

    with DATA_PATH.open(encoding="utf-8") as seed_file:
        records = json.load(seed_file)
    if len(records) != 24 or any(record.get("tier") != 1 for record in records):
        raise ValueError("Tier 1 seed data must contain exactly 24 Tier 1 sports")

    db = session_factory()
    try:
        existing_sports = db.query(models.Sport).all()
        sports_by_name = {sport.name.strip().casefold(): sport for sport in existing_sports}
        for record in records:
            sport = sports_by_name.get(record["name"].strip().casefold())
            if sport is None:
                sport = models.Sport(name=record["name"])
                db.add(sport)
                sports_by_name[record["name"].strip().casefold()] = sport

            sport.name = record["name"]
            sport.description = record["description"]
            sport.category = record["category"]
            sport.tier = record["tier"]
            sport.players_equipment = record["players_equipment"]
            sport.scoring_format = record["scoring_format"]
            sport.exact_rules = record["exact_rules"]
            sport.is_active = True
            if not sport.icon_class:
                sport.icon_class = "fas fa-trophy"
        db.commit()
        return len(records)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    count = upgrade_and_seed_tier1_sports()
    print(f"Upgraded sports metadata and seeded {count} Tier 1 sports.")
