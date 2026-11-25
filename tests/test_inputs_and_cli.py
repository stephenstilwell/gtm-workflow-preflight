import csv
import json
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree

from gtm_preflight.config import load_policy
from gtm_preflight.inputs import InputError, load_suite
from gtm_preflight.report import render_html
from gtm_preflight.runner import run_suite


ROOT = Path(__file__).resolve().parents[1]


class FixtureMixin:
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.suite_dir = Path(scratch.name)
        self.manifest = {
            "schema_version": 1, "name": "Test fixture", "as_of": "2026-11-20T12:00:00Z",
            "cases": {"routing": "Route case"},
        }
        self.tables = {
            "accounts": [{"case_id": "routing", "id": "account-a", "name": "Account Example",
                          "domain": "account.example", "crm_owner_id": "owner-a"}],
            "contacts": [],
            "events": [{"case_id": "routing", "id": "event-a", "sequence": 1, "delivery_key": "key",
                        "intent": "route", "account_id": "account-a"}],
            "actions": [{"case_id": "routing", "id": "action-a", "event_id": "event-a", "decision": "allow",
                         "account_id": "account-a", "owner_id": "owner-a"}],
            "expectations": [{"case_id": "routing", "event_id": "event-a", "decision": "allow",
                              "account_id": "account-a", "owner_id": "owner-a"}],
        }

    def write_json(self, path, value):
        file = self.suite_dir / path
        file.write_text(json.dumps(value), encoding="utf-8")
        return file

    def write_suite(self):
        self.write_json("suite.json", self.manifest)
        self.write_json("records.json", self.tables)

    def assert_invalid(self, message):
        self.write_suite()
        with self.assertRaisesRegex(InputError, message):
            load_suite(self.suite_dir)


class FixtureTests(FixtureMixin, unittest.TestCase):
    def test_duplicate_json_keys_are_rejected(self):
        self.write_json("suite.json", self.manifest)
        (self.suite_dir / "records.json").write_text('{"actions": [], "actions": []}', encoding="utf-8")
        with self.assertRaisesRegex(InputError, "duplicate JSON key"):
            load_suite(self.suite_dir)

    def test_unknown_fields_are_rejected_with_location(self):
        self.tables["events"][0]["owner"] = "bad-key"
        self.assert_invalid(r"records.json.events\[0\].*unknown field.*owner")

    def test_timestamps_need_valid_explicit_offsets(self):
        for value in ("2026-11-20T12:00:00", "2026-11-20T12:00:00+00:70", "2026-02-30T12:00:00Z"):
            with self.subTest(value=value):
                self.manifest["as_of"] = value
                self.assert_invalid("suite.json.*timestamp")

    def test_rejects_invalid_boolean_and_sequence(self):
        self.tables["accounts"][0]["customer"] = "false"
        self.assert_invalid(r"field 'customer': expected true or false")
        self.tables["accounts"][0]["customer"] = False
        self.tables["events"][0]["sequence"] = True
        self.assert_invalid("expected a positive integer")

    def test_intent_fields_and_decision_payloads_are_validated(self):
        event = self.tables["events"][0]
        event["to_stage"] = "lead"
        self.assert_invalid("fields unavailable for route")
        del event["to_stage"]
        del self.tables["expectations"][0]["owner_id"]
        self.assert_invalid("expected allow is missing payload field.*owner_id")
        self.tables["expectations"][0]["owner_id"] = "owner-a"
        self.tables["actions"][0]["decision"] = "review"
        self.assert_invalid("unexpected payload field")

    def test_rejects_dangling_action_reference_and_duplicate_sequence(self):
        event = self.tables["events"][0]
        action = self.tables["actions"][0]
        action["event_id"] = "unlisted"
        self.assert_invalid("unknown event 'unlisted'")
        action["event_id"] = event["id"]
        self.tables["events"].append(dict(event, id="event-b", delivery_key="new-delivery"))
        self.assert_invalid("duplicate sequence 1")

    def test_parent_cycles_are_rejected(self):
        self.tables["accounts"][0]["parent_id"] = "account-b"
        self.tables["accounts"].append({
            "case_id": "routing", "id": "account-b", "name": "Account B", "parent_id": "account-a",
        })
        self.assert_invalid("parent hierarchy cycle")

    def test_csv_requires_exact_header_and_row_width(self):
        self.write_json("suite.json", self.manifest)
        path = self.suite_dir / "accounts.csv"
        path.write_text("case_id,id,id,name\n", encoding="utf-8")
        with self.assertRaisesRegex(InputError, "duplicate CSV header"):
            load_suite(self.suite_dir)
        path.write_text("case_id,id,name\nrouting,account-a\n", encoding="utf-8")
        with self.assertRaisesRegex(InputError, r"accounts.csv:2: expected 3 columns, got 2"):
            load_suite(self.suite_dir)

    def test_csv_accepts_bom_quoted_fields_and_header_only_table(self):
        self.write_json("suite.json", self.manifest)
        self.tables["accounts"][0]["name"] = "Account Example, West"
        for table, rows in self.tables.items():
            columns = list(rows[0]) if rows else ["case_id", "id", "account_id"]
            with (self.suite_dir / f"{table}.csv").open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=columns)
                writer.writeheader()
                writer.writerows(rows)
        case, = load_suite(self.suite_dir).cases
        self.assertEqual(case.accounts["account-a"].name, "Account Example, West")
        self.assertEqual(case.contacts, {})

    def test_domain_identity_rejects_non_ascii_before_normalization(self):
        self.tables["accounts"][0]["domain"] = "\u212a.example"
        self.assert_invalid("expected a DNS domain")

    def test_json_and_csv_cannot_be_mixed(self):
        self.write_suite()
        (self.suite_dir / "actions.csv").touch()
        with self.assertRaisesRegex(InputError, "choose records.json or the five CSV tables"):
            load_suite(self.suite_dir)

    def test_policy_rejects_invalid_values_and_graph(self):
        for payload, problem in (
            ({"owner_authority": "last-writer"}, "expected one of"),
            ({"max_enrichment_age_days": 3651}, "between 1 and 3650"),
            ({"require_research": "false"}, "expected true or false"),
            ({"lifecycle_transitions": {"lead": ["customer"]}}, "destination stages must also be declared"),
            ({"unknown_rule": True}, "unknown field"),
        ):
            with self.subTest(payload=payload):
                policy = self.write_json("policy.json", payload)
                with self.assertRaisesRegex(InputError, problem):
                    load_policy(policy)


class ReportMarkup(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.ids = []
        self.targets = []
        self.tags = []
        self.feed(html)
        self.close()

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        fields = dict(attrs)
        if "id" in fields:
            self.ids.append(fields["id"])
        if "aria-labelledby" in fields:
            self.targets.extend(fields["aria-labelledby"].split())
        if "href" in fields:
            if not fields["href"].startswith("#"):
                raise AssertionError(f"External href {fields['href']}")
            self.targets.append(fields["href"][1:])
        if "src" in fields:
            raise AssertionError(f"External src {fields['src']}")


class CliTests(FixtureMixin, unittest.TestCase):
    def invoke(self, suite, *arguments, output="reports"):
        return subprocess.run(
            [sys.executable, "-m", "gtm_preflight", "run", str(suite),
             "--output", str(self.suite_dir / output), *map(str, arguments)],
            cwd=ROOT, capture_output=True, text=True, timeout=15, check=False,
        )

    def test_cli_examples_write_reports_with_deterministic_bytes(self):
        for label, code in (("broken", 1), ("fixed", 0)):
            with self.subTest(suite=label):
                example = ROOT / "examples" / label
                first = self.invoke(example, "--junit", output="first")
                second = self.invoke(example, "--junit", output="second")
                self.assertEqual(first.returncode, code, first.stderr)
                self.assertEqual(second.returncode, code, second.stderr)
                for name in ("report.json", "report.html", "report.junit.xml"):
                    self.assertEqual((self.suite_dir / "first" / name).read_bytes(),
                                     (self.suite_dir / "second" / name).read_bytes())
                report = json.loads((self.suite_dir / "first" / "report.json").read_text(encoding="utf-8"))
                self.assertEqual(report["schema_version"], 1)
                self.assertEqual(report["coverage"]["events"], 16)
                junit = ElementTree.parse(self.suite_dir / "first" / "report.junit.xml").getroot()
                self.assertEqual(junit.tag, "testsuite")
                self.assertEqual(int(junit.get("tests")), 16)
                self.assertEqual(int(junit.get("failures")), report["summary"]["fail"])
                self.assertEqual(len(junit.findall("./testcase/failure")), report["summary"]["fail"])
                for failure in junit.findall("./testcase/failure"):
                    self.assertTrue(failure.get("type"))
                    self.assertTrue(failure.text)

    def test_junit_marks_inconclusive_checks_skipped_and_escapes_suite_name(self):
        self.manifest["name"] = 'Routing <review> & "verification"'
        self.tables["actions"].clear()
        self.write_suite()
        report_path = self.suite_dir / "reports" / "report.junit.xml"
        result = self.invoke(self.suite_dir)
        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertFalse(report_path.exists())
        result = self.invoke(self.suite_dir, "--junit", "--allow-inconclusive")
        self.assertEqual(result.returncode, 0, result.stderr)
        root = ElementTree.parse(report_path).getroot()
        self.assertEqual(root.get("name"), self.manifest["name"])
        self.assertEqual(root.get("skipped"), "1")
        case = root.find("testcase")
        self.assertEqual((case.get("classname"), case.get("name")), ("routing", "event-a"))
        self.assertIn("No observed decision", case.find("skipped").get("message"))

    def test_cli_exit_codes_for_invalid_inconclusive_and_material_failures(self):
        self.tables["actions"].clear()
        self.write_suite()
        inconclusive = self.invoke(self.suite_dir)
        self.assertEqual(inconclusive.returncode, 3, inconclusive.stderr)
        self.assertIn("INCONCLUSIVE", inconclusive.stdout)
        self.assertEqual(self.invoke(self.suite_dir, "--allow-inconclusive").returncode, 0)
        self.assertEqual(self.invoke(ROOT / "examples" / "broken", "--allow-inconclusive").returncode, 1)
        self.tables["events"][0]["sequence"] = 0
        self.write_suite()
        invalid = self.invoke(self.suite_dir, output="invalid")
        self.assertEqual(invalid.returncode, 2)
        self.assertIn("field 'sequence'", invalid.stderr)
        self.assertFalse((self.suite_dir / "invalid" / "report.json").exists())

    def test_cli_prefers_explicit_policy_then_local_policy(self):
        self.tables["accounts"][0]["territory_owner_id"] = "owner-b"
        self.write_suite()
        self.assertEqual(self.invoke(self.suite_dir).returncode, 1)
        self.write_json("policy.json", {"owner_authority": "crm"})
        self.assertEqual(self.invoke(self.suite_dir).returncode, 0)
        override = self.write_json("override.json", {"owner_authority": "territory"})
        self.assertEqual(self.invoke(self.suite_dir, "--policy", override).returncode, 1)

    def test_report_escapes_text_and_has_valid_local_navigation_targets(self):
        self.manifest["name"] = '<script>alert("synthetic")</script>'
        self.manifest["cases"]["routing-title"] = "<b>Case without inputs</b>"
        self.write_suite()
        html = render_html(run_suite(load_suite(self.suite_dir)))
        markup = ReportMarkup(html)
        self.assertNotIn("script", markup.tags)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("&lt;b&gt;Case without inputs&lt;/b&gt;", html)
        self.assertEqual(len(set(markup.ids)), len(markup.ids))
        self.assertFalse(set(markup.targets) - set(markup.ids))
        self.assertIn("Inconclusive", html)
        self.assertIn("Undetermined", html)


if __name__ == "__main__":
    unittest.main()
