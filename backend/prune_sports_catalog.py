"""Delete sports outside the maintained core catalog from the configured DB."""

import json
from pathlib import Path

from sqlalchemy import bindparam, inspect, text

from database import engine


DATA_PATH = Path(__file__).with_name("sports_core_data.json")


def prune_sports_catalog(db_engine=engine):
    records = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    keep_names = {record["name"].strip().casefold() for record in records}
    if len(keep_names) != 24:
        raise ValueError("The maintained sports catalog must contain 24 unique names")

    with db_engine.connect() as connection:
        rows = connection.execute(text("SELECT sport_id, name FROM sports")).all()
    delete_ids = [sport_id for sport_id, name in rows if name.strip().casefold() not in keep_names]
    if not delete_ids:
        return 0

    inspector = inspect(db_engine)
    known_tables = set(inspector.get_table_names())
    with db_engine.begin() as connection:
        if "events" in known_tables:
            connection.execute(
                text("UPDATE events SET sport_id = NULL WHERE sport_id IN :ids")
                .bindparams(bindparam("ids", expanding=True)),
                {"ids": delete_ids},
            )
        if "event_sports" in known_tables:
            connection.execute(
                text("DELETE FROM event_sports WHERE sport_id IN :ids")
                .bindparams(bindparam("ids", expanding=True)),
                {"ids": delete_ids},
            )
        if "player_skills" in known_tables:
            skill_rows = connection.execute(
                text("SELECT skill_id FROM player_skills WHERE sport_id IN :ids")
                .bindparams(bindparam("ids", expanding=True)),
                {"ids": delete_ids},
            ).all()
            skill_ids = [row[0] for row in skill_rows]
            if skill_ids and "player_skill_ratings" in known_tables:
                connection.execute(
                    text("DELETE FROM player_skill_ratings WHERE skill_id IN :ids")
                    .bindparams(bindparam("ids", expanding=True)),
                    {"ids": skill_ids},
                )
            connection.execute(
                text("DELETE FROM player_skills WHERE sport_id IN :ids")
                .bindparams(bindparam("ids", expanding=True)),
                {"ids": delete_ids},
            )

        # Fail instead of leaving dangling foreign keys from any unhandled table.
        for table in known_tables:
            for foreign_key in inspector.get_foreign_keys(table):
                if foreign_key.get("referred_table") != "sports":
                    continue
                column = foreign_key["constrained_columns"][0]
                if (table, column) in {
                    ("events", "sport_id"),
                    ("event_sports", "sport_id"),
                    ("player_skills", "sport_id"),
                }:
                    continue
                remaining = connection.execute(
                    text(f"SELECT COUNT(*) FROM {table} WHERE {column} IN :ids")
                    .bindparams(bindparam("ids", expanding=True)),
                    {"ids": delete_ids},
                ).scalar_one()
                if remaining:
                    raise RuntimeError(
                        f"Cannot remove sports: {remaining} references remain in {table}.{column}"
                    )

        result = connection.execute(
            text("DELETE FROM sports WHERE sport_id IN :ids")
            .bindparams(bindparam("ids", expanding=True)),
            {"ids": delete_ids},
        )
        return result.rowcount


if __name__ == "__main__":
    removed = prune_sports_catalog()
    print(f"Removed {removed} sports outside the maintained catalog.")
