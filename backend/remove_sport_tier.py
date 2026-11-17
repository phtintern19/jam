"""Drop the retired sports.tier column and its index from the configured DB.

Run once after deploying the catalog change:
    python remove_sport_tier.py
"""

from sqlalchemy import inspect, text

from database import engine


def remove_sport_tier(db_engine=engine):
    inspector = inspect(db_engine)
    if not inspector.has_table("sports"):
        return

    indexes = {index["name"] for index in inspector.get_indexes("sports")}
    has_tier = any(column["name"] == "tier" for column in inspector.get_columns("sports"))
    preparer = db_engine.dialect.identifier_preparer

    with db_engine.begin() as connection:
        if "ix_sports_tier" in indexes:
            index_name = preparer.quote("ix_sports_tier")
            if db_engine.dialect.name == "mysql":
                connection.execute(text(f"DROP INDEX {index_name} ON {preparer.quote('sports')}"))
            else:
                connection.execute(text(f"DROP INDEX {index_name}"))
        if has_tier:
            connection.execute(text(
                f"ALTER TABLE {preparer.quote('sports')} DROP COLUMN {preparer.quote('tier')}"
            ))


if __name__ == "__main__":
    remove_sport_tier()
    print("Removed the sports.tier column and index.")
