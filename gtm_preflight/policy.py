from collections import defaultdict
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

from .config import PolicyConfig
from .model import Account, Case, Decision, Event


@dataclass(frozen=True)
class Rule:
    description: str
    severity: str
    correction: str


RULES = {
    "delivery_idempotency": Rule(
        "Accept the first delivery for a source key and skip its replays.",
        "high", "Claim the stable delivery key before producing a decision and export an explicit skip for replays.",
    ),
    "event_order": Rule(
        "Skip any event older than the latest known occurrence in its stream.",
        "high", "Compare the occurrence time with the stream watermark before applying a decision.",
    ),
    "account_identity": Rule(
        "Resolve the account by stable ID or an exact, unique domain.",
        "high", "Use a stable account ID and reconcile conflicting identity fields.",
    ),
    "account_hierarchy": Rule(
        "A shared domain cannot select between parent and subsidiary accounts.",
        "high", "Resolve the intended legal or operating entity by its stable ID before proceeding.",
    ),
    "routing_owner": Rule(
        "Route the resolved account to the owner established by field authority.",
        "high", "Select the authoritative owner for the resolved account.",
    ),
    "missing_owner": Rule(
        "An account with no assigned owner requires review.",
        "high", "Queue the account for ownership review and populate an authoritative owner before routing.",
    ),
    "conflicting_owner": Rule(
        "Conflicting CRM and territory owners require review unless policy gives one source authority.",
        "high", "Reconcile the two sources or apply the configured field authority.",
    ),
    "customer_suppression": Rule(
        "Suppress acquisition outreach to an existing customer account.",
        "critical", "Check the resolved account's customer flag and export a skip for existing customers.",
    ),
    "contact_consent": Rule(
        "Suppress outreach to an unsubscribed contact and establish consent status before proceeding.",
        "critical", "Consult the authoritative contact suppression flag and honor any opt-out.",
    ),
    "contact_identity": Rule(
        "Identify one contact on the resolved account before proposing outreach.",
        "high", "Reconcile duplicate contact identities and use the canonical contact ID and account link.",
    ),
    "enrichment_freshness": Rule(
        "Outreach relies on enrichment within the configured age limit.",
        "medium", "Refresh the enrichment and record its observation time before proposing outreach.",
    ),
    "research_evidence": Rule(
        "Outreach requiring research needs a recorded evidence link.",
        "medium", "Record the evidence URL or export a review decision when research finds no usable evidence.",
    ),
    "outreach_eligibility": Rule(
        "Outreach requires a resolved target and satisfaction of the applicable safeguards.",
        "high", "Run the account, consent, identity, enrichment, and research checks before proposing outreach.",
    ),
    "lifecycle_transition": Rule(
        "Apply only lifecycle moves allowed from the snapshot's current stage.",
        "high", "Read the authoritative lifecycle stage and limit proposals to configured transitions.",
    ),
    "task_idempotency": Rule(
        "Propose at most one task for the same account and task key within a case.",
        "high", "Key task proposals by resolved account and business task key, then skip repeated proposals.",
    ),
    "decision_contract": Rule(
        "Record one decision per event and include its required payload.",
        "high", "Export one complete decision for each event, including skips and reviews.",
    ),
    "fixture_expectation": Rule(
        "Declare the intended decision independently of the observed workflow output.",
        "medium", "Add or correct the expected decision after reviewing the business rule.",
    ),
    "case_coverage": Rule(
        "Supply at least one event per declared case.",
        "medium", "Add a synthetic event and its proposed and expected decisions.",
    ),
}


@dataclass(frozen=True)
class Ruling:
    rule: str
    value: Decision | None
    reason: str
    records: tuple[str, ...] = ()
    checked: tuple[str, ...] = ()


class CasePolicy:
    def __init__(self, case: Case, config: PolicyConfig, as_of: datetime):
        self.case = case
        self.config = config
        self.as_of = as_of
        self.domains = defaultdict(list)
        self.mailboxes = defaultdict(list)
        for account in case.accounts.values():
            if account.domain:
                self.domains[account.domain].append(account)
        for contact in case.contacts.values():
            if contact.email:
                self.mailboxes[contact.email].append(contact)
        self.deliveries: dict[str, str] = {}
        self.watermarks: dict[str, tuple[datetime, str]] = {}
        self.incomplete_streams: set[str] = set()
        self.tasks: dict[tuple[str, str], str] = {}
        self.possible_tasks: set[tuple[str | None, str]] = set()

    def evaluate(self, event: Event):
        earlier = self.deliveries.get(event.delivery_key)
        if earlier is not None:
            return Ruling("delivery_idempotency", Decision("skip"),
                          f"Delivery key {event.delivery_key} already appeared on {earlier}.",
                          (f"event/{earlier}",))
        self.deliveries[event.delivery_key] = event.id

        ordering = self.check_order(event)
        if ordering is not None:
            return ordering
        account, identity = self.resolve_account(event)
        if event.intent == "outreach":
            suppression = self.suppress(event, account)
            if suppression is not None:
                return suppression
        if identity is not None:
            return identity

        handler = {
            "route": self.route,
            "outreach": self.outreach,
            "task": self.task,
            "transition": self.transition,
        }[event.intent]
        result = handler(event, account)
        records = (f"account/{account.id}", *result.records)
        return replace(result, records=records, checked=("account_identity", *result.checked))

    def check_order(self, event):
        if event.stream_key is None:
            return None
        key = event.stream_key
        current = self.watermarks.get(key)
        when = event.occurred_at
        if when is None or when > self.as_of:
            self.incomplete_streams.add(key)
            return Ruling("event_order", None, f"Stream {key} lacks a usable occurrence time for this event.")
        if current and when < current[0]:
            return Ruling("event_order", Decision("skip"),
                          f"The occurrence predates the stream watermark set by {current[1]}.",
                          (f"event/{current[1]}",))
        self.watermarks[key] = (when, event.id)
        if key in self.incomplete_streams:
            return Ruling("event_order", None, f"An earlier event in stream {key} has an unknown occurrence time.")
        return None

    def resolve_account(self, event):
        if event.account_id:
            account = self.case.accounts.get(event.account_id)
            supplied = (f"account/{event.account_id}",)
            if account is None:
                return None, Ruling("account_identity", None, "The supplied account ID is absent from the snapshot.", supplied)
            if event.account_domain and account.domain is None:
                return None, Ruling("account_identity", None, "The snapshot has no domain to confirm the supplied domain.", supplied)
            if event.account_domain and account.domain != event.account_domain:
                return None, Ruling("account_identity", Decision("review"),
                                    "The supplied account ID and domain disagree.", supplied)
            return account, None
        if event.account_domain is None:
            return None, Ruling("account_identity", None, "No stable account ID or exact domain was supplied.")
        matches = self.domains.get(event.account_domain, ())
        if len(matches) == 1:
            return matches[0], None
        if not matches:
            return None, Ruling("account_identity", None, f"No snapshot account has domain {event.account_domain}.")
        identities = {account.id for account in matches}
        related = any(self.has_ancestor(account, identities) for account in matches)
        records = tuple(f"account/{account_id}" for account_id in sorted(identities))
        return None, Ruling("account_hierarchy" if related else "account_identity", Decision("review"),
                            f"Domain {event.account_domain} matches multiple accounts.", records)

    def has_ancestor(self, account: Account, candidates):
        while account.parent_id:
            if account.parent_id in candidates:
                return True
            account = self.case.accounts[account.parent_id]
        return False

    def route(self, event, account):
        crm = account.crm_owner_id
        territory = account.territory_owner_id
        if not (crm or territory):
            return Ruling("missing_owner", Decision("review"), "Neither ownership field has an assigned value.")
        if crm and territory and crm != territory:
            authority = self.config.owner_authority
            if authority == "review_on_conflict":
                return Ruling("conflicting_owner", Decision("review"),
                              f"CRM owner {crm} conflicts with territory owner {territory}.")
            owner = crm if authority == "crm" else territory
            return Ruling("conflicting_owner", Decision("allow", account.id, owner_id=owner),
                          f"The configured {authority} authority resolves the owner conflict.")
        return Ruling("routing_owner", Decision("allow", account.id, owner_id=crm or territory),
                      "The populated ownership fields establish the route.")

    def suppress(self, event, account):
        if account and account.customer is True:
            return Ruling("customer_suppression", Decision("skip"), "The resolved account is an existing customer.",
                          (f"account/{account.id}",), ("account_identity",))
        contact = self.case.contacts.get(event.contact_id)
        if contact and contact.unsubscribed is True:
            records = (f"contact/{contact.id}", f"account/{contact.account_id}")
            return Ruling("contact_consent", Decision("skip"), "The supplied contact has unsubscribed.", records)
        return None

    def outreach(self, event, account):
        contact = self.case.contacts.get(event.contact_id)
        if contact is None:
            records = (f"contact/{event.contact_id}",) if event.contact_id else ()
            return Ruling("contact_identity", None, "A contact from the snapshot is required for outreach.", records)
        records = (f"contact/{contact.id}",)
        if contact.account_id != account.id:
            return Ruling("contact_identity", Decision("review"), "The contact belongs to a different account.",
                          (*records, f"account/{contact.account_id}"))
        if contact.email is None:
            return Ruling("contact_identity", None, "The contact mailbox is missing from the snapshot.", records)
        matches = self.mailboxes[contact.email]
        if len(matches) > 1:
            duplicates = tuple(f"contact/{item.id}" for item in sorted(matches, key=lambda item: item.id))
            return Ruling("contact_identity", Decision("review"), "Multiple CRM contacts share the same mailbox.",
                          duplicates)
        checked = ("contact_identity",)
        if account.customer is None:
            return Ruling("customer_suppression", None, "The account customer flag is unknown.", records, checked)
        checked += ("customer_suppression",)
        if contact.unsubscribed is None:
            return Ruling("contact_consent", None, "The contact suppression flag is unknown.", records, checked)
        checked += ("contact_consent",)
        if event.enriched_at is None or event.enriched_at > self.as_of:
            return Ruling("enrichment_freshness", None, "The enrichment observation time is missing or in the future.",
                          records, checked)
        limit = self.config.max_enrichment_age_days
        if self.as_of - event.enriched_at > timedelta(days=limit):
            return Ruling("enrichment_freshness", Decision("review"),
                          f"The enrichment observation is older than {limit} days.", records, checked)
        checked += ("enrichment_freshness",)
        if self.config.require_research:
            if event.research_url is None:
                if event.research_checked is True:
                    return Ruling("research_evidence", Decision("review"),
                                  "Research completed without a recorded evidence URL.", records, checked)
                return Ruling("research_evidence", None, "Research status is unknown and no evidence URL was supplied.",
                              records, checked)
            checked += ("research_evidence",)
        return Ruling("outreach_eligibility", Decision("allow", account.id),
                      "The target and the applicable outreach safeguards are established.", records, checked)

    def task(self, event, account):
        if event.task_key is None:
            return Ruling("task_idempotency", None, "The business task key is missing.")
        task = (account.id, event.task_key)
        earlier = self.tasks.get(task)
        if earlier is not None:
            return Ruling("task_idempotency", Decision("skip"),
                          f"Task key {event.task_key} was already proposed for this account by {earlier}.",
                          (f"event/{earlier}",))
        if any(
            (account_id, task_key) in self.possible_tasks
            for account_id in (None, account.id) for task_key in (None, event.task_key)
        ):
            return Ruling("task_idempotency", None,
                          "An earlier task observation is incomplete and could duplicate this proposal.")
        return Ruling("task_idempotency", Decision("allow", account.id),
                      f"No earlier task proposal for key {event.task_key} and this account was observed.")

    def record_observations(self, event):
        if event.intent != "task":
            return
        actions = self.case.actions.get(event.id, ())
        if not actions:
            self.possible_tasks.add((None, event.task_key))
        for action in actions:
            if action.value.decision != "allow":
                continue
            account_id = action.value.account_id
            if account_id is None or event.task_key is None:
                self.possible_tasks.add((account_id, event.task_key))
            else:
                self.tasks.setdefault((account_id, event.task_key), event.id)

    def transition(self, event, account):
        transitions = self.config.lifecycle_transitions
        current = account.lifecycle
        target = event.to_stage
        if current not in transitions:
            return Ruling("lifecycle_transition", None, "The snapshot lifecycle stage is missing or undefined by policy.")
        if target is None:
            return Ruling("lifecycle_transition", None, "The event has no requested lifecycle stage.")
        if target not in transitions[current]:
            return Ruling("lifecycle_transition", Decision("skip"),
                          f"Policy does not allow a move from {current} to {target}.")
        return Ruling("lifecycle_transition", Decision("allow", account.id, to_stage=target),
                      f"Policy allows the move from {current} to {target}.")
