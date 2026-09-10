# Verbindlicher Arbeits- und Teststand

Snapshot: 10. September 2026. Maßgeblich für den jeweiligen Test ist das Artefakt,
nicht der heutige Branchname. Die [maschinenlesbare Zuordnung](acceptance-baseline.json)
enthält Commit-IDs, gemeldete Prüfsummen und den abgefragten PR-Stand.

## Arbeitsbasis und getrennte Testbasis

- Integration beim Snapshot: `01c48f3faa8e5cb00753b96bb087a37d4aa02726`.
- PR #20 (Register/Übergabe) und #25 (Metadaten-/Shortcut-Tests) sind integriert.
- Ursprünglicher Swarm #7–#25: 19 PRs, davon 16 gemergt und 3 funktionale Drafts.
  Neue unterstützende Folge-PRs werden nicht in diese historische Gruppe gezählt.
- `master` unverändert auf `027d81a583b07457a4fa5f18b3e7dcca50b05b58`.
- Kombinierter Windows-Testbranch: `codex/windows-upstream-acceptance`,
  Berichtsstand `81160a130ae0641fc8d9f220ec52fdec8fb9b863`.
  Er enthält zusätzlich die drei Drafts; **kein freigegebener Integrationsstand**.
- Die kleine Python-Pfadkorrektur aus `f604c64ded4d9b44a39913b00f9a38317f7683cd`
  wird unabhängig davon in [PR #26](https://github.com/Auda29/nulloy/pull/26)
  übernommen. Keine funktionalen Draft-Änderungen in diesem PR.

## Paketidentität

Quelle ist ausschließlich der versionierte
[Windows-Abnahmebericht](https://github.com/Auda29/nulloy/blob/81160a130ae0641fc8d9f220ec52fdec8fb9b863/docs/upstream/WINDOWS_ACCEPTANCE.md).
Die folgenden Hashes wurden dort berichtet. ZIP/EXE sind hier nicht verfügbar;
diese Session hat sie **nicht erneut heruntergeladen, gehasht oder unter Windows getestet**.

| Artefakt | Bindung |
| --- | --- |
| Korrigiertes Qt6-ZIP `NulloyFork-0.10.0-alpha.3-test-windows-x64.zip` | Commit `078c734cf8e31fd561a857fa492c530bd4bb6f76` |
| ZIP SHA-256 | `e9ce76194d4c8a87b429da7adff0b8f6d5468f99349691dc1f4e46f11f1f7b5a` |
| Früher interaktiv getestete EXE SHA-256 | `855d74e505c670194a2e85ee34a93d9358949da55ade4b8d4308610e45a152b5` |
| Überholtes Paket | Commit `f604c64ded4d9b44a39913b00f9a38317f7683cd`; wegen unsicherer Papierkorbablage nicht für Löschtests verwenden |

Version `0.10.0-alpha.3-test` ist ein Testpaket, kein veröffentlichtes Alpha.3.
Der Commit der früher interaktiv geprüften EXE ist im Bericht nicht eindeutig
angegeben; deshalb wird keiner erfunden. Die danach gepackte Variante ergänzt
die Prüfung, dass die Quelldatei nach erfolgreichem Recycling verschwunden ist.
Der aktuelle Dokumentations-Head `81160a1` ist nicht der Paket-Buildcommit.

## Abnahmen nach tatsächlichem Stand

Alle Windows-Ergebnisse in dieser Tabelle sind **übernommene Berichtsbelege**,
keine neuen Ausführungen hier. „Final“ meint nur das oben genannte korrigierte
Testpaket, nicht einen noch zu erstellenden Release-Kandidaten.

| Bereich | Artefakt / Kategorie | Ergebnis und Grenze |
| --- | --- | --- |
| Qt6-Build/CTest, entpacktes Paket ohne Toolchain-PATH | Korrigiertes Paket / berichtet final | 5/5 CTests; 520 Dateihashes, 236 x64-Binärdateien; Skin-Paketabläufe und separater Prozesslauf laut Bericht erfolgreich |
| Qt5-Vergleich und native Papierkorbtests Qt5/Qt6 | Korrigierter Quellstand / separate Builds | Qt5 5/5 CTests; Recycling an/aus und fehlende Datei berichtet geprüft. Nicht mit dem Qt6-ZIP gleichsetzen |
| WAV/MP3/FLAC/Ogg/Opus/WavPack, Unicode-Tag-Roundtrips | Überholtes Paket / nur älter | Am finalen ZIP noch offen |
| Slim-Monitorwechsel, minimiert/normal, Bedienung/Hören, Cancel nach fehlendem Recycling | Frühere interaktive EXE / nur älter | Als Nachweis erhalten, aber keine pauschale Übertragung auf die endgültige EXE |
| Finale Mehrfach-/Duplikatentfernung, Play/Pause/Stop, weitere Titelwechsel | Korrigiertes Paket / offen | Nur entbehrliche erzeugte Dateien; macOS-Originalfall separat offen |
| Echter Explorer: geschlossen/laufend, Enqueue-Regeln, Pause/Stop, getrennte Aufrufe/größere Auswahl | Korrigiertes Paket / offen | Drag-and-drop oder ein CLI-Aufruf mit vielen Pfaden ersetzt diesen Ablauf nicht |
| Unterschiedliche DPI, maximiert, weitere Skins, gezielter finaler Fenstersmoke | Korrigiertes Paket / offen | Bereits bestätigte ältere Slim-Fälle bleiben sichtbar; keine unnötige pauschale Wiederholung, aber finalen Binärstand kenntlich machen |

Die damaligen automatisierten Audioabläufe verwendeten teilweise Ersatzsinks.
Sie sind keine Hardware-Hörabnahme.

## Aktuelle Freigabesperren

Der Nutzer hat für diesen Durchlauf ausdrücklich **nur automatisierbare Arbeiten**
freigegeben; native Abnahmen bleiben offen. Die Desktop-Verbindung dieser Session
zeigt Linux, nicht den Windows-Testrechner. Kein Windows-Rechner wurde umkonfiguriert.

- [PR #15](https://github.com/Auda29/nulloy/pull/15), Head
  `212ba22b8df9d9ee3d8e8a8c7f0b8cdce00f3fc0`: Neuer Qt-Adapter benötigt eigenen
  Review. Historische Linux-Mocks des alten Shell-Aufrufs belegen keine Sicherheit
  dieses Adapters. Finale Playlistmatrix und Original-macOS-Fall bleiben offen.
- [PR #24](https://github.com/Auda29/nulloy/pull/24): Explorer-Matrix offen;
  250-ms-Leerlauf/1000-ms-Grenze bleiben eine Heuristik. Keine spekulative
  Änderung ohne reproduziertes Fehlverhalten.
- [PR #16](https://github.com/Auda29/nulloy/pull/16): DPI/maximiert/weitere Skins offen.
- Temporärer Explorer-Schlüssel
  `HKCU\Software\Classes\SystemFileAssociations\.wav\shell\NulloyForkAcceptance_20260909`:
  Entfernung nach Testabschluss offen. Hier wurde weder seine Existenz noch eine
  Entfernung verifiziert. Keine Standardzuordnungen oder anderen Schlüssel ändern.

Grüne Komponenten-/Build-CI hebt diese Sperren nicht auf. Ein Linux-Gesamtlauf
kann den integrierten Code bestätigen, nicht das finale Windows-ZIP freigeben.
Nach späteren funktionalen Merges muss der dann entstandene gemeinsame Stand
mit passendem Paket neu geprüft werden. Kein automatischer Merge nach `master`,
kein Release und keine Schließung des macOS-Upstream-Issues.
