# Visible activity history — final independent security verdict

Final reviewed production snapshot: `552ead7df240c3f5505a57bbcae56a7631ed086f`.

**Security APPROVE within the bounded ordinary credential-source and authentication-syntax scope.** This records the independent security worker final verdict; it does not claim that arbitrary opaque strings can universally be classified as secrets. No candidate recorder was installed before the security gate closed. All probes used synthetic values.

Independent checks repeated the actual `ProtocolSink → VisibleToolRecorder → temporary JSONL → load_visible_transcript` path for 33 sensitive records: curl user/proxy clusters (including Iu, Nu, IU, NU, Isu and Nsu), shell punctuation and .env reads, UTF-8/malformed quoting, trace output, nested shell/environment sources, netrc/curlrc/config, URL userinfo/authentication headers and known credential files. No opaque marker remained on disk or in restored UI rows; hidden diffs were None and original event arguments were unchanged. Five benign npm/ls/curl output/user-agent controls retained command, output and diff. Malformed list/dict/null/numeric event discriminators skipped safely. The visible-history/icon focused suites passed 22 tests.

The final short-option operand set was checked against the installed curl help. Known value-taking options are `ACDEFHKPQTUXYbcdehmortuwxyz`; authentication detection runs before the operand stop rule. Non-operand I and N no longer suppress scanning of following u/U authentication flags.

Earlier candidate findings (b7, c0 and f9) were corrected before packaging: basic credentials, punctuation/combined flags/traces, malformed event types and the final curl arity error. Bounds and visible notices received separate Python/general and React/TypeScript approvals. Model-context history remains separate from recorded UI rows. Main turn/store/generation fences, private-event exclusion and existing native Dock icon delivery remain intact in this reviewed scope.

No real credentials, private conversations, network/model calls, native helper/UI interaction, build or installation were used by the security reviewer. Native close/reopen acceptance and the complete parent suites are separate evidence.
