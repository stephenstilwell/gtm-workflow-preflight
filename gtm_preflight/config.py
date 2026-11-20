from dataclasses import dataclass, field

from .inputs import InputError, boolean, choice, identifier, object_fields, positive_int, read_json


@dataclass(frozen=True)
class PolicyConfig:
    owner_authority: str = "review_on_conflict"
    max_enrichment_age_days: int = 30
    require_research: bool = True
    lifecycle_transitions: dict[str, tuple[str, ...]] = field(default_factory=lambda: {
        "lead": ("qualified",),
        "qualified": ("customer",),
        "customer": ("former_customer",),
        "former_customer": (),
    })


def load_policy(path):
    raw = read_json(path)
    object_fields(raw, set(PolicyConfig.__dataclass_fields__), set(), path)
    if "lifecycle_transitions" in raw:
        raw["lifecycle_transitions"] = transitions(raw["lifecycle_transitions"], path)
    validators = {
        "owner_authority": choice({"review_on_conflict", "crm", "territory"}),
        "max_enrichment_age_days": positive_int,
        "require_research": boolean,
    }
    for key, validate in validators.items():
        if key not in raw:
            continue
        try:
            validate(raw[key])
            if key == "max_enrichment_age_days" and raw[key] > 3650:
                raise ValueError("expected a value between 1 and 3650")
        except ValueError as exc:
            raise InputError(f"{path}, field {key!r}: {exc}") from exc
    return PolicyConfig(**raw)


def transitions(value, path):
    where = f"{path}, field 'lifecycle_transitions'"
    if not isinstance(value, dict) or not value:
        raise InputError(f"{where}: expected a nonempty object of stage IDs to destination arrays")
    result = {}
    for stage, destinations in value.items():
        try:
            identifier(stage)
            if not isinstance(destinations, list):
                raise ValueError("expected an array of destination stage IDs")
            next_stages = tuple(identifier(destination) for destination in destinations)
            if len(set(next_stages)) != len(next_stages):
                raise ValueError("duplicate destination stage")
            if set(next_stages) - value.keys():
                raise ValueError("destination stages must also be declared as keys")
            result[stage] = next_stages
        except ValueError as exc:
            raise InputError(f"{where}, stage {stage!r}: {exc}") from exc
    return result
