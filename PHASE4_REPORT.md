# Phase 4: Portabler Player

Status: technische Umsetzung, lokale Paketprüfung und manuelle Nutzerabnahme abgeschlossen. Alpha `v0.10.0-alpha.1` veröffentlicht. Prüfung auf separatem Windows-Rechner offen.
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
Zum Zeitpunkt der lokalen Paketprüfung war die erweiterte CI noch nicht auf GitHub ausgeführt. Die späteren erfolgreichen CI- und Release-Läufe sind unten dokumentiert.

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
Die Playlist war für den Test zunächst leer.

## Manuelle Nutzerabnahme

Der Nutzer hat das bereitgestellte Phase-4-Paket am 8. September 2026 abgenommen:

> hab ich abgenommen mir ist im test nichts aufgefallen

Die Rückmeldung bezieht sich auf den zuvor angefragten Test von Drag-and-drop mit
mehreren Tracks, Waveform, Schließen/Neustart und Taskleisten-Minimierung. Es wurden
keine Auffälligkeiten gemeldet. Sie ist eine qualitative Abnahme, keine zusätzliche
Zeitmessung oder gesondert nachgewiesene Langzeitprüfung.

Paketzuordnung und Rückmeldung: [Nutzerabnahme](docs/phase4/evidence/final/user-acceptance.json).

## Alpha-Veröffentlichung

Am 8. September 2026 wurde [v0.10.0-alpha.1](https://github.com/Auda29/nulloy/releases/tag/v0.10.0-alpha.1)
als öffentliches GitHub-Prerelease veröffentlicht. Der annotierte Tag verweist auf
`9a68db416f6689043c5a9423b768e5e4feaa5db9` und löste den
[erfolgreichen Release-Workflow](https://github.com/Auda29/nulloy/actions/runs/34230352711) aus.
Beide Windows-Varianten, alle Paketprüfungen und die Veröffentlichung bestanden.

Der CI-Build des veröffentlichten Windows-ZIPs hat den SHA-256
`0f3632ce3db6d713879033d6f1519e58b3cd327a107406105207b09b6f271972`.
Alle sechs Release-Dateien wurden ohne Anmeldung erneut heruntergeladen. Die
Prüfsummen, 490 Paketdateien, 236 x64-Binärdateien, der Quellcode-Snapshot und die
Commit-Zuordnung stimmen. Beleg: [öffentliche Downloadprüfung](docs/releases/v0.10.0-alpha.1.json).
Die unterschiedliche Dateizahl zum lokalen Paket betrifft die CI-Paketierung;
dieses Release hat eigene Prüfnachweise und ersetzt nicht die frühere Nutzerabnahme.

Der Workflow verwendet für die Herkunftsprüfung dieselbe Git-Installation wie beim
Checkout. Die vorher zusätzlich installierte MSYS2-Git-Umgebung hatte den Quellstand
als verändert gemeldet. Der Release-Build weist einen unveränderten Quellstand aus.
Weitere Releases sind in [RELEASING.md](docs/RELEASING.md) beschrieben.

## Offene Prüfung

Ein Start auf einem separaten Windows-System ohne Entwicklungswerkzeuge steht
weiterhin aus. Die Nutzerabnahme bestätigt keinen Wechsel auf einen anderen Rechner.
Lokale Tests mit bereinigtem PATH ersetzen diese Prüfung nicht.
Entpacker ohne erhaltene Zeitstempel können
weiterhin einen vollständigen Cache-Aufbau auslösen.

Anleitung: [Portabler Test](docs/phase4/PORTABLE.md).
