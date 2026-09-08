# Windows x64 mit CMake

Phase 2 baut den vollständigen bisherigen Player mit Qt 5.15. Die Qt-6-Integration folgt in Phase 3. Die Skin-Formulare, Skripte und Bilder bleiben unverändert. qmake bleibt als Vergleich und für die übrigen Plattformen erhalten.

## Werkzeugkette

Eine eigenständige MSYS2-Installation mit MINGW64 verwenden. UCRT64, MSVC, Qt 6 und die DLLs der alten x86-Installation gehören nicht in diesen Build. In der MINGW64-Shell installieren:

```bash
pacman -Syu
pacman -S --needed mingw-w64-x86_64-{gcc,cmake,ninja,pkgconf,python,imagemagick,zlib,qt5-base,qt5-script,qt5-svg,qt5-tools,qt5-winextras,gstreamer,gst-plugins-base,gst-plugins-good,taglib}
```

Falls MSYS2 während des Updates einen Neustart der Shell verlangt, diesen vor dem zweiten Befehl durchführen. Die CI verwendet dieselben Paketnamen. MSYS2 ist eine Rolling-Release-Distribution; die tatsächlich installierten Versionen stehen in jedem Testpaket unter `toolchain.txt`. Das ist eine dokumentierte Werkzeugkette, kein Versprechen bitidentischer Builds mit beliebigen späteren Repository-Ständen.

## Bauen, testen und paketieren

In PowerShell im Checkout:

```powershell
./tools/phase2/build-windows.ps1 -ToolchainRoot C:/msys64 -Package
```

Der Helfer setzt PATH nur im laufenden Prozess. Er konfiguriert CMake, baut die Anwendung und Tests, führt CTest aus, protokolliert die Paketversionen und erstellt sowie prüft das ZIP. Fehler in einem Schritt brechen den Ablauf ab.

Ausgaben im standardmäßig ignorierten Verzeichnis `.phase2/build`:

- `run/Nulloy.exe`, `run/Plugins`, `run/Skins` und `run/i18n`: Build-Ausgabe mit echten Playback-Plugins.
- `test-run`: getrennte Qt-Tests. Nur hier verwendet das GStreamer-Testplugin einen Fakesink.
- `Nulloy-windows-x64.zip` und `.zip.sha256`: Testpaket und Prüfsumme.
- `*-results.txt` und `package-check`: Testprotokolle und Renderings.

Für einzelne CMake-Optionen die MINGW64-Shell verwenden:

```bash
cmake -S . -B .phase2/custom -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_PREFIX_PATH="$(cygpath -m /mingw64)"
cmake --build .phase2/custom -j 4
ctest --test-dir .phase2/custom --output-on-failure
```

## Optionen

| Bisherige Auswahl | CMake | Standard |
|---|---|---|
| Vollständige Skin-Unterstützung / `no-skins` | `NULLOY_SKINS` | `ON`, mit Slim, Silver, Metro und eingebautem Native-Skin |
| GStreamer / `no-gstreamer` | `NULLOY_GSTREAMER` | `ON` |
| GStreamer-TagReader | `NULLOY_GSTREAMER_TAGREADER` | `OFF` |
| TagLib / `no-taglib` | `NULLOY_TAGLIB` | `ON` |
| VLC | `NULLOY_VLC` | `OFF`, benötigt eigene VLC-Entwicklungsbibliotheken |
| Tests | `BUILD_TESTING` | `ON` |
| Debug-Build | `CMAKE_BUILD_TYPE=Debug` | `Release` im Helfer |
| Konsole | `NULLOY_CONSOLE` | `OFF` |
| Versionsüberschreibung | `NULLOY_VERSION` | Erste Version aus ChangeLog |
| Programmname | `NULLOY_APP_NAME` | `Nulloy` |
| Upstream-Updateprüfung | `NULLOY_UPDATE_CHECK` | `OFF` für den Fork-Testbuild |

Die bestehenden Integrationstests benötigen GStreamer und einen TagReader. Für Builds ohne GStreamer `BUILD_TESTING=OFF` setzen. Die Paketierung ist zunächst für GStreamer vorgesehen; VLC-Pakete werden ausdrücklich abgelehnt, bis deren Laufzeitabhängigkeiten geprüft sind. Statische Komplettverlinkung und Unix-Installationspfade gehören nicht zum Windows-x64-Paket.

## Paketprüfung

Der Packer übernimmt nur Anwendungsdateien und Ressourcen, keine lokalen Profile, Medien oder Cache-Dateien. Qt 5 wird über das zur Werkzeugkette gehörende `windeployqt-qt5` kopiert. ANGLE und der Software-OpenGL-Rasterizer werden für diesen Qt-Widgets-Player nicht paketiert. GStreamer-Module und Scanner kommen aus derselben MINGW64-Installation.

Danach werden PE-Importtabellen einschließlich verzögerter DLL-Imports rekursiv ausgewertet. Jede mitgelieferte EXE/DLL muss AMD64 sein. Fehlende Abhängigkeiten außerhalb der Windows-Systembibliotheken brechen die Paketierung ab. Das Manifest enthält die Importlisten und SHA-256-Werte der Paketdateien.

Der Laufzeittest entpackt das ZIP in einen temporären Pfad mit Leerzeichen und Umlaut. Er entfernt Qt-/GStreamer-Umgebungsvariablen und beschränkt PATH auf Windows System32. Ein zusätzliches Testprogramm verwendet den echten Playerkern und das unveränderte Produktions-Playbackplugin. Geprüft werden die vier Skins, Einzel- und Mehrfach-Drops über Qt-Ereignisse, Wiedergabe, Pause, Seek, Waveform-Berechnung und Cache, Metadaten, die echte Entfernen-Aktion und das Speichern der Playlist. Ein solcher Qt-Test ersetzt keinen manuellen Explorer-Drag-and-drop-Test.

Die erzeugten Zeitmessungen beschreiben diesen Testlauf. Sie sind noch kein Vergleich belastbarer Perzentile mit der alten Installation. Das Testpaket in einen beschreibbaren eigenen Ordner entpacken. Die bestehende Installation und das persönliche Profil werden für diese Prüfungen nicht benötigt.

## CI

Der Workflow `Windows x64 CMake` baut auf einem frischen Windows-2022-Runner. Nur nach erfolgreichen Tests und Paketprüfungen wird das Testpaket als GitHub-Actions-Artefakt hochgeladen. Testprotokolle werden auch bei Fehlern gesichert. Dies ist ein Testartefakt, kein öffentlich zugesagtes Release für alle bisherigen Plattformen oder Audioformate.
