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

The companion library is published as 0.3.1, based on
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

The user approved library merge/publication. Library PRs #114/#115 are merged;
[v0.3.1](https://github.com/joyfulhouse/pyintellicenter/releases/tag/v0.3.1)
targets `acdb82c62e5941f37b9e076db6df8fb8bbb9cf5d`. Publication workflow
[40011916610](https://github.com/joyfulhouse/pyintellicenter/actions/runs/40011916610)
passed build, TestPyPI and PyPI jobs. Downloaded PyPI distributions match both
their registry SHA-256 digests and the release-workflow artifacts byte for byte.
The wheel's exported version and package metadata both report 0.3.1.

The integration now pins published `pyintellicenter==0.3.1` consistently in
manifest, pyproject and lockfile. Regenerating the lock changed only this package
and its exact requirement; no unrelated dependencies were upgraded. Registry
artifact digests are:

- Wheel: `00e2d0f7f6b49d60dcf6bdccdd8b726aa9b87b998d5e2a65d7e602b9fd5ad85e`
- Source distribution: `8220d3e245eda82c633dc86697ba8107580cf45dd945de781be01ebe951da6db`

Final validation uses a fresh frozen environment resolved from the registry,
with installed library sources compared against the downloaded published wheel.
Integration merge/publication and production deployment still require separate
authorization; the library approval did not authorize either action.

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

The final combined 3.12.1 candidate passes 1,076 tests with 96% coverage on
Python 3.14.8 against the published pyintellicenter 0.3.1 distribution in a fresh
frozen registry environment. All 33 installed library source files match the
verified published wheel, with no editable/direct-URL installation metadata.
Ruff lint/format and strict mypy pass, and Bandit reports no medium/high findings
(one low finding). Earlier 0.3.0 and local-0.3.1-wheel compatibility checks also
passed; final readiness uses the published-package results.

Feature PRs #196/#197 pass CI, HACS and Hassfest. Library release PR #115 passes
CI on Python 3.13 and 3.14; its publication workflow passes all jobs. Updated
integration candidate PR CI is recorded in the release PR and beads. The next
checkpoint is explicit approval of integration merge/publication; production
deployment remains separately unapproved.
