# Portabler NulloyFork

Das Testpaket heißt `NulloyFork-0.10.0-alpha.2-windows-x64.zip`.
Es stammt aus dem [Community-Fork](https://github.com/Auda29/nulloy).
Es ist keine offizielle Nulloy-Veröffentlichung. Die vorhandenen Skins bleiben unverändert.

## Start und Daten

Das ZIP vollständig in einen beschreibbaren Ordner entpacken und `NulloyFork.exe` starten.
Der Unterordner `Data` enthält `NulloyFork.cfg`, `NulloyFork.m3u`, den Waveform-Cache
und den GStreamer-Cache. Zum Umziehen den gesamten Programmordner bei geschlossenem
Player kopieren. Medien außerhalb dieses Ordners müssen weiterhin erreichbar sein.
Ein schreibgeschützter Installationsordner wird für diesen portablen Build nicht unterstützt.

Die Einzelinstanz-Zuordnung verwendet den vollständigen EXE-Pfad. Ein zweiter Aufruf
derselben Kopie übergibt Dateien an deren laufende Instanz. Zwei getrennte portable
Ordner können gleichzeitig laufen. Die Originalinstallation und ihr Profil werden
nicht automatisch übernommen. Globale Hotkeys können weiterhin nur von einer
Anwendung gleichzeitig registriert werden.

Automatische Upstream-Updates sind abgeschaltet. Ein eigener Update-Kanal besteht
noch nicht. Testpakete werden manuell ausgetauscht; `Data` vorher sichern.

## Alte Einstellungen übernehmen

Zum ersten Test genügt ein frisches Profil und Drag-and-drop eigener Titel.
Für eine Übernahme zuerst Kopien der bisherigen `.cfg` und `.m3u` anlegen.
Den neuen Player schließen und eine frische Extraktion verwenden:

```powershell
python tools/phase4/import-profile.py --settings "D:/Profilkopie/Nulloy.cfg" --playlist "D:/Profilkopie/Nulloy.m3u" --destination "D:/Test/NulloyFork"
```

Enthält die Playlist relative Pfade, zusätzlich `--playlist-base` mit dem Verzeichnis
der ursprünglichen Playlist angeben. Der Import schreibt nur in das neue `Data` und
überschreibt kein vorhandenes Profil. Der alte Waveform-Cache wird nicht kopiert,
da seine Schlüssel vom Profilverzeichnis abhängen. Er wird beim Abspielen neu aufgebaut.

## Erststart

Das Paket enthält einen vorbereiteten GStreamer-Cache mit relativen Plugin-Pfaden.
Alle bisher mitgelieferten GStreamer-Module bleiben enthalten. Der Player verwendet
seinen Programmordner als Arbeitsverzeichnis; CLI-Dateipfade werden zuvor im
Aufrufverzeichnis aufgelöst, auch bei Übergabe an eine laufende Instanz.

GStreamer prüft den Cache weiterhin. Fehlt er, ist er beschädigt oder ändern sich
Plugin-Dateien, wird er neu aufgebaut. Dabei kann der Start wieder mehrere Sekunden
dauern. Entpacker, die Dateizeitstempel verwerfen, und andere Zeitzonen können diese
zusätzliche Prüfung ebenfalls auslösen. Die Cache-Prüfung wird nicht abgeschaltet.

## Manuelle Abnahme

1. Frisch entpacken, starten, schließen und erneut starten. Erst- und Folgestart vergleichen.
2. Einen Titel, danach mehrere Titel gleichzeitig per Drag-and-drop hinzufügen.
3. Zwischen Titeln wechseln, Waveform prüfen, suchen und während der Berechnung schließen.
4. Über die Taskleiste minimieren und wiederherstellen, Tray und eigene Hotkeys prüfen.
5. Neu starten und prüfen, ob Einstellungen und Playlist erhalten bleiben.
6. Den geschlossenen Programmordner verschieben und erneut starten.

Zusätzlich steht ein Test auf einem separaten Windows-System ohne Entwicklungswerkzeuge
aus. Die automatischen Pakettests verwenden nur Windows System32 im PATH, laufen lokal
aber weiterhin auf dem Entwicklungsrechner.

`build-info.json` nennt Version, Quell-Commit und uncommittete Änderungen beim Paketbau.
`toolchain.txt` enthält die Paketversionen. `package-manifest.json` enthält Dateihashes und
die geprüften x64-Abhängigkeiten. GPL- und Drittanbieter-Lizenztexte liegen bei.
Aktuelle Pakete stehen in den [Fork-Releases](https://github.com/Auda29/nulloy/releases).
