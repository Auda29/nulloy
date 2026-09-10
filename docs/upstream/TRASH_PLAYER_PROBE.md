# Packaged Windows trash probe — PR #15

## Isolated test stand

Branch `test/windows-trash-player` combines integration
`919468efc32f4d038c96d7276a799794dab2e86e` with PR #15 at
`774894c4eba7b646beafb38313fe0dc73cfb4671`. It does not include the
Explorer/IPC branches PR #24/#28/#29 or window PR #16.

The trash production files match the independently reviewed source at
`212ba22b8df9d9ee3d8e8a8c7f0b8cdce00f3fc0`; this equality does not turn
old Windows results into acceptance of a newly packaged executable.
The shared Linux contract has been rebuilt and passed on this combined
stand. It is not the native player acceptance below.

## Initial native scope

The opt-in `trash-player-probe` job follows the ordinary Qt5/Qt6 Windows
build matrix and consumes its Qt6 portable ZIP from the same workflow run.
The probe checkout and requested source identity both use `github.sha`,
not the PR head. ZIP, EXE and manifest identities must be recorded by the
probe and matched to the package. No release is published.

Only the internal `test/windows-trash-player` PR branch can run this job.
It uses a disposable GitHub-hosted Windows Server 2022 desktop, not a user
machine. The package is launched directly: this is trash acceptance, not
an Explorer multi-open test. Generated WAV files are the only deletion
candidates. No recycle-bin settings or Explorer associations are changed.

The first probe is intended to check these stopped-player scenarios:

| Scenario | Required evidence |
| --- | --- |
| Ordinary confirmation cancelled | Original bytes preserved and corresponding playlist rows retained |
| Successful recycle | Original absent, matching original-path recycle metadata and identical recycle payload, correct remaining playlist rows |
| Partial batch cancelled | First confirmed file recycled, second and later files byte-identical and still listed |

These are acceptance requirements, not claims of a completed Windows run.
No native PASS is recorded by this document. The first probe implementation
and independent safety review must be completed before relying on its results.

## Safety and verdicts

- Only the directly launched, identity-checked process and its own windows may
  be driven or cleaned up. No broad process killing or recycle-bin emptying.
- Unexpected dialogs must not receive a positive response. In particular,
  permanent-delete fallback must never be accepted by this initial probe.
- A missing usable recycle bin is a blocker, not a reason to allow deletion or
  to change a volume's settings. Source disappearance alone is not recycling.
- Each scenario needs visible UI and filesystem evidence, with primary errors
  kept separate from cleanup errors. Cleanup failure prevents acceptance.
- `PASS`/0, `FAIL`/1 and `BLOCKED`/2 must remain distinct. Non-Windows execution
  may test contracts but cannot produce native acceptance.
- The explicit headless-audio mode is a no-device fallback, not audio-output
  acceptance. Small generated recycled fixtures may remain for inspection;
  their paths/identities must be recorded, not mixed with user files.

## Still open after the initial probe

Even a passing first run does not cover recycling unavailable on the final
player, duplicate playlist rows, or current/next-track deletion during
Play/Pause/Stop. Those require additional native scenarios. The original
macOS case, final combined package acceptance, and release decision stay open.
PR #15 must not be merged merely because this initial subset passes.
