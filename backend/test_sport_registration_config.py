import unittest
from types import SimpleNamespace

import sport_configuration


class SportRegistrationConfigurationTests(unittest.TestCase):
    def test_sport_schemas_keep_fields_sport_specific(self):
        football = SimpleNamespace(sport_id=1, name="Football", category="Team", subcategory=None)
        badminton = SimpleNamespace(sport_id=2, name="Badminton", category="Racquet", subcategory=None)
        football_keys = {field["key"] for field in sport_configuration.schema_for(football)["fields"]}
        badminton_keys = {field["key"] for field in sport_configuration.schema_for(badminton)["fields"]}
        self.assertIn("goals", football_keys)
        self.assertNotIn("goals", badminton_keys)
        self.assertIn("win_rate", badminton_keys)

    def test_saved_rules_control_registration_numeric_bounds(self):
        sport = SimpleNamespace(sport_id=1, name="Football", category="Team", subcategory=None)
        rules = sport_configuration.normalize_existing_rules(sport, {
            "evaluation_weights": {"matches_played": 50, "goals": 50},
            "normalization_thresholds": {"matches_max": 40, "goals_max": 12},
            "enabled": True,
            "scoring_method": "weighted",
        })
        self.assertEqual(rules["normalization_thresholds"]["goals_max"], 12)
        self.assertEqual(rules["normalization_thresholds"]["matches_max"], 40)

    def test_default_weights_total_one_hundred_for_common_sports(self):
        for name in ("Football", "Badminton", "Chess"):
            sport = SimpleNamespace(sport_id=1, name=name, category="General", subcategory=None)
            rules = sport_configuration.default_rules(sport)
            self.assertEqual(sum(rules["weights"].values()), 100)

    def test_admin_defined_fields_are_supported_without_sport_specific_code(self):
        sport = SimpleNamespace(sport_id=91, name="New Sport", category="General", subcategory=None, evaluation_rules=None)
        rules = sport_configuration.validate_rules(sport, {
            "enabled": True, "scoring_method": "weighted",
            "fields": [
                {"key": "matches", "label": "Matches played", "type": "integer", "minimum": 0, "maximum": 80, "method": "higher", "required": True},
                {"key": "level", "label": "Competition level", "type": "select", "options": ["Local", "National"], "method": "categorical", "scores": {"Local": 20, "National": 80}},
            ],
            "evaluation_weights": {"matches": 75, "level": 25},
            "normalization_thresholds": {"matches_max": 80},
        })
        configured = SimpleNamespace(sport_id=91, name="New Sport", category="General", subcategory=None, evaluation_rules=rules)
        self.assertEqual([field["key"] for field in sport_configuration.schema_for(configured)["fields"]], ["matches", "level"])
        self.assertTrue(sport_configuration.schema_for(configured)["fields"][0]["required"])

    def test_custom_fields_reject_invalid_weight_and_unsupported_method(self):
        sport = SimpleNamespace(sport_id=91, name="New Sport", category="General", subcategory=None, evaluation_rules=None)
        with self.assertRaisesRegex(ValueError, "exactly 100"):
            sport_configuration.validate_rules(sport, {"enabled": True, "scoring_method": "weighted", "fields": [{"key": "score", "label": "Score", "type": "decimal", "minimum": 0, "maximum": 10}], "evaluation_weights": {"score": 99}, "normalization_thresholds": {"score_max": 10}})
        with self.assertRaisesRegex(ValueError, "Unsupported scoring method"):
            sport_configuration.validate_rules(sport, {"enabled": True, "scoring_method": "weighted", "fields": [{"key": "score", "label": "Score", "type": "decimal", "minimum": 0, "maximum": 10, "method": "magic"}], "evaluation_weights": {"score": 100}, "normalization_thresholds": {"score_max": 10}})

    def test_example_panel_builds_persistent_registration_and_scoring_schema(self):
        panels, fields, weights, thresholds = sport_configuration.validate_panels([
            {"name": "Match Experience", "value": "Matches played"}
        ])
        self.assertEqual(panels[0]["name"], "Match Experience")
        self.assertEqual(fields[0]["key"], "matches_played")
        self.assertEqual(fields[0]["panel"], "Match Experience")
        self.assertEqual(weights, {"matches_played": 100})
        self.assertEqual(thresholds, {"matches_played_max": 100})

    def test_panel_weights_must_total_one_hundred(self):
        with self.assertRaisesRegex(ValueError, "total exactly 100"):
            sport_configuration.validate_panels([{"name": "Stats", "fields": [
                {"label": "Matches", "type": "integer", "maximum": 10, "weight": 40},
                {"label": "Wins", "type": "integer", "maximum": 10, "weight": 40},
            ]}])

    def test_panel_definitions_build_registration_and_scoring_configuration(self):
        panels, fields, weights, thresholds = sport_configuration.validate_panels([{
            "name": "Performance",
            "fields": [
                {
                    "label": "Best time", "type": "decimal", "required": True,
                    "minimum": 0, "maximum": 80, "normalization_maximum": 100,
                    "method": "lower", "unit": "seconds", "weight": 60,
                },
                {
                    "label": "Competition level", "type": "select", "required": False,
                    "options": ["Local", "National"], "scores": {"Local": 25, "National": 90},
                    "weight": 40,
                },
            ],
        }])

        self.assertEqual(panels[0]["fields"][0]["maximum"], 80)
        self.assertEqual(panels[0]["fields"][0]["normalization_maximum"], 100)
        self.assertEqual(fields[0]["maximum"], 100)
        self.assertEqual(fields[0]["direction"], "lower")
        self.assertEqual(fields[0]["unit"], "seconds")
        self.assertEqual(fields[1]["scores"], {"Local": 25, "National": 90})
        self.assertEqual(weights, {"best_time": 60, "competition_level": 40})
        self.assertEqual(thresholds, {"best_time_target": 100})

    def test_new_sport_defaults_include_explicit_builder_marker_and_example_panel(self):
        defaults = sport_configuration.new_sport_panel_defaults()
        self.assertTrue(sport_configuration.panel_builder_enabled(defaults["training_config"]))
        panel = defaults["training_config"]["panel_builder"]["panels"][0]
        self.assertEqual(panel["name"], "Match Experience")
        self.assertEqual(panel["fields"][0]["label"], "Matches played")
        self.assertEqual(defaults["evaluation_rules"]["evaluation_weights"], {"matches_played": 100})
        sport = SimpleNamespace(sport_id=92, name="Example Sport", category=None, subcategory=None, evaluation_rules=defaults["evaluation_rules"])
        self.assertEqual(sport_configuration.schema_for(sport)["fields"][0]["panel"], "Match Experience")

    def test_unmarked_existing_or_promoted_sport_keeps_legacy_configuration(self):
        self.assertFalse(sport_configuration.panel_builder_enabled(None))
        self.assertFalse(sport_configuration.panel_builder_enabled({"other_config": {"enabled": True}}))

    def test_saved_panel_round_trip_preserves_registration_and_scoring_fields(self):
        defaults = sport_configuration.new_sport_panel_defaults()
        panels, fields, weights, thresholds = sport_configuration.validate_panels(defaults["training_config"]["panel_builder"]["panels"])
        self.assertEqual(panels[0]["name"], "Match Experience")
        self.assertEqual(fields[0]["key"], "matches_played")
        self.assertEqual(weights["matches_played"], 100)
        self.assertEqual(thresholds["matches_played_max"], 100)

    def test_registration_panels_are_independent_from_evaluation_fields(self):
        rules = {
            "enabled": True,
            "scoring_method": "weighted",
            "fields": [{
                "key": "score", "label": "Score", "type": "integer",
                "minimum": 0, "maximum": 10, "method": "higher",
            }],
            "evaluation_weights": {"score": 100},
            "normalization_thresholds": {"score_max": 10},
        }
        sport = SimpleNamespace(
            sport_id=93, name="Example Sport", category=None,
            subcategory=None, evaluation_rules=rules,
        )
        panels, _ = sport_configuration.validate_registration_panels([{
            "name": "Player details",
            "fields": [
                {"label": "Preferred name", "type": "text", "required": True},
                {"label": "Division", "type": "select", "options": ["Open", "Junior"]},
                {"label": "Score", "type": "integer", "minimum": 0, "maximum": 20},
            ],
        }])
        registration_fields = sport_configuration.registration_fields_for(sport, panels)

        self.assertEqual([field["key"] for field in registration_fields], ["preferred_name", "division", "score"])
        self.assertEqual(registration_fields[0]["type"], "text")
        self.assertEqual(registration_fields[1]["options"], ["Open", "Junior"])
        self.assertEqual(registration_fields[2]["maximum"], 20)
        self.assertEqual([field["key"] for field in sport_configuration.schema_for(sport)["fields"]], ["score"])
        self.assertEqual(sport_configuration.schema_for(sport)["fields"][0]["maximum"], 10)
        self.assertEqual(rules["evaluation_weights"], {"score": 100})
        self.assertEqual(panels[0]["name"], "Player details")

    def test_custom_evaluation_and_normalization_panels_round_trip(self):
        sport = SimpleNamespace(sport_id=94, name="Volleyball", category="Team", subcategory=None, evaluation_rules=None)
        payload = {
            "enabled": True,
            "scoring_method": "weighted",
            "fields": [
                {"key": "spike_power", "label": "Spike Power", "type": "decimal", "default_threshold": 120, "unit": "km/h", "method": "higher"},
                {"key": "digs_count", "label": "Digs Count", "type": "integer", "default_threshold": 50, "unit": "digs", "method": "higher"},
            ],
            "evaluation_weights": {
                "spike_power": 60,
                "digs_count": 40,
            },
            "normalization_thresholds": {
                "spike_power_max": 120,
                "digs_count_max": 50,
                "custom_norm_speed": 150,
            },
            "normalization_panels": [
                {"name": "Custom Norm Speed", "key": "custom_norm_speed", "type": "decimal", "unit": "km/h", "value": 150}
            ]
        }
        validated = sport_configuration.validate_rules(sport, payload)
        self.assertEqual(len(validated["fields"]), 2)
        self.assertEqual(validated["evaluation_weights"]["spike_power"], 60)
        self.assertEqual(validated["normalization_thresholds"]["custom_norm_speed"], 150)
        self.assertEqual(len(validated["normalization_panels"]), 1)
        self.assertEqual(validated["normalization_panels"][0]["name"], "Custom Norm Speed")

        # Test normalize_existing_rules keeps custom fields intact without adding default sport fields
        sport.evaluation_rules = validated
        normalized = sport_configuration.normalize_existing_rules(sport, validated)
        self.assertEqual(set(normalized["evaluation_weights"].keys()), {"spike_power", "digs_count"})
        self.assertEqual(len(normalized["normalization_panels"]), 1)

    def test_custom_panels_with_select_and_text_input_types(self):
        sport = SimpleNamespace(sport_id=95, name="Badminton", category="Racquet", subcategory=None, evaluation_rules=None)
        payload = {
            "enabled": True,
            "scoring_method": "weighted",
            "fields": [
                {"key": "tier_rank", "label": "Tier Rank", "type": "select", "options": ["Tier A", "Tier B"], "scores": {"Tier A": 100, "Tier B": 50}},
                {"key": "smash_speed", "label": "Smash Speed", "type": "integer", "default_threshold": 300},
                {"key": "notes", "label": "Notes", "type": "text"},
            ],
            "evaluation_weights": {
                "tier_rank": 30,
                "smash_speed": 70,
                "notes": 0,
            },
            "normalization_thresholds": {
                "smash_speed_max": 300,
                "custom_smash_target": 350,
            },
            "normalization_panels": [
                {"name": "Custom Smash Target", "key": "custom_smash_target", "type": "integer", "unit": "km/h", "value": 350},
                {"name": "Notes Info", "key": "notes_info", "type": "text", "unit": "", "value": None}
            ]
        }
        validated = sport_configuration.validate_rules(sport, payload)
        self.assertEqual(validated["evaluation_weights"]["tier_rank"], 30)
        self.assertEqual(validated["evaluation_weights"]["smash_speed"], 70)
        self.assertEqual(validated["evaluation_weights"]["notes"], 0)
        self.assertEqual(len(validated["normalization_panels"]), 2)
        self.assertEqual(validated["normalization_thresholds"]["custom_smash_target"], 350)

    def test_independent_section_merging(self):
        sport = SimpleNamespace(sport_id=96, name="Tennis", category="Racquet", subcategory=None, evaluation_rules=None)
        # Initial saved state with both sections
        initial_rules = {
            "enabled": True,
            "scoring_method": "weighted",
            "fields": [
                {"key": "aces", "label": "Aces", "type": "integer", "default_threshold": 50},
                {"key": "first_serve_pct", "label": "First Serve %", "type": "decimal", "default_threshold": 80},
            ],
            "evaluation_weights": {"aces": 50, "first_serve_pct": 50},
            "normalization_thresholds": {"aces_max": 50, "first_serve_pct_max": 80, "rally_threshold": 25},
            "normalization_panels": [
                {"name": "Rally Threshold", "key": "rally_threshold", "type": "integer", "unit": "shots", "value": 25}
            ]
        }
        sport.evaluation_rules = sport_configuration.validate_rules(sport, initial_rules)

        # 1. Update only evaluation rules (e.g. weights change to 60/40), keeping normalization intact
        eval_update_payload = {
            "enabled": True,
            "scoring_method": "weighted",
            "fields": sport.evaluation_rules["fields"],
            "evaluation_weights": {"aces": 60, "first_serve_pct": 40},
            "normalization_thresholds": sport.evaluation_rules["normalization_thresholds"],
            "normalization_panels": sport.evaluation_rules["normalization_panels"],
        }
        updated_eval = sport_configuration.validate_rules(sport, eval_update_payload)
        self.assertEqual(updated_eval["evaluation_weights"]["aces"], 60)
        self.assertEqual(updated_eval["evaluation_weights"]["first_serve_pct"], 40)
        # Normalization section preserved exactly:
        self.assertEqual(updated_eval["normalization_thresholds"]["rally_threshold"], 25)
        self.assertEqual(len(updated_eval["normalization_panels"]), 1)

        # 2. Update only normalization thresholds (e.g. rally_threshold changes to 35), keeping evaluation intact
        sport.evaluation_rules = updated_eval
        norm_update_payload = {
            "enabled": True,
            "scoring_method": "weighted",
            "fields": sport.evaluation_rules["fields"],
            "evaluation_weights": sport.evaluation_rules["evaluation_weights"],
            "normalization_thresholds": {**sport.evaluation_rules["normalization_thresholds"], "rally_threshold": 35},
            "normalization_panels": [
                {"name": "Rally Threshold", "key": "rally_threshold", "type": "integer", "unit": "shots", "value": 35}
            ],
        }
        updated_norm = sport_configuration.validate_rules(sport, norm_update_payload)
        self.assertEqual(updated_norm["normalization_thresholds"]["rally_threshold"], 35)
        self.assertEqual(updated_norm["normalization_panels"][0]["value"], 35)
        # Evaluation weights preserved exactly:
        self.assertEqual(updated_norm["evaluation_weights"]["aces"], 60)
        self.assertEqual(updated_norm["evaluation_weights"]["first_serve_pct"], 40)

    def test_normalization_panel_integer_validation(self):
        from copy import deepcopy
        sport = SimpleNamespace(sport_id=97, name="Cricket", category="Team", subcategory=None, evaluation_rules=None)
        payload = {
            "enabled": True,
            "scoring_method": "weighted",
            "fields": [
                {"key": "matches", "label": "Matches", "type": "integer", "default_threshold": 100},
            ],
            "evaluation_weights": {"matches": 100},
            "normalization_thresholds": {"matches_max": 100, "custom_int": 50},
            "normalization_panels": [
                {"name": "Custom Integer Metric", "key": "custom_int", "type": "integer", "value": 50}
            ]
        }
        validated = sport_configuration.validate_rules(sport, payload)
        self.assertEqual(validated["normalization_thresholds"]["custom_int"], 50)
        self.assertIsInstance(validated["normalization_thresholds"]["custom_int"], int)

        # Reject decimal/float for integer panel
        invalid_decimal = deepcopy(payload)
        invalid_decimal["normalization_panels"][0]["value"] = 50.5
        invalid_decimal["normalization_thresholds"]["custom_int"] = 50.5
        with self.assertRaisesRegex(ValueError, "positive whole integer"):
            sport_configuration.validate_rules(sport, invalid_decimal)

        # Reject zero or negative integer
        invalid_zero = deepcopy(payload)
        invalid_zero["normalization_panels"][0]["value"] = 0
        invalid_zero["normalization_thresholds"]["custom_int"] = 0
        with self.assertRaisesRegex(ValueError, "positive whole integer"):
            sport_configuration.validate_rules(sport, invalid_zero)

    def test_normalization_panel_text_validation_and_unit_optional(self):
        from copy import deepcopy
        sport = SimpleNamespace(sport_id=98, name="Badminton", category="Racquet", subcategory=None, evaluation_rules=None)
        # Text normalization panel without unit (unit field removed from UI)
        payload = {
            "enabled": True,
            "scoring_method": "weighted",
            "fields": [
                {"key": "win_rate", "label": "Win Rate", "type": "decimal", "default_threshold": 80},
            ],
            "evaluation_weights": {"win_rate": 100},
            "normalization_thresholds": {"win_rate_max": 80, "comp_level": "International"},
            "normalization_panels": [
                {"name": "Highest Competition Level", "key": "comp_level", "type": "text", "value": "International"}
            ]
        }
        validated = sport_configuration.validate_rules(sport, payload)
        self.assertEqual(validated["normalization_thresholds"]["comp_level"], "International")
        self.assertEqual(validated["normalization_panels"][0]["type"], "text")
        self.assertEqual(validated["normalization_panels"][0]["value"], "International")
        # Unit was omitted from payload, check it safely defaulted to empty string without raising error
        self.assertEqual(validated["normalization_panels"][0]["unit"], "")

        # Backward compatibility: existing stored unit is preserved if provided
        payload_with_unit = deepcopy(payload)
        payload_with_unit["normalization_panels"][0]["unit"] = "tier"
        validated_with_unit = sport_configuration.validate_rules(sport, payload_with_unit)
        self.assertEqual(validated_with_unit["normalization_panels"][0]["unit"], "tier")


if __name__ == "__main__":
    unittest.main()
