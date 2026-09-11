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

## Nachtrag: isoliertes PR15-Paket und Auswahlprobe

Stand dieses Nachtrags: 2026-09-11T07:47:55Z. Die älteren Abschnitte und die
ursprüngliche Paketbaseline bleiben historische Belege, keine aktuelle Freigabe.

[Build 34572047079](https://github.com/Auda29/nulloy/actions/runs/34572047079)
hat Qt5 und Qt6 nacheinander erfolgreich gebaut. Source-Commit:
`9e1b3f060e649a64c698b2a5981dbfca1d741b84`. Dieser Stand enthält Integration plus
PR #15, nicht die gemeinsame PR-#15/#16/#24-Abnahme. Die native Papierkorbprobe
war bedingungslos deaktiviert und wurde nicht ausgeführt.

| Paket | ZIP SHA-256 | EXE SHA-256 | Manifestdateien |
| --- | --- | --- | --- |
| Qt6 portable 0.10.0-alpha.2 | `5558a6ed786051224f7dcf3228a230fa45c95959f3e363e5b06b48d446ccb833` | `d7d622c3a0afe88657fa108bebf72f7bfdc69777c9f1f626fe3fe26e589315f9` | 490 |
| Qt5 nicht portabel 0.9.9 | `fe9250ea46a1d7960f184022cacdb7022b790f33aa417843049eb16ee114e4f5` | `80570a796289a848b4d8c09d384f3502bfd2723dd98c038e5aa886e4123331ca` | 412 |

Beide Pakete wurden heruntergeladen; ZIP-/EXE- und sämtliche Manifestdateien
lokal gehasht. Die später separat geladenen Testartefakte sind den ZIP-Hashes
zugeordnet. Unter beiden Toolkits bestehen Paketstart mit System32-only-PATH,
WAV/MP3/FLAC/OGG/Opus/WavPack und Unicode-Tag-Roundtrips. Die Formatläufe melden
jeweils drei PASS inklusive Init/Cleanup und einen separat übersprungenen
Portable-Prozesstest, nicht drei Fachfälle. Headless-Audio ist keine Audioausgabe-
Abnahme. Diese Ergebnisse dürfen nicht auf das spätere gemeinsame Paket wandern.

[Playerinspektion 34574196605](https://github.com/Auda29/nulloy/actions/runs/34574196605),
Prüfer `58b2dc9d43a4d7473e487729735e07b27d79050e`, besteht am obigen Qt6-ZIP:
drei genaue WAV-Playlistzeilen, Screenshot, unveränderte Dateien und Cleanup.
Keine UI-Aktion wurde ausgeführt.

[Auswahlprobe 34575720227](https://github.com/Auda29/nulloy/actions/runs/34575720227),
Prüfer `c838b013431ec31d972baa5e128f721fb3e89b9f`, ist insgesamt fehlgeschlagen:
Die ersten zwei Zeilen wurden über SelectionItem nachweislich ausgewählt, aber
das Kontextmenü öffnete sich nach der einmaligen HWND-Nachricht nicht. Kein
Menüeintrag wurde ausgelöst. Die Prozesse und eigenen Tempverzeichnisse sind
bereinigt. Dateierhalt ist in diesem Timeoutpfad nur vor der Interaktion geprüft;
er wird nicht als nachträglicher Nachweis ausgegeben. Die vorherige Probe
[34575571652](https://github.com/Auda29/nulloy/actions/runs/34575571652) stoppte
bereits an einer falschen Python-bool-Annahme, die anschließend tests-first
für den Win32-BOOL-Rückgabewert korrigiert wurde.

Die Ergebnisse und Paketzuordnung sind auch
[in PR #15 verlinkt](https://github.com/Auda29/nulloy/pull/15#issuecomment-5631014146)
(Paket-/Startnachweis; der spätere Auswahl-Timeout steht oben).
Nächste Prüfung ist der gezielte Qt-Fokus-/Kontextmenüweg ohne Menüaktion.
Die destruktive Probe bleibt gesperrt. Recycling-/Abbruch-/Duplikat-/Wiedergabe-
Matrix, macOS-Originalfall, echter Explorer, Fensterlücken und gemeinsame
Gesamtabnahme bleiben offen. Kein Merge oder Release ist dadurch freigegeben.

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
