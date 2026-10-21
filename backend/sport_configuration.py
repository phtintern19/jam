"""Sport-specific evaluation configuration schemas and validation."""
from copy import deepcopy
import math


LEVEL_SCORES = {
    "Local": 20,
    "District": 40,
    "State": 60,
    "National": 80,
    "Professional": 95,
    "International": 100,
}


def _field(key, label, unit, maximum, direction="higher", categorical=False):
    norm_key = None if categorical else (
        f"{key}_target" if direction == "lower" else f"{key}_max"
    )
    if key == "matches_played":
        norm_key = "matches_max"
    elif key == "years_experience":
        norm_key = "experience_max"
    return {
        "key": key,
        "label": label,
        "unit": unit,
        "direction": direction,
        "normalization_key": norm_key,
        "default_threshold": maximum,
        "categorical": categorical,
    }


def _fields_for(name, category):
    n = name.casefold()
    common = [_field("matches_played", "Matches / events completed", "count", 150)]
    experience = [_field("years_experience", "Experience", "years", 15)]

    if n == "cricket":
        fields = [
            _field("matches_played", "Matches played", "matches", 100),
            _field("runs", "Runs scored", "runs", 500),
            _field("wickets", "Wickets taken", "wickets", 90),
            _field("batting_average", "Batting average", "runs per dismissal", 60),
            _field("years_experience", "Experience", "years", 10),
            _field("highest_level", "Highest competition level", "level", None, categorical=True),
        ]
    elif "badminton" in n:
        fields = common + [
            _field("win_rate", "Win rate", "%", 100),
            _field("tournaments_won", "Tournaments won", "tournaments", 20),
            _field("ranking_points", "Ranking points", "points", 20000),
        ] + experience + [_field("highest_level", "Highest competition level", "level", None, categorical=True)]
    elif any(x in n for x in ("sprint", "middle-distance", "middle distance", "long-distance", "long distance", "marathon", "cross country", "relay")):
        time_baseline = 20 if "sprint" in n else 180 if "middle" in n else 600 if "long" in n else 10800 if "marathon" in n else 60 if "relay" in n else 1800
        fields = [
            _field("races_completed", "Races completed", "races", 100),
            _field("personal_best_seconds", "Personal best time", "seconds (lower is better)", time_baseline, "lower"),
            _field("podium_finishes", "Podium finishes", "finishes", 30),
        ] + experience
    elif n in {"swimming", "open water swimming", "canoe sprint", "rowing", "kayaking", "sailing", "surfing", "windsurfing", "kitesurfing", "stand up paddleboarding", "dragon boat racing", "triathlon"}:
        fields = [
            _field("events_completed", "Events completed", "events", 100),
            _field("personal_best_seconds", "Personal best time", "seconds (lower is better)", 60, "lower"),
            _field("medal_finishes", "Medal finishes", "finishes", 30),
        ] + experience
    elif n in {"javelin throw", "athletics", "diving", "artistic swimming", "gymnastics", "artistic gymnastics", "rhythmic gymnastics", "trampoline", "weightlifting", "powerlifting", "sport climbing", "skateboarding", "parkour", "modern pentathlon"}:
        metric = "personal_best_meters" if n == "javelin throw" else "performance_score"
        label = "Personal best distance" if n == "javelin throw" else "Competition performance score"
        unit = "meters" if n == "javelin throw" else "points"
        fields = common + [_field(metric, label, unit, 100 if n == "javelin throw" else 1000), _field("podium_finishes", "Podium finishes", "finishes", 30)] + experience
    elif n in {"football (soccer)", "football", "futsal", "rugby union", "rugby league", "hockey / field hockey", "field hockey", "ice hockey", "baseball", "softball", "handball", "netball", "water polo", "lacrosse", "american football", "australian rules football", "gaelic football", "hurling", "floorball", "bandy", "polo", "ultimate frisbee", "dodgeball", "volleyball", "beach volleyball", "3x3 basketball", "basketball"}:
        if "basketball" in n:
            performance = [_field("points", "Points scored", "points", 1000), _field("rebounds", "Rebounds", "rebounds", 500), _field("assists", "Assists", "assists", 500)]
        elif "volleyball" in n:
            performance = [_field("points", "Points scored", "points", 500), _field("blocks", "Blocks", "blocks", 150), _field("service_aces", "Service aces", "aces", 150)]
        elif any(x in n for x in ("american football", "australian rules", "gaelic football", "rugby", "hurling")):
            performance = [_field("points", "Points scored", "points", 500), _field("successful_tackles", "Successful tackles", "tackles", 200), _field("tries", "Tries / scoring runs", "scores", 60)]
        elif "football" in n or "soccer" in n or n == "futsal":
            performance = [_field("goals", "Goals scored", "goals", 100), _field("assists", "Assists", "assists", 100), _field("clean_sheets", "Clean sheets", "matches", 50)]
        elif "hockey" in n:
            performance = [_field("goals", "Goals scored", "goals", 100), _field("assists", "Assists", "assists", 100), _field("saves", "Saves", "saves", 500)]
        elif "baseball" in n or "softball" in n:
            performance = [_field("runs", "Runs scored", "runs", 150), _field("hits", "Hits", "hits", 250), _field("runs_batted_in", "Runs batted in", "runs", 150)]
        else:
            performance = [_field("points", "Points scored", "points", 500), _field("assists", "Assists", "assists", 100), _field("successful_actions", "Successful plays", "plays", 200)]
        fields = common + performance + experience
    elif n in {"kabaddi", "kabaddi (circle)", "kho kho", "kho kho (traditional)", "sepak takraw", "sepak takraw (regu)"}:
        fields = common + [
            _field("raid_points", "Raid / attack points", "points", 300),
            _field("tackle_points", "Defensive points", "points", 200),
            _field("successful_raids", "Successful raids", "raids", 100),
        ] + experience
    elif any(x in n for x in ("tennis", "table tennis", "pickleball", "squash", "racquetball", "padel")):
        fields = common + [
            _field("wins", "Matches won", "matches", 100),
            _field("win_rate", "Win rate", "%", 100),
            _field("ranking_points", "Ranking points", "points", 20000),
        ] + experience
    elif any(x in n for x in ("boxing", "wrestling", "judo", "karate", "mma", "mixed martial", "taekwondo", "muay thai", "kickboxing", "jiu-jitsu", "sumo", "sambo", "wushu", "kendo", "fencing", "gatka", "thang-ta", "kalaripayattu")):
        fields = common + [
            _field("bouts_won", "Bouts won", "bouts", 100),
            _field("win_rate", "Win rate", "%", 100),
            _field("competition_points", "Competition points", "points", 1000),
        ] + experience
    elif n in {"chess", "go", "draughts", "bridge", "poker", "shogi", "xiangqi", "scrabble", "quiz", "esports chess"}:
        fields = [
            _field("games_played", "Games played", "games", 500),
            _field("rating", "Current rating", "rating points", 3000),
            _field("tournament_points", "Tournament points", "points", 100),
        ] + experience
    elif (category == "Esports" or n == "esports") and not any(x in n for x in ("racing", "iracing", "trackmania")):
        fields = [
            _field("matches_played", "Matches played", "matches", 500),
            _field("wins", "Matches won", "matches", 300),
            _field("win_rate", "Win rate", "%", 100),
            _field("rating", "Competitive rating", "rating points", 5000),
            _field("average_score", "Average performance score", "points", 100),
        ] + experience
    elif any(x in n for x in ("formula", "motogp", "motocross", "rally", "racing", "speedway", "iracing", "trackmania", "drag racing")):
        fields = [
            _field("races_completed", "Races completed", "races", 100),
            _field("podium_finishes", "Podium finishes", "finishes", 50),
            _field("best_lap_seconds", "Best lap time", "seconds (lower is better)", 60, "lower"),
            _field("championship_points", "Championship points", "points", 1000),
        ] + experience
    elif any(x in n for x in ("archery", "shooting", "darts", "billiards", "snooker", "pool", "bowling", "golf", "disc golf", "lawn bowls", "boccia", "curling", "petanque", "croquet", "carrom")):
        fields = common + [
            _field("accuracy_percentage", "Accuracy", "%", 100),
            _field("competition_wins", "Competition wins", "wins", 50),
            _field("competition_points", "Competition points", "points", 1000),
        ] + experience
    else:
        # Explicit fallback schema for newly added or less common sports.
        fields = common + [
            _field("wins", "Competitions won", "wins", 100),
            _field("performance_score", "Performance score", "points", 1000),
        ] + experience
    return fields


def schema_for(sport):
    fields = _fields_for(sport.name, getattr(sport, "category", None))
    return {
        "sport_id": sport.sport_id,
        "name": sport.name,
        "category": sport.category or sport.subcategory or "General",
        "scoring_method": "weighted",
        "fields": fields,
    }


def default_rules(sport):
    fields = schema_for(sport)["fields"]
    weight = 100 // len(fields)
    weights = {field["key"]: weight for field in fields}
    weights[fields[0]["key"]] += 100 - sum(weights.values())
    normalization = {
        field["normalization_key"]: field["default_threshold"]
        for field in fields if field["normalization_key"]
    }
    rules = {
        "enabled": True,
        "scoring_method": "weighted",
        "weights": weights,
        "normalization": normalization,
        "metric_directions": {
            field["key"]: field["direction"] for field in fields
            if field["direction"] != "higher"
        },
    }
    if any(field["categorical"] for field in fields):
        rules["highest_level_scores"] = deepcopy(LEVEL_SCORES)

    # Keep the established Cricket scoring values exactly as configured.
    if sport.name.casefold() == "cricket":
        rules["weights"] = {
            "runs": 30, "wickets": 25, "highest_level": 10,
            "matches_played": 20, "years_experience": 15,
            "batting_average": 0,
        }
        rules["normalization"].update({
            "runs_max": 500, "matches_max": 100,
            "wickets_max": 90, "experience_max": 10,
            "batting_average_max": 60,
        })
        rules["highest_level_scores"] = deepcopy(LEVEL_SCORES)
    elif "badminton" in sport.name.casefold():
        rules["weights"] = {
            "matches_played": 15, "win_rate": 25,
            "tournaments_won": 25, "years_experience": 15,
            "ranking_points": 0, "highest_level": 20,
        }
        rules["normalization"].update({
            "matches_max": 200, "win_rate_max": 100,
            "tournaments_won_max": 20, "experience_max": 15,
            "ranking_points_max": 20000,
        })
        rules["highest_level_scores"] = deepcopy(LEVEL_SCORES)
    return rules


def normalize_existing_rules(sport, saved):
    """Return the split schema, adapting legacy weights/normalization JSON."""
    defaults = default_rules(sport)
    if not isinstance(saved, dict):
        saved = {}
    rules = deepcopy(saved)
    # Canonical keys are intentionally distinct. Older event snapshots and
    # sports rows used weights/normalization; accept those without data loss.
    rules["evaluation_weights"] = deepcopy(rules.get("evaluation_weights", rules.get("weights", {})))
    rules["normalization_thresholds"] = deepcopy(rules.get("normalization_thresholds", rules.get("normalization", {})))
    rules.setdefault("enabled", True)
    rules.setdefault("scoring_method", "weighted")
    for section, default_section in (("evaluation_weights", "weights"), ("normalization_thresholds", "normalization")):
        if not isinstance(rules.get(section), dict):
            rules[section] = {}
        for key, value in defaults[default_section].items():
            rules[section].setdefault(key, value)
    if "highest_level_scores" in defaults:
        rules.setdefault("highest_level_scores", deepcopy(defaults["highest_level_scores"]))
    rules["metric_directions"] = defaults["metric_directions"]
    for legacy in ("weights", "normalization"):
        rules.pop(legacy, None)
    return rules


def validate_rules(sport, data):
    if not isinstance(data, dict):
        raise ValueError("evaluation_rules must be an object")
    allowed_top = {"enabled", "scoring_method", "evaluation_weights", "normalization_thresholds", "weights", "normalization", "highest_level_scores", "metric_directions"}
    unknown_top = set(data) - allowed_top
    if unknown_top:
        raise ValueError(f"Unknown evaluation rule(s): {', '.join(sorted(unknown_top))}")
    if not isinstance(data.get("enabled"), bool):
        raise ValueError("enabled must be true or false")
    if data.get("scoring_method") != "weighted":
        raise ValueError("Only weighted scoring is currently supported")

    fields = schema_for(sport)["fields"]
    field_by_key = {field["key"]: field for field in fields}
    weights = data.get("evaluation_weights", data.get("weights"))
    normalization = data.get("normalization_thresholds", data.get("normalization"))
    if not isinstance(weights, dict) or not isinstance(normalization, dict):
        raise ValueError("weights and normalization must be objects")
    unknown_weights = set(weights) - set(field_by_key)
    if unknown_weights:
        raise ValueError(f"Unsupported scoring factor(s) for {sport.name}: {', '.join(sorted(unknown_weights))}")
    allowed_norms = {f["normalization_key"] for f in fields if f["normalization_key"]}
    unknown_norms = set(normalization) - allowed_norms
    if unknown_norms:
        raise ValueError(f"Unsupported normalization threshold(s): {', '.join(sorted(unknown_norms))}")

    normalized_weights = {}
    for key in field_by_key:
        value = weights.get(key, 0)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or value > 100:
            raise ValueError(f"Weight for {key} must be a number from 0 to 100")
        normalized_weights[key] = value
    total = sum(normalized_weights.values())
    if data["enabled"] and abs(total - 100) > 0.000001:
        raise ValueError(f"Enabled scoring weights must total exactly 100 (received {total:g})")
    if data["enabled"] and not any(v > 0 for v in normalized_weights.values()):
        raise ValueError("At least one scoring weight must be greater than zero")

    normalized_thresholds = {}
    for field in fields:
        norm_key = field["normalization_key"]
        if not norm_key:
            continue
        value = normalization.get(norm_key, field["default_threshold"])
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"Normalization threshold {norm_key} must be a positive number")
        if field["unit"] == "%" and value > 100:
            raise ValueError(f"Normalization threshold {norm_key} must not exceed 100 percent")
        normalized_thresholds[norm_key] = value

    result = {
        "enabled": data["enabled"],
        "scoring_method": "weighted",
        "evaluation_weights": normalized_weights,
        "normalization_thresholds": normalized_thresholds,
        "metric_directions": {
            field["key"]: field["direction"] for field in fields
            if field["direction"] != "higher"
        },
    }
    if any(field["categorical"] for field in fields):
        level_scores = data.get("highest_level_scores", LEVEL_SCORES)
        if not isinstance(level_scores, dict) or not level_scores:
            raise ValueError("highest_level_scores must be a non-empty object")
        checked = {}
        for name, score in level_scores.items():
            if not isinstance(name, str) or not name.strip() or isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 100:
                raise ValueError("Competition level scores must be between 0 and 100")
            checked[name.strip()] = score
        result["highest_level_scores"] = checked
    return result
