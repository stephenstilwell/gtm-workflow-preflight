# Contributing

Use Python 3.11 or newer. Run tests and both suites from the repository root.

```sh
python -m unittest discover -s tests -v
python -m gtm_preflight run examples/broken
python -m gtm_preflight run examples/fixed
```

The broken suite should exit `1` and the fixed suite should exit `0`. Include a regression test for a rule change, especially when it affects missing evidence, suppression, or replay order. Keep timestamps fixed and use fictional IDs and reserved example domains. Use the documented fixture shape so contributors can reproduce an issue from a checkout.

For a rule proposal, explain the commercial decision at risk, the authoritative fields, the safe handling of ambiguous and missing data, and the expected severity. Update the [fixture reference](docs/fixtures.md) if the input or output contract changes. For report changes, regenerate both examples and inspect keyboard navigation and a narrow viewport.

Use the [security policy](SECURITY.md) for vulnerability reports.
