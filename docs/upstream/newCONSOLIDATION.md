# Nulloy consolidation snapshot

This is the append-only operational handoff for the approved consolidation goal:
retire completed work, archive experiments, document the open PRs, merge PR30 after
review and CI, then stop. It is a snapshot **before** the parent merges PR30. It
does not claim that merge has happened and does not predict a future merge SHA or
future branch/worktree counts.

## Verified inventory and retirements

The verified post-retirement inventory is 12 remote branches, 11 local branches,
and 10 worktrees; the worktrees were clean. The preceding inventory was 33 remote,
34 local, and 33 worktrees, also clean.

The following 18 merged PR branches were retired locally and remotely:

`7, 8, 9, 10, 11, 12, 13, 14, 17, 18, 19, 20, 21, 22, 23, 25, 26, 27`

Six archived experiment branch states were retired: three remote branches and five
local branches/worktrees. Every retired ref's original SHA is in the private,
verified archive. The archive includes restored tracked files and the untracked,
ignored, and evidence packages; the repository bundle and its SHA are recorded in
that archive's restore-verification report. Do not upload private archive paths.

The old `codex/windows-upstream-acceptance` branch combined production from PR15,
PR16, and PR24. It was not the same isolated source as the `9e1b3f0` trash-package
anchor, so this handoff does not claim that all changes came from one isolated
source or that all changes were merged. The old Qt spike, unsafe trash probe,
supervisor/fixture work now combined into one issue, and single-issue-262
documentation are archived with their histories and failures preserved.

## Retained branch anchors

| Branch | Exact SHA | Purpose |
| --- | --- | --- |
| `test/windows-player-inspection` | `4ab11fa4eb11ebd6844fc8290b8d362085da1b6d` | Primary automation work strand with actual packaged-player tooling. |
| `test/windows-uia-timeout-native` | `492e7f04150783818915146ad6232892b1af21c4` | Supporting proof-only timeout/native UIA milestone; not yet ported into the player. |
| `test/windows-trash-build-only` | `9e1b3f060e649a64c698b2a5981dbfca1d741b84` | Frozen package anchor for the Integration-plus-PR15 package. |
| `test/windows-desktop-probe` | `f34c6fd0118a0b2d32f4ff79b127809b7586493e` | Specialized Explorer dependency for PR28; keep open, with no final PASS. |

`qml` remains untouched legacy, not new active work.

## Open PR handoff

- **PR15** (`774894c4eba7b646beafb38313fe0dc73cfb4671`) remains open for the
  product paperbin review. It has no formal native acceptance.
- **PR16** (`791ea82705898652d15866be7b77e3ad5f720976`) remains open for monitor
  restoration gaps: mixed DPI, maximised window, additional skins, and
  minimise/restore.
- **PR24** (`21848c11d6ca4dc1e1c8552285ffc1b84946a029`) remains open for the
  external open burst. It depends on PR29's IPC work and still needs the separate
  opening and large-selection stopgap coverage.
- **PR28** (`f34c6fd0118a0b2d32f4ff79b127809b7586493e`) is a specialized desktop
  probe. It does not fix the product, depends on PR24/PR29, stays open, and is not
  to be closed in this goal.
- **PR29** (`9d7de5108f842269ffa2a99048d69577a123d1ac`) has green component tests,
  but no Explorer PASS.
- **PR30** is open at exact head
  `1e44a4477929cbd1bad7b36c204f8466f8711f69`. Its recorded Windows run
  `34597690721` and Linux run `34597690744` both succeeded. These are PR-branch
  CI results only, not package acceptance or a combined final acceptance.

The integration anchor is
`919468efc32f4d038c96d7276a799794dab2e86e`; `master` remains
`027d81a583b07457a4fa5f18b3e7dcca50b05b58`. All documented product work is based
on Integration, not master. PR15, PR16, and PR24 remain product work; PR28/PR29
remain supporting work with their stated limits.

## Latest native UIA milestone

Workflow `492e7f04150783818915146ad6232892b1af21c4`, run `34600044236`, verified
the Windows-owned Qt responsive native-UIA snapshot. The blocked-worker timeout
was `5.046999999999969` seconds and is classified as **execution-timeout worker
containment only**. Supervisor contracts were 16 PASS with two explicit POSIX
skips; four harmless Qt-fixture contracts passed. Worker/fixture cleanup and
stdout-artifact consistency were verified, with explicit Windows CRLF checkout
hash handling.

This milestone does not prove interruption inside COM. No packaged player, player
start, menu or input action, recycling action, or destructive acceptance was
executed. It is not safe-action ready. Native worker integration into the player
is future work, not completed work.

## Recovery

Use a new destination and never overwrite an existing recovery checkout:

```sh
git clone /private/archive/repository.bundle /private/recovery/nulloy
cd /private/recovery/nulloy
git worktree add /private/recovery/nulloy-worktree <exact-retained-or-retired-sha>
tar --extract --skip-old-files --file /private/archive/evidence.tar \
  --directory /private/recovery/nulloy <selective/path> ...
```

A Git bundle does not contain untracked files. Restore the separately archived
evidence and ignored files when needed; `--skip-old-files` keeps the selective tar
restore from overwriting files already present. Archive paths are private and are
not public upload targets.

The parent may merge PR30 later and may remove its archive branch after making its
own backup. That future state must be recorded separately; this document remains
the pre-merge snapshot and the consolidation goal stops after this structuring
handoff. No new product fix or native acceptance is part of the goal.
