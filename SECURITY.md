# Security policy

The supported version for security reports is the current `main` branch.

Use **Security → Report a vulnerability** in GitHub when private reporting is enabled. Otherwise, reach Stephen Stilwell through [Useful in Practice](https://stephenstilwell.com) to arrange a private report. Include the version, a synthetic fixture or minimal steps to reproduce, and the impact.

The CLI reads local JSON and CSV as data. Policy settings are declarative JSON. Evaluation holds proposed decisions in memory and writes two local report files. Reports can expose fixture identifiers and decisions, so use synthetic data in shared examples, issues, and CI artifacts.
