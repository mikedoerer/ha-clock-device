# Wecker

HACS-Integration für Home Assistant: virtuelle, sprachgesteuerte Wecker.

Nach der Installation legst du unter *Einstellungen → Geräte & Dienste → Integration hinzufügen → Wecker* einmal die Integration an. Danach fügst du auf der Integrationsseite beliebig viele **virtuelle Wecker-Geräte** hinzu ("+ Gerät hinzufügen"). Jedes Gerät ist ein vollständiger, unabhängiger Wecker mit:

- wiederkehrendem Alarm - jeder Wochentag einzeln schaltbar, mit **eigener** Uhrzeit je Wochentag
- einmaligem Alarm (Datum + Uhrzeit), unabhängig vom wiederkehrenden Alarm
- konfigurierbarem Eingabegerät (Assist-Satellit, z.B. HA Voice PE)
- konfigurierbarem Ausgabegerät (Media Player) inkl. Sound-Quelle und Lautstärke
- optionalem Licht (beliebige `light`-Entität) mit konfigurierter Farbe/Helligkeit beim Klingeln
- Schlummern (Sprache oder Button - Blueprint folgt in Phase 3)
- Beenden **ausschließlich** per Sprache (Phase 2)

## Status

**Phase 1** (dieses Repo aktuell): Kern-Integration - Geräte, Entities, Zeitplan-Logik, `wecker.snooze`/`wecker.stop`-Services. Vollständig über die HA-Oberfläche und Entwicklerwerkzeuge nutz- und testbar, noch ohne Sprachsteuerung und ohne Button-Blueprint.

Geplant: Phase 2 (Sprachsteuerung), Phase 3 (Blueprint für Button-Snooze), Phase 4 (HACS-Feinschliff/CI).

## Installation (Entwicklungsstand)

Noch nicht über den HACS-Store gelistet. Lokal testen:

1. `custom_components/wecker/` in dein HA-`config/custom_components/`-Verzeichnis kopieren (oder als HACS-"Custom Repository" mit dieser GitHub-URL hinzufügen).
2. Home Assistant neu starten.
3. *Einstellungen → Geräte & Dienste → Integration hinzufügen → "Wecker"*.
4. Auf der Integrationsseite ein virtuelles Wecker-Gerät hinzufügen und konfigurieren.

## Manuelle Verifikation (Phase 1)

- Nach dem Anlegen eines Geräts erscheinen alle Entities (Wochentag-Switches/-Uhrzeiten, einmaliger Wecker, Snooze-Dauer, Lautstärke, `Klingelt`/`Schlummert`, `Nächster Alarm`, `Testklingeln`) auf der Geräteseite.
- Für mehrere Wochentage unterschiedliche Uhrzeiten setzen und aktivieren → `sensor.<gerät>_nachster_alarm` zeigt den korrekten, nächsten individuellen Termin.
- `button.<gerät>_testklingeln` drücken → konfigurierter Media Player spielt, konfiguriertes Licht geht an, `binary_sensor.<gerät>_klingelt` = an.
- Service `wecker.snooze` (Entwicklerwerkzeuge) auf das Gerät anwenden → Wiedergabe stoppt, `binary_sensor.<gerät>_schlummert` = an, nach der Schlummerdauer klingelt es erneut.
- Service `wecker.stop` anwenden → alles zurück auf Ruhezustand, Licht wird auf den Zustand vor dem Wecker zurückgesetzt.
- HA neu starten → alle Einstellungen (Uhrzeiten, Wochentage, scharf/unscharf) bleiben erhalten.
