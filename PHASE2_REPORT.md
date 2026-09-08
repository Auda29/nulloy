# Phase 2: CMake und Windows x64

Stand: 8. September 2026. Der vollständige Player baut mit CMake und Qt 5.15 als Windows-x64-Anwendung. Lokaler Build, saubere Windows-CI und Paket-Laufzeittests bestehen. Das CI-Testpaket wurde heruntergeladen und anhand seiner SHA-256-Prüfsumme verifiziert.

## Übernommene Basis

Phase 0 und Phase 1 wurden mit separaten Merge-Commits in den Fork `Auda29/nulloy` übernommen:

- [PR 1, Phase 0](https://github.com/Auda29/nulloy/pull/1), Merge `1b47ff69d9485144d113c2b20087f5c1d9cd62bf`.
- [PR 2, Phase 1](https://github.com/Auda29/nulloy/pull/2), Merge `1882bc7d340e873eba5e6038d13b6e5183254844`.

Der Branch `codex/phase-2-cmake-x64` beginnt am zweiten Merge. Die vorhandene Historie wurde nicht umgeschrieben. Die Anwendung verwendet weiterhin QtScript und die bisherige Skin-Dateisystem-Anbindung. Der Qt-6-Prototyp aus Phase 1 bleibt getrennt.

## Änderungen

Die rootseitige CMake-Datei baut Player, Widget-Sammlung, mitgelieferte Hilfsbibliotheken, GStreamer- und TagLib-Plugins, Qt-Tests, Übersetzungen, Icons und Skin-Archive. Originaldateien unter `src/skins` wurden nicht geändert. Slim, Silver, Metro und der eingebaute Native-Skin bleiben verfügbar.

Der Build-Helfer und der [Windows-Build-Leitfaden](docs/phase2/BUILD_WINDOWS.md) dokumentieren die MSYS2-MINGW64-Abhängigkeiten und die bisherigen Build-Optionen. qmake bleibt als Vergleich und für Linux/macOS erhalten. Eine Ablösung dieser Plattform-Builds gehört nicht zu diesem Windows-Schritt.

Das Paket übernimmt die Qt-5-Laufzeit sowie GStreamer-Module, Scanner und deren DLL-Abhängigkeiten. Der Packer prüft alle mitgelieferten PE-Dateien auf AMD64 und löst normale sowie verzögerte DLL-Imports auf. Ein Manifest mit Datei-Prüfsummen liegt im ZIP. Lokale Profile, Medien und Waveform-Caches werden nicht paketiert. Compiler- und Bibliotheksversionen stehen in `toolchain.txt`.

Vier kleinere Korrekturen waren für den Build beziehungsweise das Paket erforderlich:

- Der ActionManager bindet den verwendeten Windows-Icon-Header direkt ein. Der alte qmake-Aufbau hatte hier einen falschen Dateinamen; Phase 0 musste den Header noch beim Kompilieren erzwingen.
- Windows-Systemicons behalten ihren Pfadstring während des API-Aufrufs. Ungültige beziehungsweise leere Icon-Handles werden abgefangen.
- GStreamer erhält Unicode-Umgebungspfade. Das Prozessmanifest aktiviert UTF-8 für ANSI-Windows-APIs, und native Argumente werden als UTF-8 übergeben. Dadurch funktionieren die Audio-Module und der externe Scanner auch in einem Entpackpfad mit Umlaut.
- Die Playlist-Testfixture stellt die im Player vom ActionManager bereitgestellte Delete-Aktion her und wartet auf asynchrone Wiedergabe- und Titelwechsel. Die erwarteten Entfernungs-, Repeat- und Fokus-Ergebnisse bleiben erhalten.

## Prüfung

| Prüfung | Ergebnis |
|---|---|
| Qt 5.15.19, GCC 16.2, CMake 4.4.2, GStreamer 1.28.6, TagLib 2.2.1 | Vollständiger lokaler Release-Build |
| TrackInfoReader | 13 eigentliche Fälle bestanden, zusätzlich Initialisierung und Abschluss |
| PlaylistWidget | 3 eigentliche Fälle bestanden, zusätzlich Initialisierung und Abschluss |
| FileDrop | 4 eigentliche Fälle bestanden, zusätzlich Initialisierung und Abschluss |
| Paket mit Slim, Silver, Metro, Native | Je ein vollständiger Player-Workflow bestanden |
| Einzel- und gleichzeitiger Mehrfach-Drop | Über Qt-Drag-/Drop-Ereignisse am echten Playlist-Widget, Reihenfolge und Quelldateien geprüft |
| Echte Player-Aktionen | Entfernen-Aktion aus dem ActionManager, Playlist-Speicherung, Pause und Seek geprüft |
| Waveform | Vollständige WAV-Waveform und unmittelbarer Cache-Zugriff geprüft |
| Private MP3-Referenzen aus Phase 0 | Slim-Workflow mit Wiedergabe, Drop, Metadaten und Waveform bestanden; Medien und Logs bleiben lokal |
| Paket ohne Entwicklungs-PATH | Hashprüfung nach Entpacken; ausschließlich Windows System32 in PATH; keine Qt-/GStreamer-Pfade aus der Umgebung |
| Alternative Optionen | Ohne Skins, ohne TagLib, mit GStreamer-TagReader und Konsole kompiliert; `--version` geprüft |
| Saubere Windows-CI | Build, Tests, Paketprüfung und Artefakt-Upload bestanden |

Der zusätzliche Pakettest nutzt denselben Playerkern und das normale GStreamer-Plugin. Das Testprogramm und QtTest werden erst nach dem Entpacken ergänzt und gehören nicht zum ausgelieferten ZIP. Die drei bisherigen Tests verwenden weiterhin ein getrenntes Playbackplugin mit Fakesink. Der GitHub-Runner besitzt kein Audiogerät; dort nutzt auch der Pakettest ausdrücklich GStreamers Fallback ohne Gerät. Lokal wurde die normale Geräteauswahl bei stummgeschalteter Lautstärke geprüft. Eine Hörprüfung ist damit nicht belegt.

Die ersten beiden CI-Läufe fanden eine fehlende SVG-Build-Abhängigkeit und die fehlende Audio-Hardware des Runners. Beide Ursachen sind berücksichtigt. Die CI archiviert das Testpaket erst nach erfolgreichen Laufzeitprüfungen.

Der [erfolgreiche CI-Lauf](https://github.com/Auda29/nulloy/actions/runs/34194012324) prüfte den Code-Commit `ecfa168a6a248a22bb9982d53a4bf6d36ec6d730`. Das heruntergeladene ZIP enthält 210 x64-Binärdateien und ist 53.515.672 Bytes groß. SHA-256: `bbea42800d44ea1c30c85d7e7b7de21797c2745ecca5c35ee17c8bbdb675e7cf`. Nachweise: [Downloadprüfung](docs/phase2/ci-download-verification.json), [CI-Paketprüfung](docs/phase2/ci-package-verification.json), [lokale Paketprüfung](docs/phase2/local-package-verification.json), [Werkzeugversionen](docs/phase2/toolchain.txt) und die drei Testprotokolle unter `docs/phase2`.

## Geschwindigkeit und Grenzen

Die Funktionstests protokollieren Fensterbereitschaft, vollständige Waveform, Cache-Zugriff und Zerstörung des Playerobjekts. Bei bereits vorhandener GStreamer-Registry lagen beobachtete Fensterzeiten in lokalen Läufen ungefähr bei 0,5 Sekunden. Zehn Sekunden WAV wurden in etwa 0,25 bis 0,32 Sekunden verarbeitet. Der Cache-Zugriff lag unter der Millisekundenauflösung des Tests. Player-Abbau lag in diesen Läufen ungefähr zwischen 0,09 und 0,23 Sekunden.

Der erste Lauf aus einem frisch entpackten Verzeichnis war deutlich langsamer. Bei dem frisch heruntergeladenen CI-Paket wurden lokal sogar rund 51 Sekunden bis zur Fensterbereitschaft beobachtet. Dabei fehlt auch die GStreamer-Registry, und die DLLs liegen an einem neuen Pfad. Die jeweiligen Anteile von Plugin-Scan, Dateizugriff und Virenscanner wurden nicht getrennt gemessen. Diese Erststartkosten sind ein wesentlicher offener Punkt vor der Nutzung im Alltag. Die Werte sind nicht unmittelbar mit den Phase-0-Messungen über `WaitForInputIdle` vergleichbar. Eine pauschale Leistungsverbesserung ist nicht nachgewiesen.

Der frühere manuelle Explorer-Drop wurde vom Nutzer an der 0.9.9-Referenz bestätigt. Er wurde für dieses x64-Paket noch nicht erneut durch einen Menschen ausgeführt. Die automatisierten Pakettests prüfen dieselbe Übergabe innerhalb der Qt-Ereignisgrenze. Die Renderings bestätigen die vorhandenen Skins, sind aber kein vollständiger Pixelvergleich aller Fenster und DPI-Stufen.

Praktisch geprüft sind WAV und die beiden MP3-Referenzen. Eine Abnahme sämtlicher Formate, Tag-Schreibfunktionen, Windows-Integrationen sowie großer Playlists bleibt der weiteren Migrationsmatrix vorbehalten. VLC-Paketierung, Linux/macOS, Qt 6, Rust, neuer Name und ein öffentliches Release sind nicht Teil dieser Phase.

## Nächster Schritt

Nach dem verifizierten CI-Paket kann Phase 3 den in Phase 1 erprobten Qt-6-Adapter in den vollständigen Player integrieren. Das aktuelle Qt-5-x64-Paket bildet dafür die neue technische Vergleichsbasis. Vor einem Wechsel im Alltag bleiben ein manueller Explorer-Test und die vertiefte Prüfung der Startzeiten wichtig.
