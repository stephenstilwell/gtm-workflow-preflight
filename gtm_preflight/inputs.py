import csv
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .model import Account, Case, Contact, Decision, Event, Observation, Suite


class InputError(ValueError):
    """An invalid suite, record, or policy."""


ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}")
DOMAIN = re.compile(
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
)
TIMESTAMP = re.compile(
    r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?"
    r"(?:Z|[+-]\d{2}:\d{2})"
)
INTENTS = {"route", "outreach", "task", "transition"}


def read_json(path: Path):
    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    def bad_constant(value):
        raise ValueError(f"invalid JSON constant {value}")

    try:
        return json.loads(
            path.read_text(encoding="utf-8-sig"),
            object_pairs_hook=unique_object,
            parse_constant=bad_constant,
        )
    except (OSError, ValueError, RecursionError) as exc:
        raise InputError(f"{path}: {exc}") from exc


def object_fields(value, allowed, required, where):
    if not isinstance(value, dict):
        raise InputError(f"{where}: expected an object")
    unknown = sorted(value.keys() - allowed)
    missing = sorted(required - value.keys())
    if unknown:
        raise InputError(f"{where}: unknown field(s): {', '.join(unknown)}")
    if missing:
        raise InputError(f"{where}: missing field(s): {', '.join(missing)}")


def identifier(value):
    if isinstance(value, str) and ID.fullmatch(value):
        return value
    raise ValueError("expected an identifier of 1 to 128 letters, digits, or ._:-")


def text(value):
    if isinstance(value, str) and value.strip() and value.isprintable() and len(value) <= 240:
        return value
    raise ValueError("expected nonblank printable text of at most 240 characters")


def positive_int(value):
    if type(value) is int and value > 0:
        return value
    raise ValueError("expected a positive integer")


def boolean(value):
    if type(value) is bool:
        return value
    raise ValueError("expected true or false")


def timestamp(value):
    if isinstance(value, str) and TIMESTAMP.fullmatch(value):
        if value[-1] != "Z" and (int(value[-5:-3]) > 23 or int(value[-2:]) > 59):
            raise ValueError("invalid timestamp offset")
        try:
            return datetime.fromisoformat(value).astimezone(timezone.utc)
        except (ValueError, OverflowError):
            pass
    raise ValueError("expected an ISO 8601 timestamp with seconds and a UTC offset")


def domain(value):
    if isinstance(value, str) and value.isascii():
        normalized = value.lower().removesuffix(".")
        if len(normalized) <= 253 and DOMAIN.fullmatch(normalized):
            return normalized
    raise ValueError("expected a DNS domain, such as company.example")


def email(value):
    if isinstance(value, str) and len(value) <= 254:
        local, separator, host = value.rpartition("@")
        if separator and re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_\x60{|}~-]{1,64}", local):
            if not (local.startswith(".") or local.endswith(".") or ".." in local):
                return f"{local.lower()}@{domain(host)}"
    raise ValueError("expected a mailbox address, such as person@company.example")


def research_url(value):
    if isinstance(value, str) and len(value) <= 2048 and all(
        char.isprintable() and not char.isspace() for char in value
    ):
        parsed = urlsplit(value)
        if parsed.scheme == "https" and parsed.hostname and parsed.netloc.isascii() and "@" not in parsed.netloc:
            domain(parsed.hostname)
            _ = parsed.port
            return value
    raise ValueError("expected an absolute HTTPS evidence URL without credentials")


def choice(options):
    def convert(value):
        if isinstance(value, str) and value in options:
            return value
        raise ValueError(f"expected one of: {', '.join(sorted(options))}")

    return convert


def parse_fields(row, converters, required, where, *, csv_input=False):
    object_fields(row, converters.keys(), required, where)
    result = {}
    for key, converter in converters.items():
        value = row.get(key)
        if value is None or (csv_input and value == ""):
            if key in required:
                raise InputError(f"{where}, field {key!r}: value is required")
            continue
        try:
            if csv_input and converter is positive_int and re.fullmatch(r"[1-9][0-9]*", value):
                value = int(value)
            if csv_input and converter is boolean and value in ("true", "false"):
                value = value == "true"
            result[key] = converter(value)
        except (ValueError, OverflowError) as exc:
            raise InputError(f"{where}, field {key!r}: {exc}") from exc
    return result


SCOPED = {"case_id": identifier, "id": identifier}
DECISION = {
    "decision": choice({"allow", "skip", "review"}),
    "account_id": identifier,
    "owner_id": identifier,
    "to_stage": identifier,
}
TABLES = {
    "accounts": (
        SCOPED | {
            "name": text, "domain": domain, "parent_id": identifier, "customer": boolean,
            "crm_owner_id": identifier, "territory_owner_id": identifier, "lifecycle": identifier,
        },
        {"case_id", "id", "name"},
    ),
    "contacts": (
        SCOPED | {"account_id": identifier, "email": email, "unsubscribed": boolean},
        {"case_id", "id", "account_id"},
    ),
    "events": (
        SCOPED | {
            "sequence": positive_int, "delivery_key": identifier, "intent": choice(INTENTS),
            "occurred_at": timestamp, "stream_key": identifier, "account_id": identifier,
            "account_domain": domain, "contact_id": identifier, "task_key": identifier,
            "to_stage": identifier, "enriched_at": timestamp, "research_url": research_url,
            "research_checked": boolean,
        },
        {"case_id", "id", "sequence", "delivery_key", "intent"},
    ),
    "actions": (
        SCOPED | {"event_id": identifier} | DECISION, {"case_id", "id", "event_id", "decision"},
    ),
    "expectations": (
        {"case_id": identifier, "event_id": identifier} | DECISION,
        {"case_id", "event_id", "decision"},
    ),
}


def read_csv(path, allowed, required):
    try:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            rows = csv.reader(stream, strict=True)
            header = next(rows, [])
            if len(set(header)) != len(header):
                raise InputError(f"{path}: duplicate CSV header")
            object_fields(dict.fromkeys(header), allowed, required, f"{path} header")
            for row in rows:
                if not row:
                    continue
                where = f"{path}:{rows.line_num}"
                if len(row) != len(header):
                    raise InputError(f"{where}: expected {len(header)} columns, got {len(row)}")
                yield dict(zip(header, row)), where
    except (OSError, UnicodeError, csv.Error) as exc:
        raise InputError(f"{path}: {exc}") from exc


def load_rows(directory):
    records_path = directory / "records.json"
    csv_paths = [directory / f"{name}.csv" for name in TABLES]
    json_input = records_path.exists()
    if json_input and any(path.exists() for path in csv_paths):
        raise InputError(f"{directory}: choose records.json or the five CSV tables")
    if json_input:
        records = read_json(records_path)
        object_fields(records, TABLES.keys(), TABLES.keys(), records_path)

    for table, (converters, required) in TABLES.items():
        if json_input:
            if not isinstance(records[table], list):
                raise InputError(f"{records_path}.{table}: expected an array")
            rows = (
                (row, f"{records_path}.{table}[{index}]")
                for index, row in enumerate(records[table])
            )
        else:
            rows = read_csv(directory / f"{table}.csv", converters.keys(), required)
        for row, where in rows:
            yield table, parse_fields(row, converters, required, where, csv_input=not json_input), where


def insert(index, key, value, where):
    if key in index:
        raise InputError(f"{where}: duplicate key {key!r}")
    index[key] = value


def validate_decision(value, intent, where, *, expected):
    permitted = {
        "route": {"account_id", "owner_id"},
        "outreach": {"account_id"},
        "task": {"account_id"},
        "transition": {"account_id", "to_stage"},
    }[intent] if value.decision == "allow" else set()
    fields = value.as_dict().keys() - {"decision"}
    if fields - permitted:
        raise InputError(f"{where}: unexpected payload field(s): {', '.join(sorted(fields - permitted))}")
    if expected and permitted - fields:
        missing = ", ".join(sorted(permitted - fields))
        raise InputError(f"{where}: expected allow is missing payload field(s): {missing}")


def validate_accounts(accounts, case_id):
    resolved = set()
    for account in accounts.values():
        trail = set()
        current = account
        while current.id not in resolved:
            if current.id in trail:
                raise InputError(f"case {case_id!r}: parent hierarchy cycle at {current.id!r}")
            trail.add(current.id)
            if current.parent_id is None:
                break
            if current.parent_id not in accounts:
                raise InputError(f"case {case_id!r}: account {current.id!r} has unknown parent {current.parent_id!r}")
            current = accounts[current.parent_id]
        resolved.update(trail)


def build_case(case_id, title, rows):
    accounts = {}
    contacts = {}
    events = {}
    actions = defaultdict(list)
    expectations = {}
    sequences = set()
    action_ids = set()
    delivery_intents = {}

    for row, where in rows["accounts"]:
        account = Account(**row)
        insert(accounts, account.id, account, where)
    validate_accounts(accounts, case_id)

    for row, where in rows["contacts"]:
        contact = Contact(**row)
        if contact.account_id not in accounts:
            raise InputError(f"{where}: unknown account {contact.account_id!r}")
        insert(contacts, contact.id, contact, where)

    intent_fields = {
        "task": {"task_key"},
        "transition": {"to_stage"},
        "outreach": {"contact_id", "enriched_at", "research_url", "research_checked"},
    }
    scoped_fields = set().union(*intent_fields.values())
    for row, where in rows["events"]:
        event = Event(**row)
        unexpected = scoped_fields.intersection(row) - intent_fields.get(event.intent, set())
        if unexpected:
            raise InputError(f"{where}: fields unavailable for {event.intent}: {', '.join(sorted(unexpected))}")
        if event.sequence in sequences:
            raise InputError(f"{where}: duplicate sequence {event.sequence}")
        sequences.add(event.sequence)
        if delivery_intents.setdefault(event.delivery_key, event.intent) != event.intent:
            raise InputError(f"{where}: a delivery key cannot change intent across replays")
        insert(events, event.id, event, where)

    for table in ("actions", "expectations"):
        for row, where in rows[table]:
            event_id = row.pop("event_id")
            if event_id not in events:
                raise InputError(f"{where}: unknown event {event_id!r}")
            action_id = row.pop("id", None)
            value = Decision(**row)
            validate_decision(value, events[event_id].intent, where, expected=table == "expectations")
            if table == "expectations":
                if value.account_id is not None and value.account_id not in accounts:
                    raise InputError(f"{where}: expected account is unknown: {value.account_id!r}")
                insert(expectations, event_id, value, where)
            else:
                if action_id in action_ids:
                    raise InputError(f"{where}: duplicate action ID {action_id!r}")
                action_ids.add(action_id)
                actions[event_id].append(Observation(action_id, value))

    return Case(case_id, title, accounts, contacts,
                tuple(sorted(events.values(), key=lambda event: event.sequence)),
                {key: tuple(value) for key, value in actions.items()}, expectations)


def load_suite(directory: Path):
    manifest_path = directory / "suite.json"
    manifest = read_json(manifest_path)
    fields = {"schema_version", "name", "as_of", "cases"}
    object_fields(manifest, fields, fields, manifest_path)
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise InputError(f"{manifest_path}: schema_version must be 1")
    titles = manifest["cases"]
    if not isinstance(titles, dict) or not titles:
        raise InputError(f"{manifest_path}: cases must map one or more IDs to titles")
    try:
        name = text(manifest["name"])
        as_of = timestamp(manifest["as_of"])
        for case_id, title in titles.items():
            identifier(case_id)
            text(title)
    except ValueError as exc:
        raise InputError(f"{manifest_path}: {exc}") from exc

    by_case = {key: defaultdict(list) for key in titles}
    for table, row, where in load_rows(directory):
        case_id = row.pop("case_id")
        if case_id not in by_case:
            raise InputError(f"{where}: unknown case {case_id!r}")
        by_case[case_id][table].append((row, where))

    return Suite(name, as_of, tuple(
        build_case(case_id, title, by_case[case_id]) for case_id, title in titles.items()
    ))
