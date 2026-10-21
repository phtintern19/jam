"""Idempotently create the additive tournament and match tables."""
from database import engine
import models  # noqa: F401 - register every model with Base.metadata


TABLES_IN_DEPENDENCY_ORDER = (
    "tournaments",
    "tournament_participants",
    "competition_matches",
    "competition_match_sides",
    "match_result_audits",
    "tournament_audits",
)


def upgrade(db_engine=engine):
    for table_name in TABLES_IN_DEPENDENCY_ORDER:
        models.Base.metadata.tables[table_name].create(bind=db_engine, checkfirst=True)


if __name__ == "__main__":
    upgrade()
    print("Tournament and match tables are present.")
