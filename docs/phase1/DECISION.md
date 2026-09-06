# Qt-6-Skins: Architekturentscheidung

Stand: 6. September 2026. Geltungsbereich: Phase-1-Prototyp unter Windows x64.

Wir behalten Qt Widgets, die vorhandenen UI-Formulare und Skin-Skripte. Der Versuch mit Qt 6.11.2 ist erfolgreich. Ein Austausch der Oberfläche oder ein Rust-Rewrite ist dafür nicht erforderlich.

## Gewählter Unterbau

| Bereich | Entscheidung und Nachweis |
| --- | --- |
| Werkzeugkette | MSYS2 MINGW64, GCC 16.2.0, Qt 6.11.2, CMake 4.4.2, Ninja 1.13.2. Diese Kombination baut und testet die tatsächlichen Widgets auf Windows 11. |
| JavaScript | QJSEngine mit einem Adapter pro QObject. Bestehende Skin-Skripte bleiben unverändert. |
| Widget-Erzeugung | QUiLoader-Unterklasse erzeugt NLabel, NCoverWidget, NPlaylistWidget, NVolumeSlider, NWaveformSlider und QSizeGrip. Das vorhandene NMainWindow erhält optional diesen Loader. |
| Enums | Öffentliche Metaobjekte auslesen. Für den Namespace N verwendet der Qt-6-Zweig Q_NAMESPACE und Q_ENUM_NS. Der bisherige Qt-5-Zweig bleibt bestehen. |
| Ressourcen | Ein temporärer Ordner und ein eindeutiger QDir-Suchpräfix je Skin ersetzen im Prototyp den privaten QAbstractFileEngine. Erzeugte Bilder landen in einem getrennten Overlay. |
| NZS | ZIP-Zentralverzeichnis lesen, Stored/Deflate unterstützen, QtIOCompressor 2.3.1 zur Dekompression beibehalten. Größen, Prüfsummen und Zielpfade prüfen. |
| Nächste Build-Etappe | Den vollständigen Player und seine Plugins mit derselben MINGW64-Toolchain bauen. Keine alten Qt-5- oder 32-bit-DLLs beimischen. |

Die vollständige installierte Paketliste sowie zehn Paketdateien mit Bezugs-URLs und SHA-256 stehen in [toolchain.json](toolchain.json). Das ist eine dokumentierte lokale Werkzeugkette. Eine saubere CI-Installation mit dauerhaft verfügbaren Paketartefakten gehört zu Phase 2. MSVC wurde nicht getestet. Die erfolgreiche Ausführung auf Windows 11 ist keine Zusage für ältere Windows-Versionen.

## Nachgewiesene Unterschiede zu QtScript

QJSEngine übernimmt die bisherigen Default-Prototypen nicht. Der Adapter ergänzt deshalb Fensterflags, Attribute, Schriftgröße, Position, Eltern, Layouts, Margins, Splitter-Größen und Doppelklick-Signale. Der tatsächliche QWidget bleibt Eigentum von C++; die JavaScript-Garbage-Collection darf ihn nicht löschen.

Signaturen wie `newTitle(const QString &)` werden über QMetaObject normalisiert. `connect(this, "method")` wird in eine Verbindung zum tatsächlichen JavaScript-Funktionsobjekt übersetzt. QAbstractButton benötigt einen gesonderten bool-Signalweg, weil die Auflösung des Signals mit Default-Argument sonst `clicked()` auswählt und Metro keinen bool-Wert erhält. Ein fehlender Splitter-Wert wird wie beim bisherigen Sequenzadapter als leere Liste übergeben.

Bildmaskierung erhält auch das ungewöhnliche Alpha-Verhalten des Originals. Nach einer Änderung wird der öffentliche QPixmapCache geleert, damit erneutes Zuweisen des Stylesheets die neuen Bilder verwendet. Der Test prüft sowohl Bilddaten als auch das tatsächlich gesetzte Button-Icon beim Metro-Theme-Wechsel. Für den einzelnen Skin eines Desktop-Players ist dies zunächst ausreichend; eine spätere Optimierung muss dieselbe sichtbare Aktualisierung erhalten.

## Verbleibende Abhängigkeiten

| Abhängigkeit | Befund | Konkreter Migrationsweg |
| --- | --- | --- |
| QtSingleApplication | Unveränderter Compile-Probe scheitert in `qtlocalpeer.cpp:81` an QRegExp. Die Dateien für QtLockedFile werden dort eingebunden und dürfen nicht zusätzlich separat kompiliert werden. | QRegularExpression einsetzen, weiterhin QLocalServer/QLocalSocket und die vorhandene Sperre verwenden. Danach Zwei-Prozess-Tests für Dateiübergabe, Unicode, gleichzeitigen Start und verwaiste Sperren. Eigene Fork-Instanzkennung vor Alltagseinsatz. |
| Qxt unter Windows | `QxtGlobalShortcutPrivate` bleibt wegen `nativeEventFilter(..., long*)` abstrakt. QKeyCombination-Konvertierungen erzeugen zusätzliche Warnungen. | Ergebnisparameter auf Qt 6 mit `qintptr*` umstellen; `shortcut[0].key()` und `.keyboardModifiers()` verwenden. RegisterHotKey/UnregisterHotKey erhalten. Registrierung, Konflikte, Auslösung und Freigabe unter Windows prüfen. |
| Qxt unter Linux/macOS | X11-Zweig verwendet QX11Info und das private QPlatformNativeInterface; kein Laufzeitnachweis auf diesen Plattformen. | X11-Zugriff auf die öffentliche native Qt-Schnittstelle umstellen. Wayland-Hotkeys gesondert über den Desktop/Portal-Weg behandeln. macOS-Code mit einer eigenen Toolchain prüfen. Keine Aussage, dass der Windows-Test diese Plattformen abdeckt. |
| QtIOCompressor | Unverändert mit Qt 6 kompiliert; Dekompression aller vier neu gepackten Skins und der drei kopierten 0.9.9-Pakete erfolgreich. | Für Phase 2 beibehalten. ZIP64, verschlüsselte, mehrteilige und andere Kompressionsverfahren werden vom Prototyp ausdrücklich abgelehnt. |
| Windows-Taskleiste | QtWinExtras fehlt in Qt 6; native Ereignisse benötigen die richtige Zeigerbreite. | Im verwendeten Code bereits `QImage::toHICON()` und `qintptr*` eingesetzt. Vollständige COM-/Overlay-/Fortschrittsprüfung folgt mit dem echten Player. |
| Windows-Icons | `winIcon.cpp` verwendet weiterhin QtWin::fromHICON. Es gehört nicht zum Skin-Laufzeitpfad. | Auf `QPixmap::fromImage(QImage::fromHICON(...))` umstellen; HICON weiterhin mit DestroyIcon freigeben. |
| Hauptfenster | QDesktopWidget und alte WheelEvent-Methoden fehlen. Der frühere zusätzliche setGeometry-Aufruf beim Maximieren erzeugt mit Qt 6 eine falsche native Client-Geometrie. showNormal kann außerdem die gespeicherte Größe bereits im synchronen changeEvent löschen. | Qt-6-Zweig verwendet QScreen und angleDelta. Beim Maximieren verwaltet Qt 6 die Geometrie; die Wiederherstellungswerte werden vor showNormal gesichert. Der alte Qt-5-Zweig bleibt bestehen. Alle Skins kehren nach Vollbild und Maximierung zur Ausgangsgröße zurück, ohne Geometriewarnung. |

## Grenzen der Entscheidung

Der Prototyp ersetzt Playback, Tag-Lesen und Waveform-Berechnung durch ausdrücklich benannte Testdienste. Er verwendet die echten Widgets, aber erzeugt keinen Ton. Die Menüprüfung bestätigt den Signalaufruf und die Koordinaten; das vollständige Player-Menü ist hier nicht aufgebaut. Ein tatsächliches MP3-Decoding, Cache-Ladezeiten, vollständige Player-Startzeiten und Beenden während Hintergrundarbeit bleiben Aufgaben des vollständigen Players.

Die Skin-Dateien einschließlich der kopierten Slim-0.9-Referenz sind unverändert. Die gerenderten Windows-Bilder wurden geprüft. Qt 6 aktiviert auf diesem Rechner eine andere automatische HiDPI-Skalierung als die Qt-5-Referenz. Eine pixelidentische Darstellung und die Umrechnung gespeicherter Fenstergrößen sind damit noch nicht abgenommen; diese Prüfung bleibt ausdrücklich im Phase-3-Vergleich. Die ursprünglichen Bildschirmfotos und Nutzerprofile wurden nicht geändert. Der Offscreen-Plugin eignet sich hier für Funktionsprüfungen, seine Font-Darstellung jedoch nicht als visuelle Windows-Referenz.

Silver enthält im bisherigen Skript bei `PlaylistVisible == 'false'` Zugriffe auf `this.maximumHeight` und `minimumHeigh`. Diese vorhandene Sonderfall-Logik wurde nicht still korrigiert und gehört vor einer vollständigen Player-Abnahme in die Vergleichsmatrix. Für tatsächlich verwendete externe Skins lag außer den mitgelieferten Paketen kein weiterer Skin vor; der aktive Skin ist Slim 0.9.

## Primärquellen

- [QJSEngine](https://doc.qt.io/qt-6/qjsengine.html): QObject-Integration, Besitz und JavaScript-Ausführung.
- [QDir-Suchpfade](https://doc.qt.io/qt-6/qdir.html#addSearchPath): öffentlicher Ersatz für die Ressourcenauflösung.
- [QImage](https://doc.qt.io/qt-6/qimage.html): öffentliche HICON-Konvertierung.

Die Entscheidung beruht auf den lokalen Builds und Tests. Die Dokumentation erklärt die verwendeten APIs, ersetzt aber keinen Laufzeitnachweis.
