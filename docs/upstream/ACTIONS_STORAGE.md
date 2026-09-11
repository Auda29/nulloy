# Actions storage policy

## Windows CI

Builds, package verification, Qt5/Qt6 coverage and PR checks remain enabled.
The Windows matrix has two included jobs, not a four-job Cartesian product.
Storage savings must not come from silently removing acceptance checks.

- Normal pushes and pull requests: build and verify packages on the runner,
  but do not upload the package ZIPs.
- Manual runs: `upload_packages` defaults to `false`. Enable it only when a
  planned acceptance run needs downloadable packages. They expire after 3 days.
- Reusable calls: the same explicit opt-in applies. The existing alpha-release
  caller sets it to `true` so its asset downloads continue to work. This policy
  does not create a tag or release; existing tag-driven release behavior remains.
- Windows test evidence is uploaded even on failure, with 7-day retention.
  These are diagnostic directories, not a guaranteed fixed-size allowance.
- Copy required packages, checksums, build/probe identities and acceptance reports
  into verified durable storage before they expire. Actions artifacts are not
  the long-term acceptance archive.

## Boundaries and rollout

Retention changes apply to newly uploaded artifacts, not existing artifacts.
This change alone does not reduce the existing stored inventory or guarantee
that the account fits its quota. Existing branch-specific workflow copies may
still upload packages using their old policy. Before another expensive run,
check the actual workflow revision and apply the reviewed storage policy to that
working branch. Do not blind-merge combined product/test branches to propagate it.

No artifact, cache, run or release asset is deleted by this change. Cleanup is a
separate operation requiring a current complete inventory, protected evidence
anchors and an approved fixed artifact-ID list. Do not delete whole runs or
historical evidence merely because they are old. Check artifact bytes and cache
bytes separately; do not infer a billed amount from their sum.

## Local regression check

Use an environment with PyYAML 6.x installed:

```sh
python -B tools/upstream/test-artifact-policy.py
python -B tools/upstream/test-issue-register.py
python -B tools/release/test-alpha.py
```

The policy tests read the real workflow YAML. They cover default-off package
uploads, explicit release opt-in, bounded retention, preserved PR triggers and
serial Qt5/Qt6 verification. They are local configuration contracts, not a claim
that a new native Windows build or release has been executed.
