# Nulloy consolidation handoff

This records the completed retirements **before the updated PR30 is published and
merged**. It is not a final-product acceptance or a claim that PR30 has already
merged. The integration commit produced by that merge belongs in the subsequent
completion report. Historical register snapshots remain unchanged.

## Scope and verified inventory

| Inventory | Before retirement | After retirement, before PR30 merge |
| --- | ---: | ---: |
| Remote branches | 33 | 12 |
| Local branches | 34 | 11 |
| Worktrees | 33 | 10 |

The post-retirement worktrees were clean before preparing this documentation.
The 18 branch heads for merged PRs **#7–#14, #17–#23 and #25–#27** were removed
locally/remotely together with their 18 worktrees. Their GitHub merge/squash
commits are in integration, their original branch heads had not advanced, and
all original source commits and files were restored from the backup before
removal. Squashed PRs were not judged using `git branch --merged` alone.

Six further historical branch identities were archived, removing three remote
branches, five local branches and five worktrees:

| Archived branch | Reason / retained dependency |
| --- | --- |
| `test/windows-uia-timeout` | Reviewed supervisor files are byte-identical in the retained native branch. |
| `test/windows-uia-timeout-fixture` | Reviewed fixture files are byte-identical in the retained native branch. |
| `test/windows-qt-uia-spike` | Historical harmless default-button/Enter experiment; preserve failures and limits, no further active development. |
| `test/windows-trash-player` | Earlier unsafe/blocked trash automation; archived, not approved for execution or implicitly ported. |
| `fix/upstream-262` | Final documentation file is byte-identical in integration; native media-key/hardware gap remains open. |
| `codex/windows-upstream-acceptance` | Historical combined PR15/16/24 candidate; preserve the full original tree. It is NOT the isolated PR15 package or an accepted final product. |

Original SHAs, non-ancestor commit lists, changed paths, PR associations and
per-worktree file manifests are in the recovery inventory. Non-ancestor commits
can include squash equivalents; this is not a claim that every archived change
was integrated. No Actions artifacts, caches or release assets were deleted.

## Retained working structure

All active PRs target `integration/upstream-issues`, never `master`.

| Branch | Purpose / dependency |
| --- | --- |
| `master` | Protected product baseline, unchanged. |
| `integration/upstream-issues` | Sole product integration target; only PR30 is to merge during this goal. |
| `qml` | Unchanged legacy branch outside stabilization scope. |
| `docs/native-automation-progress` | Temporary PR30 documentation branch; close by reviewed merge and retire only after updated-head backup. |
| `fix/upstream-255` | PR15 trash correction, awaiting final-player matrix. |
| `fix/upstream-236` | PR16 window restoration, awaiting remaining platform cases. |
| `fix/upstream-211` | PR24 external-open bursts, coordinate with PR29 IPC and PR28 Explorer probe. |
| `fix/single-instance-startup` | PR29 IPC product correction; distinct from PR28 test tooling. |
| `test/windows-desktop-probe` | PR28 specialized Explorer test support; retained, not superseded. |
| `test/windows-player-inspection` | **Primary future Windows packaged-player automation work strand.** |
| `test/windows-uia-timeout-native` | **Frozen supporting proof** for a harmless fixture, not a second active product stream. |
| `test/windows-trash-build-only` | **Frozen package identity anchor**, not the combined final product. |

Exact supporting anchors:

- Player inspector: `4ab11fa4eb11ebd6844fc8290b8d362085da1b6d`.
- Native UIA fixture: `492e7f04150783818915146ad6232892b1af21c4`.
- Isolated PR15 package source: `9e1b3f060e649a64c698b2a5981dbfca1d741b84`.
- Explorer probe: `f34c6fd0118a0b2d32f4ff79b127809b7586493e`.
- Pre-merge integration: `919468efc32f4d038c96d7276a799794dab2e86e`.
- Protected master: `027d81a583b07457a4fa5f18b3e7dcca50b05b58`.

No code port is performed here. Moving the proven worker supervision into the
player inspector is explicitly future work; retaining its fixture branch does
not mean that the player inspector already has that process boundary.

## Open product and test PRs

| PR / exact head | Verified scope | Remaining acceptance and dependencies |
| --- | --- | --- |
| [#15](https://github.com/Auda29/nulloy/pull/15), `774894c4eba7b646beafb38313fe0dc73cfb4671` | Trash production correction independently reviewed; five production files verified identical between reviewed source, PR head and isolated package source. Unit/contract evidence is not native matrix acceptance. See [255.md](255.md). | Recycling possible and unavailable; cancel and partial cancel; multi-selection and duplicate playlist rows; removal of current/next track while playing, paused and stopped, using disposable files on the final player. The original macOS case remains open. Depends on safe player automation and exact final package identity. |
| [#16](https://github.com/Auda29/nulloy/pull/16), `791ea82705898652d15866be7b77e3ad5f720976` | Existing geometry/hotplug evidence is retained, not repeated or upgraded. See issue #236 in [issue-register.json](issue-register.json). | Mixed DPI, maximized state, additional skins, minimize/restore after monitor changes. Independent review and acceptance still required. |
| [#24](https://github.com/Auda29/nulloy/pull/24), `21848c11d6ca4dc1e1c8552285ffc1b84946a029` | Burst logic has component coverage; actual Explorer acceptance is incomplete. See issue #211 in [issue-register.json](issue-register.json). | Real Explorer, cold and running player, Enqueue/Play-enqueued settings, pause, two deliberately separate openings, larger selection; assess the 250/1000-ms heuristic. Coordinate PR29 and the PR28 test probe. No drag-and-drop substitute. |
| [#29](https://github.com/Auda29/nulloy/pull/29), `9d7de5108f842269ffa2a99048d69577a123d1ac` | Independent IPC review and Windows Qt5/Qt6 tests, run [34497432559](https://github.com/Auda29/nulloy/actions/runs/34497432559). | No final Explorer PASS. Verify together with the PR24 external-open behavior before treating cold/warm player startup as accepted. |
| [#28](https://github.com/Auda29/nulloy/pull/28), `f34c6fd0118a0b2d32f4ff79b127809b7586493e` | Specialized genuine Explorer/HKCU test tooling, not a product fix. | Keep open: its behavior has not been replaced or fully accepted. Track under PR24/29, including targeted removal of the temporary Explorer registry entry and ownership cleanup. |

The PR30 snapshot originally read back head
`1e44a4477929cbd1bad7b36c204f8466f8711f69` with successful Windows run
[34597690721](https://github.com/Auda29/nulloy/actions/runs/34597690721) and Linux
run [34597690744](https://github.com/Auda29/nulloy/actions/runs/34597690744).
Those are **historical checks on that head**. Require independent review and
**fresh CI for the updated PR30 head** before merging; old green checks cannot
approve this new documentation commit. PR30 CI is not final-package acceptance.

## Native observations and package identity

- Packaged-player no-action observation: inspector `4ab11fa4eb11ebd6844fc8290b8d362085da1b6d`,
  run [34589940677](https://github.com/Auda29/nulloy/actions/runs/34589940677),
  60 contracts, guarded selection/right-click/menu observation and cleanup.
  No menu invocation or trash action.
- Package source `9e1b3f060e649a64c698b2a5981dbfca1d741b84`, build
  [34572047079](https://github.com/Auda29/nulloy/actions/runs/34572047079), Qt6 ZIP
  SHA-256 `5558a6ed786051224f7dcf3228a230fa45c95959f3e363e5b06b48d446ccb833`.
  Integration plus PR15 only, **not the common final package**.
- Harmless native Qt/UIA workflow `492e7f04150783818915146ad6232892b1af21c4`,
  run [34600044236](https://github.com/Auda29/nulloy/actions/runs/34600044236):
  verified responsive snapshot; blocked worker supervision took
  `5.046999999999969` seconds. Classification:
  `execution_timeout_worker_containment_only`. Supervisor: 16 passed / two
  explicit POSIX skips; fixture: four passed. Worker/fixture cleanup, stdout
  consistency and CRLF checkout runtime hashes verified.

This timeout does not prove interruption inside a COM call. No player, menu,
input or recycling action was executed by the harmless fixture probe. It does
not establish destructive-action readiness. Historical failures stay preserved.

## Recovery

Local archive: `/workspace/nulloy-consolidation-2026-09-11/`.
Start with its **RECOVERY.md** and `backup-verified.json`; the latter identifies
all archive files and SHA-256 digests. `branch-classification.json` maps every
original local/remote branch identity to its source SHA, role and archive.

Repository bundle SHA-256:
`8efcbeacc09a375bb8cb7858ce7f75ab60e293615dd6d2f94975cfc0a73c9156`.
It was cloned into an isolated mirror, checked with `git fsck --full`, and every
original branch head resolved. Regular archived files were actually restored
and rehashed; symlink targets were checked as metadata, not followed.

Recover into a **new** directory. Use the bundle for Git history and separate
file archives for ignored/untracked files, packages and external evidence.
Do not reuse archived `.git` pointer files or overwrite active worktrees. Do not
activate archived unsafe probes or symlinks without reviewing their targets.
This is a verified local archive, **not an off-site backup**. Do not publicly
upload its contents blindly; it includes local configuration/diagnostics.

## Completion boundary

Finish only the documentation review, updated-head CI, PR30 integration and
final inventory/report. Backup PR30's updated head before retiring its branch.
Keep master unchanged, do not release, and then stop. The next separate goal is
safe final-player trash acceptance; subsequent Explorer, window and combined
Linux/Qt5/Qt6 acceptance remain open.
