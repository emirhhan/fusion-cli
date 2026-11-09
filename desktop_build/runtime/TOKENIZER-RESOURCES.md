# Offline tokenizer resources

The frozen runtime bundles the six public files referenced by installed official
`tiktoken_ext.openai_public`: GPT-2 `vocab.bpe` and `encoder.json`, plus r50k, p50k,
cl100k and o200k BPE tables. p50k_edit and o200k_harmony share those tables.
`tokenizer_cache.py` records their exact upstream HTTPS origins and SHA256 values.
The focused test checks those pins against the installed official constructors.
The cache filenames are tiktoken's SHA1 of the URL; content authority is SHA256.

The PyInstaller spec stages data only under its own build work directory. It may
read an existing public cache without modifying it, or fetch missing public data
with a 20-second socket timeout, 60-second read deadline checked per chunk, and
8 MiB per-file limit. A local no-redirect opener rejects redirects before
contacting a second origin; no process-global opener is installed. A blocked read may consume its remaining socket timeout
before the deadline check. Invalid cached or downloaded bytes fail the build;
a failed stage is discarded. Repeated builds reuse only a complete, hash-verified
staged cache. No credentials or provider API calls are needed.

Frozen startup selects the bundled cache before importing the CLI/LiteLLM, only
after applying the existing shared dotenv parser for only the two cache keys,
when neither `TIKTOKEN_CACHE_DIR` nor `DATA_GYM_CACHE_DIR` is set. This early
phase does not load unrelated dotenv values or read the stored credential vault.
The normal loader still applies all dotenv values and then stored credentials.
In frozen execution, existing cache keys (including empty values) survive both
phases; source execution keeps its existing generic empty-value behavior. Explicit values,
including empty opt-outs and tiktoken's variable precedence, remain authoritative.
Source execution is unchanged. Runtime health still loads cl100k and remains
strict: missing or corrupt data is not treated as healthy.

This addresses a measured 27373ee2 archive defect: actual frozen health failed
in an empty isolated HOME with network denied, while all six application resource
paths existed. Giving that same binary only the hash-verified cl100k data made
health pass offline. The archive contained no tokenizer data. Existing lifecycle
checks passed independently. New source tests and offline all-encoding checks are
not evidence that a newly rebuilt frozen archive has passed; repeat isolated
runtime-health after the next build. LiteLLM's independent model-cost-map fetch
and its local fallback are outside this fix.
