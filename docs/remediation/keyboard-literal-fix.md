# Unmodified arithmetic key semantics on macOS

The live acceptance request sent `desktop_key` with `1 7 * 2 3 =`. The saved
Calculator screenshot and accessibility observation showed `17×23−`, despite the
tool reporting successful event delivery. The report is delivery evidence only;
it does not establish the focused application's resulting value.

## Cause and bounded change

`KEY_CODES["="]` is ANSI virtual key 24, a physical keyboard position. On the
active Turkish layout that position produces `-`. The existing `*` implementation
already used the numeric keypad's Multiply key.

Unmodified arithmetic symbols `+ - * / =` now use their numeric keypad virtual
keys in the macOS `_post_chord` path. Constants are taken from the installed Apple
SDK's HIToolbox `Events.h`: Multiply `0x43`, Plus `0x45`, Divide `0x4B`, Minus
`0x4E`, Equals `0x51`. This preserves real key-down/up events, repeat, and hold
behavior for applications that handle keyboard events rather than text insertion.
It is generic and does not inspect or special-case an application's identity.

Every explicit modifier (Command, Control, Option, Shift) retains the previous
keycode and flags, including `cmd+=` and `cmd++`. Named navigation keys and the
Windows implementation are unchanged. `desktop_type` still uses Unicode text
injection for text; it is a separate existing path. Other printable keys still
use their existing physical keycodes: this patch is not full keyboard-layout
resolution. Applications that distinguish keypad arithmetic from the main row
will now receive keypad events for unmodified arithmetic symbols.

## Verification

No native keyboard/UI events, network calls, installation, or builds were used.
The regression fake records actual `_post_key` CoreGraphics calls, flags, releases,
and down/up order, and emulates the observed Turkish mapping for key 24.

Before the patch, the sequence test observed `17*23-` instead of `17*23=`, and
four other arithmetic/repeat tests failed (5 failures, 20 passes). After the patch:

- `pytest tests/test_desktop_literal_keys.py tests/test_tools_desktop.py tests/test_key_spec.py tests/test_desktop_win32.py -q`: 113 passed.
- Ruff check and format verification for the two changed Python files: passed.
- `mypy --follow-imports=silent src/fusion_cli/tools/desktop.py`: passed.

The new cases cover the acceptance sequence, unmodified arithmetic, all five
symbols with each of the four modifiers, and named navigation/repeat/hold
preservation. The fake verifies event selection; a native acceptance rerun must
separately read the resulting focused application value before claiming `391`.
