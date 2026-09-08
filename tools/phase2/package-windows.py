#!/usr/bin/env python3
"""Assemble a relocatable x64 test package and check its PE dependency closure."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import zipfile


def pe_imports(path):
    data = path.read_bytes()
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError(f"Not a PE binary: {path}")
    machine, sections = struct.unpack_from("<HH", data, pe + 4)
    if machine != 0x8664:
        raise ValueError(f"Not Windows x64: {path} (machine {machine:#x})")
    optional = pe + 24
    optional_size = struct.unpack_from("<H", data, pe + 20)[0]
    table = optional + optional_size

    def offset(rva):
        for i in range(sections):
            size, address, raw_size, raw = struct.unpack_from("<IIII", data, table + 40 * i + 8)
            if address <= rva < address + max(size, raw_size):
                return raw + rva - address
        raise ValueError(f"Unmapped RVA {rva:#x} in {path}")

    def name(rva):
        start = offset(rva)
        return data[start:data.index(b"\0", start)].decode("ascii").lower()

    imports = set()
    # IMAGE_OPTIONAL_HEADER64: data directories begin at byte 112.
    for index, stride, name_field in ((1, 20, 12), (13, 32, 4)):
        rva, size = struct.unpack_from("<II", data, optional + 112 + 8 * index)
        if not rva:
            continue
        cursor = offset(rva)
        for _ in range(size // stride):
            record = data[cursor:cursor + stride]
            if not any(record):
                break
            imports.add(name(struct.unpack_from("<I", record, name_field)[0]))
            cursor += stride
    return sorted(imports)


def package(args):
    prefix, build, source = (Path(p).resolve() for p in (args.prefix, args.build, args.source))
    run = build / "run"
    cache = dict(line.split("=", 1) for line in (build / "CMakeCache.txt").read_text().splitlines()
                 if "=" in line and not line.startswith(("#", "//")))
    enabled = lambda option: cache.get(option + ":BOOL", "OFF").upper() in ("ON", "YES", "TRUE", "1")
    qt_major = cache.get("NULLOY_QT_MAJOR:STRING", "5")
    portable = enabled("NULLOY_PORTABLE_FORK")
    app_name = cache.get("NULLOY_APP_NAME:STRING", "Nulloy")
    executable = args.executable or app_name + ".exe"
    version = cache.get("NULLOY_VERSION:STRING", "unknown")
    package_name = f"{app_name}-{version}-windows-x64" if portable else "Nulloy-windows-x64"
    output = build / (package_name + ".zip")
    if portable and enabled("NULLOY_UPDATE_CHECK"):
        raise RuntimeError("The portable fork must not use upstream updates")
    binaries = {p.name.lower(): p for p in (prefix / "bin").glob("*.dll")}
    system = Path(os.environ["SystemRoot"]) / "System32"
    with tempfile.TemporaryDirectory(prefix="package-", dir=build) as temp:
        stage = Path(temp) / app_name
        stage.mkdir()
        shutil.copy2(run / executable, stage)
        (stage / "Plugins").mkdir()
        for option, filename in (("NULLOY_GSTREAMER", "PluginGStreamer.dll"),
                                 ("NULLOY_TAGLIB", "PluginTagLib.dll"), ("NULLOY_VLC", "PluginVLC.dll")):
            if enabled(option):
                shutil.copy2(run / "Plugins" / filename, stage / "Plugins")
        folders = ["i18n"] + (["Skins"] if enabled("NULLOY_SKINS") else [])
        for folder in folders:
            if (run / folder).exists():
                shutil.copytree(run / folder, stage / folder)
        for filename in ("LICENSE.GPL3", "COPYING", "THANKS", "ChangeLog"):
            if (source / filename).exists():
                shutil.copy2(source / filename, stage)
        deploy = "windeployqt6.exe" if qt_major == "6" else "windeployqt-qt5.exe"
        options = ["--release", "--no-translations", "--no-compiler-runtime", "--no-opengl-sw"]
        if qt_major == "5":
            options += ["--no-angle", "--no-system-d3d-compiler"]
        subprocess.run([str(prefix / "bin" / deploy), *options, str(stage / executable)], check=True)
        if (stage / "Plugins/PluginGStreamer.dll").exists():
            shutil.copytree(prefix / "lib/gstreamer-1.0", stage / "gstreamer-1.0",
                            ignore=shutil.ignore_patterns("*.a", "*.la", "include", "pkgconfig"))
            shutil.copy2(prefix / "libexec/gstreamer-1.0/gst-plugin-scanner.exe", stage)
            if portable:
                shutil.copy2(prefix / "bin/gst-inspect-1.0.exe", stage)
        if (stage / "Plugins/PluginVLC.dll").exists():
            raise RuntimeError("VLC packaging has not been validated; use the GStreamer test package.")
        queue = sorted([*stage.rglob("*.exe"), *stage.rglob("*.dll")])
        checked = {}
        while queue:
            binary = queue.pop(0)
            relative = binary.relative_to(stage).as_posix()
            if relative in checked:
                continue
            imports = pe_imports(binary)
            if any(dll.startswith("qt" + ("5" if qt_major == "6" else "6")) for dll in imports):
                raise RuntimeError(f"Mixed Qt major versions in {relative}: {imports}")
            checked[relative] = {"machine": "AMD64", "imports": imports}
            for dll in imports:
                if (stage / dll).exists():
                    continue
                if dll in binaries:
                    destination = stage / binaries[dll].name
                    shutil.copy2(binaries[dll], destination)
                    queue.append(destination)
                elif dll.startswith(("api-ms-win-", "ext-ms-win-")) or (system / dll).is_file():
                    continue
                else:
                    raise RuntimeError(f"Unresolved dependency: {relative} -> {dll}")
        (stage / "qt.conf").write_text("[Paths]\nPlugins=.\n", encoding="utf-8")
        if portable and (stage / "gstreamer-1.0").exists():
            # ZIP timestamps have two-second resolution. Preserve them when extracting;
            # GStreamer still validates timestamps, sizes and external dependencies.
            for plugin in (stage / "gstreamer-1.0").glob("*.dll"):
                stamp = int(plugin.stat().st_mtime) // 2 * 2
                os.utime(plugin, (stamp, stamp))
            env = os.environ.copy()
            for key in list(env):
                if key.startswith(("GST_", "QT_", "QML")):
                    del env[key]
            env.update(PATH=str(system), GST_PLUGIN_SYSTEM_PATH_1_0="gstreamer-1.0",
                       GST_PLUGIN_PATH_1_0="", GST_PLUGIN_SCANNER_1_0=str(stage / "gst-plugin-scanner.exe"),
                       GST_REGISTRY=str(stage / "gstreamer-registry.seed.bin"))
            subprocess.run([str(stage / "gst-inspect-1.0.exe"), "playbin"], cwd=stage, env=env,
                           check=True, timeout=120, stdout=subprocess.DEVNULL)
            if str(stage).encode() in (stage / "gstreamer-registry.seed.bin").read_bytes():
                raise RuntimeError("Registry seed contains the staging directory")
        if (prefix / "share/licenses").exists():
            shutil.copytree(prefix / "share/licenses", stage / "licenses/msys2")
        (stage / "TEST-BUILD.txt").write_text(
            f"Nulloy community fork: Windows x64 / Qt {qt_major} CMake test build.\n"
            "Source: https://github.com/Auda29/nulloy\n"
            f"Extract into a writable folder. Settings stay {'in Data/' if portable else 'next to the executable'}.\n"
            "Do not replace an existing installation or copy personal profiles into this archive.\n"
            "Upstream update checking is disabled in the default build.\n"
            "Third-party binaries come from MSYS2 MINGW64. Package versions are in toolchain.txt.\n"
            "Corresponding MSYS2 package recipes and source locations: https://github.com/msys2/MINGW-packages\n",
            encoding="utf-8")
        commit = subprocess.check_output(["git", "-c", f"safe.directory={source.as_posix()}",
                                          "rev-parse", "HEAD"], cwd=source, text=True).strip()
        dirty = bool(subprocess.check_output(["git", "-c", f"safe.directory={source.as_posix()}",
                                             "status", "--porcelain", "--untracked-files=no"], cwd=source, text=True).strip())
        metadata = {"source_commit": commit, "tracked_changes": dirty, "version": version,
                    "executable": executable, "root": app_name, "archive": output.name,
                    "portable": portable, "upstream_update_check": enabled("NULLOY_UPDATE_CHECK")}
        (stage / "build-info.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        if portable:
            for document in ("PHASE4_REPORT.md", "docs/phase4/PORTABLE.md"):
                if (source / document).is_file():
                    shutil.copy2(source / document, stage)
        manifest = {**metadata, "qt_major": qt_major, "binaries": checked, "files": {}}
        toolchain = build / "toolchain.txt"
        if toolchain.exists():
            shutil.copy2(toolchain, stage)
        for file in sorted(stage.rglob("*")):
            if file.is_file():
                manifest["files"][file.relative_to(stage).as_posix()] = hashlib.sha256(file.read_bytes()).hexdigest()
        (stage / "package-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for file in sorted(stage.rglob("*")):
                if file.is_file():
                    archive.write(file, app_name + "/" + file.relative_to(stage).as_posix())
    (build / "package-info.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    checksum = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(".zip.sha256").write_text(f"{checksum}  {output.name}\n", encoding="ascii")
    print(f"Packaged {len(checked)} verified x64 binaries: {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for option in ("prefix", "build", "source"):
        parser.add_argument("--" + option, required=True)
    parser.add_argument("--executable", help="Override executable name from the CMake cache")
    package(parser.parse_args())
