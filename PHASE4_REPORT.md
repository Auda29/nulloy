# Phase 4: Portabler Player

Status: portable Umsetzung vorhanden, abschließende Paketprüfung läuft. Keine Veröffentlichung.
Branch: `codex/phase-4-portable-player`, Basis `683783cc2d260c92405c8b2b65b0904740c2c46a`.

## Änderungen

- Eigenes portables Preset `windows-portable-x64`, `NulloyFork.exe`, Version `0.10.0-alpha.1`.
- Eigener `Data`-Ordner. Einzelinstanzen bleiben an den vollständigen EXE-Pfad gebunden.
- Vorbereiteter relativer GStreamer-Cache. Dateiprüfung und Wiederaufbau bleiben aktiv.
- CLI-Dateien werden vor dem Wechsel des Arbeitsverzeichnisses und vor IPC aufgelöst.
- Paket mit Quellstand, Abhängigkeiten, Dateihashes, Fork-Hinweis und Lizenztexten.
- Upstream-Updates für portable Fork-Builds beim Konfigurieren ausgeschlossen.
- Importwerkzeug für ausdrücklich ausgewählte Profilkopien ohne Überschreiben vorhandener Profile.

Skins und Anordnung der Bedienelemente wurden nicht verändert.

## Prüfstand

Windows 11, Qt 6.11.2, GStreamer 1.28.6, TagLib 2.2.1, GCC 16.2.0.
Die vollständigen Versionen und Rohbelege liegen unter [docs/phase4/evidence/initial](docs/phase4/evidence/initial).

| Prüfung | Lokales Ergebnis |
|---|---|
| Qt-6-Core | Vier Testsuiten bestanden |
| Portable Oberfläche | Vier Skins, jeweils drei Durchläufe bestanden |
| Formate | WAV, MP3, FLAC, Ogg/Vorbis, Opus, WavPack mit Wiedergabe, Waveform und Unicode-Tag-Roundtrip bestanden |
| Native Fensteraktionen | Minimieren und Wiederherstellen aller Skins bestanden |
| Prozesse | Zwei getrennte portable Kopien gleichzeitig; zweite Datei an passende Instanz übergeben; relative CLI-Pfade und gespeicherte Playlists geprüft |
| Profilimport | Quelldaten unverändert, relative Pfade explizit aufgelöst, vorhandenes Zielprofil geschützt |
| Cache-Rückfall | Fehlender und beschädigter Seed sowie geänderter Plugin-Zeitstempel bei allen vier Skins bestanden |
| Paket | 236 x64-PE-Dateien, einschließlich zusätzlichem `gst-inspect-1.0.exe`; nur System32 im Test-PATH |

Die erste Paketmessung hatte einen Ausreißer von 11.617 ms bis zum sichtbaren Fenster.
Davon lagen 10.529 ms bereits vor der Meldung des geladenen GStreamer-Containers;
die eigentliche Registry-Prüfung brauchte nur 24 ms. Der Grund dieser früheren
Verzögerung ist nicht abschließend nachgewiesen. Dieser Lauf überschnitt sich zeitlich
mit dem Ende der Core-Testreihe und wird nicht als isolierte Vergleichsmessung verwendet.
Eine weitere frische Extraktion für den Formatlauf ergab 1.241 ms beim ersten Start.
Die folgenden Slim-Starts der ersten Messreihe lagen bei 762 und 530 ms.

Ohne Seed dauerte der Fensterstart 9.245 ms, mit beschädigtem Seed 10.110 ms und
nach Änderung eines Plugin-Zeitstempels 2.072 ms. GStreamer baute seinen Cache jeweils
korrekt neu auf. Der beschleunigte Cache ersetzt somit keine Fehlerprüfung.

Für die synthetischen WAV-Dateien lagen Waveform-Folgeladevorgänge unter der
Millisekundenauflösung des Tests. Das Beenden während der Berechnung dauerte in
der ersten Messreihe 17 bis 34 ms. Das ist keine Garantie für beliebige Mediendateien.

Die isolierte GStreamer-Vorprüfung auf diesem Rechner ergab 10,339 Sekunden ohne
Cache und 0,542 Sekunden nach Kopieren in einen anderen Ordner mit erhaltenen Zeitstempeln.
Diese Zahlen beschreiben den Diagnoseprozess, nicht den vollständigen Playerstart.

Das genaue Paket nennt seinen Quellstand in `build-info.json`; die Prüfbelege enthalten
den jeweiligen ZIP-SHA-256. Dokumentations- und Belegcommits können danach folgen.
CI wurde für Phase 4 erweitert, aber noch nicht auf GitHub ausgeführt.

## Offene Abnahme

Der Alltagstest des konkreten neuen Pakets und ein Start auf einem separaten
Windows-System ohne Entwicklungswerkzeuge stehen aus. Lokale Tests mit bereinigtem
PATH ersetzen diese Prüfung nicht. Entpacker ohne erhaltene Zeitstempel können
weiterhin einen vollständigen Cache-Aufbau auslösen.

Anleitung: [Portabler Test](docs/phase4/PORTABLE.md).
