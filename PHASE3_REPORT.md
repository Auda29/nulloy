# Phase 3: Vollständiger Player mit Qt 6

Stand: 8. September 2026. Der vollständige Windows-x64-Player läuft mit Qt 6.11.2,
GStreamer 1.28.6 und TagLib 2.2.1. Die technische Integration und der manuelle
Test der Kernbedienung sind erfolgreich. Der Nutzer meldet auch unauffällige
Ladezeiten, hat diese aber nicht gemessen. Die ergänzenden Format- und
Tag-Schreibtests bestehen. Der langsame Erststart wurde auf den Aufbau des
GStreamer-Plugin-Caches eingegrenzt, aber noch nicht behoben. Nach der Korrektur
bestätigt der Nutzer auch den Taskleisten-Klicktest. Die funktionale Migration
ist damit abgenommen. Mit seiner Zustimmung wird die Erststart-Optimierung
als offener Punkt in Phase 4 übernommen. Dies ist ein Teststand, keine
veröffentlichte Migrationsversion.

Basis ist Phase 2, Commit `b0ab67a4fa1ae2c4e38f6df85a8a97ea4a9285a2`.
Phase 3 liegt auf `codex/phase-3-qt6-player`. Phase 2 wird dadurch nicht gemergt.

## Umsetzung

- Der erprobte Skript- und Ressourcenadapter liegt unter `src/qt6` und wird sowohl
  vom echten Player als auch vom separaten Skin-Prototyp verwendet. Die
  Fixture-Dienste des Prototyps sind kein Bestandteil des Players.
- QJSEngine ersetzt QtScript. Öffentliche Qt-APIs und temporäre Ressourcenordner
  ersetzen das private Skin-Dateisystem. Die bisherigen Widgets werden direkt
  durch QUiLoader erzeugt.
- Qt-API-Anpassungen betreffen reguläre Ausdrücke, Zeichencodierung, QVariant,
  Mausradereignisse, Icons, globale Hotkeys und Einzelinstanz-Kommunikation.
  Core5Compat bleibt ausschließlich für die bisherigen Tag-Zeichencodierungen
  verfügbar.
- Playback-, Waveform- und TagLib-DLLs werden mit Qt 6 neu gebaut. Der Packer
  prüft AMD64 und lehnt gemischte Qt-Hauptversionen ab.
- JavaScript-Arrays und -Objekte werden vor dem Speichern in native QVariant-Werte
  umgewandelt. Ohne diese Anpassung gingen etwa die Slim-Splitterwerte beim
  Neustart verloren. Ein Test liest sie nach erneuter Initialisierung zurück.
- Das Waveform-Cacheformat verwendet ausdrücklich QDataStream `Qt_5_15`;
  ein Kompatibilitätstest prüft Laden, Speichern und erneutes Laden.
- Der Skriptinterpreter wird vor den Widgets und Plugins zerstört. Temporäre
  Skin-Ressourcen und Schriften werden vor dem Ende der Qt-GUI freigegeben.
- Die Qt-5-Rundung für HiDPI, die bisherige Windows-Standardschrift und die
  Grundpalette bleiben erhalten. Der Native-Skin hatte im Qt-5-Vergleich einen
  bereits vorhandenen Fehler beim Wiederherstellen der Fenstergröße; die in
  Phase 1 für Qt 6 erprobte Korrektur gilt nun für beide Builds.

Alle Dateien unter `src/skins` sind unverändert. Auch die Reihenfolge der
Bedienelemente bleibt erhalten. Qt 6 verwendet von sich aus eine andere
Windows-Standardschrift; die Ursache und die ursprüngliche Herleitung sind im
[Qt-5-Quellcode](https://github.com/qt/qtbase/blob/5.15/src/platformsupport/fontdatabases/windows/qwindowsfontdatabase.cpp#L1918)
nachvollziehbar. Die Anpassung übernimmt diese Systemwerte über öffentliche
Windows-APIs.

## Prüfung

| Prüfung | Lokales Ergebnis |
|---|---|
| Vollständiger Release-Build mit Qt 6.11.2 und Qt 5.15.19 | Beide gebaut |
| TrackInfoReader | 13 Fälle bestanden |
| Playlist-Verhalten | 3 Fälle bestanden |
| Externe Qt-Datei-Drops | 4 Fälle: eine/mehrere Dateien, leere/bestehende Playlist |
| Zusätzliche Migrationstests | 6 Fälle mit Qt 6; 5 mit Qt 5 |
| Gemeinsame Skin-Adapter und ursprüngliche Skins | Alle 4 Testsuiten bestanden |
| Kopiertes Profil | 83 Einstellungswerte unter beiden Qt-Versionen identisch |
| Kopierte Original-Playlist | 48 Einträge einschließlich Nulloy-Feldern unter beiden Builds identisch |
| Entpacktes Qt-6-Paket | Alle vier Skins mit echten Plugins geprüft |
| Bedienablauf im Paket | Drop, Wiedergabe, Pause, Seek, Entfernen, Menü, Fensterzustände, Tray-Anbindung und Dateiübergabe |
| Beenden während Waveform-Berechnung | Laufender Worker vor dem Destruktor nachgewiesen; sauber beendet |
| Private MP3-Kopien | Slim mit echten Metadaten, Waveform und Wiedergabe geprüft; Ausgabe stumm |
| DLL-Prüfung | 235 AMD64-Dateien, keine Qt-5-Abhängigkeit im Qt-6-Paket |
| Skalierung | Alle vier Paket-Skins zusätzlich mit Faktor 2 geprüft; logische Fenstermaße bleiben erhalten |
| Manueller Test des Nutzers | Die vorgeschlagenen Kerntests erfolgreich, auch Ladezeiten subjektiv unauffällig |

Die Migrationstests umfassen Einstellungen aus einer älteren UTF-8-INI,
M3U-Zusatzfelder, den Waveform-Cache, Unicode-IPC zwischen zwei Prozessen,
Windows-Hotkey-Registrierung und Zustellung an den eigenen nativen Eventfilter.
Der zusätzliche Qt-6-Fall betrifft persistierte JavaScript-Werte.

Die Pakettests verwenden echte Produktions-Plugins aus dem ZIP und einen PATH
mit ausschließlich System32. Der Entpackpfad enthält Leerzeichen und einen
Umlaut. Vor dem Lauf werden ZIP- und Datei-Prüfsummen geprüft. Skriptfehler und
Warnungen über nicht speicherbare QJSValue-Werte führen zum Fehlschlag.

Der Windows-Workflow enthält getrennte Qt-5- und Qt-6-Jobs. Beide Jobs des
[Integrationslaufs 34216854569](https://github.com/Auda29/nulloy/actions/runs/34216854569)
für Commit `367df4110c20022f48729e1668086795d46ba1a3` sind erfolgreich, einschließlich
Paketprüfung und Qt-6-Skin-Prototyp. Die Abschlussänderung ergänzt in beiden Jobs
die nachfolgende Formatprüfung; ihr jeweiliger Status steht im Pull Request.

## Ergänzende Abschlussprüfung

Sechs erzeugte Audioformate bestehen in den entpackten Qt-5- und Qt-6-Paketen den vollständigen
Bedienablauf: WAV, MP3, FLAC, Ogg/Vorbis, Opus und WavPack. Vor der Wiedergabe
schreibt der Test Titel, Künstler, Album und Titelnummer, öffnet die Datei neu
und vergleicht die Werte. Dazu gehören Umlaute und japanische Zeichen.
Private Musikdateien werden dafür nicht verwendet.

Dabei fiel ein vorhandener Fehler in der TagLib-Anbindung auf. Im UTF-8-Modus
wurde ein bereits dekodierter Unicode-Text zunächst verlustbehaftet nach Latin-1
konvertiert und danach erneut als UTF-8 gelesen. Der Fix übernimmt den von
TagLib dekodierten Text direkt. Explizit ausgewählte ältere Zeichencodierungen
behalten ihre bisherige Behandlung. Die sechs Pakettests schützen den Fix
gegen Regressionen. AAC/M4A, AIFF und weitere Formate sind nicht abgedeckt.
Die erzeugte VBR-MP3 enthält einen Xing-Header für Dauer und Seek. Ohne diesen
Header lieferte der Qt-5-Vergleich zunächst eine abweichende Dauerschätzung;
erst nach rund neun Sekunden passte sie. Solche MP3-Dateien sind damit keine
Bestätigung einer sofort korrekten Daueranzeige.

Der Menütest beobachtet jetzt das tatsächliche Anzeigen eines gefüllten Menüs.
Die frühere Prüfung nach einer festen Verzögerung konnte fehlschlagen, wenn
der Desktop-Fokus das bereits geöffnete Menü zwischenzeitlich schloss.
Mit der Anpassung bestehen alle vier Skins in jeweils drei aufeinanderfolgenden
Paketläufen.

Das anschließend geprüfte Paket hat SHA-256
`8af2f3324c42f428e3dfffda34275afbbe769b60d4fbf277699fe357a1e4395a`.
Die ursprüngliche manuelle Nutzerabnahme bleibt dem älteren Paket zugeordnet.
Neue Belege liegen unter [evidence/closure](docs/phase3/evidence/closure).

## Manueller Test

Der Nutzer hat die separate Qt-6-Testversion aus
`.phase3/manual-test-89375765/Nulloy` getestet und den vorgeschlagenen Ablauf als
erfolgreich zurückgemeldet. Dieser umfasste einzelne und mehrere Dateien per
Drag-and-drop, Wiedergabe, Pause, Seek, Waveform-Laden, Schließen und erneutes
Öffnen sowie den Vergleich der bisherigen Oberfläche und Bedienung.

Auch die Ladezeiten erschienen ihm unauffällig. Exakte Zeiten hat er ausdrücklich
nicht gemessen. Damit ist die persönliche Kernbedienung für dieses Paket
bestätigt. Die Rückmeldung belegt keine bestimmte Zeitgrenze und klärt nicht,
ob der zuvor beobachtete langsame Erststart aus einem frisch entpackten Ordner
behoben ist.

Die Rückmeldung ist in [manual-test.json](docs/phase3/evidence/manual-test.json)
dem geprüften Paket zugeordnet. In der anschließenden Windows-Prüfung meldet der
Nutzer alle angefragten Punkte als erfolgreich, mit einer Ausnahme: Ein Klick
auf das Taskleisten-Symbol stellt das Fenster wieder her, minimiert es aber
nicht. Details zum verwendeten Monitoraufbau wurden nicht angegeben.

### Korrektur für den Taskleisten-Klick

Der neue Pakettest reproduziert die fehlende native Fähigkeit `WS_MINIMIZEBOX`
am bisherigen Slim-Fenster. Die rahmenlosen Skins übernehmen Fensterflags von
QDialog ohne Minimier-Unterstützung. Vor der Taskleisten-Registrierung setzt der
Player nun für diese Fenster `Qt::WindowMinimizeButtonHint`. Die ursprünglichen
Skin-Dateien und der Native-Skin bleiben unverändert. Qt setzt daraus das native
Minimier-Flag, siehe [Qt-Windows-Implementierung](https://github.com/qt/qtbase/blob/6.11/src/plugins/platforms/windows/qwindowswindow.cpp#L781).

Der Regressionstest prüft die nativen Flags und sendet `SC_MINIMIZE` sowie
`SC_RESTORE` an das eigene Testfenster. Native und Qt-Fensterzustände sowie die
wiederhergestellte Größe müssen übereinstimmen. Alle vier Paket-Skins unter Qt 5 und Qt 6
bestehen. Zusätzlich bestätigt der Nutzer den echten Klicktest mit der
korrigierten Testversion: "jetzt gehts top. also phase 3 abgeschlossen?"

Das korrigierte Qt-6-Testpaket hat SHA-256
`78f90756241a2c2d6186223a46465ce2b5f2e38df9a04851995fbe9b3e94d53e`.
Der separate Testordner `.phase3/manual-test-taskbar-78f90756/Nulloy` enthält
die geprüften Dateien. Alle 516 Datei-Prüfsummen wurden nach dem Entpacken geprüft.

Belege und Nutzer-Rückmeldung: [evidence/taskbar](docs/phase3/evidence/taskbar).
Die früheren grünen CI-Läufe beziehen sich auf den Stand vor dieser Korrektur.
Die Checks des [Phase-3-PRs](https://github.com/Auda29/nulloy/pull/4) prüfen
den jeweils gepushten Abschlussstand.

## Leistung und verbleibende Prüfungen

Die abschließende Messreihe aus einem gemeinsamen Entpackordner ergab für Slim:

| Messung | Erststart | Zweiter Start | Dritter Start |
|---|---:|---:|---:|
| Bis zum sichtbaren Fenster | 13.810 ms | 553 ms | 546 ms |
| Vollständige Waveform, 10-Sekunden-WAV | 311 ms | 555 ms | 265 ms |
| Waveform aus Cache | unter 1 ms | unter 1 ms | unter 1 ms |
| Beenden während neuer Waveform | 20 ms | 21 ms | 29 ms |

Das lokal geprüfte ZIP hat SHA-256
`893757650ddc43ddc91e722385379a70d15e54d487945983e9e8f98c417818a7`.
Beim privaten MP3-Lauf dauerte die vollständige Waveform 358 ms, der Cachezugriff
unter 1 ms und das Beenden während der Berechnung des zweiten Titels 23 ms.

Dies sind lokale Einzelmessungen während der Integration, keine zugesicherten
Grenzwerte. Andere frisch entpackte Läufe lagen beim ersten Start zwischen etwa
8 und 26 Sekunden. Das Abschalten des separaten GStreamer-Scanner-Prozesses
brachte im Vergleichstest keine Verbesserung und wurde nicht übernommen.
Die ergänzende Messung mit Zeitmarken grenzt den Engpass ein: Von 9.443 ms bis
zum sichtbaren Slim-Fenster entfielen rund 7.950 ms auf die erstmalige
GStreamer-Registry-Prüfung und deren Aufbau. Im vorherigen Diagnoselauf waren es
11.905 ms bei 13.522 ms Gesamtzeit. Der zweite und dritte Start der abschließenden
Messreihe benötigten 574 und 556 ms. Die Waveform benötigte 605, 261 und 319 ms,
der Cachezugriff jeweils unter 1 ms und das Beenden 20, 28 und 25 ms.

Damit ist der langsame Abschnitt nachgewiesen. Welche einzelnen Plugins oder
lokalen Dateiprüfungen ihn dominieren, ist nicht geklärt. Eine Optimierung darf
die Formatabdeckung nicht stillschweigend verkleinern. Der Erststart bleibt
deshalb ein offener Leistungspunkt, auch wenn Folgestarts schnell sind.
Der Qt-5-Vergleich zeigt denselben Engpass: 11.612 ms Registry-Aufbau bei
13.446 ms bis zum sichtbaren Fenster. Die Verzögerung tritt somit auch ohne
die Qt-6-Migration in der neuen Paket-Toolchain auf.

Für Phase 4 übernommen:

- Erststart aus einem frisch entpackten Ordner beschleunigen und erneut messen.
  Die Diagnose ist abgeschlossen, die Optimierung nicht. Der Nutzer hat der
  Übernahme als offenem Phase-4-Punkt zugestimmt. Im heruntergeladenen CI-Paket
  vor dem Taskleisten-Fix betrug der erste lokale Start 29.940 ms. Dieser Befund
  gehört ebenfalls zur Ausgangsmessung und bleibt trotz funktionaler Abnahme offen.

Die aktuelle Rückmeldung bezieht sich auf das oben benannte Qt-6-Paket. Die
frühere Bestätigung des Referenzplayers wird dafür nicht herangezogen. Der
Teststand verändert weder die installierte Originalversion noch deren Profil.

Build und manueller Test: [Qt-6-Leitfaden](docs/phase3/BUILD_WINDOWS_QT6.md).
