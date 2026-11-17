"""Remove the retired tournament tables and tournament-only sport metadata.

Run once against the configured database after deploying the tournament removal:
    python remove_tournament_schema.py
This permanently deletes tournament records and removes the three metadata
columns that were used only by tournament setup.
"""

from sqlalchemy import inspect, text

from database import engine


TABLES = (
    "competition_match_sides",
    "match_result_audits",
    "tournament_audits",
    "competition_matches",
    "tournament_participants",
    "tournaments",
)
SPORT_COLUMNS = ("participation_format", "competition_formats", "scoring_template")


def remove_tournament_schema(db_engine=engine):
    inspector = inspect(db_engine)
    existing_tables = set(inspector.get_table_names())
    preparer = db_engine.dialect.identifier_preparer

    with db_engine.begin() as connection:
        for table in TABLES:
            if table in existing_tables:
                connection.execute(text(f"DROP TABLE {preparer.quote(table)}"))

        if "sports" in existing_tables:
            existing_columns = {column["name"] for column in inspect(db_engine).get_columns("sports")}
            for column in SPORT_COLUMNS:
                if column in existing_columns:
                    connection.execute(text(
                        f"ALTER TABLE {preparer.quote('sports')} DROP COLUMN {preparer.quote(column)}"
                    ))


if __name__ == "__main__":
    remove_tournament_schema()
    print("Tournament tables and sport metadata removed.")
