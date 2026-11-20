from dataclasses import asdict, dataclass
from datetime import datetime


@dataclass(frozen=True)
class Decision:
    decision: str
    account_id: str | None = None
    owner_id: str | None = None
    to_stage: str | None = None

    def as_dict(self):
        return {key: value for key, value in asdict(self).items() if value is not None}


@dataclass(frozen=True)
class Account:
    id: str
    name: str
    domain: str | None = None
    parent_id: str | None = None
    customer: bool | None = None
    crm_owner_id: str | None = None
    territory_owner_id: str | None = None
    lifecycle: str | None = None


@dataclass(frozen=True)
class Contact:
    id: str
    account_id: str
    email: str | None = None
    unsubscribed: bool | None = None


@dataclass(frozen=True)
class Event:
    id: str
    sequence: int
    delivery_key: str
    intent: str
    occurred_at: datetime | None = None
    stream_key: str | None = None
    account_id: str | None = None
    account_domain: str | None = None
    contact_id: str | None = None
    task_key: str | None = None
    to_stage: str | None = None
    enriched_at: datetime | None = None
    research_url: str | None = None
    research_checked: bool | None = None


@dataclass(frozen=True)
class Observation:
    id: str
    value: Decision


@dataclass(frozen=True)
class Case:
    id: str
    title: str
    accounts: dict[str, Account]
    contacts: dict[str, Contact]
    events: tuple[Event, ...]
    actions: dict[str, tuple[Observation, ...]]
    expectations: dict[str, Decision]


@dataclass(frozen=True)
class Suite:
    name: str
    as_of: datetime
    cases: tuple[Case, ...]
