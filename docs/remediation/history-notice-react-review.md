# Visible-history notice: React review

**APPROVE for the frontend-only delta in `c0c86c2f`.** No actionable CRITICAL, HIGH or MEDIUM React finding remains in this bounded scope. The concurrent backend credential/privacy correction is explicitly excluded from this verdict.

The truncation/redaction notice has a dedicated `bildirim` message role and a labelled `role=note`, rendered as escaped React text. It is neither a tool step nor an assistant answer and is outside work-history grouping, so completed Summary mode does not hide it. Replacing the reserved history notice preserves unrelated user, assistant and other notice messages. History-response application checks both the owning ProtocolClient and a per-session revision; clear, rewind/history replacement and root changes invalidate the older pending response without replacing the running client or draft owner. No Composer state or panel geometry was modified.

Independent checks passed:
- Four selected existing tests: actual RPC-to-App notice/clear, late-history suppression after clear, history flags, and notice refresh replacement (4 passed, 121 unrelated cases skipped).
- Four independent temporary tests: notice visibility in Normal/Summary/Verbose, escaped markup and unchanged assistant count, plus preserving unrelated roles while replacing/removing the reserved notice. All passed; temporary source removed.
- Canonical hooks lint, application TypeScript and exact frontend-delta whitespace checks.

No full App run, headless-browser run, native UI operation, build or production-source edit was performed by this reviewer. Full-suite, native installation and backend privacy approval remain separate gates.
