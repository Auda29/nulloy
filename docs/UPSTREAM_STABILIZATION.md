# Upstream-Stabilisierung: Arbeitsregeln und Testausführung

## Freigegebener Umfang

Ausgangspunkt: `027d81a583b07457a4fa5f18b3e7dcca50b05b58`,
[Analyse der 80 Issues](UPSTREAM_ISSUES_ANALYSIS.md).

- Alle 80 dort aufgeführten Issues werden mit aktuellem Thread und Code geprüft.
- Zuerst Stabilisierung gemäß Analyse; spätere Features, neue Plattformen und
  zurückgestellte Wünsche werden dokumentiert, nicht ungefragt implementiert.
- Zielbranch: `integration/upstream-issues`; `master` und Releases bleiben unverändert.
- Ein eigener PR pro umzusetzendem Issue. Bereits abgedeckte oder zurückgestellte
  Issues benötigen keine künstlichen Code-PRs. Testinfrastruktur und die gemeinsame
  Statusübersicht sind gesonderte unterstützende PRs.
- Implementierung und unabhängiger Review erfolgen in getrennten Arbeitsverzeichnissen.
  Nur Änderungen mit bestandenen relevanten Tests und ohne offene Review-Blocker
  werden in den Integrationsbranch gemergt.
- Keine Änderungen, Kommentare oder automatischen Schließungen im Originalrepository.
  PRs verwenden Referenzlinks statt `Closes` auf fremde Issues.

## Nachweise

Jedes geänderte Issue erhält unter `docs/upstream/` eine Beschreibung mit Verhalten,
Testkommando, beobachtetem Ergebnis und verbleibenden Abnahmepunkten. Ein bestandener
Komponententest bedeutet nicht automatisch, dass die komplette Upstream-Meldung
oder eine andere Plattform erledigt ist. Für Fehlerbehebungen muss der neue Test
am alten Verhalten scheitern und am korrigierten Verhalten bestehen.

Die Sandbox verwendet Debian 13, Qt 6.8.2, GStreamer 1.26.2 und TagLib 2.0.2.
Der Windows-Releasebuild bleibt unverändert Windows x64 vorbehalten. Linux-native
Komponententests sind keine Veröffentlichung oder Abnahme eines Linux-Players.

Native Harnesses liegen unter `tests/upstream/<Issue-Nummer>/CMakeLists.txt`.
Der gemeinsame Aufruf baut jede isoliert und speichert Befehle, Rückgabecodes,
CTest-Ausgaben und `results.json`:

```sh
python3 tools/upstream/test-run-native.py
python3 tools/upstream/run-native.py --output /tmp/nulloy-upstream-tests
# Einzelnes Issue:
python3 tools/upstream/run-native.py --issue 255 --output /tmp/nulloy-255
```

Das Ausgabeverzeichnis muss außerhalb des Quellbaums liegen. Ohne `--output` entsteht
ein neues Verzeichnis neben dem Checkout (nicht auf einem eventuell mit `noexec`
eingehängten `/tmp`). Jeder Aufruf baut pro Issue in einem neuen `run-*`-Unterverzeichnis;
alte CTest-Registrierungen können dadurch keine gelöschten Tests als bestanden ausgeben.
Vorherige Belege bleiben erhalten, es werden keine fremden Ausgabeverzeichnisse gelöscht.
Leere CTest-Suiten
sind Fehler. `--allow-empty` ist nur für die anfängliche Infrastruktur-PR vorgesehen,
bevor erste Issue-Harnesses auf diesem Branch existieren; es behauptet keine Tests.
Alle entdeckten Harnesses werden geprüft, auch wenn ein anderer fehlschlägt.
Builds laufen mit einem Compilerprozess, um parallele Agenten nicht durch
Speicherüberlastung zu stören.

Die neue Linux-CI benutzt ein per Digest festgelegtes Debian-Image und per Commit
festgelegte GitHub-Actions. APT-Paketstände bleiben bewusst die jeweils verfügbaren
Debian-Sicherheitsupdates; die genaue Paketliste wird als Beleg gespeichert. Dies
ist keine Behauptung bit-identischer Reproduzierbarkeit über spätere Paketupdates.
Der bestehende Windows-Workflow prüft weiterhin den vollständigen Qt-5-/Qt-6-Build
und das gepackte Programm; seine bestehenden Abhängigkeitsregeln bleiben erhalten.

## Ausgangsprüfung

- Vorhandener Profilimport-Test: bestanden (ein Test).
- Vorhandene Release-Vertragstests: bestanden (zwei Tests).
- Native Skin-Ressourcen- und Script-Bridge-CTest-Suiten: bestanden.
  Für Linux wurde ausschließlich der vorhandene CMake-Parameter `SKIN_TEST_FONT`
  auf eine vorhandene DejaVu-Schrift gesetzt. Der vollständige Skin-Probe-Build
  enthält weiterhin Windows-Bibliotheken und ist keine Linux-Baseline.
- Windows-CI des exakten Ausgangscommits:
  https://github.com/Auda29/nulloy/actions/runs/34250208225 (erfolgreich).

## Nicht lokal durchführbare Abnahmen

Nach Recherche nicht durchführbare Tests werden nicht als bestanden markiert.
Der jeweilige Issue-Bericht nennt Voraussetzung, Schritte und erwartetes Ergebnis.
Insbesondere ersetzen ein kontrollierter Audiosink und künstliche Bildschirmgeometrien
keinen Hardware-Hörtest, reale Explorer-Aufrufserie oder nativen Monitor-/DPI-Wechsel.
Neue native Betriebssystemfreigaben bleiben separate spätere Arbeitspakete.
