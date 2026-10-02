# Status aller 80 Upstream-Issues

## Aktueller Lieferstand

Snapshot: 2026-09-10T08:53:25.460309+00:00. Ursprüngliche Swarm-PRs #7–#25: 16 gemergt, 3 offen. PR #20 (Register) und #25 (Metadaten) sind integriert. Weitere unterstützende Folge-PRs zählen nicht zu diesen 19 ursprünglichen PRs.

Die [Paketbaseline](ACCEPTANCE_BASELINE.md) trennt das korrigierte Windows-ZIP, ältere interaktive EXE/Formatprüfung und offene Abnahmen. Die damalige Zurückstellung nativer Tests ist historisch: inzwischen sind automatisierte echte Windows-Tests auf entbehrlichen GitHub-Runnern freigegeben. Der [Folgestand der nativen Automation](NATIVE_AUTOMATION_STATUS.md) dokumentiert die offenen PRs #28/#29 und fehlgeschlagene Läufe; daraus folgt keine neue Paketabnahme. Historische Audit- und Review-Dateien bleiben unverändert.

Nachtrag 2026-09-11: Das [isolierte PR15-Paket und seine Auswahlprobe](NATIVE_AUTOMATION_STATUS.md#nachtrag-isoliertes-pr15-paket-und-auswahlprobe) sind mit Buildcommit, ZIP-/EXE-Prüfsummen und getrenntem Prüfercommit dokumentiert. Start-/Format-/Playlistbelege bestanden, Zweifachauswahl belegt, Kontextmenüprobe fehlgeschlagen. Kein gemeinsames Endpaket und keine native Papierkorb-Abnahme. Das Register führt diesen Teilstand separat unter `package_inspection_followup`.

Quelle: [ursprüngliche Analyse](../UPSTREAM_ISSUES_ANALYSIS.md). Der Swarm hat die 80 aufgeführten Issues mit ihren 126 Kommentaren erneut abgerufen und bewertet. Issue-IDs, Kommentar-IDs und alle Einzelzählungen wurden programmatisch gegen den Rohsnapshot geprüft.

Die maschinenlesbare [Statusdatei](issue-register.json) enthält je Issue die Quelllinks, Codebelege, Entscheidung, konkrete nächste Prüfung und den Lieferstatus. Der textuelle Rohsnapshot der öffentlichen Issue-Threads ist unter [handoff-evidence/audit/snapshot.jsonl](handoff-evidence/audit/snapshot.jsonl) mitversioniert; sein SHA-256 steht in der Statusdatei. [Übergabe für ein anderes Gerät](HANDOFF.md).

## Umfang

- Zielbranch: `integration/upstream-issues`. Kein Merge nach `master`, kein Release.
- Umsetzung zunächst nur für Stabilisierung; spätere Features und Plattformfreigaben bleiben zurückgestellt.
- Ein eigener PR je umzusetzendem Issue. Test-/Dokumentations-PRs werden nicht als Fehlerbehebung ausgegeben.
- „Geprüft“ bedeutet hier eine nachvollziehbare Bewertung, nicht die Reproduktion oder Lösung jedes ursprünglichen Fehlers.
- Status „Reproduktion ausstehend“ ist ausdrücklich nicht abgeschlossen. Die jeweilige nächste Prüfung und fehlende Voraussetzung bleiben sichtbar.

Audit-Entscheidungen: covered: 4, defer: 43, needs-repro: 5, platform: 12, stabilize: 16.

## Einzelstatus

| Issue | Thema | Audit | Lieferung / PR |
| --- | --- | --- | --- |
| [#265](https://github.com/nulloy/nulloy/issues/265) | Convert Nulloy to being a native Apple Silicon App | platform | spätere Plattformabnahme  |
| [#262](https://github.com/nulloy/nulloy/issues/262) | Doesn't respond to pressing multimedia keys on the keyboard or headphones | needs-repro | Bewertung dokumentiert; Hardware-/OS-Reproduktion blockiert [PR #20](https://github.com/Auda29/nulloy/pull/20) |
| [#261](https://github.com/nulloy/nulloy/issues/261) | Nulloy Crashing on MacOs | stabilize | Test-PR integriert; ursprüngliches Issue nicht pauschal geschlossen [PR #19](https://github.com/Auda29/nulloy/pull/19) |
| [#260](https://github.com/nulloy/nulloy/issues/260) | Qt6 migration | covered | Bestand im Code geprüft  |
| [#259](https://github.com/nulloy/nulloy/issues/259) | Feature request: make it visible in playlist which songs belong to a single album | defer | zurückgestellt gemäß Umfang  |
| [#256](https://github.com/nulloy/nulloy/issues/256) | Is there no portable version anymore? | covered | Bestand im Code geprüft  |
| [#255](https://github.com/nulloy/nulloy/issues/255) | Move to Trash app crash | stabilize | Draft: Qt-Papierkorbkorrektur; Windows-Nachweise paketgebunden, finale Playlistmatrix/macOS offen [PR #15](https://github.com/Auda29/nulloy/pull/15) |
| [#253](https://github.com/nulloy/nulloy/issues/253) | About dep dev-qt/linguist: are you sure that you need it? | platform | spätere Plattformabnahme  |
| [#250](https://github.com/nulloy/nulloy/issues/250) | MacOs Code Signing | platform | spätere Plattformabnahme  |
| [#249](https://github.com/nulloy/nulloy/issues/249) | AUDIO INPUT AND OUTPUT PREFERENCES MISSING | defer | zurückgestellt gemäß Umfang  |
| [#248](https://github.com/nulloy/nulloy/issues/248) | Nulloy won't play the next song in the playlist | stabilize | Dekodierte Repeat-/Übergangstests als Teilnachweis; Originalfall offen [PR #8](https://github.com/Auda29/nulloy/pull/8) [PR #11](https://github.com/Auda29/nulloy/pull/11) |
| [#246](https://github.com/nulloy/nulloy/issues/246) | Resizing window is extremely laggy (<1fps) | platform | spätere Plattformabnahme  |
| [#245](https://github.com/nulloy/nulloy/issues/245) | Bitrate `%B` not showing | needs-repro | Test-PR integriert; ursprüngliches Issue nicht pauschal geschlossen [PR #9](https://github.com/Auda29/nulloy/pull/9) |
| [#244](https://github.com/nulloy/nulloy/issues/244) | Volume slider is twitching upon volume change (with mousewheel) | platform | spätere Plattformabnahme  |
| [#243](https://github.com/nulloy/nulloy/issues/243) | Nulloy doesn't quit with the corner (X) button in MacOS | platform | spätere Plattformabnahme  |
| [#242](https://github.com/nulloy/nulloy/issues/242) | Are you sure that you need both zip and 7z? | covered | Bestand im Code geprüft  |
| [#241](https://github.com/nulloy/nulloy/issues/241) | Broken encoding for Cyrillic | stabilize | Korrektur-PR integriert; ursprüngliches Issue nicht pauschal geschlossen [PR #10](https://github.com/Auda29/nulloy/pull/10) |
| [#240](https://github.com/nulloy/nulloy/issues/240) | Incorrect loop point on non-default playback rate | stabilize | Test-PR integriert; ursprüngliches Issue nicht pauschal geschlossen [PR #11](https://github.com/Auda29/nulloy/pull/11) |
| [#238](https://github.com/nulloy/nulloy/issues/238) | Nulloy always starts on MAX-Volume | stabilize | Test-PR integriert; ursprüngliches Issue nicht pauschal geschlossen [PR #8](https://github.com/Auda29/nulloy/pull/8) |
| [#237](https://github.com/nulloy/nulloy/issues/237) | Fluent Design (Windows 11) skin | defer | zurückgestellt gemäß Umfang  |
| [#236](https://github.com/nulloy/nulloy/issues/236) | Initially works fine, then App Window is hidden on launch until reinstalled | stabilize | Draft: frühere Slim-Monitorabnahme dokumentiert; finales Paket, DPI/maximiert/weitere Skins offen [PR #16](https://github.com/Auda29/nulloy/pull/16) |
| [#235](https://github.com/nulloy/nulloy/issues/235) | Feature request: please consider adding of percentage of progress for every track - this is a commons feature for audiobook software | defer | zurückgestellt gemäß Umfang  |
| [#234](https://github.com/nulloy/nulloy/issues/234) | .config folder location: according to XDG Base Directory Specification it must be in $HOME/.config | platform | spätere Plattformabnahme  |
| [#230](https://github.com/nulloy/nulloy/issues/230) | Website: about how to install: please add link to Gentoo Guru  | defer | zurückgestellt gemäß Umfang  |
| [#227](https://github.com/nulloy/nulloy/issues/227) | Is it possible to compile without i18n? For smaller build | defer | zurückgestellt gemäß Umfang  |
| [#225](https://github.com/nulloy/nulloy/issues/225) | Constantly crashing while listening to tracks or when adding to playlist | stabilize | Playlist-/Waveform-/Engine-Teilnachweise; vollständiger Hänger nicht reproduziert [PR #12](https://github.com/Auda29/nulloy/pull/12) [PR #17](https://github.com/Auda29/nulloy/pull/17) [PR #19](https://github.com/Auda29/nulloy/pull/19) |
| [#224](https://github.com/nulloy/nulloy/issues/224) | Support for Poly Wave File Format | defer | zurückgestellt gemäß Umfang  |
| [#218](https://github.com/nulloy/nulloy/issues/218) | Feature request: Enter/Return key to play selected file | stabilize | Test-PR integriert; ursprüngliches Issue nicht pauschal geschlossen [PR #22](https://github.com/Auda29/nulloy/pull/22) |
| [#217](https://github.com/nulloy/nulloy/issues/217) | Tracker formats not working | platform | spätere Plattformabnahme  |
| [#211](https://github.com/nulloy/nulloy/issues/211) | When opening multiple songs at once it only plays the last one in the playlist | stabilize | Draft: echte Explorer-Matrix und Aufräumen des Testmenüs offen [PR #24](https://github.com/Auda29/nulloy/pull/24) |
| [#205](https://github.com/nulloy/nulloy/issues/205) | Tag editor: no way to add artwork | defer | zurückgestellt gemäß Umfang  |
| [#204](https://github.com/nulloy/nulloy/issues/204) | Tag Editor: add UNSYNCEDLYRICS | defer | zurückgestellt gemäß Umfang  |
| [#201](https://github.com/nulloy/nulloy/issues/201) | "Project MESSAGE: This project is using private headers and will therefore be tied to this specific Qt module build version": is it possible to resolve this warning? | covered | Bestand im Code geprüft  |
| [#197](https://github.com/nulloy/nulloy/issues/197) | Spectral Color Waveform View | defer | zurückgestellt gemäß Umfang  |
| [#193](https://github.com/nulloy/nulloy/issues/193) | Follow-the-cursor playback | defer | zurückgestellt gemäß Umfang  |
| [#187](https://github.com/nulloy/nulloy/issues/187) | Generate waveform ahead of time | defer | Waveform-/Cache-Messungen ergänzt; Vorberechnung bleibt zurückgestellt [PR #17](https://github.com/Auda29/nulloy/pull/17) |
| [#176](https://github.com/nulloy/nulloy/issues/176) | Error: Your GStreamer installation is missing a plug-in | needs-repro | Test-PR integriert; ursprüngliches Issue nicht pauschal geschlossen [PR #13](https://github.com/Auda29/nulloy/pull/13) |
| [#168](https://github.com/nulloy/nulloy/issues/168) | What do you think about cli (terminal, text only) player? | defer | zurückgestellt gemäß Umfang  |
| [#164](https://github.com/nulloy/nulloy/issues/164) | Add option to customize waveform colors | defer | zurückgestellt gemäß Umfang  |
| [#154](https://github.com/nulloy/nulloy/issues/154) | Waveform colored | defer | zurückgestellt gemäß Umfang  |
| [#151](https://github.com/nulloy/nulloy/issues/151) | Zoomable waveform | defer | zurückgestellt gemäß Umfang  |
| [#148](https://github.com/nulloy/nulloy/issues/148) | New Skin Proposal in Action - Live demo! | defer | zurückgestellt gemäß Umfang  |
| [#147](https://github.com/nulloy/nulloy/issues/147) | New skin proposal | defer | zurückgestellt gemäß Umfang  |
| [#146](https://github.com/nulloy/nulloy/issues/146) | Missing track information | stabilize | Test-PR integriert; ursprüngliches Issue nicht pauschal geschlossen [PR #25](https://github.com/Auda29/nulloy/pull/25) |
| [#145](https://github.com/nulloy/nulloy/issues/145) | projectM | defer | zurückgestellt gemäß Umfang  |
| [#141](https://github.com/nulloy/nulloy/issues/141) | Waveform playback ends too soon | stabilize | Test-PR integriert; ursprüngliches Issue nicht pauschal geschlossen [PR #23](https://github.com/Auda29/nulloy/pull/23) |
| [#139](https://github.com/nulloy/nulloy/issues/139) | Moving music directory freezes UI for some time | needs-repro | Korrektur-PR integriert; ursprüngliches Issue nicht pauschal geschlossen [PR #17](https://github.com/Auda29/nulloy/pull/17) |
| [#138](https://github.com/nulloy/nulloy/issues/138) | Apostrophe in filename breaks reveal in Finder | platform | spätere Plattformabnahme  |
| [#135](https://github.com/nulloy/nulloy/issues/135) | Ratings | defer | zurückgestellt gemäß Umfang  |
| [#133](https://github.com/nulloy/nulloy/issues/133) | AB repeat | defer | zurückgestellt gemäß Umfang  |
| [#132](https://github.com/nulloy/nulloy/issues/132) | Remember last playback state | stabilize | Korrektur-PR integriert; ursprüngliches Issue nicht pauschal geschlossen [PR #21](https://github.com/Auda29/nulloy/pull/21) |
| [#129](https://github.com/nulloy/nulloy/issues/129) | Application freezes when trying to remove a lot of tracks from the playlist | stabilize | Korrektur-PR integriert; ursprüngliches Issue nicht pauschal geschlossen [PR #12](https://github.com/Auda29/nulloy/pull/12) |
| [#123](https://github.com/nulloy/nulloy/issues/123) | .m3u file association | defer | zurückgestellt gemäß Umfang  |
| [#121](https://github.com/nulloy/nulloy/issues/121) | Playlist randomization | stabilize | Test-PR integriert; ursprüngliches Issue nicht pauschal geschlossen [PR #18](https://github.com/Auda29/nulloy/pull/18) |
| [#119](https://github.com/nulloy/nulloy/issues/119) | Uniform context menu icons | defer | zurückgestellt gemäß Umfang  |
| [#116](https://github.com/nulloy/nulloy/issues/116) | mp4 support on macOS | platform | spätere Plattformabnahme  |
| [#108](https://github.com/nulloy/nulloy/issues/108) | Add style ditor | defer | zurückgestellt gemäß Umfang  |
| [#106](https://github.com/nulloy/nulloy/issues/106) | Media library support | defer | zurückgestellt gemäß Umfang  |
| [#105](https://github.com/nulloy/nulloy/issues/105) | Karaoke Filter control | defer | zurückgestellt gemäß Umfang  |
| [#100](https://github.com/nulloy/nulloy/issues/100) | Sort per name / per number | defer | zurückgestellt gemäß Umfang  |
| [#98](https://github.com/nulloy/nulloy/issues/98) | Suggest last playlist  | defer | zurückgestellt gemäß Umfang  |
| [#79](https://github.com/nulloy/nulloy/issues/79) | In OSX Nulloy don't respect system Output Device. | platform | spätere Plattformabnahme  |
| [#76](https://github.com/nulloy/nulloy/issues/76) | Songs playlist | defer | zurückgestellt gemäß Umfang  |
| [#75](https://github.com/nulloy/nulloy/issues/75) | Select and loop | defer | zurückgestellt gemäß Umfang  |
| [#74](https://github.com/nulloy/nulloy/issues/74) | Add support for full-size cover arts | defer | zurückgestellt gemäß Umfang  |
| [#69](https://github.com/nulloy/nulloy/issues/69) | Using mouse wheel for seekbar instead of volume control | defer | zurückgestellt gemäß Umfang  |
| [#68](https://github.com/nulloy/nulloy/issues/68) | CUE Sheets support | defer | zurückgestellt gemäß Umfang  |
| [#55](https://github.com/nulloy/nulloy/issues/55) | Add auto pause ability #feature | defer | zurückgestellt gemäß Umfang  |
| [#53](https://github.com/nulloy/nulloy/issues/53) | Playlist search functionality | defer | zurückgestellt gemäß Umfang  |
| [#49](https://github.com/nulloy/nulloy/issues/49) | Configurable button | defer | zurückgestellt gemäß Umfang  |
| [#48](https://github.com/nulloy/nulloy/issues/48) | MPRIS support | platform | spätere Plattformabnahme  |
| [#45](https://github.com/nulloy/nulloy/issues/45) | Move to trash, global shortcut, no prompt #feature | stabilize | Bestätigungs-/Abbruchschutz im Papierkorb-PR mitgeprüft; native Löschdialoge offen [PR #15](https://github.com/Auda29/nulloy/pull/15) |
| [#31](https://github.com/nulloy/nulloy/issues/31) | Double click for next / prev buttons | defer | zurückgestellt gemäß Umfang  |
| [#28](https://github.com/nulloy/nulloy/issues/28) | Nulloy for Android request ! | defer | zurückgestellt gemäß Umfang  |
| [#23](https://github.com/nulloy/nulloy/issues/23) | Saving position when close and reopen file (continue playback) | defer | zurückgestellt gemäß Umfang  |
| [#20](https://github.com/nulloy/nulloy/issues/20) | Stereo balance (left/right) | defer | zurückgestellt gemäß Umfang  |
| [#14](https://github.com/nulloy/nulloy/issues/14) | Show 2 waveforms when is a stereo file and 1 when is mono | defer | zurückgestellt gemäß Umfang  |
| [#11](https://github.com/nulloy/nulloy/issues/11) | Fix exclusive file lock on Windows | needs-repro | Test-PR integriert; ursprüngliches Issue nicht pauschal geschlossen [PR #14](https://github.com/Auda29/nulloy/pull/14) |
| [#10](https://github.com/nulloy/nulloy/issues/10) | Feature Request: LastFm Scrobbler/scrobbling support | defer | zurückgestellt gemäß Umfang  |
| [#7](https://github.com/nulloy/nulloy/issues/7) | Different icons (or color) for different type of files | defer | zurückgestellt gemäß Umfang  |

## Offene Abnahmen

Die ursprünglichen macOS-, Windows-Explorer-, Hardware-Audio-, HID- und Monitor-/DPI-Abläufe benötigen ihre jeweilige reale Umgebung. Linux-Tests können gemeinsame Logik, GStreamer-Ausgabedaten und Qt-Widgets prüfen, aber keine plattformfremde Abnahme ersetzen. Konkrete Schritte und verbleibende Lücken sind pro Issue in der JSON-Datei und für bearbeitete Issues im jeweiligen Bericht unter `docs/upstream/` festgehalten.

## Nachtrag 2026-09-11: isolierte Paket-Kontextmenübeobachtung

Der Registereintrag `package_context_menu_milestone` dokumentiert den verifizierten grünen Lauf [34584964888](https://github.com/Auda29/nulloy/actions/runs/34584964888) mit Prüfercommit `5cf2973242321053cd4c793e6518138828baead1` und 53 bestandenen Vertragsprüfungen. Er bindet die Beobachtung an das Qt6-Paket aus Buildlauf `34572047079` / Commit `9e1b3f060e649a64c698b2a5981dbfca1d741b84` und dessen unveränderte ZIP-/EXE-Prüfsummen. Exakt zwei von drei Zeilen blieben nach einem guarded Right-Click ausgewählt; das eigene Qt-Kontextmenü und `Remove From Playlist` sowie `Move To Trash` wurden mit Labels, Automation-IDs, PID und den distinct Runtime-IDs `[42, 197778, 4, -2147483613]` bzw. `[42, 197778, 4, -2147483612]` erkannt. Kein Menüeintrag wurde aufgerufen; Fixture-Dateien und Bereinigung sind final verifiziert.

Der Befund schließt nur diese isolierte, nichtdestruktive Qt6-Paketbeobachtung. Er ist weder das finale kombinierte PR15/24/29-Paket noch eine Papierkorb-, Explorer-, PR16-DPI/Fenster-, macOS-, kombinierte Qt5/Qt6- oder Release-Abnahme. Die historischen Recognition- und stdout-Serialisierungsfehler bleiben als FAIL erhalten. Die genehmigte Speicherbereinigung (29 Artefakte / 1,674,672,514 Bytes; 31 Caches / 10,632,210,125 Bytes) ist mit 309 verbliebenen Artefakten zum Prüfzeitpunkt und geschützten IDs `10188441880`, `10188259265` vermerkt; der Wert ist nicht als aktueller Gesamtbestand zu lesen. Siehe [Native-Automationsstand](NATIVE_AUTOMATION_STATUS.md#nachtrag-2026-09-11-isoliertes-kontextmenü-milestone-grün) und die externe Verifikationsablage.

## Nachtrag 2026-09-11: PR30 und getrennte native Vertragsmilestones

Der Live-API-Snapshot vom `2026-09-11T11:50:53.817380+00:00` bestätigt PR #30 unter exakt `c2405a0375b23dfdc3561a5bdd7a1eb56a812902` als offenem Draft. Windows-Qt5/Qt6-Lauf `34588893748` und Linux-Lauf `34588893721` sind für genau diesen PR-Head grün. Das bleibt CI-Branch-Nachweis: keine neue PR30-Paketprüfung, keine neue Paket-Hashannahme und keine kombinierte Endabnahme. Die Windows-Matrix bleibt seriell; Workflows wurden hierfür nicht verändert. Integration bleibt `919468efc32f4d038c96d7276a799794dab2e86e`, `master` bleibt `027d81a583b07457a4fa5f18b3e7dcca50b05b58`.

Der geprüfte Windows-Supervisor-/Qt-Fixture-Vertrag [34595596113](https://github.com/Auda29/nulloy/actions/runs/34595596113) ist separat als PASS dokumentiert: 18 Supervisor-Tests, davon 16 PASS und zwei ausdrücklich POSIX-bedingt übersprungen; vier harmlose Qt-Fixture-Tests PASS. Reviewte Quellen sind Supervisor `68cdc90f369d6c5f507c81cf757befb509dbfeb9`, Fixture `b7d228e885841cb796ed9d31fa79526864dba031` und assembled native commit `ca49815db8db16b8704cc82f89336e09f8ed2d70`; alle fünf Laufzeitskript-Hashes sind im Register und Elternnachweis festgehalten. Dies war kein Player-Paket und keine tatsächliche UIA-Abfrage: HWND `0` wurde vor der Query abgewiesen, die synthetische PID-Prüfung ist kein nativer UIA-Nachweis. COM-/Provider-Query bleibt `not_executed`; daraus folgen keine UIA-, Player- oder Release-Behauptungen.

Die Playerbeobachtung [34589940677](https://github.com/Auda29/nulloy/actions/runs/34589940677) bestand mit 60 Vertragsprüfungen am exakt gebundenen Qt6-Paket aus Buildlauf `34572047079` / Commit `9e1b3f060e649a64c698b2a5981dbfca1d741b84` (ZIP `5558a6ed786051224f7dcf3228a230fa45c95959f3e363e5b06b48d446ccb833`, EXE `d7d622c3a0afe88657fa108bebf72f7bfdc69777c9f1f626fe3fe26e589315f9`; Prüfer `4ab11fa4eb11ebd6844fc8290b8d362085da1b6d`). Zwei von drei Zeilen blieben nach einem guarded Right-Click ausgewählt; kein Menüeintrag wurde aufgerufen, die Fixture-Dateien blieben unverändert und die Bereinigung ist bestätigt. Dies erweitert den bestehenden 53-PASS-Nachweis aus Lauf `34584964888`; er wird nicht überschrieben. PR15-Papierkorbmatrix, PR24 Explorer, PR16 DPI/Fenster, macOS, kombinierte Qt5/Qt6-Endabnahme und Release bleiben offen.

Die laufende Beobachtung bleibt ausschließlich nichtdestruktiv; sie ist keine
Papierkorbaktion.

## Nachtrag 2026-09-11: Konsolidierung vor PR30-Merge

Der append-only-Konsolidierungsstand ist in [CONSOLIDATION.md](CONSOLIDATION.md)
und im Registerfeld `consolidation_snapshot` festgehalten. Die verifizierte
Bestandsaufnahme **nach** den Retirements lautet 12 Remote-Branches, 11 lokale
Branches und 10 Worktrees; der Stand davor war 33/34/33, jeweils sauber. Exakt
18 bereits gemergte PR-Branches (#7–#14, #17–#23, #25–#27) sowie sechs
Experimentzustände wurden archiviert bzw. entfernt. Das Archiv bewahrt die
Original-SHAs, Historien, Fehlschläge sowie ungetrackte/ignorierte Nachweise.
Die alte Codex-Branch war eine kombinierte Produktionsquelle und ist nicht mit
der isolierten `9e1b3f0`-Trash-Quelle gleichzusetzen; daraus folgt keine Aussage,
dass alle Änderungen gemergt seien.

Erhalten bleiben die vier dokumentierten Branch-Anker für Playerinspektion,
proof-only UIA-Timeout, eingefrorenes Paket und PR28-Desktopprobe. PR15
(Papierkorb-Review ohne formale native Abnahme), PR16 (Mixed-DPI/maximiert/Skins/
Minimieren-Wiederherstellen), PR24 (externe Mehrfachöffnung mit PR29-IPC-
Abhängigkeit sowie getrennte Öffnungs-/Großauswahl-Lücke), PR28 (kein
Produktfix, PR24/PR29-Abhängigkeit, offen ohne finalen PASS) und PR29 (grüne
Tests, aber kein Explorer-PASS) bleiben offen. `qml` ist unangetastetes Legacy,
keine neue aktive Arbeit.

PR30 ist in diesem Snapshot exakt auf `1e44a4477929cbd1bad7b36c204f8466f8711f69`
offen; Windows-Lauf `34597690721` und Linux-Lauf `34597690744` sind erfolgreich.
Das ist nur Branch-CI, keine Paket- oder kombinierte Endabnahme. Integration
`919468efc32f4d038c96d7276a799794dab2e86e` und `master`
`027d81a583b07457a4fa5f18b3e7dcca50b05b58` bleiben getrennt. Der Eintrag ist
vor dem möglichen späteren Merge durch den Elternprozess geschrieben und
behauptet diesen Merge nicht.
