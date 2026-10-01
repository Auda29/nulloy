# Focused independent CI follow-up review

**Reviewed SHA:** `378b1f609a6de38dfeb2619d6d19dfed2e1aff91`  
**Base:** `b86a0f8bff40e3ab4b47ceddaad4603296182649`  
**Checkout:** `/home/hermes/workspace/nulloy-swarm/ci`

## Gate: approve — prior blocking finding resolved

No new meaningful findings or blockers in the four-file focused diff. The stale-CTest false green recorded in `review-ci.md` is fixed: `tools/upstream/run-native.py:62-66` creates a new per-issue `run-*` directory for each invocation rather than reusing CMake/CTest state. Existing run evidence and unrelated user files are preserved. The default output at `:54` is now a newly allocated sibling of the source checkout. Workflow artifact paths at `.github/workflows/upstream-stabilization.yml:51-53` match the new layout.

## Independent execution evidence

All execution used `flock /home/hermes/workspace/nulloy-swarm/build.lock`, with tool timeout 600 seconds and bytecode writing disabled. No skin rebuilds or broad supplemental probes were performed.

- `python3 tools/upstream/test-run-native.py -v`: **6 tests passed**, no skips (0.727 seconds).
- `python3 tools/phase4/test-import-profile.py`: **1 test passed**.
- `python3 tools/release/test-alpha.py`: **2 tests passed**.
- `git diff --check b86a0f8..HEAD`: exit **0**.
- **RED confirmed:** copied the exact new regression test and immutable old runner into an isolated temporary directory; running `RunnerContract.test_reused_output_cannot_execute_deleted_test_registrations` against the old runner failed as expected with `0 != 1`. The same regression passed in the six-test suite on the reviewed SHA.

Additional focused real CMake/Ninja/CTest probes used temporary fixtures outside the checkout:

| Probe | Runner exit | Step exits | JSON passed |
|---|---:|---|---|
| Initial registered passing test | 0 | `[0, 0, 0]` | true |
| Delete registrations, reuse output | 1 | `[0, 0, 8]` | false |
| Deleted registrations, fresh output | 1 | `[0, 0, 8]` | false |
| Actual failing test, fresh output | 1 | `[0, 0, 8]` | false |
| Actual failing test, reused output | 1 | `[0, 0, 8]` | false |
| Actual failing test, default sibling output | 1 | `[0, 0, 8]` | false |

Programmatic assertions verified three distinct `run-*` directories after three invocations sharing the same output; every preexisting run file remained byte-identical and an unrelated user sentinel remained unchanged. Default output was confirmed outside the source, directly under its parent.

The artifact suffix patterns were extracted from the checked-in workflow and applied to real generated evidence under the temporary output root. They matched exactly **1 `results.json`, 9 step logs, and 3 `LastTest.log` files** across those three runs. This validates the changed glob layout locally; it is not a claim of independently executing the hosted upload action.

## Integrity and limitations

Initial and final `git status --short --untracked-files=all` were empty. Final HEAD remained exactly the reviewed SHA; byte comparisons confirmed all four changed checkout files equal their commit blobs. Temporary fixtures were automatically removed. No repository edits, GitHub writes, commits, branch updates, or native skin rebuilds were made.

Parent reports all three hosted CI checks green on `378b1f6`; this report's approval is independently supported by the focused local evidence above, not an independently fetched hosted result. The baseline native skin verification was intentionally not repeated.

Only retained file created by this review: `/home/hermes/workspace/nulloy-swarm/evidence/review-ci-followup.md`.
