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
