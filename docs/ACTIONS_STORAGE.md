# Windows package upload policy

This policy changes package retention, not package construction or testing.

- Push and pull-request builds still run both Windows Qt5 and Qt6 jobs, all CTests,
  package verification, format checks, startup/registry recovery and skin checks.
- Ordinary push/PR runs do not retain downloadable package ZIPs.
- Manual and reusable calls must explicitly set the boolean `upload_packages` to
  `true` to retain package ZIPs and their checksum files for **3 days**.
- The alpha-release caller opts in explicitly. Its publish job still downloads
  the Qt6 package and evidence and publishes validated release assets. Existing
  release assets and tags are untouched; published assets are not subject to this
  Actions-artifact retention setting.
- Test evidence is still uploaded with `always()`, including failed runs. Its
  existing repository-default retention and all paths are unchanged. This patch
  does not shorten the lifetime of reports, logs or screenshots.

## Acceptance and reference packages

The three-day ZIP is a temporary transfer artifact, not a durable acceptance
archive. If a manual build will become an acceptance/reference baseline, download
and verify its ZIP/checksum and associated evidence before expiry and retain them
in the approved durable evidence location. Record the run, actual packaged source
commit and hashes; a PR head can differ from the synthetic source used to build.
Do not rely on rerunning a historical job to reproduce identical package bytes.

The alpha-release workflow consumes new artifacts within its own run. A retry of
only its publish job after expiry cannot download an expired package; use the
established release recovery procedure and verified retained bytes rather than
silently substituting another build.

## Branch boundaries

This change targets `master` only. The existing integration policy already has
package opt-in and three-day package retention; it is not reimplemented or changed
here. Its Windows evidence has seven-day retention, unlike master's preserved
default. Linux evidence retention is intentionally left unchanged as well.

Active fix/test branches retain their own workflow copies until a separately
reviewed policy-only update is applied. In particular the Explorer probe consumes
a same-run package and needs that dependency preserved explicitly. The player
inspection workflow consumes the fixed package from run `34572047079`; do not
remove that reference package or blindly copy a default-off upload condition over
an acceptance workflow. No product/test branches are merged by this change.

## Configuration validation

```sh
python -m pip install PyYAML==6.0.2
python tools/ci/test-artifact-policy.py
python tools/release/test-alpha.py
python tools/phase4/test-import-profile.py
```

The workflow runs the policy contract in a separate lightweight job. These are
configuration/release-helper tests, not a native Windows or release acceptance
claim. Existing Windows jobs still supply the native build/test checks.

Workflow changes do not delete old artifacts, change cache budgets, or establish
immediate billing/quota availability. Historical artifact deletion requires a
separate, explicitly approved artifact-ID list and before/after verification.
