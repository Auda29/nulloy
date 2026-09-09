# Independent CI infrastructure review

**Reviewed SHA:** `b86a0f8bff40e3ab4b47ceddaad4603296182649`  
**Repository:** `/home/hermes/workspace/nulloy-swarm/ci`  
**Scope:** the four added files versus the commit's parent. Read-only review; no repository edits, GitHub writes, branch updates, or fixes.

## Gate: changes requested — one confirmed Medium blocking finding

No High/Critical findings. The blocking finding is a reproducible false green in the documented reusable local runner; it does **not** imply that the fresh GitHub Actions run failed.

### Medium — reused build directories can execute deleted tests and report success

**Location:** `tools/upstream/run-native.py:62-65`, with the erroneous success recorded at `:82-85`. The repeated fixed-output usage is documented in `docs/UPSTREAM_STABILIZATION.md:38-40`.

The runner reconfigures an existing per-issue build without clearing previous CTest registration. If a harness previously enabled testing and registered a passing test, then its current CMake configuration no longer enables testing/registers tests, CMake leaves the old `CTestTestfile.cmake` behind. CTest runs that obsolete test; `--no-tests=error` does not help because CTest sees the stale registration. The current source has no tests but `results.json` reports `passed: true`.

**Actually reproduced:**

1. Create an isolated temporary source with `tests/upstream/255/CMakeLists.txt`:
   ```cmake
   cmake_minimum_required(VERSION 3.24)
   project(IndependentReview NONE)
   enable_testing()
   add_test(NAME pass COMMAND ${CMAKE_COMMAND} -E true)
   ```
2. Run the immutable runner with `--source "$S" --issue 255 --output "$B"`: exit **0**, CTest **1/1 passed**.
3. Replace only the temporary fixture's CMake file with its first two lines, removing all test registration.
4. Repeat the exact same runner command and output directory: exit **0**, CTest still **1/1 passed**, step exit codes `[0, 0, 0]`, JSON `passed: true`.
5. Run that same no-registration source with a new output directory: runner exit **1**, CTest exit **8**, `No tests were found!!!`, JSON `passed: false`.

This is a current-versus-stale-artifact comparison using real CMake/Ninja/CTest, not mocked subprocess results. All fixture edits were outside the repository and fixtures were removed afterward.

**Recommended correction:** add a regression contract asserting the second run fails, then configure each harness in a fresh runner-owned build directory (or explicitly reject nonempty/reused per-issue build directories). Preserve logs separately as needed. Do not blindly delete arbitrary user-provided output directories. A fresh build is preferable to clearing only one CTest file because nested stale registrations/binaries can remain. Verify RED on this SHA and GREEN on the correction before merge. This is blocking for the requested trustworthy test-evidence gate, although the hosted workflow's fresh container avoids this particular reuse path.

## Verified results

### Existing contracts and real bootstrap invocation

Commands run from the reviewed checkout with `PYTHONDONTWRITEBYTECODE=1`:

```sh
python3 tools/upstream/test-run-native.py -v
python3 tools/phase4/test-import-profile.py
python3 tools/release/test-alpha.py
```

All exited **0**: **5 runner tests**, **1 profile-import test**, **2 release-contract tests**. No skips. Repeated all three with `/usr/bin/python3` (Debian Python 3.13.5): also **5 + 1 + 2 passing**. The default interpreter was Python 3.11.15.

Actual checkout bootstrap command, with a temporary evidence directory:

```sh
/usr/bin/python3 tools/upstream/run-native.py --allow-empty --output /tmp/review-ci-bootstrap-z8pqzf0h
```

Exit **0**, JSON exactly `[]`, and explicit output `No issue harnesses yet (--allow-empty); no C++ coverage claimed.` No `tests/upstream` harnesses exist in this commit. This is deliberate bootstrap behavior, **not** a finding. Remove `--allow-empty` when harnesses are integrated.

### Independent runner boundaries

Executed the actual runner against temporary fixtures, parsed the resulting JSON, and asserted results programmatically:

| Probe | Observed result |
|---|---|
| No harnesses without `--allow-empty` | Exit 2 |
| No harnesses with explicit bootstrap flag | Exit 0; JSON `[]` |
| Missing `--issue 255` even with bootstrap flag | Exit 2 |
| Configure-failing issue 11 | Steps `[1]`; `passed: false` |
| Build-failing issue 20 | Steps `[0,1]`; `passed: false` |
| CTest-failing issue 30 | Steps `[0,0,8]`; `passed: false` |
| Registered suite with zero tests, issue 40 | Steps `[0,0,8]`; `passed: false` |
| Passing issue 255 after all preceding failures | Steps `[0,0,0]`; `passed: true` |
| Combined five-harness run | Exit 1; all five processed in numeric order |
| Repeated exact `--issue 255 --issue 255` | Exit 0; one result entry |
| Output inside source tree | Exit 2 |
| Output symlink resolving inside source | Exit 2 |
| Discovery: helper name, non-ASCII digits, symlink harness, symlink CMake file | Rejected; numeric valid fixtures retained |
| All tests explicitly disabled | Runner exit 1; CTest exit 8 |

The reuse probe above is the exception to otherwise correctly failing empty CTest suites.

### Workflow/configuration and scope checks

- Push and PR branch filters target `integration/upstream-issues`; `workflow_dispatch` is also available.
- Read-only `contents` permission, ordinary `pull_request` rather than `pull_request_target`, no secret inputs or publish steps, bounded job timeout, and cancellation concurrency are present.
- Debian image has a full digest and the two added Actions have full commit pins. APT dependencies intentionally follow available Debian package updates, matching the documentation's explicit non-bit-reproducibility caveat.
- Package provenance is produced with `dpkg-query -W`; artifact collection runs with `if: always()`. If an earlier dependency/contract step fails, subsequent runner evidence may be absent and upload warns; this does not turn the failing job green.
- All declared dependency package names were found installed by `dpkg-query -W` in the local environment. Observed CMake/CTest 3.31.6, Ninja 1.12.1, GCC 14.2.0, Qt 6.8.2, GStreamer 1.26.2, TagLib 2.0.2.
- `git diff --exit-code <SHA>^ <SHA> -- .github/workflows/windows-cmake.yml .github/workflows/alpha-release.yml` exited 0. Existing Windows PR coverage retains the Qt 5/6 full builds, CTest, package checks and evidence. No release/workflow modifications outside the four-file scope.
- `git diff --check <SHA>^ <SHA>` exited 0.

## Supplemental native component attempts and limitations

Attempted the existing `experiments/qt6-skins` resource/script-bridge targets, without changing source:

```sh
cmake -S experiments/qt6-skins -B "$B" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DSKIN_TEST_FONT=/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf
cmake --build "$B" --target test_skin_resources test_script_bridge --parallel 1
ctest --test-dir "$B" -R '^(skin_resources|script_bridge)$' \
  --output-on-failure --no-tests=error --timeout 180
```

- Under `/tmp`, configure and compilation/linking passed, but CTest exited **8** with both executables `BAD_COMMAND` / `permission denied`. `findmnt -T /tmp` confirmed `noexec`; this is a local sandbox constraint, not proof of a hosted CI defect.
- Retried under an executable temporary directory in `/home/hermes/workspace`: configure passed, compilation of `testScriptBridge.cpp` was killed (`cc1plus`, build exit **1**).
- A lower-optimization supplemental retry (`-DCMAKE_CXX_FLAGS_RELEASE=-O0 -DNDEBUG`) also failed to complete: the build exceeded the review's 240-second subprocess timeout and compiler output again reported a killed `cc1plus`.
- Therefore this review **does not claim passing local execution of the existing native skin suites**. Initial native compilation succeeded; actual native Qt test execution remains unverified locally. All temporary build directories were cleaned. These probes are supplemental and do not change the confirmed runner finding.
- Docker/Podman/actionlint and PyYAML were unavailable; no full hosted workflow execution, container launch or actionlint validation was performed by this reviewer.
- Parent supplied updated hosted evidence: PR7's three checks passed at the exact reviewed SHA (Linux native 59s, Windows Qt5 4m27, Windows Qt6 7m10). This is explicitly parent-supplied evidence, not independently fetched here. It does not exercise local output-directory reuse.

## Read-only integrity

Initial and final `git status --short --untracked-files=all` were empty. Final HEAD remained exactly `b86a0f8bff40e3ab4b47ceddaad4603296182649` on `ci/upstream-stabilization`. Programmatic byte comparisons confirmed all four checked-out files equal their immutable commit blobs.

SHA-256 of reviewed files:

```text
76f8fb1b60a6130f705f4e8bb8624a304556f9aa35e26f4a0151b17f5cc07a89  .github/workflows/upstream-stabilization.yml
f2515f9e20c99f7a25e5683dd9724dc8e90c69783cc03664f7c5dc63143da1e0  docs/UPSTREAM_STABILIZATION.md
1cb74235e2e73a42003b63bd15df0601aa2a4ba750a52c4c623ede211e4104f9  tools/upstream/run-native.py
e3422afd0a0a1bdbd93b5104913051c873e50fc884caee53adeb9e29dff4930a  tools/upstream/test-run-native.py
```

Only this report is a retained file created by the review. No fixes were applied, no repository files were modified, and `master` was untouched.
