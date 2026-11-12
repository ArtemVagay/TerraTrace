from pathlib import Path
import unittest

from services.log_parser import MAX_BYTES, LogInputError, analyze_log, decode_log, mask_private_data

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class ParserTests(unittest.TestCase):
    def test_demo_counts_and_categories(self):
        report = analyze_log((EXAMPLES / "boss_test.log").read_text(encoding="utf-8"))
        self.assertEqual(report.summary.errors, 12)
        self.assertEqual(report.summary.warnings, 1)
        self.assertEqual(report.summary.problem_groups, 4)
        self.assertEqual(report.groups[0].count, 8)
        self.assertEqual(report.tml_version, "2026.10.3.0")
        self.assertEqual(report.mods, ["AstralBosses", "CrystalFX"])
        self.assertEqual({group.finding.rule_id for group in report.groups}, {"null_reference", "missing_resource", "api_mismatch", "shader_parameter"})

    def test_multiline_stack_and_repeated_line_numbers(self):
        text = "\n".join([
            "[10:00:00.000] [Main Thread/ERROR] [MyMod]: AI failed",
            "System.NullReferenceException: object was null",
            "   at MyMod.Boss.AI() in Boss.cs:line 10",
            "[10:00:01.000] [Main Thread/ERROR] [MyMod]: AI failed",
            "System.NullReferenceException: object was null",
            "   at MyMod.Boss.AI() in Boss.cs:line 11",
        ])
        report = analyze_log(text)
        self.assertEqual(len(report.groups), 1)
        group = report.groups[0]
        self.assertEqual((group.count, group.first_line, group.last_line), (2, 1, 6))
        self.assertIn("MyMod.Boss.AI", group.excerpt)
        self.assertEqual(group.exception_type, "System.NullReferenceException")

    def test_different_resources_stay_separate(self):
        report = analyze_log("ERROR: Texture not found: MyMod/Assets/First\nERROR: Texture not found: MyMod/Assets/Second")
        self.assertEqual(len(report.groups), 2)
        self.assertTrue(all(group.finding.rule_id == "missing_resource" for group in report.groups))

    def test_unknown_error_stays_unknown(self):
        report = analyze_log((EXAMPLES / "unknown_error.log").read_text())
        self.assertFalse(report.groups[0].finding.known_pattern)
        self.assertEqual(report.groups[0].finding.rule_id, "unknown")

    def test_clean_log_does_not_claim_correct_game_behavior(self):
        report = analyze_log((EXAMPLES / "clean.log").read_text())
        self.assertEqual(report.summary.errors, 0)
        self.assertEqual(report.groups, [])
        self.assertTrue(any("не доказывает" in message for message in report.notices))

    def test_masking_preserves_versions_and_lines(self):
        source = "Terraria v1.4.4.9\nVersion=1.0.0.0\n192.0.2.10\nC:\\Users\\Artem\\Projects\\Boss.cs\n/Users/Artem/Projects\nmail=user@example.com\npassword=secret"
        masked, count = mask_private_data(source)
        self.assertIn("Terraria v1.4.4.9", masked)
        self.assertIn("Version=1.0.0.0", masked)
        self.assertNotIn("Artem", masked)
        self.assertNotIn("192.0.2.10", masked)
        self.assertNotIn("user@example.com", masked)
        self.assertNotIn("secret", masked)
        self.assertEqual(source.count("\n"), masked.count("\n"))
        self.assertEqual(count, 5)

    def test_report_contains_masked_excerpt(self):
        report = analyze_log("ERROR: Failure at C:\\Users\\Artem\\Project\\Boss.cs; host 192.0.2.10")
        self.assertNotIn("Artem", report.model_dump_json())
        self.assertNotIn("192.0.2.10", report.model_dump_json())

    def test_supported_encodings(self):
        text = "ERROR: Не найдена текстура"
        for encoding in ["utf-8-sig", "cp1251", "utf-16"]:
            with self.subTest(encoding=encoding):
                self.assertEqual(decode_log(text.encode(encoding)), text)

    def test_empty_and_binary_files_rejected(self):
        for data in [b"", b"\x00\x01\x02"]:
            with self.assertRaises(LogInputError):
                decode_log(data)

    def test_input_limits(self):
        for text in ["   ", "x" * (MAX_BYTES + 1), "line\n" * 50_001, "x" * 32_001, "ERROR: bad\x01"]:
            with self.subTest(length=len(text)):
                with self.assertRaises(LogInputError):
                    analyze_log(text)

    def test_group_limit_is_reported(self):
        text = "\n".join(f"[10:00:00.000] [Main Thread/WARN] [MyMod]: Warning {i}" for i in range(205))
        report = analyze_log(text)
        self.assertEqual(len(report.groups), 200)
        self.assertEqual(report.omitted_groups, 5)
        self.assertEqual(report.summary.warnings, 205)
        self.assertEqual(report.summary.problem_groups, 205)

    def test_system_sources_are_not_mods(self):
        report = analyze_log("[10:00:00.000] [Main Thread/ERROR] [Terraria]: Unknown error")
        self.assertEqual(report.groups[0].related_mods, [])


if __name__ == "__main__":
    unittest.main()
