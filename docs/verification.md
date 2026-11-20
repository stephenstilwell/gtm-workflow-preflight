# Local verification

The MVP was verified on Windows with CPython 3.12.16 and Microsoft Edge. Commands below run from the repository root.

```sh
python -m unittest discover -s tests -v
python -m gtm_preflight run examples/broken
python -m gtm_preflight run examples/fixed
```

| Check | Observed result |
| --- | --- |
| Standard-library regression tests | 33 passed |
| Broken JSON suite | 3 pass, 13 fail, 0 inconclusive, exit `1` |
| Corrected CSV suite | 16 pass, 0 fail, 0 inconclusive, exit `0` |
| Tutorial routing correction | 4 pass, 12 fail, 0 inconclusive, exit `1` |
| Tutorial missing suppression observation | 15 pass, 0 fail, 1 inconclusive, exit `3` |
| Installed `gtm-preflight` command invoked outside the checkout root | Same exit codes and counts as the source commands |

Both example suites cover 12 cases and 16 events. The broken report records a misdirected account and owner, duplicate webhook and task proposals, and two critical suppression findings. The test suite compares byte-identical repeat reports, verifies output payloads and references, and exercises incomplete inputs, malformed records, unsafe duplicate decisions, and policy overrides.

Both example commands also completed with a Python audit hook that rejects socket and subprocess operations. The installed command was built as a local wheel, then rebuilt offline with a cached setuptools dependency.

The standalone HTML reports were inspected in Edge. The broken report rendered at 320, 390, and 1440 CSS pixels without horizontal overflow. The corrected report rendered at 1440 CSS pixels. The skip link moved keyboard focus to the report, the case links reached focusable case sections, and both critical findings had explicit severity labels. Browser monitoring recorded zero HTTP or HTTPS requests from the reports.

The [GitHub Actions workflow](../.github/workflows/ci.yml) includes Python 3.11 and 3.14 on Linux and Python 3.12 on Windows. A hosted workflow run, full accessibility audit, and production integration behavior remain unverified. See [MVP limits](architecture.md#mvp-limits).
