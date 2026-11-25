import json
import os
from html import escape
from pathlib import Path
from tempfile import NamedTemporaryFile
from xml.etree.ElementTree import Element, SubElement, indent, tostring

from .policy import RULES
from .runner import STATUSES


CSS = """
:root {
  color-scheme: light;
  --navy: #003049;
  --blue: #669bbc;
  --cream: #fdf0d5;
  --red: #c1121f;
  --maroon: #780000;
  --paper: #fff;
  --muted: #405c6b;
  --line: #ccdae2;
  --surface: #f2f6f8;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--surface);
  color: var(--navy);
  font: 1rem/1.5 system-ui, sans-serif;
}
a { color: inherit; text-underline-offset: .2em; }
a:focus-visible, summary:focus-visible { outline: 3px solid var(--red); outline-offset: 4px; }
code { font: .9em ui-monospace, Consolas, monospace; overflow-wrap: anywhere; }
.wrap { width: min(100% - 2.5rem, 73rem); margin-inline: auto; }
.skip-link { position: absolute; top: .5rem; left: .5rem; padding: .6rem 1rem; background: var(--paper); }
.skip-link:not(:focus) { transform: translateY(-150%); }
.masthead { color: var(--paper); background: var(--navy); border-top: .4rem solid var(--blue); }
.masthead .wrap { padding-block: 2.25rem 2.5rem; }
.brand { color: var(--cream); margin: 0 0 1rem; font-weight: 650; }
.hero-line, .section-line, .finding-line {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: .5rem 1rem;
}
h1, h2, h3, h4, p { overflow-wrap: anywhere; }
h1 { font-size: clamp(2rem, 5vw, 3.4rem); line-height: 1.08; letter-spacing: -.045em; margin: 0; }
h2 { font-size: 1.45rem; line-height: 1.2; letter-spacing: -.02em; margin: 0; }
h3 { font-size: 1.2rem; line-height: 1.25; margin: 0; }
h4 { font-size: 1rem; margin: 0; }
.clock { margin: 1rem 0 0; color: var(--cream); }
.badge {
  display: inline-flex;
  align-items: center;
  gap: .45em;
  padding: .18em .63em;
  border: 1px solid currentColor;
  border-radius: 99rem;
  font-weight: 700;
  font-size: .83rem;
  white-space: nowrap;
}
.badge::before { content: ""; width: .47em; height: .47em; border-radius: 50%; background: currentColor; }
.badge.pass { color: var(--navy); background: #edf6fa; }
.badge.fail { color: var(--maroon); background: #fff0ef; }
.badge.inconclusive { color: var(--navy); background: var(--cream); border-style: dashed; }
.hero-line .badge { font-size: 1rem; }
main { padding-block: 1.65rem 3rem; }
.overview { display: grid; grid-template-columns: minmax(0, 1.7fr) minmax(0, 1fr); gap: 1rem; }
.panel, .case {
  padding: 1.15rem 1.25rem;
  border: 1px solid var(--line);
  border-radius: .65rem;
  background: var(--paper);
  min-width: 0;
}
.metrics { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .65rem; margin: .85rem 0 0; }
.metric { background: var(--surface); border-top: .22rem solid var(--blue); border-radius: .25rem; padding: .7rem .75rem; }
.metric.fail { border-top-color: var(--red); }
.metric.inconclusive { border-top-color: var(--maroon); background: var(--cream); }
.metric dt { font-size: .85rem; font-weight: 650; overflow-wrap: anywhere; }
.metric dd { margin: .18rem 0 0; font-size: 1.95rem; line-height: 1; font-weight: 720; font-variant-numeric: tabular-nums; }
.coverage-counts { margin: .7rem 0 .45rem; }
.coverage-details summary { cursor: pointer; text-decoration: underline; text-underline-offset: .2em; }
.coverage-details ul { padding-left: 1.25rem; margin: .6rem 0 0; }
.case-nav { margin-block: 1rem 1.6rem; }
.case-nav ul, .records { list-style: none; padding: 0; margin: .75rem 0 0; }
.case-nav ul { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: .4rem 1.25rem; }
.case-nav li { display: flex; gap: .45rem; align-items: baseline; }
.case-nav li a { min-width: 0; overflow-wrap: anywhere; }
.case-nav .badge { flex: none; padding: .04em .5em; font-size: .72rem; }
.case { margin-block: .85rem; border-top: .22rem solid var(--blue); scroll-margin-top: 1rem; }
.case.fail { border-top-color: var(--red); }
.case.inconclusive { border-top-color: var(--maroon); }
.case:target { outline: 3px solid var(--navy); outline-offset: 2px; }
.finding { border-top: 1px solid var(--line); margin-top: .9rem; padding-top: .9rem; }
.finding-line { justify-content: flex-start; }
.finding-line .severity { color: var(--muted); font-size: .85rem; }
.finding-line .critical { color: var(--maroon); font-weight: 700; }
.finding p { margin: .5rem 0; }
.detail { color: var(--muted); }
.decisions { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: .65rem; margin: .8rem 0; }
.decisions > div { padding: .58rem .68rem; background: var(--surface); border-radius: .35rem; }
.decisions dt { font-weight: 700; font-size: .82rem; }
.decisions dd { margin: .33rem 0 0; }
.decision-list { list-style: none; padding: 0; margin: 0; }
.decision-list li + li { margin-top: .45rem; padding-top: .4rem; border-top: 1px solid var(--line); }
.decision-fields { display: block; }
.records { display: flex; flex-wrap: wrap; gap: .35rem; margin: .35rem 0 0; }
.records li { border: 1px solid var(--line); border-radius: .28rem; padding: .08rem .42rem; max-width: 100%; }
@media (max-width: 49rem) {
  .overview { grid-template-columns: 1fr; }
}
@media (max-width: 34rem) {
  .wrap { width: calc(100% - 1.25rem); }
  .masthead .wrap { padding-block: 1.55rem 1.7rem; }
  .panel, .case { padding-inline: .8rem; }
  .metric { padding-inline: .45rem; }
  .metric dt { font-size: .78rem; }
  .case-nav ul, .decisions { grid-template-columns: 1fr; }
}
@media (max-width: 23rem) {
  .metrics { grid-template-columns: minmax(0, .85fr) minmax(0, .85fr) minmax(0, 1.3fr); }
  .clock time { display: inline-block; }
}
@media print {
  body, .masthead { color: #000; background: #fff; }
  .masthead, .panel, .case, .finding { border-color: #555; }
  .brand, .clock { color: #000; }
  .wrap { width: 100%; }
  .masthead .wrap, main { padding-block: .6rem; }
  .skip-link, .case-nav { display: none; }
  h2, h3, h4 { break-after: avoid; }
  .finding { break-inside: avoid; }
}
"""


def write_atomic(path, content):
    temporary = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def write_reports(directory, report, *, junit=False):
    html = render_html(report)
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    directory.mkdir(parents=True, exist_ok=True)
    write_atomic(directory / "report.json", payload)
    write_atomic(directory / "report.html", html)
    if junit:
        write_atomic(directory / "report.junit.xml", render_junit(report))


def render_junit(report):
    counts = report["summary"]
    suite = Element("testsuite", {
        "name": report["suite"], "tests": str(sum(counts.values())), "failures": str(counts["fail"]),
        "errors": "0", "skipped": str(counts["inconclusive"]),
    })
    for case in report["cases"]:
        for finding in case["findings"]:
            test = SubElement(suite, "testcase", {
                "classname": case["id"], "name": finding["event_id"] or "Case coverage",
            })
            if finding["status"] == "fail":
                failure = SubElement(test, "failure", {"type": finding["rule_id"], "message": finding["detail"]})
                failure.text = finding["correction"]
            elif finding["status"] == "inconclusive":
                SubElement(test, "skipped", {"message": finding["detail"]})
    indent(suite)
    return tostring(suite, encoding="unicode", xml_declaration=True) + "\n"


def badge(status):
    return f'<span class="badge {escape(status)}">{escape(status.title())}</span>'


def render_decision(value, absent):
    if value is None:
        return escape(absent)
    labels = {"id": "Action", "account_id": "Account", "owner_id": "Owner", "to_stage": "Stage"}
    fields = "".join(
        f'<span class="decision-fields">{label} <code>{escape(value[field])}</code></span>'
        for field, label in labels.items() if field in value
    )
    return f'<strong>{escape(value["decision"].title())}</strong>{fields}'


def render_finding(item, anchor):
    event = escape(item["event_id"] or "Case coverage")
    intent = escape(item["intent"] or "")
    rule = escape(item["business_rule"])
    detail = escape(item["detail"])
    severity = escape(item["severity"])
    status = item["status"]
    marker = (
        f'<span class="severity {severity}">Rule severity {severity.title()}</span>'
        if status != "pass" else ""
    )
    actual = "No observed decision"
    if item["actual"]:
        actions = "".join(f'<li>{render_decision(action, "")}</li>' for action in item["actual"])
        actual = f'<ul class="decision-list">{actions}</ul>'
    panels = {
        "Expected": render_decision(item["expected"], "No expected decision"),
        "Policy decision": render_decision(item["policy_decision"], "Undetermined"),
        "Observed": actual,
    }
    decisions = "".join(f'<div><dt>{label}</dt><dd>{value}</dd></div>' for label, value in panels.items())
    records = "".join(f'<li><code>{escape(record)}</code></li>' for record in item["affected_records"])
    correction = escape(item["correction"])
    records_html = f'<p><strong>Affected records</strong></p><ul class="records">{records}</ul>' if records else ""
    fix = f'<p><strong>Suggested fix</strong> {correction}</p>' if status != "pass" else ""
    return f"""<article class="finding" aria-labelledby="{anchor}">
  <div class="finding-line">
    <h4 id="{anchor}">{event}</h4>{f'<span class="detail">{intent}</span>' if intent else ''}
    {badge(status)}{marker}
  </div>
  <p><strong>Business rule</strong> {rule}</p>
  <p class="detail">{detail}</p>
  <dl class="decisions">{decisions}</dl>
  {records_html}
  {fix}
</article>"""


def render_case(case):
    case_id = escape(case["id"])
    findings = "\n".join(
        render_finding(item, f"finding-{case_id}-{index}")
        for index, item in enumerate(case["findings"], start=1)
    )
    return f"""<section id="case-{case_id}" class="case {escape(case["status"])}" aria-labelledby="title-{case_id}" tabindex="-1">
  <div class="section-line"><h3 id="title-{case_id}">{escape(case["title"])}</h3>{badge(case["status"])}</div>
  {findings}
</section>"""


def render_html(report):
    name = escape(report["suite"])
    clock = escape(report["as_of"])
    clock_label = clock.removesuffix("+00:00").replace("T", " ", 1) + " UTC"
    counts = "".join(
        f'<div class="metric {status}"><dt>{status.title()}</dt><dd>{report["summary"][status]}</dd></div>'
        for status in STATUSES
    )
    coverage = report["coverage"]
    rules = "".join(
        f'<li>{escape(RULES[key].description)} <strong>({count})</strong></li>'
        for key, count in coverage["rules"].items()
    )
    rule_details = (
        f'<details class="coverage-details"><summary>Policy rules reached</summary><ul>{rules}</ul></details>'
        if rules else '<p>No policy rules reached.</p>'
    )
    index = "\n".join(
        f'<li><a href="#case-{escape(case["id"])}">{escape(case["title"])}</a>{badge(case["status"])}</li>'
        for case in report["cases"]
    )
    cases = "\n".join(render_case(case) for case in report["cases"])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
  <title>{name} | GTM Workflow Preflight</title>
  <style>{CSS}</style>
</head>
<body>
  <a class="skip-link" href="#main">Skip to report</a>
  <header class="masthead">
    <div class="wrap">
      <p class="brand">GTM Workflow Preflight</p>
      <div class="hero-line"><h1>{name}</h1>{badge(report["status"])}</div>
      <p class="clock">Evaluation clock <time datetime="{clock}">{clock_label}</time></p>
    </div>
  </header>
  <main class="wrap" id="main" tabindex="-1">
    <div class="overview">
      <section class="panel" aria-labelledby="summary-title">
        <h2 id="summary-title">Summary</h2>
        <dl class="metrics">{counts}</dl>
      </section>
      <section class="panel" aria-labelledby="coverage-title">
        <h2 id="coverage-title">Coverage</h2>
        <p class="coverage-counts"><strong>{coverage["cases"]}</strong> cases ·
          <strong>{coverage["events"]}</strong> events · <strong>{len(coverage["rules"])}</strong> policy rules</p>
        {rule_details}
      </section>
    </div>
    <nav aria-labelledby="jump-title" class="case-nav panel">
      <h2 id="jump-title">Jump to a case</h2>
      <ul>{index}</ul>
    </nav>
    <section aria-labelledby="cases-title">
      <h2 id="cases-title">Case results</h2>
      {cases}
    </section>
  </main>
</body>
</html>
"""
