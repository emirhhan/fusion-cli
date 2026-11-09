# K21 owned native desktop references

Native background inspection now presents 25-character opaque `dref_` handles
instead of the full base64 AX references. The table belongs to `DesktopView`;
there is no global cache or persisted setting. The original native response is
not modified. Legacy full refs remain accepted and undergo the same native
validation as before.

Each handle is bound to a fresh `ToolContext` owner token, job/session scope,
observation turn, desktop-turn identity, PID and window ID. A
`dataclasses.replace` child gets its own owner token even when desktop state and
job scope are shared. PID/window are the application binding available in the
existing native inspect protocol; that response contains no separate bundle ID.
Fresh policy target resolution still checks the actual application. Native
fingerprint, path, identity, uniqueness and tree-completeness checks are unchanged.

The table allows at most 2,000 entries and 4,000,000 UTF-8 reference bytes, with
a 300-second monotonic lifetime. Reinspection revokes the previous handles for
that owner/PID/window, including failed inspections. Turn start/finish clears
the table. Capacity failure returns an explicit reinspection error rather than
falling back to an unresolved alias. Late inspect results from another turn
are rejected. Full refs are restored before approval, risk classification,
native recovery receipts and native dispatch. Hook and approval argument
replacements are resolved again, and leases are checked after approval waits.

Each inspection receives a per-owner/PID/window ticket before native dispatch.
Only the latest ticket can publish handles, checked atomically with registration;
an older request completing after a newer one cannot revoke the newer handles.
Outstanding tickets also have the 300-second lifetime and 2,000-item bound, and
turn reset clears them. Reverse-completion concurrency has a failing-before,
passing-after regression.

An actual run of the production observation boundary against synthetic native
outputs measured 11 inspections with 37 controls each:

| Measurement | Full refs | Owned handles |
| --- | ---: | ---: |
| Model-facing JSON characters | 148,243 | 44,858 |
| Reference characters | 113,560 | 10,175 |

This is a 69.74% output-character reduction and 91.04% reference-character
reduction on the owned local fixture. It is not a live GUI, provider-token,
latency or frozen-package measurement. Reproduce with
`PYTHONPATH=src:. python -m pytest tests/test_desktop_ref_handles.py -k production_boundary_fixture_measurement -q -s`.

Acceptance covers exact original refs at the native boundary, destructive-label
risk parity, unknown/foreign/child/session/turn/window/PID aliases, reinspection,
bounded lifetime/count/bytes, native stale failure preservation, late observations,
real agent execution, hook replacement, approval replacement and revocation
during approval. No flags or persisted settings are changed. Real GUI/native
package acceptance remains a separate release requirement.
