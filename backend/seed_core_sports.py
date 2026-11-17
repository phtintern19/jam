"""Safely upgrade and seed the established core sports catalog records."""
import json
import logging
from pathlib import Path

from sqlalchemy import Column, DateTime, String, Table, func, select

from database import Base, SessionLocal, engine
import models
from sports_schema import upgrade_sports_schema

DATA_PATH = Path(__file__).with_name("sports_core_data.json")
SEED_STATE = Table(
    "sports_catalog_seed_state",
    Base.metadata,
    Column("seed_name", String(50), primary_key=True),
    Column("seeded_at", DateTime, server_default=func.current_timestamp(), nullable=False),
)


def upgrade_and_seed_core_sports(db_engine=engine, session_factory=SessionLocal):
    """Create the initial catalog only when the sports table is empty.

    Once initialized, admin additions and deletions remain authoritative across
    application restarts instead of being recreated from this seed file.
    """
    Base.metadata.create_all(bind=db_engine)
    upgrade_sports_schema(db_engine)

    with DATA_PATH.open(encoding="utf-8") as seed_file:
        records = json.load(seed_file)
    if len(records) != 24:
        raise ValueError("Core sports seed data must contain exactly 24 records")

    db = session_factory()
    try:
        initialized = db.execute(select(SEED_STATE.c.seed_name).where(
            SEED_STATE.c.seed_name == "initial_core_sports"
        )).first()
        if initialized:
            return 0

        is_empty = not db.query(models.Sport.sport_id).first()
        if is_empty:
            for record in records:
                db.add(models.Sport(
                    name=record["name"],
                    description=record["description"],
                    category=record["category"],
                    players_equipment=record["players_equipment"],
                    scoring_format=record["scoring_format"],
                    exact_rules=record["exact_rules"],
                    icon_class="fas fa-trophy",
                    is_active=True,
                ))
        db.execute(SEED_STATE.insert().values(seed_name="initial_core_sports"))
        db.commit()
        return len(records) if is_empty else 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    count = upgrade_and_seed_core_sports()
    print(f"Initialized the sports catalog with {count} core sports.")
