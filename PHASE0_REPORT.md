# Phase 0: Vergleichsbasis und Build-Befunde

Stand: 6. September 2026. Status: technische Bestandsaufnahme durchgeführt, Abschluss noch offen. Zur vollständigen Abnahme fehlen die Bestätigung der persönlichen Kernabläufe und die Entscheidung zur Wiederherstellung der unten beschriebenen Originaleinstellung.

## Quellstand und Vergleichsentscheidung

Der Fork [Auda29/nulloy](https://github.com/Auda29/nulloy) übernimmt die Upstream-Historie. `origin` verweist auf diesen Fork, `upstream` auf `https://github.com/nulloy/nulloy.git`. Die lokale Arbeitsbranch heißt `codex/phase-0-baseline` und basiert auf `f4eddff8be2538526f3019f57f56c68db3c8c267`.

Die täglich genutzte Installation ist Nulloy 0.9.9 mit Qt 5.15.2, beide x86. Sie bestimmt das zu erhaltende UI- und Bedienverhalten. Der untersuchte Master enthält 16 weitere Commits gegenüber Tag 0.9.9. Diese betreffen unter anderem Aktionen und Tastenkürzel, die Papierkorb-Bestätigung, Metadaten, Tag-Editor, Update-Prüfung und Übersetzungen. Skin-Ressourcen, ScriptEngine, SkinLoader und WaveformPeaks sind gegenüber dem Tag unverändert.

Master ist die technische Ausgangsbasis, aber Änderungen nach 0.9.9 werden nicht automatisch zum gewünschten Bedienverhalten erklärt. Besonders die Aufteilung von Play-, Pause- und Play/Pause-Aktionen muss später mit der installierten Referenz verglichen werden.

Die [Integritätsprüfung](docs/phase0/source-integrity.json) vergleicht alle 340 regulären Dateien des Git-Archivs mit dem gebauten Quellbaum. Keine davon wurde verändert. Im Arbeitsbaum ist von diesen Dateien ausschließlich `.gitignore` um den lokalen Evidenzordner ergänzt. Es gibt keine Implementierung einer Qt-6-, CMake- oder Rust-Migration.

## Tatsächlich verwendete Umgebung

| Merkmal | Festgestellter Wert |
|---|---|
| System | Windows 11 Home, 10.0.22631, 64 Bit |
| Originalprogramm | `C:\Program Files (x86)\Nulloy\Nulloy.exe` |
| Aktives Profil | `E:\Roaming\Nulloy` |
| Skin und Stil | Slim 0.9, Fusion |
| Sprache | Deutsch; einzelne Texte bleiben Englisch |
| Wiedergabe und Waveform | GStreamer |
| Tags und Cover | TagLib |
| Sprungweiten | 5, 30 und 100 Sekunden |
| Weitere Einstellungen | Shuffle an, Repeat aus, Lautstärke 0,93, Playlist-Wiederherstellung an |
| Fensterverhalten | Immer im Vordergrund an, Tray aus, Einzelinstanz an |
| Aktualisierung | Automatische Update-Prüfung aus |
| Bildschirme | Zwei Displays mit jeweils 1920 × 1080; 144 und 75 Hz |
| Skalierung | Logische DPI 110, entsprechend etwa 114,6 % von 96 DPI; Qt meldet Device-Pixel-Ratio 1 |

Die Anzeigeangaben stammen aus einer ausgeführten Qt-Abfrage, siehe [Messwerte](docs/phase0/display-environment.json) und [Probe](tools/phase0/display-probe.cpp). Device-Pixel-Ratio 1 bedeutet hier nicht, dass Windows auf 100 % steht. Ältere Profile unter anderen Pfaden wurden gefunden, aber nicht als aktive Konfiguration verwendet.

Aus der Konfiguration ergeben sich als zu prüfende Abläufe das Öffnen lokaler Audiodateien, Playlist-Wiederherstellung, Play/Pause, Waveform-Seeking und die drei Sprungweiten. Die persönliche Gewichtung dieser Abläufe ist noch nicht vom Nutzer bestätigt. Die Belegung umfasst unter anderem X/C/Leertaste für Play/Pause, V für Stop, Z/B für vorherigen/nächsten Titel sowie F11 für Vollbild.

## Getrennte Referenz und Datenschutz

Unter `.phase0/reference/installed-0.9.9` liegt eine vollständige Kopie der installierten Anwendung. Einstellungen, Playlist und Waveform-Daten wurden gesichert. Zwei MP3-Dateien wurden als `reference-1.mp3` und `reference-2.mp3` in `.phase0/media` kopiert. Die Testplaylist verwendet diese Kopien. Quelldateien wurden nicht bearbeitet.

In der Testkopie sind Einzelinstanz und immer im Vordergrund ausgeschaltet, der Start erfolgt pausiert. Diese Abweichungen dienen der getrennten Ausführung. Weitere Fensteränderungen betreffen die Testkopie.

Der gesamte Ordner `.phase0` ist von Git ausgeschlossen. Er enthält persönliche Titel, Pfade, Profile, Medien, Screenshots und vollständige lokale Logs. Diese Inhalte gehören nicht in einen öffentlichen Commit. Die Dateien unter `docs/phase0` enthalten technische Nachweise ohne die persönliche Playlist.

### Offener Vorfall an der Originalinstallation

Ein Startversuch über die App-Steuerung öffnete unerwartet auch das registrierte Originalprogramm statt ausschließlich der angegebenen Kopie. Danach wurde jede weitere Testinstanz über den vollständigen Dateipfad gestartet und das Fenster anhand seines Prozesspfads geprüft.

Der anschließende Vergleich von 102 geschützten Originaldateien zeigte genau eine Abweichung: In `Nulloy.cfg` änderte sich `PlaylistRow=47, 0.202023` zu `PlaylistRow=47, 0`. Die restlichen geprüften Dateien waren unverändert. Sicherung und Hashliste liegen unter `.phase0/private`.

Die abschließende Hashkontrolle nach Schließen der Testkopie bestätigt dieselbe einzelne Dateiabweichung. Beide Testanwendungen sind geschlossen; die Originalinstanz ist weiterhin geöffnet.

Die Originalinstanz wurde nicht zwangsweise beendet und ihre Konfiguration nicht blind zurückgeschrieben. Es ist noch offen, ob der Nutzer sie zwischenzeitlich selbst bedient hat. Die Rückfrage dazu bleibt erforderlich, damit eine Wiederherstellung keine neueren Nutzereingaben überschreibt. Bis zur Klärung wird die Originalumgebung ausdrücklich nicht als unverändert abgenommen.

## Werkzeugkette und Build

Die Werkzeuge liegen isoliert unter `E:\Temp\NulloyPhase0-01a0773b\msys64`. Es wurde keine globale PATH-Einstellung geändert. Der erste erfolgreiche Build liegt unter `E:\Temp\NulloyPhase0-01a0773b\source`.

| Bestandteil | Verwendetes Paket |
|---|---|
| Qt Base | 5.15.19+kde+r96-1 |
| Qt Script | 5.15.19-1 |
| Qt SVG | 5.15.19+kde+r5-1 |
| Qt Tools / WinExtras | jeweils 5.15.19-1 |
| GCC | 16.2.0-3; Qt selbst meldet GCC 16.1.0 als Build-Compiler |
| GStreamer / Base / Good | jeweils 1.28.6-1 |
| TagLib | 2.2.1-1 |
| GNU Make | 4.4.1-5 |
| ImageMagick / librsvg | 7.1.2.30-1 / 2.62.3-1 |

Die vollständige Paketliste steht in [msys2-packages.lock.txt](docs/phase0/msys2-packages.lock.txt). Sie ist ein Versionsnachweis, kein selbstständig auflösbares Installations-Lockfile. Die heruntergeladenen Pakete liegen zusätzlich im lokalen Pacman-Cache. Ein späterer Download derselben Versionen ist damit nicht zugesagt.

Das MSYS2-Basisarchiv stammt aus den [offiziellen Installer-Releases](https://github.com/msys2/msys2-installer/releases/tag/nightly-x86_64). Die am Prüftag heruntergeladene Datei wurde gegen die veröffentlichte SHA-256 geprüft: `05cc0c4702cd2c68fdc1991df94e2db1cb9a735f1fbfd78315d3819db7e19238`. Wegen HTTP-429-Antworten wurde ausschließlich die isolierte Mirrorliste auf `https://repo.msys2.org/mingw/$repo/` und ein paralleler Download umgestellt. Paketsignaturprüfungen blieben aktiv.

### Historische Build-Probleme

Der unveränderte Standardaufruf baut in dieser Umgebung nicht ohne Hilfsschritte. Festgestellt wurden:

- MSYS-Pfade wie `/e/Temp/...` werden von nativen qmake/moc-Aufrufen falsch interpretiert. Der Hilfsaufbau schreibt native Laufwerkspfade.
- Ressourcenbefehle mischen Unix- und Windows-Shellsyntax. Skins, Übersetzungen und Icons werden mit denselben Quelldateien explizit erzeugt.
- `src/src.pri` referenziert `winIcons.pri`, während die Datei `winIcon.pri` heißt. Die zusätzliche Einbindung über die Widget-Sammlung ermöglicht den Build trotzdem.
- `actionManager.cpp` verwendet `NWinIcon` ohne die erforderliche Deklaration. Ein ausschließlich im Build-Verzeichnis erzeugter Forced-Include ergänzt den bestehenden Header. Compiler- und moc-Prüfläufe ohne Qt-Includepfade werden dabei ausgenommen.

Der Helfer [build-baseline.ps1](tools/phase0/build-baseline.ps1) exportiert den festgelegten Commit in ein neues Verzeichnis, erzeugt die Ressourcen und baut Anwendung, Plugins und Tests. Er löscht keine vorhandenen Build-Verzeichnisse. Beispiel mit der vorbereiteten Toolchain:

```powershell
.\tools\phase0\build-baseline.ps1 `
  -MsysRoot 'E:\Temp\NulloyPhase0-01a0773b\msys64' `
  -StageRoot 'E:\Temp\NulloyPhase0-01a0773b\neuer-build'
```

Der Helfer wurde mit einem neuen Verzeichnis `repro-build4` erfolgreich vom Git-Archiv bis zu allen drei EXE-Dateien ausgeführt. Die beiden dort neu gebauten Testprogramme liefern erneut 15/0 und 3/2, siehe [TrackInfo-Wiederholung](docs/phase0/repro-trackinfo.txt) und [Playlist-Wiederholung](docs/phase0/repro-playlist.txt).

Der Helfer erzeugt einen Testbuild mit `_TESTS_`. Dessen GStreamer-Plugin verwendet `fakesink`. Er ist kein normales Wiedergabepaket. Für den getrennten GUI-Lauf wurde das GStreamer-Plugin im ersten Build ohne `_TESTS_` neu kompiliert. Das Testplugin wurde zuvor unter `.phase0/test-build` gesichert.

Der erfolgreiche Erstbuild ist x64, die installierte Referenz x86. [Binärgrößen, PE-Architektur und SHA-256](docs/phase0/binary-manifest.json) sind festgehalten. Dies ist ein Build- und Laufzeitnachweis auf dem Entwicklungsrechner, keine Paketabnahme auf einem Rechner ohne Toolchain.

## Tests und beobachtetes Laufzeitverhalten

| Prüfung | Ergebnis |
|---|---|
| TrackInfoReader | 15 bestanden einschließlich Initialisierung und Abschluss, 0 fehlgeschlagen; 13 eigentliche Testfälle |
| PlaylistWidget | 3 bestanden einschließlich Initialisierung und Abschluss, 2 fehlgeschlagen |
| PlaylistWidget mit Windows-Plattform statt offscreen | Dieselben zwei Fehler; kein ausschließlich durch offscreen verursachter Befund |
| Originalkopie | Start, Plugin-Laden, Playlist, berechnete Waveform, laufende Wiedergabeanzeige und Pause beobachtet |
| Neu gebauter Master | Start und Plugin-Laden erfolgreich, Waveform wird berechnet und Wiedergabefortschritt sichtbar |
| Metadatenanzeige im neuen Build | Titel-/Zeit-/Bitrate-Anzeige teilweise leer; Ursache zwischen Quellstand, Profil und neuen Abhängigkeiten noch nicht isoliert |
| Tatsächliche Audioausgabe | Kein Hörtest durchgeführt; sichtbarer Fortschritt ersetzt diesen Nachweis nicht |

Die unveränderten Testprogramme und ihre Ergebnisse stehen in [TrackInfoReader](docs/phase0/testTrackInfoReader.txt) und [PlaylistWidget unter Windows](docs/phase0/testPlaylistWidget-windows.txt). Die Fehler betreffen `testPlaylistRemoval`, Zeile 83, mit 10 statt 9 Einträgen und `testRepeat`, Zeile 211, mit 10 statt 1 Einträgen. `testAutoPlay` besteht.

Zur Wiederholung im neuen Build-Verzeichnis wird dessen `mingw64\bin` aus der oben genannten MSYS2-Installation vorübergehend dem Prozess-PATH vorangestellt. `QT_PLUGIN_PATH` zeigt auf `mingw64\share\qt5\plugins`, `GST_PLUGIN_SYSTEM_PATH_1_0` auf `mingw64\lib\gstreamer-1.0` und `QT_QPA_PLATFORM` steht auf `windows`. Dann im Build-Verzeichnis ausführen:

```powershell
.\testTrackInfoReader.exe -o 'trackinfo.txt,txt'
.\testPlaylistWidget.exe -o 'playlist.txt,txt'
```

Die Ausgabeoption muss jeweils ein einzelnes Argument sein. Die erwarteten Exitcodes dieser Baseline sind 0 und 2. Die WAV-Testdateien erzeugt der vorhandene qmake-Testaufbau selbst.

Die Quellcodeprüfung liefert eine plausible Erklärung: Die Tests erzeugen das Playlist-Widget direkt. Die Delete-Aktion wurde seit 0.9.9 aus dessen Konstruktor in den ActionManager verschoben. Die Tests wurden daran nicht angepasst. Das erklärt die ausbleibende Entfernung, ist aber kein Nachweis, dass die vollständige Anwendung dieselbe Fehlfunktion hat. Die Fehler wurden in Phase 0 weder kaschiert noch repariert.

### Gesicherte UI-Referenzen

Alle genannten Dateien liegen privat unter `.phase0/screenshots`. Die zugehörigen JSON-Dateien dokumentieren die Fensterzuordnung.

| Zustand | Nachweis und Grenze |
|---|---|
| Hauptfenster / laufender Track / Pause | `01-main-paused`, `02-track-open-playing`, `03-waveform-paused` |
| Menü | `05-main-menu`, einschließlich zusätzlicher Menüfenster |
| Einstellungen und Kürzel | `06-preferences-general`, `07-preferences-shortcuts` |
| Vollbild | `15-fullscreen-visible` zeigt die tatsächlich sichtbare Vollbildansicht; ältere Aufnahme `08-fullscreen` wegen eingeblendeter Taskleiste nicht für einen pixelgenauen Vergleich verwenden |
| Maximiert / wiederhergestellt / verkleinert | `09-maximized-testcopy`, `12-restored`, `13-resized` |
| Play-Hover | `10-play-hover` |
| Pressed-Grafiken | Originale Slim-0.9-Assets unter `.phase0/reference/slim-0.9-assets`; kein belastbares Live-Bild des gesamten gedrückten Fensters |
| Waveform-Klick während Pause | `14-waveform-click-paused`; Slider verändert, Zeittext nicht unmittelbar aktualisiert |
| Leertaste und pausierter Sprung | `16-space-shortcut` zeigt Pause bei 0:31; `17-shift-right-paused` weiterhin 0:31; `18-resumed-after-jump` laufende Wiedergabe bei 0:42. Play/Pause ist damit beobachtet, die exakte Sprungweite wegen verstrichener Zeit zwischen Aktionen nicht gemessen. |
| Master-Build | `20-upstream-built-main`, `21-upstream-built-after-play` |

`09-maximized` ohne Zusatz `testcopy` zeigt versehentlich die Originalinstanz. Diese Aufnahme ist keine Testreferenz und darf nicht als solche verglichen werden. Die Sprungversuche `04-*` und `11-jump5` belegen keine erfolgreiche exakte 5-Sekunden-Änderung. Der sichtbare Zeittext blieb im pausierten Zustand unverändert. Eine vollständige Prüfung der Tastenkürzel steht damit aus.

## Abschlusskriterien und nächste Entscheidung

Quellbasis, laufende Originalkopie, Toolchain, Testprofil und bestehende Fehler sind dokumentiert. Die nächste technische Etappe bleibt der Qt-6-Skin-Prototyp mit Slim als erster Referenz. Ein vollständiger Rust-Rewrite wurde nicht beschlossen.

Vor dem vollständigen Abschluss von Phase 0 bleiben die persönlichen Kernabläufe zu bestätigen, die offenen UI-Aufnahmen und Shortcut-Prüfungen zu vervollständigen sowie die Änderung der Originalposition mit dem Nutzer zu klären. Die zwei vorhandenen Testfehler und die Auffälligkeit im Master-Build dürfen als ausdrücklich bekannte Ausgangsfehler in die nächsten Phasen übernommen werden. Sie gelten nicht als erfolgreiche Funktionsabnahme.
