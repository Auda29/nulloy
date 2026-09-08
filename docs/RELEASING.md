# Alpha-Releases

Ein Push eines Tags wie `v0.10.0-alpha.1` startet `Alpha release`.
Der Tag muss zur `NULLOY_VERSION` des Presets `windows-portable-x64` passen.
Erst die Versionskennung und Änderungen committen, dann einen annotierten Tag auf
diesem Quellstand anlegen und pushen. Bestehende Release-Tags nicht verschieben.

Der Workflow ruft die reguläre Windows-CI für Qt 5 und Qt 6 auf. Nur nach erfolgreichen
Builds, Tests und Paketprüfungen veröffentlicht er das portable Qt-6-Paket als
GitHub-Prerelease. Vor der Veröffentlichung prüft er nochmals Quell-Commit, Version,
Dateihashes und die Zuordnung aller sechs Paketprüfberichte zum ZIP.

Die Release-Dateien umfassen das Windows-ZIP, dessen SHA-256, einen Quellcode-Snapshot,
die Qt-6-Testnachweise, `release-validation.json` und `SHA256SUMS.txt`.
Die Veröffentlichung erfolgt zunächst als Draft mit allen Dateien und anschließend
als Prerelease. Ein Alpha-Release wird nicht als neuestes stabiles Release markiert.

Nach dem Lauf den veröffentlichten Status, das Tag-Ziel und frisch heruntergeladene
Dateien gegen `SHA256SUMS.txt` prüfen. Bei Fehlern bleibt der Lauf fehlgeschlagen oder
das Release unveröffentlicht. Einen vorhandenen Draft vor einem neuen Publish-Versuch
prüfen; veröffentlichte Dateien nicht stillschweigend ersetzen.

Die manuelle Phase-4-Abnahme gilt für das damalige lokale Paket. Jeder Release-Build
hat eigene Herkunftsangaben und Hashes. Die bekannte ausstehende Prüfung auf einem
separaten Windows-Rechner wird in den Alpha-Release-Notizen genannt.
