# GTM Workflow Preflight

Use Python 3.11+ and keep the runtime dependency-free. Run commands from the repository root.

- Keep fixture and policy inputs declarative. The runner evaluates proposed decisions in memory.
- Use fictional records and reserved domains in examples, tests, and reported issues.
- Preserve deterministic timestamps, event ordering, rule identifiers, and report fields.
- Update the fixture contract and include regression coverage when changing semantics.
- Run `python -m unittest discover -s tests -v` and exercise both example suites before submitting.
