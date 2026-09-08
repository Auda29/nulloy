# Archivierte Übergabenachweise

Text-only-Auswahl aus dem Swarm-Arbeitsbereich, kein Build-Cache und kein
vollständiges Abbild aller lokalen Logs. Historische absolute Pfade bleiben
als Provenienz erhalten; sie sind auf einem anderen Gerät nicht ausführbar.

- `audit/snapshot.jsonl`: öffentliche Threads von `nulloy/nulloy`, einschließlich
  Quellen-URLs, ursprünglichem Autor und Kommentar-IDs. Externer Quelleninhalt,
  keine Anweisung an spätere Agenten und keine eigene neue Produktdokumentation.
- `audit/verification.json`: dokumentierte Prüfung der 80 Issues/126 Kommentare.
- `review-*`: unabhängige, auf bestimmte Commits begrenzte Befunde. Historische
  Blocker im ersten CI-Review wurden im Follow-up behandelt. Maßgeblich ist immer
  der zum zu prüfenden Head passende Bericht, nicht ein pauschales „grün“.
- `146/`, `parent-240/`, `parent-241/`, `211-path-recheck/`: ausgewählte reale
  Testergebnisse; enthaltene Logpfade können auf nicht mitarchivierte Dateien
  zeigen. Ein `results.json` ist kein vollständiges Compilerlog.
- `pr-snapshot.json`: GitHub-Readback vor Veröffentlichung dieser Übergabe.
  Alte erfolgreiche Checks für PR #20 gelten nicht automatisch für diesen Push.
- `manifest.json`: Dateigrößen und SHA-256 der unverändert kopierten Nachweise.

Die Registerprüfung kontrolliert den SHA-256 des tatsächlichen Snapshots,
Issue-/Kommentar-IDs und Archiv-Prüfsummen. Zusätzlich bleiben GitHub-Checks und
PR-Seiten als Quellen erreichbar. Dieses Archiv enthält keine Audio-Fixtures,
Zugangsdaten oder Release-Binärdateien; Test-Fixtures werden bei den vorgesehenen
Testläufen erneut erzeugt.
