#!/usr/bin/env python3
"""Disposable Qt6 package geometry checks on the actual Windows monitors."""
from __future__ import annotations

import argparse
import ctypes as c
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

from probe import extract_and_validate, _app_environment


def wait_for(predicate, description, timeout=20):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.1)
    raise RuntimeError(f"Timed out: {description}")


def run(args):
    if os.name != 'nt':
        raise RuntimeError('Requires a native Windows desktop')
    user = c.WinDLL('user32', use_last_error=True)
    user.SetProcessDpiAwarenessContext.argtypes = [c.c_void_p]
    user.SetProcessDpiAwarenessContext(c.c_void_p(-4))
    callback_type = c.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    user.EnumWindows.argtypes = [callback_type, w.LPARAM]
    user.GetWindowThreadProcessId.argtypes = [w.HWND, c.POINTER(w.DWORD)]
    user.GetWindow.argtypes = [w.HWND, w.UINT]
    user.GetWindow.restype = w.HWND
    user.IsWindowVisible.argtypes = [w.HWND]
    user.IsIconic.argtypes = [w.HWND]
    user.GetWindowRect.argtypes = [w.HWND, c.POINTER(w.RECT)]
    user.GetWindowTextW.argtypes = [w.HWND, w.LPWSTR, c.c_int]
    user.GetClassNameW.argtypes = [w.HWND, w.LPWSTR, c.c_int]
    user.ShowWindow.argtypes = [w.HWND, c.c_int]
    user.SetWindowPos.argtypes = [w.HWND, w.HWND, c.c_int, c.c_int, c.c_int, c.c_int, w.UINT]
    user.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]

    class MonitorInfo(c.Structure):
        _fields_ = [('size', w.DWORD), ('bounds', w.RECT), ('work', w.RECT),
                    ('flags', w.DWORD), ('device', w.WCHAR * 32)]

    def rect_values(rect):
        return [rect.left, rect.top, rect.right, rect.bottom]

    monitors = []
    monitor_callback = c.WINFUNCTYPE(w.BOOL, w.HANDLE, w.HDC, c.POINTER(w.RECT), w.LPARAM)
    user.EnumDisplayMonitors.argtypes = [w.HDC, c.POINTER(w.RECT), monitor_callback, w.LPARAM]
    user.GetMonitorInfoW.argtypes = [w.HANDLE, c.POINTER(MonitorInfo)]
    dpi = c.WinDLL('shcore').GetDpiForMonitor
    dpi.argtypes = [w.HANDLE, c.c_int, c.POINTER(w.UINT), c.POINTER(w.UINT)]

    @monitor_callback
    def collect(handle, dc, bounds, data):
        info = MonitorInfo()
        info.size = c.sizeof(info)
        if not user.GetMonitorInfoW(handle, c.byref(info)):
            return False
        x, y = w.UINT(), w.UINT()
        result = dpi(handle, 0, c.byref(x), c.byref(y))
        monitors.append({'device': info.device, 'bounds': rect_values(info.bounds),
                         'work': rect_values(info.work), 'primary': bool(info.flags & 1),
                         'dpi': [x.value, y.value], 'dpi_hresult': result})
        return True

    if not user.EnumDisplayMonitors(None, None, collect, 0) or len(monitors) < 2:
        raise RuntimeError('Two real monitors are required')

    def find_window(process):
        if process.poll() is not None:
            raise RuntimeError(f'Player exited before observation: {process.returncode}')
        windows = []

        @callback_type
        def collect_window(hwnd, data):
            pid = w.DWORD()
            user.GetWindowThreadProcessId(hwnd, c.byref(pid))
            if pid.value == process.pid and user.IsWindowVisible(hwnd) and not user.GetWindow(hwnd, 4):
                title, kind = c.create_unicode_buffer(512), c.create_unicode_buffer(256)
                user.GetWindowTextW(hwnd, title, len(title))
                user.GetClassNameW(hwnd, kind, len(kind))
                if 'Nulloy' in title.value:
                    windows.append((hwnd, title.value, kind.value))
            return True

        user.EnumWindows(collect_window, 0)
        if len(windows) > 1:
            raise RuntimeError(f'Multiple owned main-window candidates: {windows}')
        return windows[0] if windows else None

    def rect(hwnd):
        value = w.RECT()
        if not user.GetWindowRect(hwnd, c.byref(value)):
            raise c.WinError(c.get_last_error())
        return rect_values(value)

    def stable_rect(hwnd):
        previous, count = None, 0
        def sample():
            nonlocal previous, count
            current = rect(hwnd)
            count = count + 1 if current == previous else 0
            previous = current
            return current if count >= 4 else None
        return wait_for(sample, 'stable window rectangle')

    def contained(value, work):
        # GetWindowRect includes the invisible native resize border; Qt clips
        # the widget rectangle. Permit only that small frame margin.
        margin = 16
        return (value[0] >= work[0] - margin and value[1] >= work[1] - margin
                and value[2] <= work[2] + margin and value[3] <= work[3] + margin
                and value[2] > value[0] and value[3] > value[1])

    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    evidence = {'status': 'FAIL', 'monitors': monitors, 'cases': [],
                'coverage': 'real monitor move, minimize/restore, persisted restart, offscreen startup',
                'mixed_dpi_tested': False, 'physical_hotplug_tested': False}
    try:
        with tempfile.TemporaryDirectory(prefix='nulloy-monitor-') as temporary:
            package = extract_and_validate(args.package.resolve(), Path(temporary), args.source_sha)
            if not package.contract.portable:
                raise RuntimeError('Only an isolated portable package may be used')
            evidence.update(source_sha=args.source_sha, archive_sha256=package.archive_sha256,
                            executable_sha256=package.executable_sha256,
                            file_hashes_verified=package.file_hashes_verified)
            config = package.root / 'Data' / (package.executable.stem + '.cfg')
            config.parent.mkdir(exist_ok=True)
            environment = _app_environment()
            environment['GST_PLUGIN_FEATURE_RANK'] = 'directsoundsink:0,waveformsink:0,wasapisink:0,wasapi2sink:0'
            for skin in ('Slim/0.9', 'Metro/0.9', 'Silver/0.9', 'Native (Built-in)/0.9'):
                name = skin.split('/')[0].split(' ')[0].lower()
                settings = ('[General]\nSettingsVersion=0.8\nSingleInstance=false\nRestorePlaylist=false\n'
                            'Language=en\nTrayIcon=false\nMinimizeToTray=false\nDisplayLogDialog=false\n'
                            'AutoCheckUpdates=false\nVolume=0\n'
                            f'Skin={skin}\nPosition=30000, 30000\nSize=9999, 9999\nMaximized=false\n')
                config.write_text(settings, encoding='utf-8')
                expected_restart = None
                for phase in ('offscreen-and-move', 'persisted-restart'):
                    case = {'skin': skin, 'phase': phase, 'status': 'FAIL', 'rectangles': []}
                    evidence['cases'].append(case)
                    process = None
                    hwnd = None
                    try:
                        with (output / f'{name}-{phase}.log').open('wb') as log:
                            process = subprocess.Popen([str(package.executable)], cwd=package.root,
                                                       env=environment, stdout=log, stderr=log)
                            hwnd, title, kind = wait_for(lambda: find_window(process), 'owned player window', 45)
                            case.update(pid=process.pid, hwnd=hwnd, title=title, window_class=kind)
                            initial = stable_rect(hwnd)
                            case['rectangles'].append({'stage': 'startup', 'rect': initial})
                            if not any(contained(initial, m['work']) for m in monitors):
                                raise AssertionError(f'Startup window outside work areas: {initial}')
                            if phase == 'persisted-restart':
                                if any(abs(a - b) > 16 for a, b in zip(initial, expected_restart)):
                                    raise AssertionError(f'Restored geometry differs: {initial} vs {expected_restart}')
                            else:
                                for monitor in monitors:
                                    left, top, right, bottom = monitor['work']
                                    if not user.SetWindowPos(hwnd, None, left + 100, top + 100, 640, 480, 0x14):
                                        raise c.WinError(c.get_last_error())
                                    placed = stable_rect(hwnd)
                                    case['rectangles'].append({'stage': 'move', 'monitor': monitor['device'], 'rect': placed})
                                    if not contained(placed, monitor['work']):
                                        raise AssertionError('Moved window is not inside target monitor')
                                    user.ShowWindow(hwnd, 6)
                                    wait_for(lambda: user.IsIconic(hwnd), 'minimized player')
                                    user.ShowWindow(hwnd, 9)
                                    wait_for(lambda: not user.IsIconic(hwnd), 'restored player')
                                    restored = stable_rect(hwnd)
                                    case['rectangles'].append({'stage': 'restore', 'monitor': monitor['device'], 'rect': restored})
                                    if any(abs(a - b) > 2 for a, b in zip(restored, placed)):
                                        raise AssertionError(f'Minimize/restore changed geometry: {placed} vs {restored}')
                                    expected_restart = restored
                            user.PostMessageW(hwnd, 0x10, 0, 0)
                            process.wait(timeout=15)
                            if process.returncode != 0:
                                raise RuntimeError(f'Player exit code {process.returncode}')
                            case['status'] = 'PASS'
                    except Exception as error:
                        case['error'] = repr(error)
                    finally:
                        if process is not None and process.poll() is None:
                            if hwnd:
                                user.PostMessageW(hwnd, 0x10, 0, 0)
                            try:
                                process.wait(timeout=5)
                            except subprocess.TimeoutExpired:
                                process.kill()
                                process.wait(timeout=5)
                        case['process_cleanup_verified'] = process is None or process.poll() is not None
                        if config.exists():
                            (output / f'{name}-{phase}.cfg').write_bytes(config.read_bytes())
                    if case['status'] != 'PASS':
                        break
            evidence['status'] = 'PASS' if len(evidence['cases']) == 8 and all(
                case['status'] == 'PASS' and case['process_cleanup_verified']
                for case in evidence['cases']) else 'FAIL'
    finally:
        (output / 'result.json').write_text(json.dumps(evidence, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(evidence, indent=2))
    return 0 if evidence['status'] == 'PASS' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--source-sha', required=True)
    parser.add_argument('--output', type=Path, required=True)
    raise SystemExit(run(parser.parse_args()))
