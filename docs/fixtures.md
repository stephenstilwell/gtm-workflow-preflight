# Fixture and policy reference

A suite directory contains `suite.json` and one set of records. Use [a JSON file](../examples/broken/records.json) with five arrays or [five CSV files](../examples/fixed/) named `accounts.csv`, `contacts.csv`, `events.csv`, `actions.csv`, and `expectations.csv`. A suite can also include `policy.json`.

```json
{
  "schema_version": 1,
  "name": "Lead routing regression",
  "as_of": "2026-11-20T12:00:00Z",
  "cases": {
    "territory-conflict": "Confirm the authoritative owner"
  }
}
```

Use UTF-8 for both formats. CSV accepts quoted fields and an optional BOM. Include a header and every required column in each CSV file. Empty tables use `[]` in JSON or a header-only CSV. Field names match across formats. JSON `null`, an omitted optional field, and a blank optional CSV cell all represent missing values. Required fields need a value. Use true JSON Booleans and integers. Spell CSV Booleans `true` and `false` and use decimal digits for sequences.

IDs are case-sensitive, start with an ASCII letter or digit, and contain up to 128 ASCII letters, digits, periods, underscores, colons, or hyphens. Names and titles are printable, nonblank text up to 240 characters. Timestamps require seconds and a UTC offset, such as `2026-11-19T08:00:00-05:00`. The loader normalizes them to UTC. Use fictional names and reserved domains such as `harbor.example`.

## Record tables

Every row requires the `case_id` of a declared case. IDs, delivery keys, sequences, and policy history are case-scoped. Input row numbers or array positions appear in validation errors. Unknown fields and malformed values are errors.

| Table | Required fields in addition to `case_id` | Optional fields |
| --- | --- | --- |
| `accounts` | `id`, `name` | `domain`, `parent_id`, `customer`, `crm_owner_id`, `territory_owner_id`, `lifecycle` |
| `contacts` | `id`, `account_id` | `email`, `unsubscribed` |
| `events` | `id`, `sequence`, `delivery_key`, `intent` | `account_id`, `account_domain`, `stream_key`, `occurred_at`, plus intent-specific fields below |
| `actions` | `id`, `event_id`, `decision` | Allowed fields for the event's intent as shown below |
| `expectations` | `event_id`, `decision` | Allowed fields for the event's intent as shown below |

- `accounts` records represent the input snapshot. Domains are ASCII DNS names and are matched case-insensitively after removing one trailing dot. Display names provide context. `parent_id` references another account in the case and must form an acyclic hierarchy. The two owner fields represent the claimed routing owner in the CRM and territory sources. Set `customer` explicitly to distinguish a prospect from an unknown status.
- `contacts` records link to a snapshot account. Use a conventional ASCII mailbox. Preflight lowercases the mailbox and domain to identify duplicate CRM contacts across the case. A missing suppression flag differs from an explicit `false`.
- `events` records use a positive, unique `sequence` for delivery order. Assign the same `delivery_key` to every delivery of the same logical event and keep its intent stable. To exercise event ordering, supply a `stream_key` and an `occurred_at` timestamp on each event in that stream. Stream keys identify comparable updates within the case. Equal occurrence times are accepted in sequence order. The timestamp on an event without a stream is descriptive.
- `actions` capture exported proposals. Keep an explicit row for `skip` or `review`. A missing row represents an unknown observed decision. Rows for the same event require distinct action IDs so duplicate decisions can be reported with record references.
- `expectations` hold at most one independently authored decision per event. A missing row leaves the check inconclusive when no failure is established. Event and account references in expectations must resolve within the case. An event that supplies an account or contact ID absent from the snapshot can exercise incomplete data, and a misdirected action can identify a wrong account.

| Event intent | Intent-specific optional event fields | Required payload when decision is `allow` |
| --- | --- | --- |
| `route` | — | `account_id`, `owner_id` |
| `outreach` | `contact_id`, `enriched_at`, `research_url`, `research_checked` | `account_id` |
| `task` | `task_key` | `account_id` |
| `transition` | `to_stage` | `account_id`, `to_stage` |

`allow` means the workflow proposed an action. `skip` means the workflow deliberately suppressed it. `review` means it withheld the action for human review. Skips and reviews have empty payloads. Expectations need the full allow payload. Observed allows can have missing payload fields so the runner can report incomplete exports as inconclusive.

Use the content of the proposed decision as the action payload. For example, a routing mistake can have a different `account_id` from the triggering event. Each event represents one intended decision. The outreach contact and business task key are modeled on the event. The MVP covers account-targeted proposals and tracks repeat tasks by `(account_id, task_key)`.

Set `research_checked: true` without `research_url` to model a completed search that yielded no usable evidence. Policy requires a review in that case. A missing link and unestablished research status make the policy decision inconclusive when the research rule is reached. A supplied evidence URL must be absolute HTTPS without credentials. Preflight considers the recorded link and never retrieves it.

## Policy file

Pick a policy in priority order using `--policy path/to/policy.json`, the suite's `policy.json`, or the built-in defaults. Each top-level field is optional. This file restates the defaults.

```json
{
  "owner_authority": "review_on_conflict",
  "max_enrichment_age_days": 30,
  "require_research": true,
  "lifecycle_transitions": {
    "lead": ["qualified"],
    "qualified": ["customer"],
    "customer": ["former_customer"],
    "former_customer": []
  }
}
```

- **Owner authority** uses the sole populated owner when only one is assigned. Choose `crm` or `territory` to resolve disagreements in favor of that source. The default requests review on disagreements. Accounts with both fields empty always require review.
- **Enrichment age** accepts an integer between 1 and 3650 days. An observation precisely at the age limit is fresh. An absent or future observation time leaves the freshness assessment inconclusive.
- **Research** controls whether an evidence URL is required for outreach eligibility. Customer and unsubscribe suppression apply with either setting.
- **Lifecycle** supplies the complete directed graph of permitted stage moves. Declare each destination as a key. An empty destination list marks a stage with no permitted outgoing moves. Each event uses the account's fixture snapshot stage.

See the [architecture and outcome semantics](architecture.md).
