# Group editing and equipment commissioning

Group configuration actions remain unavailable. The published
`pyintellicenter==0.3.1` dependency supports local planning and offline readback
comparison; its `apply_group_edit()` raises before network I/O. A locally valid
plan does not establish firmware support or authorize a panel write.

Existing group control continues to use the `CIRCUIT` parent with subtype
`LITSHO` or `CIRCGRP`. Objects whose **type** is `CIRCGRP` are membership rows,
not independent group entities. Entity identity follows the parent object ID;
panel `SNAME` changes are distinct from Home Assistant display-name changes.
Home Assistant display-name customization does not edit panel configuration.

## Requirements for configuration actions

The library's [group configuration evidence matrix](https://github.com/joyfulhouse/pyintellicenter/blob/main/docs/GROUP_CONFIGURATION.md#evidence-collection-handoff)
is the handoff for the outstanding scope of
[pyintellicenter #104](https://github.com/joyfulhouse/pyintellicenter/issues/104).
That issue was closed after a partial planning delivery; the writer, HA actions,
deletion and equipment associations are still pending device evidence.

Before exposing typed create/edit actions in HA, a supported library writer must
establish created parent identity, empty-create/subsequent-membership sequencing,
feature/light target casing, membership replace/patch behavior, firmware-specific
limits and independent authoritative readback. Partial application, timeout and
disconnect must surface uncertainty and reconcile actual configuration instead
of treating acknowledgements as completion or blindly retrying creation.

Integration validation must then cover awaited errors, parent rename with stable
registry IDs, membership-row replacement without row entities, removal and
reconnect subscription reconciliation, and unrelated equipment preservation.
Existing synthetic topology and reconnect tests help protect these paths but do
not establish commissioning semantics on a device. Deletion and associations
need separate typed schemas and actionable dependency errors for each supported
equipment type; an arbitrary object writer is not a substitute.

The current HA dependency remains the published library version. A future
writer needs a compatible published release before HA can depend on its API.
No release, deployment or new live panel mutations are part of this evidence
handoff. Any device collection must have applicable explicit authorization;
see the matrix for the exact captures and provenance needed.

Progress is tracked by the Groups/equipment entry in
[intellicenter #188](https://github.com/joyfulhouse/intellicenter/issues/188).
