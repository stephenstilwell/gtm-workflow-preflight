import unittest
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

from gtm_preflight.config import PolicyConfig
from gtm_preflight.inputs import load_suite
from gtm_preflight.model import Decision, Observation
from gtm_preflight.runner import run_suite


EXAMPLES = Path(__file__).resolve().parents[1] / "examples"


class PolicyRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.broken = load_suite(EXAMPLES / "broken")
        cls.fixed = load_suite(EXAMPLES / "fixed")
        cls.by_case = {case.id: case for case in cls.fixed.cases}

    def findings(self, case, config=None):
        suite = replace(self.fixed, cases=(case,))
        return run_suite(suite, config)["cases"][0]["findings"]

    def set_decision(self, case, event, decision, *, actual=None):
        return replace(
            case,
            expectations={**case.expectations, event.id: decision},
            actions={**case.actions, event.id: (Observation("test-action", actual or decision),)},
        )

    def outreach_case(self):
        case = self.by_case["existing-customer"]
        account = replace(case.accounts["harbor"], customer=False)
        return replace(case, accounts={account.id: account}), case.events[0]

    def test_examples_share_inputs_and_expected_decisions(self):
        self.assertEqual(self.broken.as_of, self.fixed.as_of)
        self.assertEqual(len(self.fixed.cases), 12)
        for broken, fixed in zip(self.broken.cases, self.fixed.cases, strict=True):
            with self.subTest(case=fixed.id):
                self.assertEqual(replace(broken, actions={}), replace(fixed, actions={}))

    def test_broken_and_fixed_cover_every_scenario(self):
        broken = run_suite(self.broken)
        fixed = run_suite(self.fixed)
        self.assertEqual(broken["summary"], {"pass": 3, "fail": 13, "inconclusive": 0})
        self.assertEqual(fixed["summary"], {"pass": 16, "fail": 0, "inconclusive": 0})
        self.assertEqual(broken["coverage"], fixed["coverage"])
        expected_rules = {
            "webhook-replay": {"delivery_idempotency"},
            "duplicate-contacts": {"contact_identity"},
            "similar-names": {"account_identity"},
            "account-hierarchy": {"account_hierarchy"},
            "account-ownership": {"missing_owner", "conflicting_owner"},
            "existing-customer": {"customer_suppression"},
            "unsubscribed": {"contact_consent"},
            "stale-enrichment": {"enrichment_freshness"},
            "missing-research": {"research_evidence"},
            "event-order": {"event_order"},
            "lifecycle": {"lifecycle_transition"},
            "repeated-task": {"task_idempotency"},
        }
        for case in broken["cases"]:
            with self.subTest(case=case["id"]):
                failures = {item["rule_id"] for item in case["findings"] if item["status"] == "fail"}
                self.assertEqual(failures, expected_rules[case["id"]])

    def test_missing_observation_expectation_and_empty_case_are_inconclusive(self):
        case = self.by_case["similar-names"]
        for input_case, rule in (
            (replace(case, actions={}), "decision_contract"),
            (replace(case, expectations={}), "fixture_expectation"),
            (replace(case, events=(), actions={}, expectations={}), "case_coverage"),
        ):
            with self.subTest(rule=rule):
                finding, = self.findings(input_case)
                self.assertEqual((finding["status"], finding["rule_id"]), ("inconclusive", rule))

    def test_incomplete_allow_payload_is_inconclusive_but_wrong_payload_fails(self):
        case = self.by_case["similar-names"]
        event, = case.events
        expected = case.expectations[event.id]
        for actual, status in (
            (Decision("allow", "harbor"), "inconclusive"),
            (Decision("allow", "harbor", "wrong-owner"), "fail"),
        ):
            with self.subTest(status=status):
                changed = self.set_decision(case, event, expected, actual=actual)
                self.assertEqual(self.findings(changed)[0]["status"], status)

    def test_multiple_observations_fail_even_when_identical(self):
        case = self.by_case["similar-names"]
        event, = case.events
        original, = case.actions[event.id]
        changed = replace(case, actions={event.id: (original, replace(original, id="duplicate"))})
        finding, = self.findings(changed)
        self.assertEqual((finding["status"], finding["rule_id"]), ("fail", "decision_contract"))
        self.assertIn("action/duplicate", finding["affected_records"])

    def test_missing_expectation_does_not_mask_known_suppression_violation(self):
        case = next(case for case in self.broken.cases if case.id == "unsubscribed")
        finding, = self.findings(replace(case, expectations={}))
        self.assertEqual((finding["status"], finding["severity"]), ("fail", "critical"))

    def test_duplicate_decisions_retain_severity_of_known_unsafe_outreach(self):
        case = self.by_case["existing-customer"]
        event, = case.events
        safe, = case.actions[event.id]
        unsafe = Observation("unsafe-outreach", Decision("allow", "harbor"))
        changed = replace(case, actions={event.id: (safe, unsafe)})
        finding, = self.findings(changed)
        self.assertEqual((finding["status"], finding["rule_id"], finding["severity"]),
                         ("fail", "customer_suppression", "critical"))

    def test_fixture_expectation_can_conflict_with_policy(self):
        case = self.by_case["existing-customer"]
        event, = case.events
        contradicted = replace(case, expectations={event.id: Decision("allow", "harbor")})
        finding, = self.findings(contradicted)
        self.assertEqual(finding["status"], "fail")
        self.assertEqual(finding["rule_id"], "fixture_expectation")
        self.assertEqual(finding["policy_rule_id"], "customer_suppression")

    def test_complete_outreach_at_exact_freshness_limit_passes(self):
        case, event = self.outreach_case()
        event = replace(event, enriched_at=self.fixed.as_of - timedelta(days=30))
        changed = self.set_decision(replace(case, events=(event,)), event, Decision("allow", "harbor"))
        self.assertEqual(self.findings(changed)[0]["status"], "pass")

    def test_unknown_outreach_inputs_never_pass_despite_matching_expected_output(self):
        case, event = self.outreach_case()
        contact = case.contacts["contact-a"]
        account = case.accounts["harbor"]
        for candidate, rule in (
            (replace(case, accounts={account.id: replace(account, customer=None)}), "customer_suppression"),
            (replace(case, contacts={contact.id: replace(contact, unsubscribed=None)}), "contact_consent"),
            (replace(case, events=(replace(event, enriched_at=None),)), "enrichment_freshness"),
            (replace(case, events=(replace(event, enriched_at=self.fixed.as_of + timedelta(seconds=1)),)),
             "enrichment_freshness"),
            (replace(case, events=(replace(event, research_url=None),)), "research_evidence"),
            (replace(case, events=(replace(event, account_id=None),)), "account_identity"),
        ):
            with self.subTest(rule=rule):
                candidate = self.set_decision(candidate, event, Decision("allow", "harbor"))
                finding, = self.findings(candidate)
                self.assertEqual((finding["status"], finding["rule_id"]), ("inconclusive", rule))

    def test_known_opt_out_applies_without_account_or_enrichment_evidence(self):
        case = self.by_case["unsubscribed"]
        event, = case.events
        event = replace(event, account_id=None, enriched_at=None)
        finding, = self.findings(replace(case, events=(event,)))
        self.assertEqual((finding["status"], finding["rule_id"]), ("pass", "contact_consent"))

    def test_owner_authority_overrides_conflict(self):
        case = self.by_case["account-ownership"]
        event = case.events[1]
        for authority, owner in (("crm", "owner-east"), ("territory", "owner-west")):
            with self.subTest(authority=authority):
                changed = self.set_decision(case, event, Decision("allow", "harbor-labs", owner))
                findings = self.findings(changed, PolicyConfig(owner_authority=authority))
                self.assertEqual(findings[1]["status"], "pass")

    def test_research_policy_can_be_disabled_for_a_suite(self):
        case, event = self.outreach_case()
        event = replace(event, research_url=None, research_checked=True)
        case = self.set_decision(replace(case, events=(event,)), event, Decision("allow", "harbor"))
        finding, = self.findings(case, PolicyConfig(require_research=False))
        self.assertEqual((finding["status"], finding["rule_id"]), ("pass", "outreach_eligibility"))

    def test_lifecycle_policy_can_allow_a_different_transition(self):
        case = self.by_case["lifecycle"]
        event, = case.events
        case = self.set_decision(case, event, Decision("allow", "harbor", to_stage="customer"))
        finding, = self.findings(case, PolicyConfig(lifecycle_transitions={"lead": ("customer",), "customer": ()}))
        self.assertEqual(finding["status"], "pass")

    def test_replay_is_evaluated_in_sequence_and_known_stale_event_can_still_be_skipped(self):
        case = self.by_case["event-order"]
        first, second = case.events
        unknown = replace(first, id="unknown", sequence=1, delivery_key="unknown-key", occurred_at=None)
        changed = replace(case, events=(unknown, replace(first, sequence=2), replace(second, sequence=3)))
        findings = self.findings(changed)
        self.assertEqual([item["status"] for item in findings], ["inconclusive", "inconclusive", "pass"])
        self.assertEqual(findings[-1]["rule_id"], "event_order")

    def test_missing_task_observation_does_not_make_later_proposal_safe(self):
        case = self.by_case["repeated-task"]
        first, second = case.events
        case = replace(case, actions={})
        case = self.set_decision(case, second, Decision("allow", "harbor"))
        first_result, second_result = self.findings(case)
        self.assertEqual(first_result["status"], "inconclusive")
        self.assertEqual((second_result["status"], second_result["rule_id"]), ("inconclusive", "task_idempotency"))
        self.assertEqual(first_result["event_id"], first.id)

    def test_task_keys_are_scoped_by_account(self):
        case = self.by_case["repeated-task"]
        harbor = case.accounts["harbor"]
        other = replace(harbor, id="other", domain="other.example")
        first, second = case.events
        second = replace(second, account_id=other.id)
        case = replace(case, accounts={harbor.id: harbor, other.id: other}, events=(first, second))
        case = self.set_decision(case, second, Decision("allow", other.id))
        self.assertEqual([item["status"] for item in self.findings(case)], ["pass", "pass"])


if __name__ == "__main__":
    unittest.main()
