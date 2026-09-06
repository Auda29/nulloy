# Phase 0: Vergleichsbasis und Build-Befunde

Stand: 6. September 2026. Status: Phase 0 abgeschlossen. Vergleichsbasis, Build, Tests und erste Zeitmessungen sind dokumentiert. Persönliche Kernabläufe und der manuelle Mehrfach-Drop sind bestätigt; die Originaleinstellungen sind wiederhergestellt. Bekannte Ausgangsfehler und Grenzen der Nachweise stehen ausdrücklich im Bericht.

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

Der Nutzer nennt ausdrücklich das Einfügen neuer Tracks per Drag-and-drop, auch mehrerer gleichzeitig, schnelles Öffnen und Schließen sowie schnelles Laden der Waveform als wichtigste Abläufe. Zusätzlich ergeben sich aus der Konfiguration Playlist-Wiederherstellung, Play/Pause und die drei Sprungweiten. Die Belegung umfasst unter anderem X/C/Leertaste für Play/Pause, V für Stop, Z/B für vorherigen/nächsten Titel sowie F11 für Vollbild.

## Getrennte Referenz und Datenschutz

Unter `.phase0/reference/installed-0.9.9` liegt eine vollständige Kopie der installierten Anwendung. Einstellungen, Playlist und Waveform-Daten wurden gesichert. Zwei MP3-Dateien wurden als `reference-1.mp3` und `reference-2.mp3` in `.phase0/media` kopiert. Die Testplaylist verwendet diese Kopien. Quelldateien wurden nicht bearbeitet.

In der Testkopie sind Einzelinstanz und immer im Vordergrund ausgeschaltet, der Start erfolgt pausiert. Diese Abweichungen dienen der getrennten Ausführung. Weitere Fensteränderungen betreffen die Testkopie.

Der gesamte Ordner `.phase0` ist von Git ausgeschlossen. Er enthält persönliche Titel, Pfade, Profile, Medien, Screenshots und vollständige lokale Logs. Diese Inhalte gehören nicht in einen öffentlichen Commit. Die Dateien unter `docs/phase0` enthalten technische Nachweise ohne die persönliche Playlist.

### Wiederhergestellte Originalinstallation

Ein Startversuch über die App-Steuerung öffnete unerwartet auch das registrierte Originalprogramm statt ausschließlich der angegebenen Kopie. Danach wurde jede weitere Testinstanz über den vollständigen Dateipfad gestartet und das Fenster anhand seines Prozesspfads geprüft.

Der anschließende Vergleich von 102 geschützten Originaldateien zeigte genau eine Abweichung: In `Nulloy.cfg` änderte sich `PlaylistRow=47, 0.202023` zu `PlaylistRow=47, 0`. Die restlichen geprüften Dateien waren unverändert. Sicherung und Hashliste liegen unter `.phase0/private`.

Der Nutzer bestätigte anschließend, den Player während der Tests nicht selbst bedient zu haben. Vor der Wiederherstellung war das Original bereits beendet; die Konfiguration entsprach weiterhin exakt der zuvor festgestellten Abweichung. Die gesicherte Originalkonfiguration wurde zurückkopiert. Die anschließende Prüfung bestätigt **102 von 102 Dateien ohne Abweichung**, siehe [Wiederherstellungsnachweis](docs/phase0/original-restoration.json). Der Vorfall ist damit behoben. Weitere Prüfungen verwenden ausschließlich die getrennte Kopie.

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
| Button-Zustände | 21 originale Normal-/Hover-/Pressed-Grafiken unter `.phase0/reference/slim-0.9-assets`; zugehörige Galerie `.phase0/reference/BUTTON_REFERENCE.html` und versionierte Prüfsummen |
| Waveform-Klick während Pause | `14-waveform-click-paused`; Slider verändert, Zeittext nicht unmittelbar aktualisiert |
| Leertaste und pausierter Sprung | `16-space-shortcut` zeigt Pause bei 0:31; `17-shift-right-paused` weiterhin 0:31; `18-resumed-after-jump` laufende Wiedergabe bei 0:42. Play/Pause ist damit beobachtet, die exakte Sprungweite wegen verstrichener Zeit zwischen Aktionen nicht gemessen. |
| Master-Build | `20-upstream-built-main`, `21-upstream-built-after-play` |

`09-maximized` ohne Zusatz `testcopy` zeigt versehentlich die Originalinstanz. Diese Aufnahme ist keine Testreferenz und darf nicht als solche verglichen werden. Die frühen Sprungversuche `04-*` und `11-jump5` sind durch die nachfolgenden Messungen ergänzt, ohne den unveränderten Zeittext während Pause als Fehler zu bewerten.

### Ergänzende Shortcut-Messungen

Alle sechs Sprungbefehle wurden anschließend während laufender Wiedergabe an der getrennten 0.9.9-Kopie geprüft. Die [Beobachtungen](docs/phase0/shortcut-observations.json) enthalten die sichtbaren Zeiten vor und nach dem Tastendruck sowie die dazwischen vergangene Wandzeit. Aus der Positionsänderung abzüglich Wandzeit ergeben sich folgende Werte:

| Befehl | Erwarteter Sprung | Beobachteter Sprung, gerundet |
|---|---:|---:|
| Shift + Rechts | +5 s | +4,2 s |
| Rechts | +30 s | +29,7 s |
| Strg + Links | −100 s | −100,6 s |
| Strg + Rechts | +100 s | +99,3 s |
| Links | −30 s | −30,3 s |
| Shift + Links | −5 s | −4,6 s |

Die Abweichungen liegen innerhalb der sekundengenauen Anzeige und asynchronen UI-Abfrage. Dies bestätigt Richtung und Größenordnung der konfigurierten Sprünge, keine samplegenaue Seek-Präzision. B wechselt zur zweiten Testdatei, Z zurück zur ersten; die Bilder `22-next-key` und `23-prev-key` belegen die Titelwechsel.

V stoppt die Wiedergabe und setzt den Slider an den Anfang. Der Zeittext zeigt zunächst noch die vorherige Position. X startet danach wieder am Titelanfang; C pausiert. Die Aufnahmen `24-stop-key`, `25-play-x-after-stop` und `26-pause-c` halten diese Zustände fest. Zusammen mit dem vorherigen Leertastentest sind damit die konfigurierten Grundbefehle geprüft.

Die sieben vorhandenen Pressed-Bilder sowie Form und Skript sind zusätzlich über [SHA-256](docs/phase0/pressed-assets.json) identifiziert. Die CSS-Zuordnungen stehen direkt in der gesicherten `form.ui`; das Skript wechselt im Spielzustand auf `pause-press.png`. Die vollständige [Zustandsreferenz](docs/phase0/button-reference-manifest.json) umfasst 21 originale PNG-Dateien. Die lokale Galerie `.phase0/reference/BUTTON_REFERENCE.html` zeigt sie ohne Bildänderungen in natürlicher Größe nebeneinander und nennt Urheber und Lizenz.

Eine zusätzliche Live-Gesamtfensteraufnahme mit gehaltenem Mausdruck wurde zuvor zu streng als eigenes Abschlusskriterium geführt. Der Migrationsplan verlangt Referenzbilder der Zustände. Dafür liegen die tatsächlich verwendeten Originalgrafiken mit ihrer nachgewiesenen Skin-Zuordnung vor. Die Galerie ist ausdrücklich kein Live-Screenshot und belegt keine Ereignisfolge unter Qt 6. Dessen tatsächliches Hover-/Pressed-Verhalten bleibt Bestandteil der vorgesehenen Skin- und Laufzeitvergleiche in Phase 1 und 3.

## Persönliche Kernabläufe: Drop und Geschwindigkeit

### Einzel- und Mehrfach-Drop

Der neue [Qt-Integrationstest](tests/testFileDrop.cpp) schickt externe `text/uri-list`-Daten durch DragEnter-, DragMove- und Drop-Events an das echte Playlist-Widget. Er prüft jeweils einen beziehungsweise zwei Tracks in einer leeren und einer bereits vorhandenen Playlist. Dateipfade mit Leerzeichen und Umlaut, Reihenfolge, erhaltene bestehende Einträge und weiter vorhandene Quelldateien gehören zu den Prüfungen.

Alle vier Fälle bestehen. QtTest meldet einschließlich Initialisierung und Abschluss **6 bestanden, 0 fehlgeschlagen**, siehe [Testergebnis](docs/phase0/testFileDrop.txt). Das ist ein gezielter neuer Referenztest gegen den gebauten Master auf Qt 5.15.19. Die zwei unveränderten Upstream-Testprogramme und ihre bereits dokumentierten Fehler bleiben davon getrennt.

Die App-Steuerung konnte den tatsächlichen Explorer-Drop nicht selbst ausführen, weil sie Drag-Ziele außerhalb des Quellfensters beziehungsweise über einem anderen Prozess ablehnt. Der Nutzer führte den vorbereiteten Mehrfach-Drop anschließend in der 0.9.9-Testkopie durch und bestätigte den Erfolg. Nach dem Schließen enthält die gespeicherte Playlist sechs Einträge, `reference-1.mp3` und `reference-2.mp3` jeweils dreimal. Zuvor waren zwei Einträge vorhanden. Damit sind hinzugefügte Dateien und ihre Persistenz belegt. Die Anzahl der einzelnen Drag-Gesten wurde nicht aufgezeichnet. Der [manuelle Nachweis](docs/phase0/manual-drop-verification.json) hält Bestätigung, gespeicherte Einträge und Playlist-Prüfsumme fest. Dieser Nachweis ergänzt den Qt-Test um die tatsächliche Bedienung über Explorer.

Für die Wiederholung des zusätzlichen Tests werden `tests/testFileDrop.cpp` und `tests/testFileDrop.pro` aus diesem Arbeitsstand in das `tests`-Verzeichnis eines über `build-baseline.ps1` vorbereiteten Builds kopiert. Mit derselben dokumentierten MSYS2-Umgebung dort `qmake-qt5 testFileDrop.pro -o Makefile.FileDrop` und `mingw32-make -f Makefile.FileDrop -j4` ausführen. Danach aus dem Build-Hauptverzeichnis `testFileDrop.exe -o 'filedrop-result.txt,txt'` starten. Die bestehenden WAV-Fixtures und das GStreamer-Testplugin mit `fakesink` werden weiterverwendet. Der ursprüngliche Baseline-Helfer exportiert bewusst den festgelegten Upstream-Commit und enthält diesen später ergänzten Test daher nicht automatisch.

### Erste Zeitmessungen der installierten Referenzkopie

Gemessen wurde die unveränderte x86-Anwendung 0.9.9 mit ihrem mitgelieferten Qt 5.15.2. Testdatei war `reference-1.mp3`, 3:19 Minuten, 7.993.594 Bytes, 320 kbit/s und 44,1 kHz. Es gab je einen Lauf mit leerem und vorhandenem Nulloy-Waveform-Cache. Der Windows-Dateicache wurde nicht geleert. Die Ergebnisse sind erste Referenzwerte, keine belastbaren Perzentile oder Aussagen über alle Medien und Playlistgrößen.

| Messpunkt | Leerer Nulloy-Cache | Vorhandener Nulloy-Cache |
|---|---:|---:|
| Startaufruf bis Windows-Eingabebereitschaft | 568 ms | 505 ms |
| Startaufruf bis neue, nicht leere Peaks-Datei | 1.465 ms | Nicht anwendbar, Datei vorhanden |
| Schließaufruf über die App-Steuerung bis Prozessende | 186 ms | 234 ms |

Die [Rohwerte](docs/phase0/reference-timings.json) enthalten UTC-Zeitpunkte und Messdefinitionen. Der [Messhelfer](tools/phase0/measure-reference.ps1) arbeitet ausschließlich mit der privaten Referenzkopie und sichert deren alten Peaks-Cache vor einer Kaltmessung. Beispiele:

```powershell
.\tools\phase0\measure-reference.ps1 -RunName eigener-kaltlauf -ColdWaveform
.\tools\phase0\measure-reference.ps1 -RunName eigener-warmlauf
```

Die Kopie muss vor jedem Lauf geschlossen sein. Nach Erscheinen der Messwerte wird sie innerhalb von 60 Sekunden normal über ihre Oberfläche geschlossen, damit der Helfer das Prozessende protokollieren kann. Die Zeit des tatsächlichen Schließaufrufs muss zusätzlich erfasst werden; sie ist kein vom Helfer ausgelöster automatischer Klick.

`WaitForInputIdle` beweist keine vollständig gezeichnete Oberfläche. Die Peaks-Datei ist ein Näherungswert für die abgeschlossene Berechnung, kein Frame-Zeitstempel. Der betreffende Cache-Code ist zwischen Tag 0.9.9 und dem untersuchten Master unverändert und speichert nur abgeschlossene Peaks. Die erzeugte Datei wurde zusätzlich erfolgreich dekomprimiert; deklarierte und tatsächliche Nutzdatenlänge betragen jeweils 17.295 Bytes. `27-cold-waveform` und `28-warm-waveform` zeigen danach die vollständige Waveform. Die Schließzeiten enthalten den Aufrufweg der App-Steuerung und sind deshalb keine isolierten internen Shutdown-Zeiten.

Vor einer Migrationsabnahme werden dieselben Messpunkte mit mehreren Wiederholungen, längeren Tracks und einer repräsentativen großen Playlist verglichen. Nulloy-Cache, Windows-Dateicache und laufende Waveform-Berechnung beim Beenden müssen getrennt betrachtet werden. Die heutigen Einzelmessungen legen noch keine verbindliche Regressionstoleranz fest.

## Abschlusskriterien und nächste Entscheidung

Quellbasis, laufende Originalkopie, Toolchain, Testprofil und bestehende Fehler sind dokumentiert. Die nächste technische Etappe bleibt der Qt-6-Skin-Prototyp mit Slim als erster Referenz. Ein vollständiger Rust-Rewrite wurde nicht beschlossen.

Die Abnahmekriterien von Phase 0 sind erfüllt. Die zwei vorhandenen Testfehler und die Auffälligkeit im Master-Build werden als ausdrücklich bekannte Ausgangsfehler in die nächsten Phasen übernommen. Das ist keine Freigabe eines neuen Player-Releases. Die Referenz bleibt die installierte Version 0.9.9; die nächste Arbeit ist der Qt-6-Skin-Prototyp.

### Abnahmeprüfung gegen den Plan

| Anforderung aus Phase 0 | Nachweis | Stand |
|---|---|---|
| Lokale Arbeitskopie, vollständige Historie, Dokumente erhalten | Git-Branch und Quellstand; Plan und Bericht versioniert | Erfüllt |
| origin, upstream, codex-Arbeitsbranch | Lokale Git-Konfiguration | Erfüllt |
| Installierte Version, Skin, Profil, Backend, Windows, DPI | Tatsächliche Installation, Profilkopie, GUI und Display-Probe | Erfüllt |
| Getrennte Installation, Profil-, Playlist- und Medienkopien | `.phase0/reference`, `.phase0/private`, `.phase0/media`; Wiederherstellungsnachweis | Erfüllt; Originaldateien wieder vollständig hashgleich |
| Originalcode mit dokumentierter Toolchain bauen | Erfolgreicher Erstbuild und Wiederholung über Build-Helfer; 340 Dateien bytegleich zum Archiv | Erfüllt mit dokumentierten Windows-Workarounds |
| Vorhandene Tests ausführen | Zwei Testprogramme, unabhängiger Neubuild mit denselben Ergebnissen | Erfüllt; zwei Baseline-Fehler offen dokumentiert |
| UI-Zustände und Bedienabläufe erfassen | Screenshots, Shortcut-Messungen, 21 Original-Buttonbilder mit Skin-Zuordnung, ergänzter Qt-Drop-Test und bestätigter Explorer-Drop | Erfüllt; Ressourcenreferenz und Live-Nachweise sind getrennt gekennzeichnet |
| Abweichung zwischen Installation und Commit bewerten | Vergleich mit Tag 0.9.9; Bedienreferenz ausdrücklich festgelegt | Erfüllt |
| Persönliche Kernabläufe bekannt | Vom Nutzer ausdrücklich genannt; Drop-Test und erste Geschwindigkeitsmessungen ergänzt | Erfüllt |

Die vorhandenen Build-Workarounds, Baseline-Testfehler, Metadatenauffälligkeit und Messgrenzen bleiben im Bericht erhalten. Sie werden bei späteren Vergleichen nicht stillschweigend als behobene Fehler oder erfolgreiche Release-Abnahme behandelt.
