# Reliability wave: independent Python and general review

Review date: 2026-11-05. Scope: identity commit `090483c9`, intro validation commit `410a82dc`, and the uncommitted current-fact/source-scope implementation observed during this review. Production source was not edited by the reviewer.

## Verdict

**BLOCK the initial current-fact/source-scope candidate.** No high finding was identified in the scoped identity or cosmetic-introduction changes. The freshness changes need the fixes and regression cases below. This report is an initial snapshot; the parent is already applying corrections, which need a follow-up review.

### High: current-fact detection changes local/history/translation requests into web research

Locations: `engines/effects/current_facts.py:32`, `engines/effects/detect.py:455`.

Executed results all incorrectly returned `web_lookup`:

- `README.md dosyasındaki son sürüm nedir?`
- `Dosyadaki güncel fiyatı oku.`
- `En son konuştuğumuz Python sürümünü hatırlıyor musun?`
- `Şu metni çevir: "What is the latest stable version of Python?"`
- `Güncel release notlarını yerel CHANGELOG.md dosyasından oku.`

The new detector scans temporal/topic keywords across reconstructed clauses, bypasses the explanation guard, and precedes workspace-read detection. Its comment that callers supply unquoted text is not true. Preserve explicit local/history/transformation scope and bind changing-fact intent to the applicable clause before forcing network evidence.

### High: ordinary query URLs remove the source constraint

Location: `engines/effects/detect.py:432`.

Executed `requested_web_urls('Güncel sürümü https://Example.com/Release?x=1&y=2 adresinden araştır.')` returned an empty tuple. The generic action-clause parser splits the question mark inside the URL; the reconstructed positive text no longer contains the original URL. The engine then falls back to accepting any successful web lookup, so an unrelated source satisfies the task. Protect parsed URL tokens while determining clause polarity.

The same extraction also trims the valid closing parenthesis from `https://example.com/a_(b)`, causing an exact legitimate read to fail the source check. Preserve balanced URL punctuation.

### High: continuation inherits research effect but initially lost the required source URLs

Location: initial `engines/agent/execution_policy.py:171`.

Executed policy for `devam et` with a prior real-user request to research a specific Python downloads page produced `required_effect='web_lookup'`, `required_web_urls=()`. An unrelated successful lookup was accepted. Source constraints must use the same effective request/history resolution as the effect. The parent began implementing `effect_request` during the review; this finding must be rechecked against that correction.

### Medium: guessed canonicalization conflates different resources

Location: `engines/agent/research_scope.py:13`.

Executed checks accepted HTTP as proof of an explicitly requested HTTPS page, bare host as proof of `www` host, and `/page` as proof of `/page/`. These can serve different content. Compare the requested origin/path conservatively; admit alternate URLs only with actual redirect provenance. This is source-proof correctness, not an access-control bypass.

## Independent checks

- Ruff passed for all seven changed source modules plus four affected test modules at the initial reviewed snapshot.
- Mypy passed for the seven changed source modules.
- Scoped current-fact/source-contract/identity/narration pytest command exited 0. Log: task workspace `work/reliability-v2/python-review-tests.log`.
- Pure adversarial checks above reproduced the missing cases despite that green suite. Existing green tests do not establish the broader source-scope requirement.
- No raw user configuration, prompt contents, credentials, or real private history were captured.

No repository-wide passing claim is made. The current source-proof contract proves only that a named URL was read; it does not establish that every factual assertion is supported or current.

## Follow-up snapshot

The parent's corrections now pass independent checks for query-URL preservation, balanced parentheses, distinct HTTP/HTTPS/host/path resources, English negative source clauses, genuine-history continuation and the originally listed local/history/quoted-data examples. Ruff and mypy passed on the five corrected source modules. The expanded scoped pytest command exited 0 (`work/reliability-v2/python-review-corrections-tests.log`). Identity and intro validation still have no scoped high finding.

**One high structural issue remains before freshness approval:** current-fact detection still runs on the combined clause text. Executed `Bugün Python öğrendim. Sürüm kavramını açıkla.` returns `web_lookup`, borrowing the temporal word from one sentence and a topic from another. Evaluate changing-fact intent on each affirmative clause. The same-clause conceptual request `Bugün öğrendiğim döviz kuru kavramını açıkla.` is also still forced into web lookup; preserve explicit concept/definition scope. These are concrete local intent regressions, not a requirement to prove perfect natural-language understanding.

## Final scoped approval: `08a57107`

**APPROVE the corrected current-fact/source-contract changes.** All blockers and the resource-normalization warning above were resolved. These earlier sections remain as historical review evidence, not current open findings. No HIGH or CRITICAL issue remains in this reviewed scope.

The final correction uses the same quote-masked affirmative clauses for both current-fact recognition and explicit research commands. Independently executed `"Güncel Python sürümünü araştır" ne demek?` now remains an explanation; a genuine unquoted research command still requires a lookup. Cross-sentence temporal/topic mixing, conceptual explanations, local/history references, query URLs, balanced URL parentheses, distinct scheme/host/path/query resources and continuation/harness-note ownership were rechecked.

Independent final Ruff and mypy checks passed. The corrected seven-module pytest scope exited 0, followed by the two latest current-fact/source-contract test modules exiting 0 after the quoted-command fix. Logs: `work/reliability-v2/python-review-final-scope-tests.log` and `python-review-final-quote-tests.log`. The broader run retained one existing Pydantic warning. Exact reviewed source hashes are in `work/reliability-v2/python-review-approved-source-hashes.json`.

Identity `090483c9` and introduction validation `410a82dc` also remain approved in their finite reviewed scopes. Response-format report commit `ceaa5117` is **excluded** from this approval and requires its own review; the recorded `loop.py` hash includes that separately tracked neighboring code. This approval does not assert perfect language classification, semantic factual verification, live release acceptance, or completion of the overall AI-quality goal.
