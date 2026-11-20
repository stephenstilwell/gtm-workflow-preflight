from collections import Counter
from dataclasses import asdict

from .config import PolicyConfig
from .policy import RULES, CasePolicy


STATUSES = ("pass", "fail", "inconclusive")


def finding(case, event, rule_id, status, reason, ruling=None):
    rule = RULES[rule_id]
    expected = case.expectations.get(event.id) if event else None
    actual = case.actions.get(event.id, ()) if event else ()
    affected = []
    if event:
        affected.append(f"event/{event.id}")
        if event.account_id:
            affected.append(f"account/{event.account_id}")
        if event.contact_id:
            affected.append(f"contact/{event.contact_id}")
    for action in actual:
        affected.append(f"action/{action.id}")
        if action.value.account_id:
            affected.append(f"account/{action.value.account_id}")
    if ruling:
        affected.extend(ruling.records)

    return {
        "event_id": event.id if event else None,
        "intent": event.intent if event else None,
        "status": status,
        "severity": rule.severity,
        "rule_id": rule_id,
        "business_rule": rule.description,
        "detail": reason,
        "correction": rule.correction,
        "expected": expected.as_dict() if expected else None,
        "policy_rule_id": ruling.rule if ruling else None,
        "policy_decision": ruling.value.as_dict() if ruling and ruling.value else None,
        "actual": [{"id": action.id, **action.value.as_dict()} for action in actual],
        "affected_records": list(dict.fromkeys(affected)),
    }


def conflicts(observed, target):
    expected = target.as_dict()
    return any(expected.get(key) != value for key, value in observed.as_dict().items())


def check_event(case, event, ruling):
    actions = case.actions.get(event.id, ())
    expected = case.expectations.get(event.id)
    value = ruling.value

    def result(status, detail, rule_id=ruling.rule):
        return finding(case, event, rule_id, status, detail, ruling)

    if len(actions) > 1:
        violates_policy = value is not None and any(conflicts(action.value, value) for action in actions)
        rule_id = ruling.rule if violates_policy else "decision_contract"
        message = "The workflow exported more than one decision for this event. "
        return result("fail", message + ruling.reason, rule_id)

    actual = actions[0].value if actions else None
    if actual and value and conflicts(actual, value):
        if actual.decision == value.decision == "allow" and actual.account_id and actual.account_id != value.account_id:
            return result("fail", "The proposed decision targets a different account from the resolved identity.",
                          "account_identity")
        return result("fail", ruling.reason)
    if expected and value and expected != value:
        return result("fail", "The fixture expectation conflicts with policy. " + ruling.reason,
                      "fixture_expectation")
    if actual and expected and conflicts(actual, expected):
        return result("fail", "The observed decision differs from the fixture expectation. " + ruling.reason,
                      "fixture_expectation")
    if not expected:
        return result("inconclusive", "No expected decision was supplied. " + ruling.reason, "fixture_expectation")
    if not actual:
        return result("inconclusive", "No observed decision was exported. " + ruling.reason, "decision_contract")
    if value is None:
        return result("inconclusive", ruling.reason)
    if actual != value:
        return result("inconclusive", "The observed allow is missing required payload. " + ruling.reason,
                      "decision_contract")
    return result("pass", ruling.reason)


def summary(findings):
    counts = Counter(item["status"] for item in findings)
    return {status: counts[status] for status in STATUSES}


def overall(counts):
    if counts["fail"]:
        return "fail"
    if counts["inconclusive"]:
        return "inconclusive"
    return "pass"


def run_suite(suite, config: PolicyConfig | None = None):
    config = config if config is not None else PolicyConfig()
    cases = []
    coverage = Counter()
    all_findings = []
    for case in suite.cases:
        evaluator = CasePolicy(case, config, suite.as_of)
        findings = []
        for event in case.events:
            ruling = evaluator.evaluate(event)
            findings.append(check_event(case, event, ruling))
            coverage.update(dict.fromkeys((ruling.rule, *ruling.checked), 1))
            evaluator.record_observations(event)
        if not findings:
            findings.append(finding(case, None, "case_coverage", "inconclusive", "The case has no events."))
        counts = summary(findings)
        all_findings.extend(findings)
        cases.append({"id": case.id, "title": case.title, "status": overall(counts),
                      "summary": counts, "findings": findings})

    counts = summary(all_findings)
    return {
        "schema_version": 1,
        "suite": suite.name,
        "as_of": suite.as_of.isoformat(),
        "policy": asdict(config),
        "status": overall(counts),
        "summary": counts,
        "coverage": {"cases": len(cases), "events": sum(len(case.events) for case in suite.cases),
                     "rules": dict(sorted(coverage.items()))},
        "cases": cases,
    }
