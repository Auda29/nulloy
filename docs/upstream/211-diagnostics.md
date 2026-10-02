# Optional player diagnostics for #211 acceptance

The package can write additional local JSONL diagnostics when the existing
`NULLOY_STARTUP_TRACE_DIR` environment variable names an existing directory.
Tracing is off when that variable is absent or empty. No directory is created,
no data is uploaded, and an unavailable output directory does not prevent opening
or playing files. Playlist path enumeration is skipped when tracing is disabled.

The diagnostics include full local media paths and CLI arguments. Enable them
only intentionally, use a private directory, and review logs before sharing.

Events emitted by the real `NPlayer::readMessage` handler:

- `player-message`: the original message and `rows_before` captured at handler
  entry. This record is emitted after the message has been processed.
- `player-open-policy`: enqueue/play-enqueued settings and the actual bounded
  grouping decision, evaluated exactly once as before. The record is emitted
  after the playlist action.
- `player-open-result`: ordered playlist paths and immediate playing-row snapshot,
  emitted after the playlist action.

Empty, invalid, and recognized command messages emit one `player-message` record
after their normal handling; they do not emit open-policy or open-result records.
The result snapshot is intentionally immediate pending-media state, not settled
playback state.

The `time_msec` wall-clock field describes when each record was emitted. It is not
an exact entry or receipt timestamp; in particular, `player-message`'s fields
capture entry state while its record is written later. Synchronous post-processing
tracing still adds file-I/O overhead to later message deliveries. The harness tests
normal behavior with tracing enabled in the same package; it does not claim zero
overhead.

The last snapshot is not a settled playback assertion: asynchronous media loading
may still leave playing_row=-1. Acceptance must separately observe the current
media and playback state/position in the native UI. The IPC observer instead uses
conservative same-controller monotonic brackets around process launch and
observation of the completed handler records. Opt-in logging does not promise
exact threshold timing or prove an arbitrary Explorer selection transaction.
Normal playback/grouping/CLI semantics remain unchanged.

`tests/upstream/211` tests the enabled, disabled and unavailable-directory paths,
expected event order/fields, normal playlist/playback behavior, and cessation of
writes after disabling tracing. The enabled test fails against the uninstrumented
candidate and passes with instrumentation. Native candidate acceptance still
requires a new package whose source commit and hashes include this change.
