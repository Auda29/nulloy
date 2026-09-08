# Windows x64 mit Qt 6 bauen

Der vollständige Player nutzt CMake, Qt Widgets und QJSEngine. Slim, Silver, Metro
und Native stammen unverändert aus `src/skins`. Rust gehört nicht zu Phase 3.

## Abhängigkeiten

Eine separate MSYS2-MINGW64-Installation verwenden. Die Qt-5-Versionen können für
Vergleiche daneben installiert bleiben. Für Qt 6 werden benötigt:

```bash
pacman -S --needed \
  mingw-w64-x86_64-gcc mingw-w64-x86_64-cmake mingw-w64-x86_64-ninja \
  mingw-w64-x86_64-pkgconf mingw-w64-x86_64-python \
  mingw-w64-x86_64-imagemagick mingw-w64-x86_64-librsvg \
  mingw-w64-x86_64-qt6-base mingw-w64-x86_64-qt6-declarative \
  mingw-w64-x86_64-qt6-svg mingw-w64-x86_64-qt6-tools \
  mingw-w64-x86_64-qt6-5compat \
  mingw-w64-x86_64-gstreamer mingw-w64-x86_64-gst-plugins-base \
  mingw-w64-x86_64-gst-plugins-good mingw-w64-x86_64-taglib \
  mingw-w64-x86_64-zlib
```

Qt 6.8 oder neuer ist erforderlich. Core5Compat erhält `QTextCodec` für ältere
Tag-Zeichencodierungen; QtScript und private Qt-Dateisystem-APIs werden im
Qt-6-Player nicht mehr verwendet.

## Build und Prüfung

Aus PowerShell im Checkout, mit dem tatsächlichen Pfad zur isolierten Toolchain:

```powershell
./tools/phase2/build-windows.ps1 -ToolchainRoot 'C:/Tools/msys64' `
  -Preset windows-qt6-x64 -Package
```

Oder in der MINGW64-Shell:

```bash
cmake --preset windows-qt6-x64 -DCMAKE_PREFIX_PATH="$(cygpath -m /mingw64)"
cmake --build --preset windows-qt6-x64
ctest --preset windows-qt6-x64
python tools/phase2/package-windows.py --prefix "$(cygpath -m /mingw64)" --build .phase3/build --source .
python tools/phase2/verify-package.py --prefix "$(cygpath -m /mingw64)" --build .phase3/build --repeat 3
```

Ergebnis: `.phase3/build/Nulloy-windows-x64.zip` plus SHA-256-Datei. Der Packer
prüft AMD64, DLL-Abhängigkeiten und die Qt-Hauptversion. Profil, Musikdateien und
Testprogramme werden nicht mitgeliefert. Der Laufzeittest entpackt in einen
temporären Ordner mit Leerzeichen und Umlaut; sein PATH enthält nur System32.

Die Testwiedergabe ist stummgeschaltet. `--headless-audio` verwendet den
GStreamer-Ersatz für Systeme ohne Audiogerät; dies ist kein Hörtest.

Ergänzende Format- und Tag-Prüfung mit erzeugten Testdateien:

```bash
python tools/phase3/build-format-fixtures.py --prefix "$(cygpath -m /mingw64)" --build .phase3/build
python tools/phase2/verify-package.py --prefix "$(cygpath -m /mingw64)" --build .phase3/build --format-fixtures .phase3/build/format-fixtures
python tools/phase2/verify-package.py --prefix "$(cygpath -m /mingw64)" --build .phase3/build --trace-startup --repeat 3
```

Die Formatprüfung schreibt Unicode-Tags ausschließlich in temporäre Kopien der
erzeugten Dateien. Ergebnisse liegen unter `format-check`. Die Startdiagnose
protokolliert Plugin-Zeitmarken und GStreamer-Registry-Meldungen unter
`startup-check`; Erststart und Folgestarts bleiben getrennt auswertbar.

Der Vergleichsbuild bleibt unter dem Preset `windows-x64` mit Qt 5.15 verfügbar.
Für die ursprünglichen Skin-Tests werden dieselben Produktionsadapter verwendet:

```bash
cmake -S experiments/qt6-skins -B .phase3/skin-probe -G Ninja \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH="$(cygpath -m /mingw64)"
cmake --build .phase3/skin-probe -j 4
ctest --test-dir .phase3/skin-probe --output-on-failure
```

## Manueller Test

Das ZIP in einen eigenen beschreibbaren Ordner entpacken und dessen `Nulloy.exe`
starten. Einstellungen bleiben bei diesem Build neben der EXE. Die bestehende
Installation nicht als Testverzeichnis verwenden.

1. Slim mit dem bisherigen Player bei gleicher Skalierung vergleichen.
2. Eine neue Datei und anschließend mehrere neue Dateien gleichzeitig aus dem
   Explorer in die leere beziehungsweise bereits gefüllte Playlist ziehen.
3. Wiedergabe, Pause, Seek und hörbare Ausgabe prüfen.
4. Schließen und erneut öffnen; zusätzlich direkt während einer neuen
   Waveform-Berechnung schließen. Erststart und Folgestarts getrennt beurteilen.
5. Menü, Vollbild, Maximieren/Wiederherstellen, Tray und globale Hotkeys prüfen.

Die offenen Grenzen und Messungen stehen im [Phase-3-Bericht](../../PHASE3_REPORT.md).
