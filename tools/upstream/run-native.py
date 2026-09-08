"""Run standalone C++ issue harnesses without changing the Windows release build.

No discovered harness is success only with an explicit --allow-empty. A configured
harness with zero registered tests always fails. Logs and a JSON result are kept
outside the source tree by default.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile


def discover(source):
    root = source / "tests" / "upstream"
    if not root.is_dir():
        return []
    return sorted(
        (p for p in root.iterdir()
         if p.name.isascii() and p.name.isdecimal() and p.is_dir()
         and not p.is_symlink() and (p / "CMakeLists.txt").is_file()
         and not (p / "CMakeLists.txt").is_symlink()),
        key=lambda p: int(p.name),
    )


def commands(source, output):
    return [
        ["cmake", "-S", str(source), "-B", str(output), "-G", "Ninja",
         "-DCMAKE_BUILD_TYPE=Release"],
        ["cmake", "--build", str(output), "--parallel", "1"],
        ["ctest", "--test-dir", str(output), "--output-on-failure",
         "--no-tests=error", "--timeout", "180"],
    ]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--issue", action="append", default=[], help="Run only this exact numeric issue directory")
    parser.add_argument("--allow-empty", action="store_true")
    args = parser.parse_args()
    source = args.source.resolve()
    harnesses = discover(source)
    if args.issue:
        missing = set(args.issue) - {p.name for p in harnesses}
        if missing:
            parser.error("No harness for: " + ", ".join(sorted(missing)))
        harnesses = [p for p in harnesses if p.name in args.issue]
    if not harnesses and not args.allow_empty:
        parser.error("No native issue harnesses discovered")
    output = args.output.resolve() if args.output else Path(tempfile.mkdtemp(prefix="nulloy-upstream-"))
    if output == source or source in output.parents:
        parser.error("--output must be outside the source tree")
    output.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    results = []
    for harness in harnesses:
        build = output / harness.name
        build.mkdir(parents=True, exist_ok=True)
        entry = {"issue": int(harness.name), "source": str(harness), "steps": [], "passed": False}
        for index, command in enumerate(commands(harness, build)):
            log = build / ("step-%d.log" % index)
            print("+ " + " ".join(command), flush=True)
            try:
                with log.open("w", encoding="utf-8") as stream:
                    process = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT,
                                             env=env, timeout=900, check=False)
                code = process.returncode
            except subprocess.TimeoutExpired:
                code = 124
            except OSError as error:
                log.write_text(str(error), encoding="utf-8")
                code = 127
            entry["steps"].append({"command": command, "exit_code": code, "log": str(log)})
            print(log.read_text(encoding="utf-8", errors="replace"), flush=True)
            if code:
                break
        else:
            entry["passed"] = True
        results.append(entry)
        (output / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    if not results:
        (output / "results.json").write_text("[]\n", encoding="utf-8")
        print("No issue harnesses yet (--allow-empty); no C++ coverage claimed.")
    print("Evidence: " + str(output / "results.json"), flush=True)
    return 0 if all(entry["passed"] for entry in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
