# IntelliCenter 3.12.1 candidate assessment

Assessment date: 2026-10-23. Tracking: homelab-v4u.
This is an unpublished candidate, with no production deployment or new device
validation. The parent prepared it from verified remote main
`fa395ef921521241af7ad9a488701d98007b7a85` in an isolated worktree.

## Scope and review

The candidate combines two independently owned feature branches:

- [PR #197](https://github.com/joyfulhouse/intellicenter/pull/197), source commit
  `180445f7073d72d485e089ab5a3431fa6c2f012c`: physical heater diagnostics report
  known inactivity or explicit uncertainty. They cannot confirm a firing source.
  Body activity, source selection and combustion remain distinct. Entity IDs
  remain stable. See [the evidence limits](heater-activity-attribution.md).
- [PR #196](https://github.com/joyfulhouse/intellicenter/pull/196), source head
  `9fe8298f2ac99e8e3469f5d216bc1ed892bc9b00`: existing read-only restriction
  context includes `field_freshness_unverified` while connected, including after
  partial updates and reconnect. Cached observations do not prove field age.

Parent review returned the heater tests' mock-versus-real-model fixture error;
the owner replaced it with real-model cases and passed the corrected suite.
Integration resolved only adjacent changelog entries; runtime files did not
conflict. No new protocol contract or equipment command is introduced.

The companion library candidate is 0.3.1, based on
`a44f96bfebd9b970517e4bf1b3c2a30a69ee0b76` plus
[PR #114](https://github.com/joyfulhouse/pyintellicenter/pull/114), source commit
`dfa9d5aa4931492b661150b041d8d446915331d5`. It omits rejected payloads from
identified logs/errors and masks password fields in object representations,
preserving raw read values. Its access report distinguishes local permissions,
cloud accounts and physical remotes; it adds no administration API. Parent
review corrected a firmware table that confused integration and panel versions,
and requested formatted-traceback regression coverage; both are resolved.

Patch versions fit these correctness/security/documentation changes. No new
device capability or public protocol API justifies a minor-version release.

## Dependency and release checkpoint

The integration candidate currently retains the exact published
`pyintellicenter==0.3.0` pin consistently in manifest, pyproject and lockfile.
Its runtime changes require no new library API. This candidate therefore does
not yet distribute the companion library's diagnostic security correction.

Before distributing the combined release, obtain explicit authorization for
library merge/publication, verify the published 0.3.1 distribution, update all
three integration dependency declarations together, and rerun required checks
against that published package. A temporary development install or local wheel
does not satisfy this final gate. No unpublished package hashes are fabricated.
Integration merge/publication and production deployment remain separate
authorization checkpoints.

## Evidence limits

The [3.12.0 soak](PRODUCTION_SOAK_3.12.0.md) remains historical evidence only.
This development contacted no equipment and performed no reconnect forcing,
calibration, mode changes, firmware installation, commissioning or deployment.
IC 1.064 / ICWEB 2021-10-19 1.007 is the recorded controller baseline, not a new
access/source-attribution validation.

Calibration's support registry remains empty; broader light actions, firmware
installation and group commissioning retain their guards. Cover assignments,
purifier restrictions, source attribution and field freshness remain explicitly
uncertain. GitHub investigations #183, #185, #187 and the library backlog remain
open where their hardware acceptance criteria are unmet. #188 remains an umbrella.

The original `/data/projects/joyfulhouse` checkouts and historical homelab beads
database were absent on this Omnigent host. Clean GitHub copies were used;
unrelated work in the original checkouts was never accessed or modified. The
original homelab-z462 evidence must be reconciled before claiming its state.
Repository memory identity was available, but no callable recall tool was
advertised; conclusions here use current code, live issues and versioned docs.

## Validation

Feature checks: heater 1,075 tests / 96% coverage; restriction freshness 1,013 /
96%; library access/redaction 1,099 / 92%. All feature lint/format and strict
mypy checks pass; integration Bandit has no medium/high findings.

The combined 3.12.1 candidate passes 1,076 tests with 96% coverage on Python
3.14.8 against published pyintellicenter 0.3.0. Ruff lint/format and strict mypy
pass, and Bandit reports no medium/high findings (one low finding). Feature
PRs #196/#197 pass CI, HACS and Hassfest. Companion library PR #114 passes CI
on Python 3.13 and 3.14. Candidate PR CI and the final published-0.3.1 dependency
gate remain separately recorded in the release PR and beads.
