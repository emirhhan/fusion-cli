# Public visible history general review

Final reviewed snapshot: exact `2aee489a..552ead7d`, including icon-only list projection (`029a79f5`), durable public history (`b7b5bc95`), common bounded projection and visible notice (`c0c86c2f`), credential suppression (`f9c1a6b4`) and final curl arity correction (`552ead7d`). Verdict: **APPROVE — all findings tracked by this general review are closed, zero open findings.** Independent Python/security specialist gates remain separately owned. Previously approved UI geometry at `59a755d4` is unchanged by the final backend corrections.

## Final closeout at 552ead7d

Reviewed the exact two-file final diff and current scanner callers. The operand-consuming curl short-option set now excludes no-operand I/N and includes actual operand options; authentication options are checked before the operand stop. Thus head/no-buffer and other documented non-operand clusters no longer bypass u/U recognition. Genuine attached values such as output filenames and user-agent strings still terminate option scanning appropriately and retain ordinary public history. Tests exercise all listed non-operand prefixes followed by both server/proxy authentication, plus explicit Is/Ns clusters and benign -o/-A controls.

Independent final proof repeated the actual ProtocolSink → VisibleToolRecorder → temporary TranscriptStore → load_visible_transcript path for the six formerly relevant clusters Iu, Nu, IU, NU, Isu and Nsu. Opaque credential, shadow-argument, output-trace and diff sentinels were absent from disk and all six replayed rows; diffs were null and original event arguments remained unchanged. No command was executed and no network request was made. All 22 focused visible-transcript/icon tests passed with exit 0 under the original project venv. Combined whitespace checks passed at exact HEAD `552ead7df240c3f5505a57bbcae56a7631ed086f`.

The earlier global-limit notice is visibly rendered through the actual history decoder/session/Conversation path as a non-tool React-text note. It cannot approve a tool or inflate operation counts, and clear/root/client fences prevent late startup restoration into replaced history. Imported, missing-file and legacy RAM paths share the finite projection rather than bypassing bounds. Recorder ownership, durable private-store scoping, session/version validation and exclusion from model transcript loading remain intact. Credential-source suppression happens before append and is reapplied on replay; it does not mutate executable/model tool inputs. Icon stripping remains limited to the list-model/UI projection, preserving native dock data and legitimate ordinary text. This is a bounded source/security contract approval, not a claim that arbitrary secret encodings can be identified or that live native/full-App acceptance was independently repeated.

No additional actionable issue was established. Only this review report was edited; concurrent reports/source owned by other workers were preserved. No actual UI/helper/private chat/secret, model, network, uv, broad suite, build or installation operation was performed.

## Final Review Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 0 | pass |
| LOW | 0 | pass |

Verdict: APPROVE at `552ead7d` — the notice P2, shell-punctuation P1 and curl no-operand-cluster P1 below are resolved. Historical failed-candidate reviews are retained for traceability.

---

# Historical f9c1a6b4 review (cluster finding resolved by 552ead7d)

Latest reviewed snapshot: exact `2aee489a..f9c1a6b4`. Verdict: **WARNING — one HIGH/P1 curl-cluster suppression defect remains.** The original global-notice P2 and the c0 shell-punctuation credential-file P1 are resolved. Independent Python/security reviews remain separately owned.

## HIGH / P1 — no-operand curl flags prematurely stop credential scanning

File: `src/fusion_cli/appserver/visible_transcript.py:102`, consumed at lines 185–189.

The set `_CURL_VALUE_OPTIONS = frozenset("AbcCdDeEFHIKmNoPQrTtwxXyYz")` includes `I` and `N`. These are curl's no-operand `--head` and `--no-buffer` flags, confirmed from the installed curl's local `--help all` output without making a network request. The cluster scanner stops at any member of that set, so `curl -Iu user:OPAQUE_REVIEW_SENTINEL https://example.test` and `curl -Nu ...` never inspect their following `u` authentication option. The same failure occurs with `-Isu` and `-Nsu`; the control `-su` is correctly concealed.

Independent proof used the actual ProtocolSink → VisibleToolRecorder → temporary TranscriptStore → load_visible_transcript path with two synthetic ToolExecuted records (`-Iu`, `-Nu`), an opaque credential sentinel and an opaque trace sentinel. Both sentinels remained in the JSONL, and both records replayed the credential (`credential_on_disk=True`, `trace_on_disk=True`, `replayed_leaking_rows=2`). No curl request or shell command was executed. Generic redaction does not identify the opaque operand or trace, so the incorrect option table bypasses the only suppression guard for these valid clusters.

Fix: remove the no-operand flags from the operand-consuming option set, and add actual recorder/disk/replay regressions for `-Iu`/`-Nu` (including proxy-user variants), while retaining the benign attached-output and user-agent controls. This is a narrow parser correction, with no permission or runtime tool behavior change.

## f9 corrective scope otherwise reviewed

The exact two-file f9 diff closes the prior punctuation case with bounded shell lexing and raw credential-file detection, without expanding/evaluating commands. Credential-bearing commands conceal all projected argument values, output and diff before append; the original event/model arguments remain intact. Malformed/over-budget commands and excessive nested-shell inspection fail closed. Recognized environment, nested shell, curl authentication/config/netrc and sensitive-file sources retain visible suppression metadata. Ordinary public command/file previews and diffs remain supported. The existing owner/store/generation fences, common fallback/import output bounds, standalone non-tool history notice and previously approved geometry source are unchanged.

Independent f9 validation: 22 visible-transcript/icon tests passed; combined range whitespace checks passed. The new tests cover the formerly leaking punctuation forms, curl clusters/traces, environment/config sources, original-event immutability, bounded inspection and benign controls. No broad/backend/full-App/browser/native build, actual user UI/helper/private chat, real credential, network, model or uv operation was performed. Only this report was edited.

## Current Review Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0 | pass |
| HIGH | 1 | warn |
| MEDIUM | 0 | pass |
| LOW | 0 | pass |

Verdict: WARNING at `f9c1a6b4` — resolve the proven curl no-operand cluster gap before packaging.

---

# Historical c0c86c2f review (punctuation finding resolved by f9c1a6b4)

Final reviewed snapshot: exact `2aee489a..c0c86c2f`, including icon projection, durable tool history and its corrective UI/backend projection. Verdict: **WARNING — one HIGH/P1 credential suppression gap remains.** The original global-limit-notice P2 is closed. Python/security specialist verdicts remain independently owned.

## HIGH / P1 — shell punctuation bypasses credential-file output suppression

File: `src/fusion_cli/appserver/visible_transcript.py:142` (also line 145).

The credential-target detector uses `parts = shlex.split(item)` and then `any(_credential_path(part) for part in parts)`. Ordinary shell syntax remains attached to the path: `cat<.env` becomes one token, `cat <.env` contains `<.env`, and `cat .env; echo done` contains `.env;`. None matches the known credential basename `.env`. Therefore `sensitive_target` is false, and the new durable record retains the file output/diff instead of suppressing it.

Independent proof used no executed command, real file content or credential: injected three synthetic successful run_shell ToolExecuted events through the actual ProtocolSink → VisibleToolRecorder → temporary TranscriptStore → durable loader path, with the three command strings above and an opaque sentinel output. The temporary JSONL contained the sentinel and all three replayed rows retained it (`disk_contains_sentinel=True`, `replayed_rows_with_sentinel=3`). The control `cat .env` correctly suppressed the same output. Generic redaction cannot catch an opaque credential without a matching secret label/pattern, and the file-name guard never recognizes these punctuation-attached operands. This persists sensitive content that the corrective commit explicitly intends to exclude.

Fix: recognize known credential operands across shell separators/redirections before persistence, conservatively suppressing uncertain sensitive command content. Add recorder/disk/replay RED regressions for these syntax forms and retain normal public-command controls. No tool execution or permission change is required.

## Corrective contracts closed at c0c86c2f

- Both startup/reload history consumers pass the strict global truncation flag to historyMessages. A standalone `bildirim` message renders as a visible React-text `role=note`, with no tool step, permission button or action callback. Its fixed text discloses omitted history and sensitive-detail suppression. It does not change operation counts, model context or authority. Refresh replaces the existing history notice, and clear/root/replacement versions reject late startup history; client identity fences reject replaced clients.
- Imported and RAM fallback views now use the common bounded projection: last 300 input messages, bounded public event fields, 16k text rows, removal of oversized optional findings, 300-row/1M-character output window and explicit global truncation. The route captures store/generation and verifies both after its threaded read for imported and durable views.
- Non-string event discriminators are skipped before set membership. Credential-file read/write content and diffs are suppressed for recognized targets before disk; curl quoted, attached and equals authentication operands are masked before clipping. These improvements do not close the shell-punctuation finding above.
- Prior icon-only projection, recorder owner fences, durable version/session/tombstone/rewind guards, ignored private/token/legacy event classes and separate model transcript behavior remain intact. Geometry source was already reviewed separately at 59a755d4 and was not expanded here.

Independent corrective validation: 18 visible-transcript/icon tests and 20 frontend history/store tests passed; combined range whitespace checks passed. Read the actual RPC-to-note integration regression and late-clear/history refresh tests. No full App/browser/native build, actual UI/helper, shell command execution, private chat, real secret, network, model or uv operation was performed. Only this report was edited for the review.

## Current Review Summary

| Severity | Count | Status |
|----------|-------|--------|
| CRITICAL | 0 | pass |
| HIGH | 1 | warn |
| MEDIUM | 0 | pass |
| LOW | 0 | pass |

Verdict: WARNING at `c0c86c2f` — resolve the proven credential-file shell-syntax bypass before packaging.

---

# Initial b7b5bc95 review (superseded)

Snapshot: exact `2aee489a..b7b5bc95` (`029a79f5` and `b7b5bc95`). Verdict: **WARNING — one MEDIUM/P2 integration finding.** No additional CRITICAL/HIGH issue established in this bounded general review. The independent Python/security reviews have separate scopes and dispositions.

## MEDIUM / P2 — global history limits are invisible in the actual UI

File: `src/fusion_cli/appserver/session.py:1106`; consumer `app/src/sessions/useSessions.ts:272`.

When the durable loader drops rows for its 300-row/total-character/read-tail limits, or encounters VisibleHistoryLimited, it sets `VisibleTranscript.truncated`. The route returns only a top-level `gecmis_kirpildi: true` marker alongside the remaining tool/text rows. Existing startup/reload consumers pass only `result.mesajlar` to `historyMessages`; neither that decoder nor any other app source consumes `gecmis_kirpildi` or `history_truncated` (repository search confirmed no UI consumer). The durable limit marker itself never becomes a visible row. Consequently, a long turn is shown after reopen as a shorter, apparently complete list, without telling the user earlier work was omitted. An ellipsis on a clipped individual output does not disclose omitted tool records.

Trigger: exceed the per-turn captured-record cap, or load a conversation whose bounded tail/300-row window excludes older records. Backend tests establish `history.truncated` and bounded rows but do not establish a displayed notice. This conflicts with the requested honest/visible history-limit boundary and the user's expectation of retained work details.

Fix: expose a bounded non-tool public notice through a supported UI path, or consume the flag in an explicit history banner. Do not invent a ToolExecuted event or add a fake operation to panel counts. Add an integration regression from a truncated history response to an actual visible notice, while preserving ordinary complete-history rendering and the tool count.

## Other reviewed contracts

- Icon projection removes only the known `icon` property from fresh list-result row copies. Native dock consumers retain original icons/metadata; ordinary title/value text, inspect payloads and structured-tool behavior remain unchanged. No blanket base64 stripping was added.
- Recorder input is the serialized public event envelope. It allowlists ToolExecuted fields/scalar arguments, redacts before clipping, rejects child/foreign session/foreign attempt records, bounds identity bookkeeping, and records only while the captured turn/store/generation is active. Late owners after cancellation, clear, import or rebind cannot append their tool records into a different visible context.
- Durable UI records use a versioned event type in the existing private JSONL store and are ignored by model transcript loading. The UI loader validates identity/version/outcome, scopes project/conversation, handles tombstones and bounded rewind uncertainty, ignores tokens/private/legacy raw tool events, and preserves append order plus event-ID replacement semantics. This review does not reconstruct omitted legacy tools.
- Existing protocol projection, frontend React text rendering and permission handling are unchanged. No new tool action, authority-bearing payload or automatic replay execution was added. The independent Python review separately identified a fallback/import-bounds issue; that is not duplicated as a new finding here and must also be included in the owner's correction batch.

Independent validation: 13 focused visible-transcript/icon-projection tests passed together under the existing project venv with worktree PYTHONPATH/MYPYPATH; combined source/test whitespace checks passed. No actual model/network/native helper/UI, real secret/private chat read, `uv`, build, installation, full App or broad backend-suite run was performed. Other workers' geometry/UI changes were excluded and untouched.

## Review Summary

| Severity | New findings | Status |
|----------|--------------|--------|
| CRITICAL | 0 | pass |
| HIGH | 0 | pass |
| MEDIUM | 1 | info |
| LOW | 0 | pass |

Verdict: WARNING — correct the visible global-limit notice and complete the separately owned Python/security gates before packaging.
