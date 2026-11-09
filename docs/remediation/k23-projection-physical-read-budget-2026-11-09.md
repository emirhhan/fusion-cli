# K23 physical I/O budget for optional projection

One explicit ReadBudget now accompanies each optional context projection. It
allows 32 MiB of regular-file content and 20,000 visited entries across production
checkpoint loading, source hashing, artifact hashing, environment executable /
dependency / configuration hashing, and standard installed runner metadata.
The same instance and cooperative validity predicate flow through those calls;
there is no context variable, hidden global budget or reset between phases.

The predicate includes the optional worker deadline/cancellation and the current
live attempt/conversation/plan/step/root owner. Revocation stops subsequent
physical chunks and directory entries rather than merely suppressing delivery.
Caller latency remains bounded by the existing one-worker optional reader.

Regular files are opened without following a final symlink and with nonblocking
flags, validated by fstat, and read in chunks of at most 64 KiB. An oversized file
is rejected from its size before reading content. The total never exceeds the
remaining byte budget, and size/mtime/inode are rechecked before completion.
Partial reads and exhausted/revoked work never produce a complete digest.
Directory enumeration checks the entry limit before requesting the next item;
only the bounded collected list is sorted. Exhaustion makes the entire optional
projection unavailable, with no evidence pins.

Artifact files retain raw SHA-256. Fully read directories retain the legacy
sorted-Path relative-name:size digest. Fully read source/environment content
digests preserve their legacy format. Standard installed runner METADATA or
PKG-INFO is read through the same budget instead of an unbounded metadata.version
read. Nonstandard archive/custom metadata providers are unavailable in bounded
mode. Legacy APIs retain their existing default behavior.

JsonCheckpointStore exposes load_bounded for production optional projection.
Scoped production loads use the same canonical/legacy identities and ownership
checks, and all JSON bytes are budgeted before parsing. The ordinary load API is
unchanged. Custom checkpoint stores without a bounded API keep the existing
single-worker/deadline fallback; their internal I/O cannot be made byte-bounded
by this adapter. Unknown current source hashes cannot compare equal to unknown
recorded hashes to admit evidence.

Limits remain explicit: an already-entered OS metadata/read syscall cannot be
cancelled; at most its admitted chunk may finish after revocation, followed by no
more chunks. This is not a transactional multi-file filesystem snapshot. JSON
parsing and third-party custom-store computation remain subject to worker/caller
deadlines rather than preemptive CPU cancellation. The byte cap covers regular
file content, while directory/path metadata is constrained by entry checks and
cooperative boundaries. Checkpoint, trace and unrelated legacy reads outside
optional projection are not silently changed. Experimental flags remain OFF.

Provider-free controls cover sparse large files, cumulative multi-read limits,
entry exhaustion, legacy raw-file/directory/source/environment hash equality,
production bounded checkpoint load, cross-phase source/artifact sharing,
unknown-hash rejection, live owner revocation and late chunk completion after a
deadline. No provider, GUI, service, settings or credential operation is involved.
