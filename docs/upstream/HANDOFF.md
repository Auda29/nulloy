# Weiterarbeiten: Nulloy-Upstream-Stabilisierung

Stand: 10. September 2026. PR #20, #25, #26 und #27 sind inzwischen in
`integration/upstream-issues` integriert. Die alte Übergabe auf
`docs/upstream-issue-register` ist ein historischer Snapshot, nicht mehr die
empfohlene Entwicklungsbasis.

## Einstieg

```sh
git clone --branch integration/upstream-issues https://github.com/Auda29/nulloy.git
cd nulloy
git status -sb
# Bei vorhandenem Checkout (erst eigene Änderungen sichern):
git fetch --all --prune --tags
git switch integration/upstream-issues
git pull --ff-only
```

Zum Zeitpunkt der Bestandsaufnahme ist der Integrationscommit
`919468efc32f4d038c96d7276a799794dab2e86e`. Unterstützende Folge-PRs können diesen
Stand später erweitern. Keine ungeprüften Resets, Force-Pushes oder automatischen
Merges von offenen Drafts.

## Welche Dokumente gelten?

1. [Arbeits-/Teststand und Freigabesperren](ACCEPTANCE_BASELINE.md): verbindliche
   Trennung von korrigiertem Windows-Paket, älteren Abnahmen und offenen Fällen.
2. [Maschinenlesbare Paket-/PR-Zuordnung](acceptance-baseline.json),
   [80-Issue-Register](issue-register.json) und [Übersicht](STATUS.md).
3. [Archivierte Nachweise](handoff-evidence/README.md): historische Audit- und
   Review-Dateien bleiben unverändert; ältere PR-Snapshots dort sind nicht aktuell.
4. [Arbeitsregeln](../UPSTREAM_STABILIZATION.md) und Issue-Berichte auf dem
   jeweiligen Branch; [Hardwaretasten-Testlücke](262.md).

Die ursprünglichen 19 Swarm-PRs enthalten jetzt 16 Merges und 3 offene funktionale
Drafts. Neue Unterstützungs-PRs gehören nicht zu dieser ursprünglichen Zählung.
`master` und Release-Tags wurden nicht freigegeben.

PR #26 (separate Python-Pfadkorrektur) ist mit `264b05ddbd732dcb6970d42bc5ab82adde5c5e1f` gemergt,
ohne funktionale Draft-Änderungen. Die unveränderten berichteten Windows-Paket-IDs
bleiben davon getrennt; siehe ACCEPTANCE_BASELINE.md.

## Nachtrag 11. September: Paketbindung vor Papierkorb-Abnahme

Der [aktuelle Teilnachweis](NATIVE_AUTOMATION_STATUS.md#nachtrag-isoliertes-pr15-paket-und-auswahlprobe)
verwendet den isolierten Build `9e1b3f060e649a64c698b2a5981dbfca1d741b84`
aus Lauf `34572047079`. Seine vollständigen Qt5-/Qt6-Prüfsummen und Grenzen stehen
dort; nicht mit älteren kombinierten Paketen oder dem Prüfercommit verwechseln.
Die Zweifachauswahl am Qt6-Player ist belegt, die Kontextmenüprobe läuft auf einen
Timeout. Als Nächstes den gezielten Fokus-/Kontextmenüweg ohne Menüaktion prüfen.
Die alte destruktive Probe bleibt gesperrt; keine abgeschlossene Papierkorbmatrix.
Historische Belege, macOS- und übrige native Abnahmelücken bleiben erhalten.

## Offene Arbeit

| PR | Thema | Nächster Schritt |
| --- | --- | --- |
| [#15](https://github.com/Auda29/nulloy/pull/15) | Neuer Qt-Papierkorbadapter | Review-Test-/Dokufixes auf `774894c4eba7b646beafb38313fe0dc73cfb4671`; separater Linux-Vertrag berichtet 26 QtTest / 1 CTest. Finale Mehrfach-/Duplikat-/Play/Pause/Stop-Abnahme und macOS bleiben offen |
| [#24](https://github.com/Auda29/nulloy/pull/24) | Explorer/IPC | Echte Explorer-Matrix und gezieltes Aufräumen des temporären Testmenüs |
| [#16](https://github.com/Auda29/nulloy/pull/16) | Fenster | DPI, maximiert, weitere Skins; vorhandene ältere Slim-Abnahmen getrennt bewahren |

Der Nutzer kann nicht manuell testen; automatisierte echte native Tests auf
entbehrlichen GitHub-Windows-Runnern sind inzwischen freigegeben. Sie laufen in
Draft PR #28, während Draft PR #29 einen dabei gefundenen Start-/IPC-Fehler
separat bearbeitet. Siehe [Folgestand und Paketidentität](NATIVE_AUTOMATION_STATUS.md).
Die drei funktionalen Drafts bleiben ohne ihre vollständige Abnahme offen, auch
bei grüner CI. Vor jedem späteren Merge PR-Head und passende Review-/Testbelege prüfen.

```sh
gh pr list --repo Auda29/nulloy --base integration/upstream-issues --state all
gh pr view 26 --repo Auda29/nulloy --json state,headRefOid,mergeCommit
# Einzelnen Draft ohne Integration auschecken:
gh pr checkout 15
```

`codex/windows-upstream-acceptance` ist ein kombinierter **Testbranch**, nicht die
freigegebene Basis. Das dort dokumentierte ZIP wurde aus `078c734` gebaut;
sein späterer Berichts-Head ist nicht die Build-ID. Pfade und vollständige
Prüfsummen stehen in ACCEPTANCE_BASELINE.md. Ein neues Paket braucht eigene
Prüfsummen und eine eigene Abnahmematrix.

## Automatisierte Prüfungen

Vom Checkout-Root (Python 3.9+, CMake und Ninja für die echten Runner-Vertragstests):

```sh
python3 tools/upstream/test-issue-register.py
python3 tools/upstream/test-run-native.py
python3 tools/phase4/test-import-profile.py
python3 tools/release/test-alpha.py
# Native Linux-Komponenten, neue Ausgabe außerhalb des Checkout:
python3 tools/upstream/run-native.py --output ../nulloy-test-evidence
```

Unter Windows gegebenenfalls `python` statt `python3`. Native Issue-Harnesses
sind nicht pauschal Windows-kompatibel. Die genaue Linux-Paketinstallation steht
in [upstream-stabilization.yml](../../.github/workflows/upstream-stabilization.yml),
Windows-Build/Packaging in [windows-cmake.yml](../../.github/workflows/windows-cmake.yml).

Im Container tatsächliche cgroup-Limits beachten und schwere Builds/Timingtests
nacheinander ausführen. Alte CMake-Verzeichnisse und absolute `/home/hermes/...`-
Pfade aus historischen Logs nicht auf einem anderen Gerät übernehmen.

Compiler-Caches und fremde Audio-Fixtures sind nicht versioniert. Die vorgesehenen
Harnesses erzeugen ihre Testdaten selbst. Für spätere ursprüngliche Reporterfälle
gegebenenfalls Originaldateien mit geklärten Nutzungsrechten beschaffen. Die alte
Hermes-Session ist keine Voraussetzung zum Weiterarbeiten.

## Vor Release

Erst nach den funktionalen Einzelmerges den dann endgültigen Integrationsstand
prüfen: Linux-Komponenten, Windows Qt5/Qt6, entpacktes finales Paket ohne
Toolchain-PATH, Formatmatrix und native Smoke-/Bedienabnahme. Anschließend
Register und Übergabe aktualisieren. **Kein automatischer Release oder Merge nach
master.** Das hier dokumentierte Alpha.3-Testpaket ist keine Veröffentlichung.

## Nachtrag 11. September: grünes isoliertes Kontextmenü-Milestone

Der aktuelle, separat verifizierte Nachweis ist [NATIVE_AUTOMATION_STATUS.md#nachtrag-2026-09-11-isoliertes-kontextmenü-milestone-grün](NATIVE_AUTOMATION_STATUS.md#nachtrag-2026-09-11-isoliertes-kontextmenü-milestone-grün). Lauf `34584964888` / Prüfercommit `5cf2973242321053cd4c793e6518138828baead1` bestand mit 53 Vertragsprüfungen gegen das exakt gebundene Qt6-Paket aus Lauf `34572047079`, Buildcommit `9e1b3f060e649a64c698b2a5981dbfca1d741b84`. Die ZIP-/EXE- und Laufzeitskript-Hashes, Auswahlretention von genau 2/3 Zeilen, einmalige guarded Pointer-Eingabe, eigenes Qt-Menu mit den beiden exakten Einträgen sowie finale Fixture-/Cleanup-Prüfung sind im Register festgehalten.

Arbeitsgrenze: Dies war eine beobachtende, nichtdestruktive Aktion ohne Menüaufruf. Das Paket ist Integration plus PR15 und nicht die gemeinsame PR15/24/29-Endabnahme. PR15 native Trash-Matrix und macOS-Originalfall, PR24 Explorer, PR16 DPI/Fenster sowie der kombinierte Qt5/Qt6-Abschluss bleiben offen; Release ist nicht autorisiert. Fail-open visibility, per-call COM-Boundedness und Diagnostic-Error-Masking sind nicht als behoben zu behandeln. Die früheren Läufe `34582957766` (Recognition) und `34584359190` (stdout-Serialisierung) bleiben historische FAILs.

Die separat genehmigte Speicherbereinigung löschte 29 veraltete Paketartefakte und 31 MSYS2-Caches; Verifikation bestätigte 309 verbliebene Artefakte zum Bereinigungszeitpunkt und schützte unter anderem IDs `10188441880` und `10188259265`. Das ist ein Punkt-in-Zeit-Bestand, keine Quoten- oder aktueller-Gesamtbestand-Aussage. Siehe externe Nachweise unter `/home/hermes/workspace/nulloy-status-current/player-inspection-34584964888/` und `/home/hermes/workspace/nulloy-status-current/storage-cleanup/`.

## Nachtrag 2026-09-11: PR30-Register und getrennte Vertragsnachweise

Die Live-API-Ablage `/home/hermes/workspace/nulloy-status-current/native-timeout-register-live.json` wurde um `2026-09-11T11:50:53.817380+00:00` gelesen. PR #30 ist weiterhin OPEN/DRAFT mit dem exakten Head `c2405a0375b23dfdc3561a5bdd7a1eb56a812902`; Windows-Qt5/Qt6 `34588893748` und Linux `34588893721` sind grün. Das ist nur CI auf dem PR30-Branch, nicht das kombinierte Endpaket. Keine frische PR30-Paket-Hashannahme, kein Workflowumbau, kein Merge und kein Release.

Der native Supervisor-/Qt-Fixture-Nachweis [34595596113](https://github.com/Auda29/nulloy/actions/runs/34595596113) ist ein eigener Vertragsmilestone: 18 Supervisor-Tests mit 16 PASS und zwei expliziten POSIX-Skips sowie vier PASS-Fixturetests auf Windows-2022 / PySide6-Qt6.8.2 / Python3.11.9. Reviewte Commits: `68cdc90f369d6c5f507c81cf757befb509dbfeb9`, `b7d228e885841cb796ed9d31fa79526864dba031`, assembled `ca49815db8db16b8704cc82f89336e09f8ed2d70`. Kein Player wurde gestartet, kein Playerpaket wurde verwendet und keine tatsächliche UIA-Query ausgeführt; der HWND-0-Guard lehnt vor der Query ab. Synthetische PID-Rennen sind Vertragskontrollen, kein nativer UIA-Nachweis. Der COM-/Provider-Schritt bleibt offen.

Die Playerbeobachtung [34589940677](https://github.com/Auda29/nulloy/actions/runs/34589940677) besteht mit 60 Tests am selben isolierten Qt6-Paket aus `34572047079` / `9e1b3f060e649a64c698b2a5981dbfca1d741b84`. Zwei von drei Zeilen blieben nach genau einem guarded Right-Click ausgewählt; es gab keine Menüaktion, keine Fixtureänderung und bestätigte Bereinigung. Der frühere 53-PASS-Lauf `34584964888` bleibt als eigener historischer Milestone erhalten. Dieser Nachweis autorisiert keine destruktive Papierkorbaktion.

Weiterhin offen und vor einer kombinierten Freigabe zu erledigen: PR15 Recycling-/Abbruch-/Teilabbruch-/Duplikat-/Play-Pause-Stop-Matrix, Original-macOS-Fall, echte Explorer-Kalt-/Warmstart-/Enqueue-/Pause-/große-Auswahl-Matrix für PR24, PR16 Mixed-DPI/maximiert/Skins, abschließendes kombiniertes Qt5/Qt6-Paket sowie Releaseentscheidung. `master` und Release bleiben unangetastet; kein automatischer Release.

## Nachtrag 2026-09-11: Konsolidierungsübergabe vor PR30-Merge

Der vollständige append-only-Betriebsstand steht in [CONSOLIDATION.md](CONSOLIDATION.md)
und im Feld `consolidation_snapshot` des Registers. Er beschreibt den Stand nach
den verifizierten Retirements: 12 Remote-Branches, 11 lokale Branches und 10
Worktrees, zuvor 33/34/33, jeweils sauber. Die 18 abgeschlossenen PR-Branches
#7–#14, #17–#23, #25–#27 und sechs Experimentzustände (3 Remote, 5 lokal,
5 Worktrees) sind archiviert bzw. entfernt. Die private Ablage erhält originale
SHAs, Historien, Fehlschläge und ungetrackte/ignorierte Evidenz. Die alte Codex-
Kombination aus PR15/16/24 ist nicht die isolierte `9e1b3f0`-Quelle; eine
Gesamtbehauptung „alle Änderungen gemergt“ ist ausdrücklich ausgeschlossen.

Beibehalten werden die vier exakten Branch-Anker für Playerinspektion,
proof-only UIA-Timeout, eingefrorenes PR15-Paket und die spezialisierte PR28-
Explorerprobe. PR15 bleibt Review ohne formale native Abnahme; PR16 behält die
Mixed-DPI-/maximiert-/Skins-/Minimieren-Wiederherstellen-Lücken; PR24 bleibt von
PR29-IPC abhängig und braucht getrennte Öffnungs- und Großauswahlabdeckung; PR28
ist kein Produktfix und bleibt offen ohne finalen PASS; PR29 hat grüne Tests,
aber keinen Explorer-PASS. `qml` bleibt Legacy und wird nicht neue aktive Arbeit.

PR30 ist hier vor dem Eltern-Merge mit Head
`1e44a4477929cbd1bad7b36c204f8466f8711f69` dokumentiert. Windows `34597690721`
und Linux `34597690744` sind erfolgreiche Branch-CI; daraus folgt keine neue
Paket-Hashannahme oder kombinierte Endabnahme. Integration
`919468efc32f4d038c96d7276a799794dab2e86e` und `master`
`027d81a583b07457a4fa5f18b3e7dcca50b05b58` bleiben getrennt.

Die Wiederherstellung erfolgt nur in einem neuen Verzeichnis: Bundle klonen,
dann mit `git worktree add` den exakten SHA auschecken und selektive Archive mit
`tar --skip-old-files` einspielen. Git-Bundles enthalten keine ungetrackten
Dateien; private Archivpfade sind keine öffentlichen Upload-Ziele. Der Eltern-
prozess kann den Archiv-Branch nach eigener Backup-Prüfung später entfernen.
