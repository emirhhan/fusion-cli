# Returned-owner approval changes

Explicit permission operations use accepted root/profile/conversation identity after old → other → old. Selecting a permission mode updates the running owner's mode and revokes its stale scopes; forgetting a site removes only that site, preserving unrelated grants. Inferred mutable state differences and history/config/root adoption still require the exact accepted generation.

Approval-only completion adoption accepts the returned owner when current permission revisions match. Thus consent earned after a roundtrip survives the next ordinary or browser-panel job without adopting another chat's history or configuration. The roundtrip classifier-fallback → explicit manual-mode case also clears stale consent.

The reviewer's two failing revocation cases were reproduced; its unchanged A+B control passed. A subsequent ordinary-job consent-continuity control and fallback-roundtrip revocation control also first failed, then passed. All 136 selected ownership, auto-profile, capability, receipt, transcript and document tests passed; Ruff, formatting, mypy and diff checks passed. No provider, native UI, network, package or ORIGINAL changes were made.
