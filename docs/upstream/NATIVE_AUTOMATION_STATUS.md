# Native Automation: Arbeitsstand, keine Paketfreigabe

Snapshot: 2026-09-10T13:38:33Z. Integrationsbasis:
`919468efc32f4d038c96d7276a799794dab2e86e` (PR #27).

## Nachtrag: IPC-Komponententest inzwischen grün

Der unten erhaltene Snapshot beschreibt die früheren Fehlläufe. PR #29 steht
inzwischen auf `9d7de5108f842269ffa2a99048d69577a123d1ac` und bleibt Draft/offen.
[Windows-Lauf 34497432559](https://github.com/Auda29/nulloy/actions/runs/34497432559)
besteht unter Qt5 und Qt6: jeweils sechs Verhaltensfälle plus Init/Cleanup,
keine Fehler oder Skips. Die erfolgreiche Zustellung erfolgt nach tatsächlich
beobachtetem vollständigem Nachrichtenrahmen und zurückgehaltener Bestätigung
(159 ms unter Qt5, 154 ms unter Qt6). Unabhängiger Nachreview und Negativkontrolle
sind [in PR #29 dokumentiert](https://github.com/Auda29/nulloy/pull/29#issuecomment-5621566637).

Der tatsächliche Paket-Buildcommit ist
`5e502fc65aafc9cdfb2db3df615afc19956990b9`; seine Git-Tree-Identität mit dem
genannten PR-Head wurde separat verifiziert. Das ist kein neuer
Explorer-Nachweis und nicht das gemeinsame PR-#15/#16/#24-Abnahmepaket.
Die ursprünglichen negativen Explorer-Belege und ihre Paketzuordnung bleiben
unverändert. Der weiter unten genannte nächste IPC-Testschritt ist historisch;
die echte Explorer-Matrix sowie Papierkorb- und Fensterabnahmen bleiben offen.

## Geltungsbereich

Manuelle Nutzertests stehen nicht zur Verfügung. Automatisierte echte native
Tests auf entbehrlichen GitHub-hosted Windows-Runnern sind inzwischen freigegeben.
Die frühere Zurückstellung in `acceptance-baseline.json` ist eine historische
Entscheidung, keine aktuelle Sperre dieser Automation. Die darin dokumentierten
Paketidentitäten und Abnahmezuordnungen bleiben unverändert. Dieser Folgestand
erteilt weder eine Paketfreigabe noch einen Merge nach `master` oder einen Release.

## Getrennte offene Branches

| PR | veröffentlichter Head im Snapshot | Ergebnis / Grenze |
| --- | --- | --- |
| [#28](https://github.com/Auda29/nulloy/pull/28) | `f34c6fd0118a0b2d32f4ff79b127809b7586493e` | Draft mit PR #24 zum Test; enthält PR #29 nicht. [Lauf 34479448157](https://github.com/Auda29/nulloy/actions/runs/34479448157) fehlgeschlagen. Keine vollständige Explorer-Abnahme. |
| [#29](https://github.com/Auda29/nulloy/pull/29) | `a5524cc62dd147835760fd30927a589b1c99f09d` | Separater Draft auf Integration. [Lauf 34483041859](https://github.com/Auda29/nulloy/actions/runs/34483041859) fehlgeschlagen. Disconnect-ohne-Header besteht unter Qt5/Qt6; erzwungener Timeout garantiert keine Nachrichtenübernahme. |

Die Heads sind Branchidentitäten, nicht automatisch die gebauten synthetischen
Mergecommits. Unterstützende PRs verändern die ursprüngliche 80-Issue-/19-PR-
Zählung nicht und schließen kein ursprüngliches Issue.

## Paketgebundener negativer Explorer-Nachweis

[Lauf 34477210965](https://github.com/Auda29/nulloy/actions/runs/34477210965)
belegte nach echter Explorer-Mehrfachauswahl drei Playerhauptfenster. Siehe auch
[Auswertung in PR #28](https://github.com/Auda29/nulloy/pull/28#issuecomment-5618825616).
Die folgenden Werte stammen aus dem heruntergeladenen Probe-Artefakt `result.json`;
sie bezeichnen **diesen fehlgeschlagenen Lauf**, nicht den aktuellen Branchhead.
Die Hashwerte sind hier aus dem Probebericht übernommen; dieser
Dokumentationsnachtrag enthält keine neue lokale ZIP-/EXE-Hashberechnung:

| Identität | Wert |
| --- | --- |
| tatsächlich gebauter Source-Commit | `e3371b2cf8b5c364bdba3aa0c142b9bd2d936e5f` |
| ZIP SHA-256 | `691f8eda18fbb4309450b417ad1991f5ccb7e592ed34ede867af305f86fca232` |
| EXE SHA-256 laut Probe | `fa1a1148d776fb73e554f30990aab83b39bb87599f166277911e3e298654dde6` |
| Ergebnis | `FAIL` |

Der Probebericht meldet `cleanup_verified=true`. Wegen offener Ownership-Befunde
ist dieses Feld allein keine allgemeine Sicherheitsabnahme. Die Probe läuft mit
explizitem Headless-Audio-Fallback; tatsächliche Audioausgabe ist nicht geprüft.

## IPC-Vertrag und offene Nacharbeit

Der neue Rollen-/Startpfad verhindert bei fehlender IPC-Bestätigung den Start
eines weiteren Players. Der zusätzliche Empfangsfix beendet die Leseschleife
bei einem unvollständigen Header statt sie nach Disconnect weiterlaufen zu lassen.
Der alte Review des Rollenhelpers deckt diese zusätzliche Produktionsänderung
nicht ab; ein eigenständiger Reviewabschluss ist hier nicht belegt.

[Windows-Nachweis zu a5524cc](https://github.com/Auda29/nulloy/pull/29#issuecomment-5619561702):
Der Primärprozess beendet sich wieder, aber nach dem erzwungenen Timeout wurde
unter Windows keine Nachricht empfangen. Unter Linux war verspäteter Empfang
beobachtet worden. Fehlende Bestätigung bedeutet daher weder sicher verlorene
noch sicher übernommene Nachricht. Kein blindes Resend und keine Gleichsetzung
von explizitem Fehler mit verlustfreier Dateiöffnung.

Nächste Prüfung: bestätigte verzögerte Zustellung exakt einmal prüfen; den
absichtlichen Fehlerfall synchronisieren und getrennt auf Fehlerexit, keinen
zweiten Player, keine Wiederholung und keinen Hänger prüfen. Danach Windows
Qt5/Qt6 erneut ausführen. Eine grüne Komponentensuite ersetzt die echte
Explorer-Matrix am gemeinsamen Paket nicht.

## Verbleibende Freigabesperren

- **PR #15 zuerst:** finale Papierkorbmatrix mit entbehrlichen Dateien, Recycling
  möglich/unmöglich, Abbruch/Teilabbruch, Mehrfachauswahl/Duplikate und aktueller/
  nächster Titel bei Play/Pause/Stop. Ursprünglicher macOS-Fall bleibt offen.
- **PR #28 Safety:** Prozess-Startownership, Registry-Eigentum und Menübindung
  weiter prüfen; Explorer-Cleanup wurde nachgebessert, aber abschließender
  unabhängiger/nativer Nachweis fehlt. Nur nachweislich eigene Objekte bereinigen.
- **PR #24:** nach behobenem Startproblem echte Kalt-/Warmstartmatrix, Enqueue/
  Play-enqueued, Pause, getrennte Öffnungen und größere Auswahl. Temporäres Menü
  gezielt entfernen und Entfernung nachweisen; kein Drag-and-drop-Ersatz.
- **PR #16:** Mixed-DPI, maximiert, weitere Skins, Minimieren/Wiederherstellen nach
  Monitorwechsel. Ältere Slim-Abnahmen nicht als neue Paketabnahme ausgeben.
- **Gemeinsamer Abschluss:** Einzelreviews/Merges, Linux-Komponenten, Windows
  Qt5/Qt6, verifiziertes Paket ohne Toolchain-PATH, finale Formatprüfung und
  Gesamtdurchlauf. Hardware-/Audio-/Plattformlücken ausdrücklich erhalten.

Kein automatischer Merge der funktionalen Drafts, kein automatischer Release.
