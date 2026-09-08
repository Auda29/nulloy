# Migrationsplan für den Nulloy-Fork

Stand: 8. September 2026

Status: Phasen 0 bis 3 abgeschlossen und in Fork-`master` gemergt. Phase 4 technisch umgesetzt und vom Nutzer abgenommen; Prüfung auf separatem Windows-Rechner offen. Siehe [Phase-4-Bericht](PHASE4_REPORT.md).

Repository: [Auda29/nulloy](https://github.com/Auda29/nulloy)

Untersuchte Quellcodebasis: [`f4eddff8be2538526f3019f57f56c68db3c8c267`](https://github.com/Auda29/nulloy/tree/f4eddff8be2538526f3019f57f56c68db3c8c267)

## 1. Ziel und verbindliche Grenzen

Wir modernisieren Nulloys technischen Unterbau und schaffen eine Grundlage für spätere Erweiterungen. Die vorhandene Oberfläche und ihre Bedienung bleiben in der ersten Migrationsetappe unverändert.

Das umfasst Layout, Farben, Icons, Skins, Waveform-Darstellung, Menüs, Dialoge, Tastenkürzel, Drag-and-drop und Fensterverhalten. Auch die bisherige Auswahl an Ansichten und Einstellungen bleibt erhalten. Technische Änderungen an UI-Code sind zulässig, wenn sie dieses Verhalten erhalten.

Die vom Nutzer bestätigten Kernabläufe sind das Einfügen neuer Tracks per Drag-and-drop, ausdrücklich auch mehrerer Dateien gleichzeitig, schnelles Öffnen und Schließen sowie schnelles Laden der Waveform. Diese Abläufe haben Vorrang bei den Migrationsvergleichen. Start, Ende und Waveform mit beziehungsweise ohne vorhandenen Nulloy-Cache werden getrennt gemessen. Erste Referenzwerte stehen im Phase-0-Protokoll.

Die erste Etappe endet mit einer unter Windows nutzbaren 64-Bit-Version auf Qt 6 und CMake. Danach erproben wir eine abgegrenzte Rust-Komponente hinter der bestehenden Qt-/C++-Oberfläche. Ein vollständiger Rewrite ist kein beschlossenes Ziel.

Nicht Teil dieser Etappe sind ein Redesign, neue Funktionen, ein neues Skin-Format, ein Austausch der Audio-Engine oder die gleichzeitige Veröffentlichung für alle Betriebssysteme. Name und Branding werden separat entschieden. Linux- und macOS-Code bleiben Bestandteil des Projekts.

## 2. Geprüfte Ausgangslage

Die folgende Bestandsaufnahme beruht auf dem Repository-Baum und ausgewählten Quelldateien des oben genannten Commits. Sie ist keine vollständige Codeprüfung. Build, vorhandene Tests und erste Laufzeitvergleiche wurden inzwischen in Phase 0 durchgeführt. Ergebnisse und Grenzen stehen im [Prüfprotokoll](PHASE0_REPORT.md).

| Bereich | Befund | Bedeutung für die Migration |
|---|---|---|
| Build | `nulloy.pro` organisiert Anwendung, Widgets, optionale Plugins und Tests über qmake. `src/src.pri` enthält zusätzlich Ressourcen-, Skin- und Plattformschritte. | CMake muss auch diese Schritte abbilden, nicht nur die C++-Dateien kompilieren. |
| Skripte | `NScriptEngine` erbt von `QScriptEngine`. Eigene Prototypen verwenden `QScriptable`, Typregistrierung und `setDefaultPrototype`. | Der Wechsel zu `QJSEngine` erfordert eine Kompatibilitätsschicht oder gezielte Anpassungen. |
| Skin-Verhalten | Skripte greifen auf `Ui`, `Player`, `PlaybackEngine`, `Settings`, Qt-Konstanten und überladene Signale zu. | Gleiche Bilddateien allein garantieren keine gleiche Bedienung. |
| Skin-Dateien | `skinLoader.cpp` lädt Verzeichnisse und `.nzs`-Pakete mit `form.ui`, `script.js` und Ressourcen. Der Baum enthält Native, Slim, Silver und Metro. | Diese Varianten gehören in die Prüfung. Der Nutzer verwendet Slim 0.9. |
| Private Qt-API | `skinFileSystem.h` bindet `QtCore/private/qabstractfileengine_p.h` ein; der Build verwendet `core-private`. | Zweiter früher Prüfpunkt neben QtScript. Öffentliche APIs als Ersatz untersuchen. |
| Audio und Metadaten | Plugins für GStreamer, VLC und TagLib sowie eigene Playback-, Tag-, Cover- und Waveform-Schnittstellen sind vorhanden. | Bestehende Backends zunächst erhalten. Den tatsächlich genutzten Backend-Umfang in Phase 0 feststellen. |
| Threading | Das Waveform-Interface erbt von `QThread` und liefert eine Referenz auf Peaks. | Lebensdauer, Abbruch und Datenzugriff vor einer Rust-Anbindung ausdrücklich klären. |
| Persistenz | M3U-Dateien können `#NULLOY:`-Felder für Fehlerstatus, Wiedergabezähler, Position und Titelformat enthalten. Einstellungen nutzen eine INI-Datei. | Diese Daten müssen beim Lesen und Schreiben erhalten bleiben. |
| Datenpfade | `common.cpp` leitet Konfigurations- und Playlist-Pfade aus Programmname und Installationsort ab. | Ein anderer Programmname oder Installationsort kann die Datenzuordnung verändern. |
| Weitere Abhängigkeiten | QtSingleApplication, QtIOCompressor und eine angepasste Qxt-Shortcut-Komponente liegen unter `3rdParty`. | Qt-6-/64-Bit-Kompatibilität einzeln bewerten. |
| Tests und CI | Zwei QtTest-Programme sind im Baum vorhanden. Im untersuchten Commit gibt es keine `.github/workflows`-Dateien. | Bestehende Tests zunächst ausführen; gezielt um Migrationsrisiken ergänzen. |
| Update-Prüfung | `updateChecker.cpp` leitet Update- und Download-Adressen aus der Organisationsdomain ab. | Vor einer Fork-Veröffentlichung eigene Update-Zuordnung festlegen. |
| Lizenzhinweise | Der Quellcode nennt GPL-3.0; beispielsweise nennt das Slim-Skin-Skript für sein Skin-Paket CC-BY-SA 3.0. | Lizenzhinweise für Code, Skins und weitere Abhängigkeiten getrennt erfassen und erhalten. |

## 3. Technische Richtung

| Baustein | Ziel | Entscheidungsstand |
|---|---|---|
| Oberfläche | Vorhandene Qt Widgets, UI-Formulare und Skin-Ressourcen | Festgelegt |
| Qt | Eine zum Umsetzungszeitpunkt unterstützte Qt-6-Version | Hauptversion festgelegt; konkrete Version nach Kompatibilitätsprüfung |
| C++ | Mindestens C++17 für die Qt-6-Etappe | Vorschlag; kein flächendeckendes Syntax-Refactoring |
| Build | CMake, dokumentierte Presets und festgelegte Abhängigkeiten | Festgelegt |
| Windows-Werkzeuge | Einheitliche x64-Toolchain für Qt, Anwendung und Plugins | MSVC oder MinGW in Phase 1 anhand der Abhängigkeiten auswählen |
| Audio und Tags | Bestehende Backend-Schnittstellen und geprüfte Bibliotheksversionen | Erhalten; keine pauschale Zusage zur Kompatibilität aktueller Versionen |
| Rust | Kleine Bibliothek mit klarer C++-Schnittstelle | Pilot nach erfolgreicher Qt-6-Etappe |
| Rust-Anbindung | CXX für reine Daten-/Funktionsschnittstellen; CXX-Qt bei benötigter QObject-Integration prüfen | Noch nicht entschieden |
| Plattformen | Windows x64 zuerst; Linux und macOS anschließend mit eigenen Laufzeitnachweisen | Priorisierung, keine Aufgabe anderer Plattformen |

Versionen von Compiler, Qt, CMake, Bibliotheken und später Rust werden mit Bezugsquellen und Prüfsummen beziehungsweise Lockfiles dokumentiert. Ein reproduzierbarer Build bedeutet zunächst, dass er auf einer sauberen Umgebung mit diesen Vorgaben gelingt. Byte-identische Binärdateien sind kein zugesagtes Ergebnis dieser Etappe.

## 4. Phasen und Abnahmekriterien

### Phase 0: Vergleichsbasis und Arbeitskopie

- [x] Fork in den lokalen Projektordner übernehmen und vorhandene Dokumente erhalten.
- [x] `origin` auf den eigenen Fork und `upstream` auf `nulloy/nulloy` setzen. Upstream-Historie bewahren; Arbeitszweige unter `codex/` verwenden.
- [x] Installierte Nulloy-Version, aktiven Skin, Einstellungen, Backend, Windows-Version und DPI-Skalierung feststellen. Keine dieser Angaben aus dokumentierten Defaults ableiten.
- [x] Eine getrennte Testinstallation und Kopien von Einstellungen, Playlists und Testmedien vorbereiten. Die täglich verwendete Installation bleibt die Vergleichsbasis. Die unbeabsichtigte Positionsänderung wurde nach Rückmeldung des Nutzers zurückgesetzt; alle 102 geschützten Originaldateien stimmen mit der Sicherung überein.
- [x] Originalquellcode mit dokumentierter Werkzeugkette bauen; Qt 5.15 als Migrationsbasis prüfen. Historische Build-Probleme und die Hilfsschritte im Prüfprotokoll dokumentieren.
- [x] Vorhandene Tests ausführen und Ergebnisse festhalten. Zwei bestehende Playlist-Testfehler sind reproduziert.
- [x] Referenzbilder und Bedienabläufe erfassen: Hauptfenster, Menüs, Dialoge, Hover-/Pressed-Zustände, maximiert, Vollbild und veränderte Fenstergröße. Button-Zustände sind zusätzlich über die unveränderten Originalgrafiken und ihre CSS-Zuordnung referenziert.
- [x] Falls installierte Version und untersuchter Commit abweichen, die Unterschiede festhalten und die Referenz für jedes betroffene Verhalten bestimmen. Installiertes 0.9.9 ist die Bedienreferenz; Master ist die technische Basis.

Referenzbilder sind vorhanden. Die sechs Sprungbefehle für ±5, ±30 und ±100 Sekunden sowie Play/Pause und Titelwechsel wurden an der Testkopie geprüft. Die persönlichen Kernabläufe sind bestätigt und erste Start-/Ende-/Waveform-Zeiten gemessen. Einzel- und Mehrfach-Drops in leere und vorhandene Playlists bestehen den ergänzten Qt-Integrationstest. Der Nutzer hat den echten Explorer-Mehrfach-Drop erfolgreich durchgeführt; die hinzugefügten Einträge sind in der gespeicherten Playlist nachgewiesen. Für Normal-, Hover- und Pressed-Zustände liegen 21 unveränderte Originalgrafiken mit Zuordnung, Prüfsummen und lokaler Referenzgalerie vor.

**Abnahme:** Quellcodebasis, ausführbare Referenz, Werkzeugkette und Testprofil sind dokumentiert. Der aktive Skin und die persönlichen Kernabläufe sind bekannt. Noch offene Build-Blocker sind ausdrücklich benannt.

### Phase 1: Qt-6-Machbarkeit für Skins nachweisen

- [x] Alle QtScript-Nutzungen und privaten Qt-APIs im gesamten Quellcode inventarisieren.
- [x] Einen kleinen Qt-6-Testaufbau für die vorhandenen UI-Formulare und eigenen Widgets erstellen.
- [x] `QJSEngine` mit den benötigten Globals, Signalen, Enums, Prototyp-Funktionen und Wertumwandlungen erproben. Auch `print`, Bildmasken, Font-Laden und Ressourcenpfade berücksichtigen.
- [x] Den aktiven Skin zuerst prüfen; anschließend Native, Slim, Silver und Metro sowie tatsächlich verwendete externe Skins.
- [x] Einen Ersatz für das private Skin-Dateisystem über öffentliche Qt-APIs untersuchen. Verzeichnisse, `.nzs`-Pakete, relative CSS-Pfade und dynamisch erzeugte Bilder müssen weiter funktionieren.
- [x] QtSingleApplication, Qxt-Hotkeys, QtIOCompressor und Windows-Integration auf konkrete Qt-6-/x64-Blocker prüfen.
- [x] Zielversionen und Compiler anhand dieses Nachweises festlegen; Ergebnisse und offene Einschränkungen in einer kurzen Architekturentscheidung dokumentieren.

Nachweis: [Phase-1-Bericht](PHASE1_REPORT.md) und [Architekturentscheidung](docs/phase1/DECISION.md). Qt 6.11.2 mit GCC 16.2.0 baut die vorhandenen Widgets. Vier Testsuiten bestehen unter Windows, einschließlich der kopierten 0.9.9-Skins und des Datei-Drop-Tests. HiDPI-Vergleich, vollständige Menüs, echte Audiobackends und Player-Leistungsmessungen bleiben Teil der vollständigen Migration.

**Abnahme:** Die kritischen Skin-Funktionen laufen im Qt-6-Testaufbau ohne beabsichtigte optische oder funktionale Änderung. Für verbleibende Abhängigkeiten liegt ein konkreter Migrationsweg vor.

**Bei einem Blocker:** Keine Skins entfernen und keine neue Oberfläche als Ersatz einführen. Ursache isolieren und den Plan anpassen. Der Prototyp ist noch kein auslieferbarer Player und ersetzt die Vergleichsbasis nicht.

### Phase 2: CMake und Windows x64

- [x] CMake-Ziele für Anwendung, Widget-Sammlung, Plugins, Tests, Übersetzungen, Icons und Skin-Pakete anlegen.
- [x] Den CMake-Aufbau zunächst gegen die Qt-5-Vergleichsbasis prüfen, soweit die in Phase 1 gewählte Werkzeugkette dies erlaubt. Ausnahmen dokumentieren.
- [x] Architekturwechsel separat prüfen. Anwendung, Qt, Plugins und native Bibliotheken müssen dieselbe Architektur und eine kompatible Compiler-/Runtime-Kombination verwenden.
- [x] Bestehende Build-Optionen ausdrücklich abbilden. Den bisherigen Skin-Umfang als Standard erhalten.
- [x] Einen sauberen Windows-CI-Build mit Tests und herunterladbarem Testpaket einrichten. Abhängigkeiten und Build-Befehle dokumentieren.
- [x] qmake erst entfernen, wenn CMake die benötigten Funktionen nachweislich abdeckt. Für Linux/macOS und den bisherigen Vergleich bleibt es vorerst erhalten.

Nachweis: [Phase-2-Bericht](PHASE2_REPORT.md) und [Windows-Build-Leitfaden](docs/phase2/BUILD_WINDOWS.md). Qt-5-x64-Build, bestehende Tests und Paket-Workflows für alle vier Skins bestehen lokal und in der Windows-CI. Das heruntergeladene Testpaket wurde verifiziert. Erststartkosten, erneuter manueller Explorer-Drop und umfassende Leistungs-/Darstellungsvergleiche bleiben ausdrücklich offen; die technische Build-Abnahme ersetzt diese Prüfungen nicht.

**Abnahme:** Ein Windows-x64-Build entsteht auf einer sauberen Umgebung nach dokumentierten Schritten. Das Paket enthält alle benötigten Ressourcen und Bibliotheken. Vorhandene Tests und die wesentlichen Referenzabläufe bestehen.

### Phase 3: Vollständiger Player auf Qt 6

- [x] Den in Phase 1 erprobten Skript- und Ressourcenadapter integrieren.
- [x] Die für den vollständigen Windows-Build benötigten Qt-5-APIs ersetzen; Core5Compat erhält ältere Tag-Zeichencodierungen.
- [x] Playback-, Waveform- und Metadaten-Plugins gegen die neue Toolchain bauen; Paket auf gemischte Qt-Hauptversionen prüfen.
- [x] Einstellungen und M3U-Daten einschließlich Nulloy-Zusatzfeldern anhand kopierter Profile vergleichen: 83 Werte und 48 Playlist-Einträge identisch.
- [x] Fensterrahmen, Tray, Taskleiste und globale Hotkeys manuell abnehmen. Der Nutzer bestätigt die angefragten Prüfungen und nach der Korrektur auch Minimieren/Wiederherstellen durch Taskleisten-Klick.
- [x] Lebensdauer von Qt-Objekten, Abbruch von Hintergrundarbeit und Beenden während der Waveform-Berechnung prüfen.
- [x] Die Kernbedienung manuell vergleichen. Der Nutzer bestätigt den vorgeschlagenen Testablauf für das Qt-6-Paket als erfolgreich, einschließlich subjektiv unauffälliger Ladezeiten. Exakte Zeiten wurden nicht gemessen.
- [x] WAV, MP3, FLAC, Ogg/Vorbis, Opus und WavPack mit Wiedergabe, Waveform und Unicode-Tag-Schreiben im Paket prüfen; Prüfung in beide CI-Jobs aufnehmen.
- [x] Erststart messen und eingrenzen: Der Aufbau des GStreamer-Plugin-Caches dominiert die Verzögerung. Folgestarts liegen in der letzten Slim-Messreihe bei 574 und 556 ms.

**Abnahme:** Der komplette Player läuft unter Windows x64 mit Qt 6. Die bisherigen Kernfunktionen bestehen den Vergleich. Es gibt keine ungeklärten Änderungen an Darstellung, Bedienung oder gespeicherten Nutzerdaten.

Die funktionale Abnahme ist abgeschlossen. Mit Zustimmung des Nutzers bleibt die Erststart-Optimierung ein offener Punkt in Phase 4. Der langsame Erststart gilt damit ausdrücklich nicht als behoben. Siehe [Phase-3-Bericht](PHASE3_REPORT.md).

### Phase 4: Erste nutzbare Migrationsversion

- [x] Den Erststart aus einem frisch entpackten Ordner beschleunigen. Der Aufbau des GStreamer-Plugin-Caches ist als Engpass nachgewiesen, auch im Qt-5-Vergleich. Erststart und Folgestarts getrennt messen, die bisher geprüften Audioformate beibehalten und die Pakettests erneut bestehen lassen. Ausgangswerte und Messbelege stehen im [Phase-3-Bericht](PHASE3_REPORT.md).
- [x] Ein portables Windows-x64-Testpaket erstellen und lokal mit bereinigtem PATH prüfen.
- [ ] Das Paket auf einem separaten Windows-System ohne Entwicklungswerkzeuge starten.
- [x] Eigene Daten- und Einzelinstanz-Zuordnung für den Fork festlegen, damit er parallel zum Original geprüft werden kann. Übernahme alter Daten zunächst über Kopien, ohne das Originalprofil umzuschreiben.
- [x] Update-Prüfung eindeutig dem Fork zuordnen. Solange kein eigener Update-Kanal besteht, automatische Upstream-Prüfungen für Testpakete deaktivieren und dies dokumentieren. Sichtbare Änderungen am Update-Dialog separat entscheiden.
- [x] Versionskennung, Fork-Hinweis und mitzuliefernde Lizenztexte festlegen. Eine Änderung des Designs ist damit nicht verbunden.
- [x] Ein versioniertes Prüfprotokoll mit Commit, Abhängigkeiten, Testergebnissen und bekannten Einschränkungen beilegen.
- [x] Das konkrete Paket manuell mit dem bisherigen Player vergleichen und vom Nutzer abnehmen lassen. Am 8. September bestätigt der Nutzer die Abnahme ohne Auffälligkeiten im Test. Eine Langzeitprüfung ist damit nicht nachgewiesen; eine Veröffentlichung ist ein eigener Umsetzungsschritt.
- [ ] Bei Veröffentlichung Tag, Quellstand, heruntergeladenes Release-Paket und SHA-256 prüfen. Ein erfolgreicher CI-Lauf allein gilt nicht als Paketabnahme.

Stand vom 8. September: Testpaket erstellt, lokal mit bereinigtem PATH geprüft und vom Nutzer ohne gemeldete Auffälligkeiten abgenommen. Erststarts der abschließenden automatischen Messungen lagen bei 1,67 bis 1,92 Sekunden. Der separate Windows-Rechner bleibt offen. Details und Ausreißer stehen im [Phase-4-Bericht](PHASE4_REPORT.md).

**Abnahme:** Ein eigenständig startbares Paket mit nachvollziehbarer Herkunft ist vorhanden. Der Nutzer bestätigt den Erhalt seines bisherigen UI- und Bedienverhaltens. Diese Bestätigung betrifft das konkrete Testpaket; die vorangehenden technischen Arbeiten können unabhängig davon erfolgen.

### Phase 5: Begrenzter Rust-Pilot

Diese Phase beginnt nach der Qt-6-Abnahme. Sie entscheidet, ob eine weitere Rust-Migration den zusätzlichen Integrationsaufwand rechtfertigt.

- [ ] Zunächst `playlistStorage` als Kandidaten für reine Parser-/Serializer-Logik untersuchen. Qt-seitige Dateioperationen und UI bleiben zunächst bestehen. Alternativ die reine Peak-Berechnung prüfen, falls sie sich besser abgrenzen lässt.
- [ ] Nur eine Komponente auswählen und ihr beobachtbares Verhalten mit Referenzdaten festhalten. Vorhandene Fehler als solche dokumentieren; Korrekturen separat behandeln.
- [ ] Datenformate, Pfad-/Unicode-Konvertierung, Speicherbesitz, Fehlerrückgabe und Aufruf-Threads an der Sprachgrenze definieren.
- [ ] CXX und gegebenenfalls CXX-Qt in einem kleinen Integrationsversuch vergleichen. Keine Widgets nach Rust übertragen.
- [ ] Rust-Panics und C++-Ausnahmen dürfen die Sprachgrenze nicht unkontrolliert überschreiten. `unsafe` auf begründete, überprüfbare Stellen beschränken.
- [ ] C++- und Rust-Implementierung mit denselben gültigen und fehlerhaften Eingaben vergleichen. Bei Playlists gehören relative Pfade, fehlende Dateien, Unicode, Kommas und `#NULLOY:`-Felder dazu.
- [ ] Build, Tests und Paketierung um Cargo und ein eingechecktes Lockfile ergänzen. Für Windows muss das Rust-Ziel zur ausgewählten nativen Toolchain passen.
- [ ] Vorübergehend per Build-Option auf die C++-Implementierung zurückwechseln können. Kein neuer Schalter in der Benutzeroberfläche.
- [ ] Wartbarkeit, Build-Aufwand und gemessene Laufzeit-/Speichereigenschaften bewerten. Weitere Rust-Komponenten erst aus diesem Ergebnis ableiten.

**Abnahme:** Eine klar abgegrenzte Rust-Komponente funktioniert hinter der unveränderten Oberfläche, besteht den Verhaltensvergleich und lässt sich im normalen CI-/Release-Prozess bauen. Eine kurze Entscheidung hält fest, ob Rust beibehalten, erweitert oder der Pilot zurückgenommen wird.

## 5. Vergleichs- und Testmatrix

Automatisierte Tests prüfen gezielt Datenformate, Zustandswechsel und Schnittstellen. Optik, Audio-Ausgabe und Betriebssystemintegration benötigen zusätzlich reale Laufzeittests.

| Bereich | Prüfungen | Erfolgskriterium |
|---|---|---|
| Oberfläche | Aktiver Skin und mitgelieferte Skins; Hauptfenster, Menüs, Dialoge, Hover, Vollbild, Größenänderung | Gleiche Anordnung, Assets, Texte und Bedienabläufe bei vergleichbarer Umgebung |
| Skalierung | Gleicher Rechner, Schriftarten und Fensterzustand; 100 %, 125 %, 150 %, 200 % sowie aktuelle Nutzereinstellung | Keine neuen Überlappungen, abgeschnittenen Elemente oder falschen Klickflächen |
| Screenshots | Identische Testdaten und Zustände; dynamische Zeitwerte stabilisieren | Unterschiede nachvollziehbar prüfen; Rendering-Toleranzen vor dem Vergleich festlegen und nicht nachträglich ausweiten |
| Wiedergabe | Öffnen, Play, Pause, Stop, nächster/vorheriger Titel, Seek, Lautstärke, Repeat, Shuffle, Geschwindigkeit soweit im Referenzbackend vorhanden | Verhalten entspricht der festgehaltenen Referenz; keine neuen Aussetzer oder Hänger |
| Formate | MP3 einschließlich VBR, FLAC, WAV, Ogg/Vorbis, Opus, M4A/AAC und persönlich genutzte Formate, soweit vom Referenzbackend unterstützt | Dateien spielen ab; Dauer, Tags, Cover und Seek sind plausibel und vergleichbar |
| Waveform | Kurze/lange Dateien, Stille, Stereo, laufende Berechnung, schneller Titelwechsel, Abbruch und Programmende | Vergleichbare Peaks und Darstellung; korrekte Zuordnung zum Titel; keine veralteten Ergebnisse |
| Playlists | Import/Export, Reihenfolge, Auswahl, Drag-and-drop, Duplikate, fehlende Dateien, relative Pfade, Unicode | Kein Verlust von Einträgen oder Nulloy-Zusatzdaten |
| Einstellungen | Kopiertes Altprofil, Skin-Auswahl, Tastenkürzel, Fenstergeometrie, Playlist-Wiederherstellung | Werte und Startverhalten bleiben erhalten; Originalprofil bleibt unberührt |
| Metadaten | Titel, Album, Künstler, fehlende Tags, Cover; Tag-Editor an Dateikopien | Vorhandene Lese-/Schreibfunktionen bleiben erhalten; keine ungewollten Änderungen an Mediendaten |
| Windows | Einzelinstanz, Explorer-Dateiübergabe, globale Hotkeys, Tray, Taskleistenfortschritt | Bisherige Integration funktioniert mit dem neuen Paket |
| Robustheit | Fehlerhafte Medien, schneller Dateiwechsel, Beenden während Hintergrundarbeit, wiederholtes Starten | Kein neuer Absturz, Deadlock oder unbegrenztes Anwachsen des Speichers |
| Paket | Start ohne Qt-/Compiler-Installation und ohne Build-Verzeichnis im Suchpfad | Alle erforderlichen DLLs, Qt-/Audio-Plugins, Skins und Übersetzungen sind enthalten |

Startzeit, Speicherverbrauch und Zeit bis zur ersten beziehungsweise vollständigen Waveform werden mit einem festen kleinen Medienkorpus auf derselben Maschine verglichen. Messbare Toleranzen legen wir nach der Baseline und vor der jeweiligen Migration fest. Der Plan verspricht keine pauschalen Leistungsgewinne durch Qt 6 oder Rust.

## 6. Risiken und Rückweg

| Risiko | Vorgehen | Rückweg |
|---|---|---|
| QtScript-Verhalten lässt sich nicht direkt abbilden | Früher Skin-Prototyp; eigene Adapter für benötigte Funktionen | Qt-5-Referenz beibehalten, problematische Funktion isolieren |
| Private Qt-Dateisystem-API ändert sich | Öffentliche Ressourcen-/Datei-APIs erproben; alle Skin-Ladewege prüfen | Keine breite Integration vor erfolgreichem Nachweis |
| Gemischte Architektur oder inkompatible Bibliotheken | Einheitliche Toolchain und vollständige Paketprüfung | Letzte geprüfte Kombination wiederherstellen |
| Qt 6 verändert Geometrie oder Darstellung | Referenzbilder, feste DPI-Umgebung und Bedienvergleich | Abweichung beheben; kein stilles Akzeptieren als Redesign |
| Daten gehen bei Import oder Versionswechsel verloren | Kopien, Formatvergleiche und getrennte Testinstallation | Originalinstallation und Originaldaten weiterverwenden |
| Rust erzeugt mehr Pflegeaufwand als Nutzen | Nur ein Pilot mit klarer Schnittstelle | C++-Implementierung bis zur Entscheidung verfügbar halten |
| Zu viele Umbauten erschweren die Fehlersuche | CMake, x64, Qt 6 und Rust in getrennten Änderungen behandeln | Auf letzten geprüften Commit zurückgehen |

Jede Phase endet mit einem dokumentierten Commit und einem kurzen Prüfprotokoll. Historie wird nicht umgeschrieben; Upstream-Änderungen werden gezielt übernommen und gegen dieselbe Referenz geprüft. Öffentlich unterstützte Plattformen werden erst zugesagt, wenn passende Pakete und Laufzeittests vorliegen.

## 7. Offene Entscheidungen und nächste Arbeit

| Entscheidung | Zeitpunkt |
|---|---|
| Aktive Nulloy-Version, Skin, Backend und persönliche Kernabläufe | In Phase 0 festgestellt und vom Nutzer priorisiert; siehe Prüfprotokoll |
| Qt-Version, Compiler, Bibliotheksversionen und unterstützte Windows-Versionen | Phase 1 |
| Genaue Lösung für Skript-Kompatibilität und Skin-Ressourcen | Phase 1 |
| Grenzen für Screenshot- und Leistungstoleranzen | Nach Baseline, vor jeweiliger Migration |
| Fork-Datenpfade, Update-Kanal und Paketkennung | Vor Phase-4-Paketabnahme |
| Erste Rust-Komponente und Art der Anbindung | Phase 5 |
| Linux-/macOS-Paketierung, endgültiger Name und spätere Funktionen | Nach Windows-Migrationsetappe |

Phase 0 und Phase 1 sind in den Fork gemergt. Phase 2 liegt auf einem eigenen Branch vor. Die vollständige Qt-6-Integration aus Phase 3 ist umgesetzt, getestet und vom Nutzer funktional abgenommen, einschließlich des korrigierten Taskleisten-Klicks. Die Erststart-Optimierung wurde ausdrücklich als offener Punkt in Phase 4 übernommen. Der [Phase-3-Bericht](PHASE3_REPORT.md) hält den Stand fest. Dieser Plan enthält keine festen Terminzusagen.

## 8. Quellen

- [Untersuchte Nulloy-Quellcodebasis](https://github.com/Auda29/nulloy/tree/f4eddff8be2538526f3019f57f56c68db3c8c267): insbesondere `nulloy.pro`, `src/src.pri`, `src/scriptEngine.*`, `src/scriptQtPrototypes.h`, `src/skinLoader.cpp`, `src/skinFileSystem.*`, `src/skins/slim/script.js`, `src/playlistStorage.cpp`, `src/settings.cpp`, `src/common.cpp`, `src/updateChecker.cpp` und `src/interfaces`.
- [Qt: Porting to Qt 6](https://doc.qt.io/qt-6/portingguide.html): Migration, API-Änderungen und HiDPI-Verhalten.
- [Qt: Build with CMake](https://doc.qt.io/qt-6/cmake-manual.html): CMake-Integration und Qt-5-/Qt-6-Übergang.
- [Qt: QJSEngine](https://doc.qt.io/qt-6/qjsengine.html): JavaScript-Einbindung als zu prüfende Alternative für QtScript.
- [CXX-Qt-Dokumentation](https://kdab.github.io/cxx-qt/book/): Verbindung von Qt- und Rust-Code.
- [CXX-Qt-Maintainer zu Qt Widgets](https://github.com/KDAB/cxx-qt/discussions/1330): vorhandene C++-Widgets mit Rust-Komponenten kombinieren.

Die Bibliotheksdokumentation beschreibt Möglichkeiten. Sie ist kein Nachweis, dass Nulloys Migration bereits funktioniert.
