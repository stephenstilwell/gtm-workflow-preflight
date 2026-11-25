# GTM Workflow Preflight

Run regression tests on the decisions your GTM workflow proposes before connecting it to a production CRM. Supply synthetic accounts, contacts, events, observed decisions, and independent expectations. Preflight checks the observed decisions against deterministic business rules and writes JSON and standalone HTML reports.

Use it to catch routing to the wrong account or owner, repeat task proposals after a webhook replay, and acquisition outreach to customers or unsubscribed contacts. Preflight evaluates exported decisions. Execution and platform-specific behavior remain in Clay, Apollo, n8n, HubSpot, Salesforce, or whichever system produced the export.

## Quickstart

From a checkout with Python 3.11 or newer, run the examples offline with the standard library.

```sh
python -m gtm_preflight run examples/broken
python -m gtm_preflight run examples/fixed
```

On Windows, use `py` if that is your Python launcher. For the `gtm-preflight` command, install the local package in a virtual environment with `python -m pip install .`. Installation needs the setuptools build dependency available through your package cache or index. A checkout runs directly without installing it.

```sh
gtm-preflight run examples/broken
gtm-preflight run examples/fixed
```

| Suite | Cases | Pass | Fail | Inconclusive | Exit |
| --- | ---: | ---: | ---: | ---: | ---: |
| [Broken JSON](examples/broken/) | 12 | 3 | 13 | 0 | 1 |
| [Corrected CSV](examples/fixed/) | 12 | 16 | 0 | 0 | 0 |

Open `reports/broken/report.html` or `reports/fixed/report.html` in any browser. Their companion `report.json` files include the effective policy, case counts, rule identifiers, expected and observed decisions, and affected record IDs. Both suites use the same synthetic inputs, independent expectations, and evaluation clock. The observed decisions are the only substantive difference.

## Run your own cases

1. Copy an [example suite](examples/fixed/) and give each scenario a case ID and title.
2. Prepare synthetic input records and write the expected decisions before exporting your workflow's proposed outputs.
3. Export one observed decision for every event. Use explicit `skip` or `review` rows when the workflow blocks an action.
4. Run Preflight with the fixture directory. If your routing or lifecycle rules differ, add a fixture-local `policy.json` or pass `--policy path/to/policy.json`.

```sh
gtm-preflight run fixtures/lead-routing --policy policies/lead-routing.json --output reports/lead-routing
```

| Exit | Meaning |
| --- | --- |
| `0` | Every check passed, or the run is inconclusive and `--allow-inconclusive` was supplied |
| `1` | One or more failures, including incompatible decisions or confirmed duplicates |
| `2` | Invalid CLI usage or input, or an I/O error |
| `3` | No known failure and at least one inconclusive check |

Keep the default exit handling for a CI gate that requires complete evidence. The included workflow runs the unit tests, checks both example exit codes, and uploads their reports.

### Publish results to a CI test viewer

```sh
gtm-preflight run fixtures/lead-routing --output reports/lead-routing --junit
```

Configure your CI test viewer to read `reports/lead-routing/report.junit.xml`, including on failed runs. Each policy finding becomes a test case identified by its fixture case and event. Failed checks include the rule identifier and suggested correction. Inconclusive checks appear as skipped in the XML. Use the CLI exit code to enforce the gate.

## Learn and extend

- Follow the [ten-minute tutorial](docs/tutorial.md) to diagnose an incident and turn a known failure into an explicit inconclusive check.
- Adapt the [fixture and policy reference](docs/fixtures.md) to your export format.
- Read the [architecture and limits](docs/architecture.md) and review the [local verification evidence](docs/verification.md).
- See [contributing](CONTRIBUTING.md) and the [security policy](SECURITY.md).

## Related Useful in Practice projects

- [GTM Signal Lab](https://github.com/stephenstilwell/gtm-signal-lab) captures public signals and tracks evidence and commercial hypotheses. If you want to test routing or suppression downstream, recreate a signal as a synthetic Preflight event and attach its proposed decision to the case.
- [GTM Commercial Engineering](https://github.com/stephenstilwell/gtm-commercial-engineering) teaches signal-to-opportunity workflows. Its offline routing lab is a starting point for defining independent expectations for owner assignment, decision review, and task proposals.
- [GTM AI Buyer Readiness](https://github.com/stephenstilwell/gtm-ai-buyer-readiness) uses offline demo responses and reports evidence with corrections. Use it for public product and service information audits. Preflight serves the internal decision testing stage.

Preflight runs independently with local fixtures. Maintained by Stephen Stilwell at [Useful in Practice](https://stephenstilwell.com). Released under the [MIT License](LICENSE).
