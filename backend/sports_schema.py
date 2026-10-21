"""Additive schema upgrades for the shared sports catalog table."""

from sqlalchemy import inspect, text

import models


# ALTER TABLE ADD COLUMN is supported by both SQLite and MySQL for these
# nullable metadata fields. The small set of non-null columns has a safe
# server default so populated legacy tables can be upgraded without rewriting
# or deleting their rows.
_SERVER_DEFAULTS = {
    "is_active": "1",
    "created_at": "CURRENT_TIMESTAMP",
    "updated_at": "CURRENT_TIMESTAMP",
}


def upgrade_sports_schema(db_engine):
    """Add every missing mapped Sport column, preserving all existing data."""
    inspector = inspect(db_engine)
    if not inspector.has_table(models.Sport.__tablename__):
        models.Sport.__table__.create(bind=db_engine, checkfirst=True)
        return []

    existing = {column["name"] for column in inspector.get_columns("sports")}
    added = []
    preparer = db_engine.dialect.identifier_preparer
    with db_engine.begin() as connection:
        for column in models.Sport.__table__.columns:
            if column.name in existing:
                continue
            name = preparer.quote(column.name)
            type_sql = column.type.compile(dialect=db_engine.dialect)
            default = _SERVER_DEFAULTS.get(column.name)
            default_sql = f" DEFAULT {default}" if default is not None else ""
            connection.execute(text(
                f"ALTER TABLE sports ADD COLUMN {name} {type_sql}{default_sql}"
            ))
            added.append(column.name)
    return added
