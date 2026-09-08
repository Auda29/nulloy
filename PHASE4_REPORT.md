# Phase 4: Portabler Player

Status: technische Umsetzung und lokale Paketprüfung abgeschlossen. Manuelle Abnahme und separater Windows-Rechner offen. Keine Veröffentlichung.
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

## Abschließendes Testpaket

Quellstand des Pakets: `aafa738632d6e6196c9f95e07b2ea3308ea4294c`, ohne uncommittete Änderungen beim Paketbau.
ZIP: `NulloyFork-0.10.0-alpha.1-windows-x64.zip`.
SHA-256: `9733d197da77a73bb8ba40392df117b49934aca0137e9bfee0e194af0f0ba272`.
EXE-SHA-256: `04c58b54bae9bd921e666f7f9ddfaf0058e5dd3756cd226d679a0b547f732dc8`.

Das endgültige ZIP besteht die vier Skin-Workflows jeweils dreimal in zwei frischen
Extraktionen, die Prozess-/IPC-Prüfung und die sechs Formatprüfungen. 521 Dateihashes
und 236 x64-Binärdateien wurden geprüft. Alle 98 mitgelieferten GStreamer-Module und
die drei externen Skin-Archive sind bytegleich zum Phase-3-Paket. Die vier
Qt-5-Vergleichssuiten bestehen ebenfalls mit Qt 5.15.19.

| Messung am endgültigen ZIP | Fenster sichtbar ab Beginn des Player-Konstruktors |
|---|---:|
| Frische Extraktion 1 | 1.920 ms |
| Folgestarts derselben Kopie | 844 / 543 ms |
| Frische Extraktion 2 | 1.671 ms |
| Folgestarts derselben Kopie | 537 / 547 ms |
| Weitere frische Extraktion für Formatprüfung | 1.888 ms |

Das sind lokale Messungen auf einem laufenden Windows-System. Die Zeit vor dem
Player-Konstruktor, etwa das Laden des Testprogramms und der Qt-DLLs, gehört nicht zu
diesen Zahlen. Die GStreamer-Registry-Prüfung benötigte im zweiten Erststart 23 ms.
Die früher beobachtete Verzögerung vor dem Laden des Containers bleibt als Ausreißer
dokumentiert; eine allgemeine Obergrenze für Erststarts wird nicht behauptet.

Belege: [abschließende Paketprüfung](docs/phase4/evidence/final).
Das Archiv bleibt nach der Prüfung unverändert. Dieser ergänzte Bericht wird neben
das ZIP gelegt; der im ZIP enthaltene Bericht dokumentiert den Stand beim Paketbau.

Für den manuellen Test wurde `.phase4/manual-test-aafa738/NulloyFork` vorbereitet.
Die Einstellungen stammen aus einer unveränderten Kopie des abgenommenen Phase-3-Tests.
Die Playlist beginnt leer. Die neue EXE wurde noch nicht für den Nutzer gestartet.

## Offene Abnahme

Der Alltagstest des konkreten neuen Pakets und ein Start auf einem separaten
Windows-System ohne Entwicklungswerkzeuge stehen aus. Lokale Tests mit bereinigtem
PATH ersetzen diese Prüfung nicht. Entpacker ohne erhaltene Zeitstempel können
weiterhin einen vollständigen Cache-Aufbau auslösen.

Anleitung: [Portabler Test](docs/phase4/PORTABLE.md).
