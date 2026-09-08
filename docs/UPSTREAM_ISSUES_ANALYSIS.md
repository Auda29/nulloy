# Analyse der offenen Upstream-Issues

Stand: 8. September 2026. Verglichen mit unserem Release `v0.10.0-alpha.2`, Commit `4a34c2ccd13b4515913600fb6d9b52d0b8fe2403`.

## Empfehlung

Vor Phase 5 würde ich einen kleinen Stabilisierungsschritt einschieben. Die wichtigsten Themen sind der Papierkorb-Ablauf, das Entfernen eines pausierten Titels, die Lautstärke beim Titelwechsel und das Öffnen mehrerer Dateien über Windows Explorer. Danach sollten wir große Playlists und das Laden der Waveform unter Last messen. Die vorhandene Oberfläche kann dabei unverändert bleiben.

Einige Wünsche erfüllt unser Fork bereits, insbesondere Qt 6 und ein portables Windows-Paket. Viele andere Issues beschreiben zusätzliche Funktionen oder betreffen macOS und Linux. Sie sind kein Grund, den Player komplett neu zu schreiben. Der begrenzte Rust-Pilot aus dem [Migrationsplan](../MIGRATION_PLAN.md) bleibt sinnvoll, sobald die vorrangigen Verhaltensfragen geklärt sind.

## Umfang und Nachweisgrenzen

- Alle **80 offenen Issues**, ohne Pull Requests, einschließlich ihrer **126 Kommentare** gelesen. Abruf über die GitHub-API am `2026-09-08T16:01:13Z`.
- Beschreibungen und Diskussionen mit dem aktuellen Fork-Code sowie den vorhandenen Tests verglichen. Verlinkte Bilder, Videos und Beispieldateien wurden nicht vollständig heruntergeladen oder geprüft. Wo der Text keine belastbare Reproduktion enthält, steht das in der Bewertung.
- Dies ist eine Text- und Codeanalyse, keine Reproduktion aller 80 Meldungen. Ein statischer Codebefund und ein bestandener Test werden ausdrücklich unterschieden. Insbesondere bestätigen Windows-Tests keine Fehlerbehebung auf macOS oder Wayland.
- Im Original-Repository wurden keine Issues angelegt, kommentiert, geändert oder geschlossen. Auch im Fork wurden keine 80 Tickets automatisch importiert und während dieser Analyse keine Player-Fixes vorgenommen.
- Der lokale Rohdaten-Snapshot liegt unter `.phase4/upstream-issues-2026-09-08.json`, außerhalb der versionierten Dateien. SHA-256: `9338aac4a803b803ea84d556526f58af7040331a1a2ebba522de68e0c4dc31b1`.

Ausgangspunkt ist die [offene Issue-Liste von Nulloy](https://github.com/nulloy/nulloy/issues?q=is%3Aissue%20state%3Aopen). Jede Tabellenzeile verlinkt die zugehörige Diskussion. Der Snapshot dokumentiert den Abrufstand; spätere Änderungen auf GitHub können davon abweichen.

## Was zuerst geklärt werden sollte

### 1. Papierkorb und Entfernen aus der Playlist

Bei [#255](https://github.com/nulloy/nulloy/issues/255) geht es um einen macOS-Absturz nach dem Verschieben in den Papierkorb. Unser Port von PR #263 korrigiert veraltete Item-Zeiger und die Zuordnung zum nächsten Titel. Das beseitigt aber nicht alle Probleme des gesamten Ablaufs.

Im aktuellen gemeinsamen Code gibt `NTrash::moveToTrash()` die Eingabeliste zurück, aus der erfolgreich bearbeitete Dateien entfernt wurden. Der Aufrufer nennt diese Rückgabe `deleted` und reicht sie an `removeFiles()` weiter. Damit stimmen die Verträge nicht überein: Bei vollständigem Erfolg bleibt die Playlist unverändert; bei einem frühen Abbruch kann sie gerade die nicht verschobenen Einträge verlieren. Das ist ein konkreter statischer Befund. Ein Papierkorb-Test auf dem veröffentlichten Paket wurde hier nicht durchgeführt. Siehe C4.

Zusätzlich ruft `removeSelected()` für den entfernten aktuellen Titel `playItem()` auf, solange der Zustand nicht `PlaybackStopped` ist. Das schließt `PlaybackPaused` ein. `playItem()` startet die Wiedergabe ausdrücklich. Der in [#129](https://github.com/nulloy/nulloy/issues/129) beschriebene unerwartete Start hat damit weiterhin einen passenden Codepfad. Die in PR #6 verbesserte Zustandswiederherstellung bei abgebrochenen Titelübergängen deckt diesen separaten Pfad nicht ab. Siehe C3.

**Nächster Schritt:** Eine eigene Korrektur mit Tests für Erfolg, Abbruch und Teilerfolg des Papierkorbs sowie für das Entfernen des aktuellen und des nächsten Titels während Play, Pause und Stop. Betriebssystemtests nur mit eigens erzeugten Testdateien. Die Bestätigung für endgültiges Löschen aus [#45](https://github.com/nulloy/nulloy/issues/45) sollte erhalten bleiben.

### 2. Lautstärke und Wiederholung bei geändertem Tempo

[#238](https://github.com/nulloy/nulloy/issues/238) beschreibt tatsächlich 100 % Lautstärke trotz eines Reglers bei 20 %, teils erst beim zweiten Öffnen oder Wiederholen. Der Fork setzt beim Laden der Einstellungen die Engine-Lautstärke und verarbeitet GStreamer-Volume-Nachrichten. Das ist noch kein Nachweis, dass alle Start- und Übergangspfade den Pegel erhalten. Die Pakettests verwenden überwiegend Lautstärke 0 beziehungsweise einen Ersatz für das Audiogerät. Siehe C2 und C8.

[#240](https://github.com/nulloy/nulloy/issues/240) betrifft ein zu frühes Wiederholen bei 0,5-facher Geschwindigkeit. Die neuen Übergangs- und Kurztracktests prüfen keine Tempomatrix. `checkStatus()` und `STREAM_START` behandeln Tempo und Positionsabfragen weiterhin gesondert. Aus dem erfolgreichen PR-Port lässt sich deshalb keine Behebung dieses Fehlers ableiten.

**Nächster Schritt:** Lautstärkeerhalt bei Neustart, Explorer-Aufruf, manuellem Wechsel, natürlichem Übergang und Repeat prüfen. Anschließend 0,5×, 1× und 2× mit Zeitmessung und bekanntem Audiosignal testen. Eine Messung des tatsächlichen Ausgangssignals ergänzt die Prüfung des Regler- und Engine-Werts.

### 3. Mehrere Dateien öffnen und unsichtbare Fenster

[#211](https://github.com/nulloy/nulloy/issues/211) ist nicht mit dem bereits akzeptierten Mehrfach-Drag-and-drop gleichzusetzen. Explorer kann für mehrere ausgewählte Dateien mehrere Programmstarts beziehungsweise IPC-Nachrichten erzeugen. `readMessage()` ersetzt bei deaktiviertem `EnqueueFiles` die Playlist pro Nachricht. Bei aktivem `PlayEnqueued` kann jede Nachricht erneut die Wiedergabe umstellen. Unsere Tests prüfen mehrere Pfade innerhalb einer Nachricht, aber keine vollständige Explorer-Startserie mit diesen Einstellungsvarianten. Siehe C5 und C8.

Bei [#236](https://github.com/nulloy/nulloy/issues/236) ist eine gespeicherte Fensterposition außerhalb der angeschlossenen Monitore eine plausible Ursache. `NMainWindow::loadSettings()` übernimmt die gespeicherten Koordinaten ohne Prüfung gegen die aktuell erreichbaren Bildschirmflächen. Der früher abgenommene Taskleisten-Fix betrifft Minimieren und Wiederherstellen; er ersetzt diese Prüfung nicht. Siehe C6.

**Nächster Schritt:** Explorer mit drei Dateien, laufendem und geschlossenem Player sowie allen relevanten Enqueue-Einstellungen prüfen. Separat eine gespeicherte Position auf einem inzwischen entfernten Monitor und einen DPI-Wechsel testen.

### 4. Große Playlists, Waveform und schnelles Schließen

[#129](https://github.com/nulloy/nulloy/issues/129) nennt ungefähr 5.000 Titel. Die jetzigen Tests für Drag-and-drop und Löschen verwenden kleine Listen. `removeFiles()` durchsucht für jede Playlistzeile eine `QStringList`; `removeSelected()` entfernt Zeilen einzeln und aktualisiert anschließend Metadaten, Dauer und Indizes. Das begründet einen Lasttest, belegt aber noch keinen aktuellen Hänger. [#139](https://github.com/nulloy/nulloy/issues/139) enthält außer dem Titel keine Reproduktionsdetails. Siehe C3.

[#187](https://github.com/nulloy/nulloy/issues/187) wünscht vorab berechnete Waveforms. Wir haben einen Cache, aber keine Warteschlange zur Vorberechnung kommender Titel. Beim Wechsel stoppt der GStreamer-Waveform-Builder den bisherigen Auftrag und wartet auf seinen Thread. Beim Speichern wird der vorhandene Peak-Cache serialisiert und komprimiert. Diese Stellen sollten wir messen, bevor zusätzliche Hintergrundaufträge eingeführt werden. Siehe C7.

**Nächster Schritt:** 100, 1.000 und 5.000 Playlistzeilen; einzelne und gleichzeitige Datei-Drops; kurze und lange Audiodateien; kalter und warmer Cache; rascher Titelwechsel und Schließen während der Berechnung. Fensterreaktion, vollständige Waveform, Abbruchzeit und Speicher getrennt messen. Vorberechnung bleibt ein späterer, optionaler Schritt mit begrenzter Parallelität und Abbruchmöglichkeit.

### 5. Reichweite von PR #6 und den Plattformtests

[#248](https://github.com/nulloy/nulloy/issues/248), [#261](https://github.com/nulloy/nulloy/issues/261) und [#225](https://github.com/nulloy/nulloy/issues/225) passen zu den Bereichen Titelübergang, schnelles Seek und Playliständerungen. Der Fork entfernt das blockierende Warten auf die GUI im GStreamer-Callback und testet mehrere dieser Abläufe unter Windows. Das ist ein belegter Fortschritt; die ursprünglichen macOS-Fälle bleiben mangels entsprechendem Build und Test offen. [Portbericht zu PR #263](UPSTREAM_PR_263.md), C2 und C8.

Der aktuelle CMake-Build lehnt andere Ziele als Windows x64 ausdrücklich ab. Apple Silicon, Signierung, Wayland und Linux-Paketierung sind somit eigene spätere Arbeitspakete. Der vorhandene historische qmake-Build ist keine Abnahme unserer Migration auf diesen Plattformen. Siehe C1.

## Bewertungsschlüssel

| Status | Anzahl | Bedeutung |
| --- | --- | --- |
| Abgedeckt | 4 | Der konkret benannte Bedarf ist im aktuellen Windows-Qt-6-Fork erfüllt. Keine Aussage über andere Plattformen. |
| Teilweise | 14 | Passende Funktion, Codeverbesserung oder Test vorhanden, aber die vollständige Meldung ist nicht nachgewiesen erledigt. |
| Prüfen | 10 | Fehler oder Lücke betrifft den aktuellen Kern; gezielte Reproduktion oder Korrektur einplanen. |
| Später | 25 | Sinnvolle mögliche Erweiterung nach Stabilisierung; keine aktuelle Zusage. |
| Plattform | 12 | Vor allem bei einer späteren Linux- oder macOS-Freigabe bearbeiten. |
| Zurückstellen | 15 | Kein sinnvoller nächster Schritt für unsere derzeitige Zielsetzung. |

**P1** bedeutet vor dem Rust-Piloten prüfen. **P2** folgt als gezielte Stabilisierung oder innerhalb des betreffenden Plattformpakets. **P3** ist ein späterer Wunsch beziehungsweise eine Dokumentationsverbesserung. Priorität bezeichnet unsere Arbeitsreihenfolge, nicht einen nachgewiesenen Schweregrad des Upstream-Fehlers. `—` bedeutet aktuell kein eigener Umsetzungsschritt.

## Alle 80 Issues

Die Kurztitel sind deutsch zusammengefasst. C1 bis C10 verweisen auf die am Ende aufgeführten Codebelege.

| Issue | Thema | Status | Priorität | Bewertung für unseren Fork und nächster Schritt |
| --- | --- | --- | --- | --- |
| [#265](https://github.com/nulloy/nulloy/issues/265) | Apple Silicon | Plattform | P2 | Ein Windows-x64-Build liefert keine ARM64-macOS-App. Für eine Mac-Freigabe CMake, Qt, Decoder, Paketierung und native Ausführung gemeinsam prüfen. C1. |
| [#262](https://github.com/nulloy/nulloy/issues/262) | Medien- und Kopfhörertasten | Teilweise | P2 | Konfigurierbare globale Shortcuts und Windows-Zuordnungen für einige Medientasten existieren. Automatische Kopfhörersteuerung und Betriebssystem-Mediensitzung sind damit nicht belegt. Hardwaretest und Default-Zuordnungen prüfen. C10. |
| [#261](https://github.com/nulloy/nulloy/issues/261) | Absturz beim schnellen Wechseln und Seek auf Mac | Teilweise | P1 | PR #6 adressiert einen passenden Deadlock-Pfad; Windows-Stresstests bestehen. Kein Test der verlinkten Aufnahme und kein macOS-Nachweis. Längeren Wechsel-/Seek-Test ergänzen, Mac später gesondert. C2, C8. |
| [#260](https://github.com/nulloy/nulloy/issues/260) | Qt 6 | Abgedeckt | — | Qt 6 mit erhaltener Widgets-Oberfläche ist unser Release-Unterbau. Der in der Diskussion erwähnte QML-Zweig ist eine andere Lösung und für diesen Bedarf nicht erforderlich. C1. |
| [#259](https://github.com/nulloy/nulloy/issues/259) | Alben optisch gruppieren | Später | P3 | Verändert die Playlistdarstellung. Allenfalls später optional; das bestehende Layout bleibt zunächst erhalten. |
| [#256](https://github.com/nulloy/nulloy/issues/256) | Portable Ausgabe | Abgedeckt | — | Alpha.2 liefert ein portables Windows-x64-ZIP mit eigenem Data-Ordner und Instanztrennung. C5 und Release-Nachweise. |
| [#255](https://github.com/nulloy/nulloy/issues/255) | Absturz nach Papierkorb-Aktion | Prüfen | P1 | Item-Lebensdauer in PR #6 verbessert, aber Rückgabevertrag des Papierkorb-Aufrufers bleibt widersprüchlich. Zuerst Erfolg, Abbruch und Teilerfolg korrigieren/testen; Mac-Absturz nicht als behoben zählen. C3, C4. |
| [#253](https://github.com/nulloy/nulloy/issues/253) | Linguist als Build-Abhängigkeit | Plattform | P3 | Unser Build verwendet `lrelease` für Übersetzungen und benötigt LinguistTools. Das Gentoo-Paketproblem separat prüfen; die Windows-Abhängigkeit nicht ersatzlos entfernen. C1. |
| [#250](https://github.com/nulloy/nulloy/issues/250) | macOS-Signierung | Plattform | P2 | Gehört zu einer künftigen Mac-Veröffentlichung einschließlich Prüfung auf sauberem System. Der Workaround in den Kommentaren ersetzt keine eigene Release-Lösung. |
| [#249](https://github.com/nulloy/nulloy/issues/249) | Audioausgang und Kanalzuordnung auswählen | Später | P2 | GStreamer nutzt hier keine ausgearbeitete Geräteauswahl im Player. Für Audiointerfaces und Mehrkanalausgabe sinnvoll; mit #79 gemeinsam planen. Aufnahmefunktionen sind nicht automatisch Teil davon. C2. |
| [#248](https://github.com/nulloy/nulloy/issues/248) | Nächster Titel startet nicht | Teilweise | P1 | Nachfolger-Cache und EOS-Fallback sind im Fork verbessert und unter Windows geprüft. Berichte betreffen Mac, teils Google-Drive-Dateien. Normale Übergänge, Cloud-Dateien und Plattformunterschiede getrennt prüfen. C2, C8. |
| [#246](https://github.com/nulloy/nulloy/issues/246) | Sehr langsames Resize auf Wayland | Plattform | P2 | Bericht nennt GNOME/Wayland und große Cover; der Maintainer konnte es mit Weston/XWayland nicht bestätigen. Unser Windows-Test entscheidet das nicht. Bei Linux-Port Resize, Covergröße und Skalierung messen. C7. |
| [#245](https://github.com/nulloy/nulloy/issues/245) | Fehlende Bitrate `%B` | Prüfen | P2 | TagLib-Abfrage vorhanden, aber in der Diskussion fehlt ein Dateimuster. Bekannte Dateien mit festem und variablem Bitratentyp sowie sinnvoller Leeranzeige prüfen. C9. |
| [#244](https://github.com/nulloy/nulloy/issues/244) | Zuckender Lautstärkeregler | Plattform | P2 | Laut Text rein visuell, unter Wayland. Nicht mit tatsächlichen Pegelsprüngen aus #238 vermischen. Qt 6 allein belegt keine Behebung. |
| [#243](https://github.com/nulloy/nulloy/issues/243) | Schließen versus Beenden auf Mac | Plattform | P2 | Diskussion unterscheidet Fensterschließen und App-Ende; Einstellung `QuitOnClose` existiert. Beim Mac-Port mit beiden Optionen und allen Skins abnehmen. Windows-Taskleistentest deckt dies nicht ab. C6. |
| [#242](https://github.com/nulloy/nulloy/issues/242) | Doppelte zip-/7z-Abhängigkeit | Abgedeckt | — | Der aktive CMake-Skinbuild verwendet Python für Archive. Die alte qmake-Datei bleibt historisch erhalten; das Problem erfordert für unser Release keine zweite Migration. C1. |
| [#241](https://github.com/nulloy/nulloy/issues/241) | Kyrillische Tags und Alt-Encoding | Teilweise | P2 | Diskussion nennt Windows-1251 und manuelle Auswahl. Unicode-Roundtrips im Fork sind getestet, automatische Erkennung alter Encodings nicht. Gemischte UTF-8-/1251-Beispiele ergänzen; Unicode-Dateipfade allein reichen nicht. C9. |
| [#240](https://github.com/nulloy/nulloy/issues/240) | Repeat bei geändertem Tempo | Prüfen | P1 | Die Übergangstests laufen nicht als 0,5×-/2×-Matrix. Repeat-Endpunkt, Positionsanzeige und Titelwechsel bei verändertem Tempo messen. C2, C8. |
| [#238](https://github.com/nulloy/nulloy/issues/238) | 100 % Pegel trotz niedrigem Regler | Prüfen | P1 | Konkreter Windows-11-Bericht mit wiederholtem Öffnen. Nicht durch stumme Pakettests abgedeckt. Regler, Engine-Wert und tatsächliches Signal über Neustarts und Übergänge vergleichen. C2, C8. |
| [#237](https://github.com/nulloy/nulloy/issues/237) | Fluent-Design-Skin | Zurückstellen | P3 | Zusätzlicher Community-Skin, keine notwendige Modernisierung. Erst später optional mit Kompatibilitätsprüfung; die vier bisherigen Skins bleiben. |
| [#236](https://github.com/nulloy/nulloy/issues/236) | Player läuft ohne sichtbares Fenster | Prüfen | P1 | Gespeicherte Position wird ohne Bildschirmprüfung übernommen. Mehrmonitor-/DPI-Wechsel reproduzieren und sichtbare Wiederherstellung absichern. Keine Gleichsetzung mit dem erledigten Minimierungsfehler. C6. |
| [#235](https://github.com/nulloy/nulloy/issues/235) | Fortschritt je Hörbuchtrack | Später | P3 | Per-Datei-Resume und Anzeige gemeinsam mit #23/#132 spezifizieren. Ein gespeicherter Playliststatus ist noch keine verlässliche Fortschrittsanzeige pro Datei. C5. |
| [#234](https://github.com/nulloy/nulloy/issues/234) | Linux-Konfigurationspfad | Plattform | P2 | Historischer Nicht-Windows-Pfad verwendet unter bestimmten Installationspfaden `~/.nulloy`. Bei Linux-Migration neue Pfadregeln und Import bestehender Profile planen; Windows-Data bleibt portabel. C5. |
| [#230](https://github.com/nulloy/nulloy/issues/230) | Gentoo-Link auf Originalwebsite | Zurückstellen | P3 | Betrifft die Upstream-Website. Einen Fork-Link erst mit nachgewiesenem Paket für unseren Fork dokumentieren; kein Originalpaket als Fork-Build bewerben. |
| [#227](https://github.com/nulloy/nulloy/issues/227) | Ohne Übersetzungen bauen | Später | P3 | Noch keine CMake-Option dafür. Übersetzungen werden erstellt; geringer unmittelbarer Nutzen für unseren Player. Größenersparnis vor zusätzlicher Buildvariante messen. C1. |
| [#225](https://github.com/nulloy/nulloy/issues/225) | Hänger beim Hören und Hinzufügen auf Mac | Teilweise | P1 | Diskussion enthält auch einen aktuellen Bericht nach früherem Vorab-Fix. PR #6 und Drop-Tests betreffen passende Bereiche, beweisen aber keine Beseitigung sämtlicher Hänger. Dauerlast und Abbruch testen. C2, C7, C8. |
| [#224](https://github.com/nulloy/nulloy/issues/224) | Poly-WAV | Später | P2 | Nur ein kurzer Hinweis auf eine E-Mail-Anfrage. Beispieldatei und erwartetes Kanal-/Metadatenverhalten fehlen. Normales WAV in CI belegt keine Poly-WAV-Unterstützung. |
| [#218](https://github.com/nulloy/nulloy/issues/218) | Enter und Entfernen per Tastatur | Teilweise | P2 | `itemActivated` startet Titel, Entfernen ist konfigurierbar. Mac-Return/Backspace-Verhalten aus der Diskussion separat prüfen; der Windows-Test prüft Delete-Aktion, nicht jede echte Tastenkombination. C3, C8, C10. |
| [#217](https://github.com/nulloy/nulloy/issues/217) | Trackerformate | Plattform | P2 | Upstream nennt fehlendes Decoder-Plugin im Mac-Paket. Die aktuelle Sechs-Format-Matrix enthält IT/MOD/S3M/XM nicht. Vor Zusage auf jedem Zielsystem Paketinhalt und Beispieldateien testen. |
| [#211](https://github.com/nulloy/nulloy/issues/211) | Explorer öffnet nur letzten Titel | Prüfen | P1 | Mehrere Explorer-Aufrufe sind ein anderer Pfad als mehrere Dateien pro Drop/IPC-Nachricht. Enqueue/PlayEnqueued mit laufender und neuer Instanz testen; Reihenfolge und Trackindizes prüfen. C5, C8. |
| [#205](https://github.com/nulloy/nulloy/issues/205) | Cover im Tag-Editor hinzufügen | Später | P3 | Coverlesen und Tag-Schreiben sind keine Cover-Schreibfunktion. Später mit formatspezifischen Roundtrips planen; aktuelle TagLib-Lebensdauerfixes erfüllen diesen Wunsch nicht. C9. |
| [#204](https://github.com/nulloy/nulloy/issues/204) | Lyrics bearbeiten | Teilweise | P3 | Der Autor findet USLT bereits unter Raw Tags. Eine komfortable, formatübergreifende Lyrics-Funktion ist damit nicht erledigt. Bedarf und unterstützte Tags vor UI-Erweiterung klären. |
| [#201](https://github.com/nulloy/nulloy/issues/201) | Private Qt-Header | Abgedeckt | — | Qt-6-Skinpfad nutzt die neue Ressourcenimplementierung; `Qt5::CorePrivate` bleibt nur im Vergleichsbuild. Für das veröffentlichte Qt-6-Paket erfüllt. C1. |
| [#197](https://github.com/nulloy/nulloy/issues/197) | Spektralfarben in Waveform | Später | P3 | Zusammen mit #154 planen. Erfordert zusätzliche Audiodaten/Berechnung und Darstellung; ist kein bloßer Farbwechsel des vorhandenen Peaksignals. C7. |
| [#193](https://github.com/nulloy/nulloy/issues/193) | Auswahl startet sofort Wiedergabe | Später | P3 | Würde Tastaturnavigation und Mehrfachauswahl beeinflussen. Allenfalls ausdrückliche Option; Default-Verhalten beim Drag-and-drop erhalten. C3. |
| [#187](https://github.com/nulloy/nulloy/issues/187) | Waveform vorberechnen | Später | P2 | Direkt interessant für schnelles Vorhören. Cache vorhanden, Vorberechnungsqueue nicht. Erst Abbruch, Cache-I/O und Priorisierung messen, dann optional vorladen. Mini-Waveform aus Kommentar separat behandeln. C7. |
| [#176](https://github.com/nulloy/nulloy/issues/176) | Fehlendes GStreamer-Plugin | Prüfen | P2 | Mehrere Berichte ohne einheitliche reproduzierbare Datei. Paketierte Decoder und sechs Testformate helfen, belegen aber nicht alle Recorder-Formate. Fehlermeldung und konkrete Dateien zuordnen. C2, C8. |
| [#168](https://github.com/nulloy/nulloy/issues/168) | Terminalplayer | Zurückstellen | P3 | Eine zusätzliche Oberfläche liegt außerhalb der aktuellen Migration. Bestehende Kommandozeilensteuerung ist keine vollständige Terminaloberfläche. |
| [#164](https://github.com/nulloy/nulloy/issues/164) | Waveformfarben einstellen | Teilweise | P3 | Farben sind über Skin-Dateien veränderbar, wie auch ein Kommentar beschreibt. Ein komfortabler Einstellungsdialog fehlt. Bestehenden Mechanismus dokumentieren; Editor später. C7. |
| [#154](https://github.com/nulloy/nulloy/issues/154) | Frequenzabhängige Waveformfarbe | Später | P3 | Gemeinsames Vorhaben mit #197; zusätzlich erwähnte logarithmische Darstellung gesondert bewerten. Keine Änderung am Standardbild im Stabilisierungsschritt. C7. |
| [#151](https://github.com/nulloy/nulloy/issues/151) | Waveform zoomen | Später | P3 | Für lange Aufnahmen sinnvoll. Datenauflösung, Navigation und Speicherbedarf zuerst festlegen; mit Bereichsschleifen kompatibel planen. C7. |
| [#148](https://github.com/nulloy/nulloy/issues/148) | Skin-Demo | Zurückstellen | P3 | Fortsetzung von #147, kein separater Fehler. Gestaltungsvorschlag derzeit nicht übernehmen. |
| [#147](https://github.com/nulloy/nulloy/issues/147) | Neuer Skin-Vorschlag | Zurückstellen | P3 | Zusätzliche Gestaltung, widerspricht der Priorität auf unverändertem UI im ersten Schritt. Später als optionale Alternative bewertbar. |
| [#146](https://github.com/nulloy/nulloy/issues/146) | Metadaten fehlen bei Pfeiltasten-Shortcuts | Teilweise | P2 | Kommentare grenzen auf Up/Down als Trackwechsel ein. `setPlayingItem()` erzwingt inzwischen Metadaten-Refresh, aber der konkrete Shortcut-Fall ist nicht gezielt abgenommen. Mit neu belegten Pfeiltasten testen. C3, C9. |
| [#145](https://github.com/nulloy/nulloy/issues/145) | projectM-Visualisierung | Zurückstellen | P3 | Zusätzliche Visualisierung und Abhängigkeit, kein Nutzen für die aktuell priorisierten Start-/Waveformzeiten. |
| [#141](https://github.com/nulloy/nulloy/issues/141) | Waveform erreicht Ende zu früh | Teilweise | P2 | Engine behandelt kurze Dateien, neue Tests decken 50/250/800 ms und Übergänge ab. Sie messen keine Synchronität zwischen sichtbarem Ende und tatsächlicher Audioausgabe. Diese Messung ergänzen. C2, C8. |
| [#139](https://github.com/nulloy/nulloy/issues/139) | Verschieben eines Musikordners blockiert UI | Prüfen | P2 | Keine Beschreibung außer Titel. Externes Verschieben, nicht erreichbare Dateien und laufende Waveform getrennt reproduzieren; keine bestimmte Ursache behaupten. C7. |
| [#138](https://github.com/nulloy/nulloy/issues/138) | Apostroph beim Anzeigen in Finder | Plattform | P2 | Im direkten `open -R`-Argument wird weiterhin Shell-Escaping auf den Pfad angewandt. Das ist ein konkreter Prüfpunkt; direkte Argumentliste und benutzerdefinierten Shell-Befehl getrennt behandeln. Mac-Laufzeittest fehlt. C5. |
| [#135](https://github.com/nulloy/nulloy/issues/135) | Bewertungen | Später | P3 | Lesbare/schreibbare Rating-Tags und deren Darstellung separat spezifizieren. Kein Teil der aktuellen Metadatenfixes. |
| [#133](https://github.com/nulloy/nulloy/issues/133) | A/B-Wiederholung | Später | P3 | Mit #75 zu einem Vorhaben zusammenfassen. Erst gewöhnliches Repeat bei verändertem Tempo absichern. |
| [#132](https://github.com/nulloy/nulloy/issues/132) | Letzten Wiedergabestatus merken | Teilweise | P2 | Sitzungswiederherstellung und StartPaused vorhanden; Issue selbst ohne Details. Play/Pause/Position nach Neustart testen und vom Per-Datei-Wunsch #23 abgrenzen. C5. |
| [#129](https://github.com/nulloy/nulloy/issues/129) | Entfernen von 5.000 Titeln hängt | Prüfen | P1 | Große Listen bisher nicht entsprechend geprüft; separater Codepfad startet Nachfolger auch aus Pause. Last und Zustandserhalt getrennt testen. C3, C8. |
| [#123](https://github.com/nulloy/nulloy/issues/123) | M3U-Dateizuordnung | Später | P3 | M3U-Verarbeitung existiert. Registrierung im Betriebssystem ist eine eigene optionale Integrationsaufgabe; das portable ZIP richtet sie nicht automatisch ein. C5. |
| [#121](https://github.com/nulloy/nulloy/issues/121) | Playlist mischen | Teilweise | P2 | Shuffle existiert, PR #6 korrigiert das vollständige Entnehmen der Items und prüft den Nachfolger. Issue enthält keine genaue Erwartung. Shuffle während Play/Pause und Persistenz ergänzend prüfen. C3, C8. |
| [#119](https://github.com/nulloy/nulloy/issues/119) | Einheitliche Kontextmenü-Icons | Zurückstellen | P3 | Rein optisch und ohne nähere Beschreibung. Vorhandene Darstellung zunächst erhalten. |
| [#116](https://github.com/nulloy/nulloy/issues/116) | MP4 auf macOS | Plattform | P2 | Nur E-Mail-Vermerk, keine Datei. Container/Codec-Probe im späteren Mac-Paket nötig; sechs erfolgreiche Windowsformate sind kein MP4-Nachweis. |
| [#108](https://github.com/nulloy/nulloy/issues/108) | Stil-Editor | Zurückstellen | P3 | Eigenes Werkzeug für Skins, keine Voraussetzung für deren Qt-6-Betrieb. Mit #164 nur bei konkretem Bedarf aufgreifen. |
| [#106](https://github.com/nulloy/nulloy/issues/106) | Medienbibliothek | Zurückstellen | P3 | Größerer Funktions- und Architekturumfang. Zunächst den schnellen datei-/playlistbasierten Ablauf pflegen. |
| [#105](https://github.com/nulloy/nulloy/issues/105) | Karaoke-Filter | Zurückstellen | P3 | Kein näherer Anwendungsfall im Issue. Audioeffekt wäre gesondertes Feature, kein Migrationsbedarf. |
| [#100](https://github.com/nulloy/nulloy/issues/100) | Aktuelle Playlist sortieren | Später | P2 | Sortierung beim Nachladen eines Ordners ist vorhanden, Sortieren der bestehenden Playlist nach Name/Nummer/Dauer ist ein anderer Wunsch. Später mit stabiler Wiedergabezuordnung testen. C3, C10. |
| [#98](https://github.com/nulloy/nulloy/issues/98) | Letzte Playlist abhängig vom Startweg | Später | P2 | Gewünscht ist Wiederherstellen beim Direktstart, Ersetzen beim Dateiöffnen. Kommentare präzisieren dies; bloßes RestorePlaylist erfüllt es nicht vollständig. Mit #211/#23 als Startregel spezifizieren. C5. |
| [#79](https://github.com/nulloy/nulloy/issues/79) | System-Audioausgang wechselt nicht mit | Plattform | P2 | Separater Fall von Geräte-Hotplug während laufender App. Bei Mac-Freigabe Kopfhörer, Display und Rückwechsel testen; mit #249 zusammenführen. C2. |
| [#76](https://github.com/nulloy/nulloy/issues/76) | Playlist-Seitenleiste oder Tabs | Zurückstellen | P3 | Verändert Fensteraufbau und Bedienung. Keine Voraussetzung für die technische Modernisierung. |
| [#75](https://github.com/nulloy/nulloy/issues/75) | Markierten Bereich wiederholen | Später | P3 | Gleicher Kernbedarf wie #133. Ein gemeinsames optionales Feature genügt; Grenzpunkte bei Seek und Tempo testen. |
| [#74](https://github.com/nulloy/nulloy/issues/74) | Cover in voller Größe | Später | P3 | Ohne genaue Anforderungen. Vorhandenes Coverladen nicht mit einer Vollbild-/Originalgrößenansicht gleichsetzen. |
| [#69](https://github.com/nulloy/nulloy/issues/69) | Mausrad zum Seek statt Lautstärke | Später | P3 | Als ausdrückliche Einstellung denkbar. Bestehende Belegung bleibt Default; mit eventuellem Waveformzoom abstimmen. |
| [#68](https://github.com/nulloy/nulloy/issues/68) | CUE-Sheets | Später | P2 | Eigene Parser-/Subtrackfunktion. Relevante mögliche Erweiterung für lange Aufnahmen, aber keine Folgerung aus bestehendem M3U-Support. |
| [#55](https://github.com/nulloy/nulloy/issues/55) | Pause nach jedem Titel | Später | P3 | Geplante manuelle Kontrolle darf nicht wie #248 als Fehler behandelt werden. Bei Umsetzung bereits vorbereiteten Nachfolger ausdrücklich berücksichtigen. C2, C3. |
| [#53](https://github.com/nulloy/nulloy/issues/53) | Playlistsuche | Später | P2 | Sinnvoll für größere Listen. Filterung muss Abspielreihenfolge, Auswahl und Drag-and-drop erhalten. Nach Lasttests und mit optionalem Suchfeld planen. |
| [#49](https://github.com/nulloy/nulloy/issues/49) | Frei konfigurierbarer Startknopf | Zurückstellen | P3 | Zusätzlicher Button und externer Prozessstart sind kein aktueller Bedarf. Bestehende Shortcuts lösen nicht automatisch diesen Wunsch. |
| [#48](https://github.com/nulloy/nulloy/issues/48) | MPRIS | Plattform | P2 | Für spätere Linux-Desktopintegration sinnvoll. Zusammen mit #262 in einem Plattformkonzept behandeln; Windows-Shortcuts sind keine MPRIS-Implementierung. |
| [#45](https://github.com/nulloy/nulloy/issues/45) | Papierkorb-Shortcut ohne Nachfrage | Teilweise | P2 | Aktion ist inzwischen konfigurierbar und die normale Bestätigung abschaltbar. Fehlerfall mit endgültigem Löschen gesondert schützen; zuerst Rückgabevertrag aus #255 korrigieren. C4, C10. |
| [#31](https://github.com/nulloy/nulloy/issues/31) | Doppelklick auf Vor/Zurück | Zurückstellen | P3 | E-Mail-Vermerk ohne gewünschte Semantik. Nicht eigenmächtig eine neue Doppelklickbelegung festlegen. |
| [#28](https://github.com/nulloy/nulloy/issues/28) | Android-Ausgabe | Zurückstellen | P3 | Separate Plattform und Bedienung, weit außerhalb unseres Windows-Migrationsschritts. |
| [#23](https://github.com/nulloy/nulloy/issues/23) | Position beim erneuten Dateiöffnen merken | Später | P2 | Kommentare verlangen ausdrücklich Resume pro Datei, auch beim externen Öffnen. Sitzungswiederherstellung ist vorhanden, diesen Fall setzt `readMessage()` teilweise auf Anfang. Gemeinsam mit #235/#98 planen. C5. |
| [#20](https://github.com/nulloy/nulloy/issues/20) | Stereo-Balance | Später | P3 | Kleine mögliche Audioerweiterung, aber Geräte-/Kanalauswahl und Lautstärkeerhalt haben Vorrang. Später mit bekannten Links-/Rechts-Testsignalen. |
| [#14](https://github.com/nulloy/nulloy/issues/14) | Separate Stereo-Waveforms | Später | P3 | Aktuell werden Kanäle vor der Peak-Erfassung zusammengeführt. Getrennte Ansichten brauchen Daten- und Darstellungsänderungen; die vorhandene Kanalzahl-Metadatenabfrage ist nur ein Teilbedarf. C7, C9. |
| [#11](https://github.com/nulloy/nulloy/issues/11) | Exklusive Dateisperre unter Windows | Prüfen | P2 | Der verlinkte Originalkommentar beschreibt Konflikte mit anderen Programmen während Wiedergabe. TagLib-Lebensdauerfixes helfen, beweisen aber keine Freigabe aller GStreamer-Handles. Öffnen, Umbenennen und Tag-Änderung während Play/Pause/Stop prüfen. C2, C9. |
| [#10](https://github.com/nulloy/nulloy/issues/10) | Last.fm-Scrobbling | Zurückstellen | P3 | Konto- und Netzwerkintegration ist eine optionale spätere Erweiterung. Keine Voraussetzung für den lokalen Player. |
| [#7](https://github.com/nulloy/nulloy/issues/7) | Icons/Farben nach Dateityp | Teilweise | P3 | Die diskutierte Alternative `%e`/`%E` ist bereits implementiert. Unterschiedliche Dateityp-Icons sind damit nicht erfüllt und bleiben eine optionale Gestaltung. C9. |

## Gebündelte Arbeitspakete statt 80 Kopien

| Reihenfolge | Arbeitspaket | Zugehörige Issues | Erledigungskriterium |
| --- | --- | --- | --- |
| 1 | Papierkorb und Zustand beim Entfernen | #255, #129, #45, angrenzend #11 | Rückgaben unterscheiden Erfolg/Abbruch/Fehler; nur tatsächlich verschobene Dateien verschwinden aus der Playlist; Pause bleibt erhalten. |
| 2 | Lautstärke, Tempo und Übergänge | #238, #240, #248, #261, #225, #141 | Automatisierte Zustands-/Zeitprüfungen plus bestätigte manuelle Audioabnahme. Fehler nicht allein anhand des UI-Reglers bewerten. |
| 3 | Öffnen und Fensterwiederherstellung | #211, #236, später #98 | Definierte Mehrdatei-Reihenfolge über Explorer/IPC; erreichbares Fenster nach Monitorwechsel; bestehender Mehrfach-Drop bleibt erfolgreich. |
| 4 | Große Listen und Waveform-Laufzeiten | #129, #139, #187, ergänzend #146 | Vergleichbare Messungen für 100/1.000/5.000 Titel und lange Dateien, einschließlich Abbruch/Schließen und Speicher. Kein ungeprüftes paralleles Vorladen. |
| 5 | Metadaten- und Formatlücken | #241, #245, #176, #224, #217, #116 | Pro Fall konkrete Beispieldatei, erwartetes Ergebnis und passender Test auf der unterstützten Plattform. |
| 6 | Begrenzter Rust-Pilot | Migrationsplan Phase 5 | Eine kleine Komponente, gleiche Eingaben und Ergebnisse, gemessener Integrationsaufwand, unverändertes UI. Kein gleichzeitiger Playback-Rewrite. |
| Separat | Linux-/macOS-Freigaben | #265, #250, #246, #244, #243, #234, #79, #48 | Eigene Builds, Pakete und reale Plattformtests. Kein pauschales Übertragen der Windows-Abnahme. |

Die übrigen Features bleiben eine Wunschliste. Besonders Suche, Sortieren, Resume und optionale Waveform-Vorberechnung passen zum bisherigen Bedienkonzept. Neue Skins, Bibliotheksansicht, Android und Visualisierungen würde ich derzeit zurückstellen.

## Codebelege zum geprüften Release

Die Links verwenden den vollständigen Commit des Releases und bleiben unabhängig von späteren Änderungen an `master`.

- **C1, Build und Qt-Migration:** [CMakeLists.txt](https://github.com/Auda29/nulloy/blob/4a34c2ccd13b4515913600fb6d9b52d0b8fe2403/CMakeLists.txt), [Skin-Ressourcen](https://github.com/Auda29/nulloy/blob/4a34c2ccd13b4515913600fb6d9b52d0b8fe2403/src/qt6/skinResources.cpp), [Archiv-Erzeugung](https://github.com/Auda29/nulloy/blob/4a34c2ccd13b4515913600fb6d9b52d0b8fe2403/tools/phase2/build-assets.py).
- **C2, Wiedergabe:** [playbackEngineGstreamer.cpp](https://github.com/Auda29/nulloy/blob/4a34c2ccd13b4515913600fb6d9b52d0b8fe2403/src/plugins/pluginGstreamer/playbackEngineGstreamer.cpp). Besonders `_handleAboutToFinish`, `resetPipeline`, `setVolume`, `processGstMessage` und `checkStatus`.
- **C3, Playlist:** [playlistWidget.cpp](https://github.com/Auda29/nulloy/blob/4a34c2ccd13b4515913600fb6d9b52d0b8fe2403/src/widgetCollection/playlistWidget.cpp). Besonders `removeFiles`, `removeSelected`, `setPlayingItem`, `playItem`, Nachfolgerbehandlung und `shufflePlaylist`.
- **C4, Papierkorb:** [trash.cpp](https://github.com/Auda29/nulloy/blob/4a34c2ccd13b4515913600fb6d9b52d0b8fe2403/src/platform/trash.cpp), [Windows-Aufruf](https://github.com/Auda29/nulloy/blob/4a34c2ccd13b4515913600fb6d9b52d0b8fe2403/src/platform/trash_win.cpp), [Aufrufer in actionManager.cpp](https://github.com/Auda29/nulloy/blob/4a34c2ccd13b4515913600fb6d9b52d0b8fe2403/src/actionManager.cpp#L452).
- **C5, Start und Persistenz:** [player.cpp](https://github.com/Auda29/nulloy/blob/4a34c2ccd13b4515913600fb6d9b52d0b8fe2403/src/player.cpp), [main.cpp](https://github.com/Auda29/nulloy/blob/4a34c2ccd13b4515913600fb6d9b52d0b8fe2403/src/main.cpp), [common.cpp](https://github.com/Auda29/nulloy/blob/4a34c2ccd13b4515913600fb6d9b52d0b8fe2403/src/common.cpp), [playlistStorage.cpp](https://github.com/Auda29/nulloy/blob/4a34c2ccd13b4515913600fb6d9b52d0b8fe2403/src/playlistStorage.cpp). Besonders `readMessage`, `loadDefaultPlaylist`, `revealInFileManager` und `rcDir`.
- **C6, Fenster:** [mainWindow.cpp](https://github.com/Auda29/nulloy/blob/4a34c2ccd13b4515913600fb6d9b52d0b8fe2403/src/mainWindow.cpp). Besonders `loadSettings` und `closeEvent`.
- **C7, Waveform:** [waveformBuilderGstreamer.cpp](https://github.com/Auda29/nulloy/blob/4a34c2ccd13b4515913600fb6d9b52d0b8fe2403/src/plugins/pluginGstreamer/waveformBuilderGstreamer.cpp), [abstractWaveformBuilder.cpp](https://github.com/Auda29/nulloy/blob/4a34c2ccd13b4515913600fb6d9b52d0b8fe2403/src/plugins/abstractWaveformBuilder.cpp), [waveformSlider.cpp](https://github.com/Auda29/nulloy/blob/4a34c2ccd13b4515913600fb6d9b52d0b8fe2403/src/widgetCollection/waveformSlider.cpp).
- **C8, Testumfang:** [testPlaylistWidget.cpp](https://github.com/Auda29/nulloy/blob/4a34c2ccd13b4515913600fb6d9b52d0b8fe2403/tests/testPlaylistWidget.cpp), [testPlayerPackage.cpp](https://github.com/Auda29/nulloy/blob/4a34c2ccd13b4515913600fb6d9b52d0b8fe2403/tests/testPlayerPackage.cpp), [testFileDrop.cpp](https://github.com/Auda29/nulloy/blob/4a34c2ccd13b4515913600fb6d9b52d0b8fe2403/tests/testFileDrop.cpp), [testPluginResources.cpp](https://github.com/Auda29/nulloy/blob/4a34c2ccd13b4515913600fb6d9b52d0b8fe2403/tests/testPluginResources.cpp).
- **C9, Tags und Cover:** [tagReaderTaglib.cpp](https://github.com/Auda29/nulloy/blob/4a34c2ccd13b4515913600fb6d9b52d0b8fe2403/src/plugins/pluginTaglib/tagReaderTaglib.cpp), [coverReaderTaglib.cpp](https://github.com/Auda29/nulloy/blob/4a34c2ccd13b4515913600fb6d9b52d0b8fe2403/src/plugins/pluginTaglib/coverReaderTaglib.cpp), [trackInfoReader.cpp](https://github.com/Auda29/nulloy/blob/4a34c2ccd13b4515913600fb6d9b52d0b8fe2403/src/trackInfoReader.cpp).
- **C10, Aktionen und Shortcuts:** [actionManager.cpp](https://github.com/Auda29/nulloy/blob/4a34c2ccd13b4515913600fb6d9b52d0b8fe2403/src/actionManager.cpp), [settings.cpp](https://github.com/Auda29/nulloy/blob/4a34c2ccd13b4515913600fb6d9b52d0b8fe2403/src/settings.cpp), [Windows-Tastenzuordnung](https://github.com/Auda29/nulloy/blob/4a34c2ccd13b4515913600fb6d9b52d0b8fe2403/3rdParty/qxt-696423b-patched/qxtglobalshortcut_win.cpp).

## Release-Zuordnung

PR [#6 im Fork](https://github.com/Auda29/nulloy/pull/6) wurde am 8. September 2026 gemergt. Der neue Tag enthält den angepassten Port von Upstream-PR #263 sowie aktualisierte Fork-Dokumentation und Release-Hinweise.

- [Release v0.10.0-alpha.2](https://github.com/Auda29/nulloy/releases/tag/v0.10.0-alpha.2)
- [Release-Workflow](https://github.com/Auda29/nulloy/actions/runs/34248258786)
- [Änderungen in Alpha.2](releases/0.10.0-alpha.2.md)

Der Release-Workflow ist erfolgreich abgeschlossen. Die Veröffentlichung ist öffentlich und als Vorabversion markiert, kein Entwurf. Der entfernte Tag zeigt auf den oben genannten Commit. Alle sechs Assets wurden anschließend ohne GitHub-Anmeldung heruntergeladen und gegen die veröffentlichten Prüfsummen geprüft. Die internen Hashes von 490 im Paketmanifest erfassten Dateien stimmen; alle 236 enthaltenen EXE-/DLL-Dateien besitzen einen x64-PE-Header. Die veröffentlichten Testnachweise gehören zum selben Paket.

SHA-256 des Windows-ZIPs: `91f733bad90ee9a7514e0d0e0c9d3b77e58a1645e3d29e3abf988112a4db51f5`. Lokaler Prüfbeleg: `.phase4/published-alpha-2/public-download-verification.json`.

Die manuelle Hör- und Bedienabnahme dieses neuen Releases ist noch nicht bestätigt. Die frühere Abnahme der Migration bleibt dokumentiert, ersetzt aber keinen aktuellen Hörtest. Die hier aufgeführten offenen Prüfpunkte werden durch die Veröffentlichung einer Alpha nicht als erledigt markiert.
