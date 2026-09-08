# Übergabe: Nulloy-Upstream-Stabilisierung

Stand: 8. September 2026. Diese Übergabe sichert den Arbeitsstand für ein anderes
Gerät; sie ist weder ein Release noch eine Erklärung, dass alle Issues gelöst sind.
Aktuelle PR-/CI-Zustände vor weiteren Änderungen auf GitHub erneut prüfen.

## Schnellstart auf einem anderen Gerät

Git und Zugriff auf `Auda29/nulloy` werden benötigt. GitHub CLI (`gh`) ist für
PR-/CI-Abfragen hilfreich, aber nicht zum Klonen erforderlich.

```sh
git clone --branch docs/upstream-issue-register https://github.com/Auda29/nulloy.git
cd nulloy
git status -sb
```

Dieser Übergabebranch enthält den integrierten Code plus Statusregister und
Nachweise. Er ist der Head von [PR #20](https://github.com/Auda29/nulloy/pull/20),
nicht der freigegebene Integrationsbranch. Papierkorb-, Fenster- und IPC-Drafts
werden dadurch **nicht** stillschweigend übernommen.

Für neue Implementierungsarbeit vom Integrationsbranch starten:

```sh
git fetch origin
git switch --track origin/integration/upstream-issues
git switch -c work/next-stabilization
```

Falls ein lokaler Integrationsbranch bereits existiert: `git switch
integration/upstream-issues` und anschließend `git pull --ff-only` verwenden.
Eigene uncommittete Änderungen vorher separat sichern; kein Reset oder Force-Push.
Die Übergabe bleibt auf `origin/docs/upstream-issue-register` bzw. im Browser lesbar.

## Welche Basis ist gesichert?

- Repository: https://github.com/Auda29/nulloy
- `master`: unverändert auf `027d81a583b07457a4fa5f18b3e7dcca50b05b58`.
- `integration/upstream-issues`: `2d54d7d4ebd132add13cbdf1a64159357df5b42a`
  beim Übergabe-Snapshot. Enthält 14 gemergte Swarm-PRs.
- 19 Swarm-PRs insgesamt: 17 issuebezogen, Infrastruktur #7 und Register #20.
- Alle 80 Issues und 126 Kommentare wurden bewertet. Prüfung bedeutet nicht
  automatisch Reproduktion, Behebung oder native Plattformabnahme.
- Kein Merge nach `master`, kein Release. Zurückgestellte Features und neue
  Plattformen bleiben außerhalb des aktuellen Stabilisierungsumfangs.

Die vier integrierten Produktionskorrekturen betreffen Pause beim Entfernen
(#129), gespeicherten Playlist-Zustand (#132), Waveform-Fehlerbehandlung (#139)
und Unicode-/Legacy-Tags (#241). Weitere gemergte PRs ergänzen Tests, ohne die
jeweilige Originalmeldung pauschal als behoben auszugeben.

## Offene PRs und nächster sinnvoller Schritt

| PR | Branch | Status bei Übergabe / nächster Schritt |
| --- | --- | --- |
| [#20](https://github.com/Auda29/nulloy/pull/20) | `docs/upstream-issue-register` | Register, Übergabe und Nachweise; neue CI nach diesem Push prüfen, dann separat reviewen/mergen. |
| [#25](https://github.com/Auda29/nulloy/pull/25) | `fix/upstream-146` | Test-/Dokumentations-PR, alle drei CI-Jobs grün auf `7bcc139562a7a207c5030ca1f629ebeb3f2542d7`; unabhängiger Review ohne Blocker archiviert. Noch Draft, nicht gemergt. |
| [#15](https://github.com/Auda29/nulloy/pull/15) | `fix/upstream-255` | Papierkorb-/Abbruchkorrektur. Echte Windows-Dialoge, Abbruch und permanentes Löschen mit entbehrlichen Dateien prüfen. Draft lassen, solange diese Abnahme fehlt. |
| [#16](https://github.com/Auda29/nulloy/pull/16) | `fix/upstream-236` | Fensterwiederherstellung. Reale Monitor-/DPI-Wechsel und Erreichbarkeit prüfen. Xvfb-Geometrie ist kein Hardware-Nachweis. |
| [#24](https://github.com/Auda29/nulloy/pull/24) | `fix/upstream-211` | Externe Dateiöffnung. Vollständige Explorer-/Mehrprozessserie prüfen; 250-ms-/1000-ms-Bündelung ist heuristisch, keine garantierte IPC-Gruppierung. |

`fix/upstream-262` enthält nur die Dokumentation der Hardwaretasten-Testlücke;
dieselbe Datei liegt in PR #20. Kein zusätzlicher künstlicher Issue-PR nötig.

Einen offenen Issue-Branch auf dem neuen Gerät auschecken:

```sh
git fetch origin
git switch --track origin/fix/upstream-211
# Alternativ mit GitHub CLI: gh pr checkout 24
```

Nicht blind die offenen PRs zusammenmergen. Für jeden PR den exakten aktuellen
Head, unabhängigen Review und alle relevanten CI-/Abnahmepunkte prüfen.

```sh
gh pr list --repo Auda29/nulloy --base integration/upstream-issues --state all
gh pr checks 20 --repo Auda29/nulloy
gh pr checks 25 --repo Auda29/nulloy
```

## Tests auf dem neuen Gerät

### Schnelle Python-Prüfungen auf dem Übergabebranch

```sh
python3 tools/upstream/test-issue-register.py
python3 tools/upstream/test-run-native.py
python3 tools/phase4/test-import-profile.py
python3 tools/release/test-alpha.py
```

Unter Windows bei Bedarf `python` statt `python3` verwenden. Für die echten
CTest-Vertragstests des Runners müssen CMake und Ninja auf PATH liegen; ohne
sie werden die entsprechenden Fälle übersprungen, nicht nativ verifiziert.

### Native Linux-Komponententests

Die genaue Paketliste und Installation stehen in
[`.github/workflows/upstream-stabilization.yml`](../../.github/workflows/upstream-stabilization.yml).
Referenzumgebung: Debian 13, Qt 6.8.2, GStreamer 1.26.2, TagLib 2.0.2,
CMake, Ninja, FFmpeg, Xvfb. Kein vollständiger Linux-Releasebuild.
Vom Checkout-Root aus:

```sh
python3 tools/upstream/run-native.py --output ../nulloy-test-evidence
# Einzelnes vorhandenes Issue, auf dem passenden Branch:
python3 tools/upstream/run-native.py --issue 241 --output ../nulloy-241-evidence
```

Der Runner legt frische Build-Unterverzeichnisse an. Keine alten lokalen
Build-Caches übernehmen; keine absoluten `/home/hermes/...`-Pfade aus den
historischen Logs als Befehle auf dem neuen Gerät verwenden. Das Ausgabeverzeichnis
muss außerhalb des Quellbaums auf einem ausführbaren Dateisystem liegen.
Mehrere Builds teilen sich CPU/RAM auch bei `-j1`: im Container tatsächliche
cgroup-Limits prüfen und schwere Builds/Audio-Timingtests nacheinander ausführen.

### Windows

[Windows-CMake-Workflow](../../.github/workflows/windows-cmake.yml) als Anleitung
für MSYS2/Qt5-/Qt6-Pakete, Build, Tests und Packaging verwenden. Die Linux-
Komponentenharnesses behaupten keine unveränderte Windows-Lauffähigkeit.
Die grünen Windows-CI-Builds ersetzen keine Explorer-, HID-, Papierkorb- oder
Monitor-/DPI-Abnahme. Diese Schritte stehen in den jeweiligen Issue-Berichten
auf dem zugehörigen Branch.

## Wo sind Entscheidungen und Nachweise?

- [Status aller 80 Issues](STATUS.md), maschinenlesbar: [issue-register.json](issue-register.json).
- [Arbeitsregeln und Testgrenzen](../UPSTREAM_STABILIZATION.md).
- [Hardware-/Kopfhörertasten: offene Reproduktion](262.md).
- [Archivierte Nachweise](handoff-evidence/README.md): öffentlicher Issue-Snapshot,
  Audit-Zählprüfung, unabhängige Review-Berichte, ausgewählte Testergebnisse,
  PR-/CI-Snapshot und Prüfsummen.
- Weitere Issue-Berichte liegen unter `docs/upstream/` auf dem jeweiligen Branch.
- CI-Logs und Artefakte über die Checks des jeweiligen PRs abrufen. GitHub hat
  Aufbewahrungsfristen; benötigte Binärartefakte rechtzeitig separat herunterladen.

Historische Review-Berichte sind datei-/commitgebundene Befunde, keine formelle
GitHub-Approval und keine Freigabe späterer Änderungen. Absolute Pfade in ihnen
bezeichnen die ursprüngliche Testumgebung. Die neue CI dieses Übergabepushs ist
nicht vom vorher aufgenommenen PR-Snapshot abgedeckt.

## Was wurde absichtlich nicht übertragen?

Compiler-/Build-Caches, komplette temporäre Prozesslogs und heruntergeladene
fremde Audio-Dateien wurden nicht ins Repository aufgenommen. Sie sind keine
Voraussetzung für den Checkout oder die automatisch erzeugten Test-Fixtures.
Originalmedien für noch offene Reporterfälle müssen gegebenenfalls mit geklärten
Nutzungsrechten erneut beschafft werden. Benötigte Reviewergebnisse und ein
textueller Audit-Snapshot sind dagegen mitversioniert.

Die damaligen Koordinationsskripte außerhalb des Repositories enthalten lokale
Worktree-Pfade und sind kein portables Buildsystem. Das Register kann direkt in
JSON/Markdown aktualisiert und mit `test-issue-register.py` geprüft werden;
GitHub bleibt die Quelle des aktuellen PR-/CI-Status. Für die Fortsetzung sind
weder die alte Hermes-Session noch die alten Worktrees erforderlich.
