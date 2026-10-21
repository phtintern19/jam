"""Idempotent catalog upgrade and seed for the shared JAMRIG sports table."""
import re

from sqlalchemy import inspect, text

from database import Base, SessionLocal, engine
import models
from sports_schema import upgrade_sports_schema


# Catalog records describe classification and broad competition capabilities only.
# A record in this list does not imply that its official rules are implemented.
GROUPS = {
    "Team Sports": "Football, Futsal, Rugby Union, Rugby League, Basketball, 3x3 Basketball, Volleyball, Beach Volleyball, Handball, Field Hockey, Ice Hockey, Baseball, Softball, Cricket, Kabaddi, Kho Kho, Netball, Water Polo, Lacrosse, American Football, Australian Rules Football, Gaelic Football, Hurling, Sepak Takraw, Ultimate Frisbee, Floorball, Bandy, Dodgeball, Tug of War, Polo, Dragon Boat Racing".split(", "),
    "Racket Sports": "Tennis, Table Tennis, Badminton, Squash, Racquetball, Padel, Pickleball, Real Tennis, Soft Tennis, Beach Tennis".split(", "),
    "Combat Sports": "Boxing, Wrestling, Judo, Taekwondo, Karate, Fencing, Muay Thai, Kickboxing, Brazilian Jiu-Jitsu, Mixed Martial Arts, Sumo, Sambo, Wushu, Kendo".split(", "),
    "Water Sports": "Swimming, Artistic Swimming, Diving, Open Water Swimming, Rowing, Canoe Sprint, Canoe Slalom, Kayaking, Sailing, Surfing, Windsurfing, Kitesurfing, Stand Up Paddleboarding".split(", "),
    "Athletics": "Athletics, Marathon, Cross Country, Triathlon, Modern Pentathlon, Gymnastics, Artistic Gymnastics, Rhythmic Gymnastics, Trampoline, Weightlifting, Powerlifting, Sport Climbing, Skateboarding, Parkour".split(", "),
    "Motorsports": "Formula Racing, Formula 1, Kart Racing, MotoGP, Motocross, Rally, Endurance Racing, Drag Racing, Speedway, Sim Racing".split(", "),
    "Mind Sports": "Chess, Go, Draughts, Bridge, Poker, Shogi, Xiangqi, Scrabble, Quiz, Esports Chess".split(", "),
    "Traditional Sports": "Carrom, Kho Kho (Traditional), Mallakhamb, Kabaddi (Circle), Kalaripayattu, Sepak Takraw (Regu), Gatka, Thang-Ta".split(", "),
    "Board Sports": "Billiards, Snooker, Pool, Ten-Pin Bowling, Lawn Bowls, Boccia, Darts, Disc Golf, Golf, Mini Golf, Archery, Shooting, Curling, Petanque, Croquet".split(", "),
    "Esports": "Valorant, Counter-Strike 2, Dota 2, League of Legends, EA Sports FC, PUBG Mobile, PUBG Battlegrounds, Mobile Legends Bang Bang, Free Fire, Call of Duty, Call of Duty Mobile, Overwatch 2, Rainbow Six Siege, Rocket League, Fortnite, Apex Legends, StarCraft II, Warcraft III, Tekken 8, Street Fighter 6, Super Smash Bros Ultimate, eFootball, Honor of Kings, Arena of Valor, Clash Royale, Clash of Clans, Hearthstone, Teamfight Tactics, Wild Rift, Pokemon Unite, Age of Empires IV, iRacing, Trackmania, Splatoon 3".split(", "),
}


def slugify(name):
    return re.sub(r"[^a-z0-9]+", "-", name.casefold()).strip("-")


def _template(name, category):
    if name in {"Tennis", "Badminton", "Table Tennis", "Squash", "Volleyball", "Beach Volleyball"}:
        return "sets"
    if name in {"Chess", "Go", "Draughts", "Shogi", "Xiangqi"}:
        return "win_draw_loss"
    if name in {"Golf", "Archery", "Shooting", "Kart Racing", "Motocross", "Rally", "Endurance Racing"}:
        return "placement"
    if name in {"Swimming", "Athletics", "Marathon", "Formula 1", "Formula Racing", "Triathlon", "Cross Country"}:
        return "timed_distance"
    if category == "Esports":
        return "series"  # generic series envelope, game-specific win rules are not asserted
    if name in {"Football", "Futsal", "Rugby Union", "Rugby League", "Basketball", "Cricket", "Carrom"}:
        return "points"
    return None


def catalog_records():
    records = []
    for category, names in GROUPS.items():
        for name in names:
            classification = "esport" if category == "Esports" else "traditional"
            subcategory = ({"Esports": "esports", "Racket Sports": "racket", "Combat Sports": "combat", "Water Sports": "water", "Athletics": "athletics", "Motorsports": "motorsport", "Mind Sports": "mind", "Traditional Sports": "traditional", "Board Sports": "board"}.get(category, "team"))
            individual = category in {"Racket Sports", "Combat Sports", "Athletics", "Motorsports", "Mind Sports", "Board Sports"} or name in {"Swimming", "Diving", "Surfing", "Chess", "Golf", "Archery", "Shooting"}
            team = category in {"Team Sports", "Esports"} or name in {"Tennis", "Badminton", "Table Tennis", "Squash", "Carrom", "Swimming", "Rowing", "Sailing"}
            participation = "both" if individual and team else ("team" if team else "individual")
            scoring_template = _template(name, category)
            formats = ["single_elimination", "round_robin"]
            if scoring_template == "placement":
                formats.append("multi_entrant")
            records.append({"name": name, "slug": slugify(name), "category": category, "subcategory": subcategory,
                            "classification": classification, "participation_format": participation,
                            # These are the two currently implemented generic
                            # pairwise formats; placement entries also support
                            # the generic multi-entrant result envelope.
                            "competition_formats": formats,
                            "scoring_template": scoring_template})
    # Existing Tier 1 workbook metadata remains the richer source for those entries.
    return records


def upgrade_and_seed_catalog(db_engine=engine, session_factory=SessionLocal):
    Base.metadata.create_all(bind=db_engine)
    upgrade_sports_schema(db_engine)
    indexes = {item["name"] for item in inspect(db_engine).get_indexes("sports")}
    with db_engine.begin() as connection:
        if "ix_sports_slug" not in indexes:
            connection.execute(text("CREATE UNIQUE INDEX ix_sports_slug ON sports (slug)"))
        if "ix_sports_classification" not in indexes:
            connection.execute(text("CREATE INDEX ix_sports_classification ON sports (classification)"))

    db = session_factory()
    try:
        by_slug = {s.slug: s for s in db.query(models.Sport).filter(models.Sport.slug.isnot(None)).all()}
        by_name = {s.name.strip().casefold(): s for s in db.query(models.Sport).all()}
        records = catalog_records()
        for record in records:
            sport = by_slug.get(record["slug"]) or by_name.get(record["name"].casefold())
            if sport is None:
                sport = models.Sport(name=record["name"])
                db.add(sport)
            sport.name = record["name"]
            for key, value in record.items():
                if key != "name":
                    setattr(sport, key, value)
            if not sport.icon_class:
                sport.icon_class = "fas fa-trophy"
            by_slug[record["slug"]] = sport
            by_name[record["name"].casefold()] = sport
        db.commit()
        return len(records)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print(f"Upgraded catalog and seeded {upgrade_and_seed_catalog()} catalog entries.")
