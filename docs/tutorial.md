# Test a workflow in ten minutes

## Minutes 0–2 · Run both suites

From the checkout, use Python 3.11 or later. On Windows you can substitute `py` for `python`.

```sh
python -m gtm_preflight run examples/broken
python -m gtm_preflight run examples/fixed
```

The first command returns `1` with 13 failures. The second returns `0` with 16 passes. Open `reports/broken/report.html`. Its summary counts decisions. Its case index covers 12 scenarios because replay, routing authority, event ordering, and repeated tasks use two decisions each.

## Minutes 2–4 · Follow a replay

Open **Duplicate webhook deliveries**. Both events carry delivery key `source-773`. The first event routes to `owner-east`. The second expects a skip, but the workflow exported another route.

A source delivery key identifies a logical webhook across retries. In **Repeated task creation**, the deliveries have different source keys and the same task key, `review-signal`, for account `harbor`. That business key is what makes both proposals represent the same task. Use both keys in regression fixtures when a workflow receives retries and repeated business signals.

## Minutes 4–6 · Check identity, authority, and suppression

In **Similar company names with different identities**, `harbor.example` resolves to `harbor`. The observed result selects `harbor-labs` and its owner instead. In **Parent and subsidiary account ambiguity**, two account IDs share a domain. Review is the required decision until the correct entity is identified.

Open **Missing or conflicting account ownership**. The first account lacks an owner. The second has both CRM and territory owners with different values. The default policy requests review in both cases. Your business can designate the CRM field as authoritative using `"owner_authority": "crm"` in `policy.json`. An independent expectation should specify the resulting owner.

In **Existing customer suppression** and **Unsubscribed contacts**, the rule requires a skip. The broken workflow proposes outreach. The report marks both findings critical, with the expected decision, the observed proposal, and the affected records.

## Minutes 6–8 · Fix one decision

Copy the broken example to a scratch suite.

```sh
cp -R examples/broken reports/tutorial-fixture
```

In PowerShell, use `Copy-Item -Recurse examples/broken reports/tutorial-fixture`. In the scratch `records.json`, find the action with `"id":"similar-names-1-decision"`. Change its `account_id` to `harbor` and its `owner_id` to `owner-east`. Keep the expected decision as written.

```sh
python -m gtm_preflight run reports/tutorial-fixture --output reports/tutorial-result
```

The run still exits `1`. It now has four passes and twelve failures. Open the report to see the **Similar company names with different identities** case pass. A small recorded regression makes it possible to upgrade a workflow later and verify that the exact error stays fixed.

## Minutes 8–10 · Make uncertainty visible

Copy the corrected example with `cp -R examples/fixed reports/tutorial-inconclusive` or PowerShell's `Copy-Item -Recurse examples/fixed reports/tutorial-inconclusive`. In the scratch `actions.csv`, delete the row with action ID `existing-customer-1-decision`. Leave its expected skip in `expectations.csv`.

```sh
python -m gtm_preflight run reports/tutorial-inconclusive --output reports/tutorial-inconclusive-result
```

Exit `3` indicates 15 passes and one inconclusive check. The customer rule still indicates **Skip** and the report says **No observed decision**. An explicit skip in the workflow export is the evidence that makes the check pass.

For your first workflow, start with one correct route, one replay, and one suppressed contact. Define the expectations before exporting the decisions, and run the suite when the workflow or policy changes. The [fixture reference](fixtures.md) shows each field and the included [GitHub Actions workflow](../.github/workflows/ci.yml) shows how to use the exit codes.
