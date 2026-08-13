# Wecker

HACS-Integration für Home Assistant: virtuelle, sprachgesteuerte Wecker.

Nach der Installation legst du unter *Einstellungen → Geräte & Dienste → Integration hinzufügen → Wecker* einmal die Integration an. Danach fügst du auf der Integrationsseite beliebig viele **virtuelle Wecker-Geräte** hinzu ("+ Gerät hinzufügen"). Jedes Gerät ist ein vollständiger, unabhängiger Wecker mit:

- wiederkehrendem Alarm - jeder Wochentag einzeln schaltbar, mit **eigener** Uhrzeit je Wochentag
- einmaligem Alarm (Datum + Uhrzeit), unabhängig vom wiederkehrenden Alarm
- konfigurierbarem Eingabegerät (Assist-Satellit, z.B. HA Voice PE)
- Ausgabegerät + Wecker-Sound in **einem** Schritt per "Medien durchsuchen"-Auswahl (das Gerät, auf dem du den Sound aussuchst, ist zugleich das Ausgabegerät - keine doppelte Geräteauswahl) plus separat einstellbarer Lautstärke
- optionalem Licht (beliebige `light`-Entität) mit konfigurierter Farbe/Helligkeit beim Klingeln - geht beim Beenden immer aus (kein Zustands-Restore)
- Schlummern per Sprache (Phase 2), Button-Entity oder Voice-PE-Taste (Blueprint folgt in Phase 3)
- Beenden per Sprache (Phase 2) oder Button-Entity

## Status

**Phase 1** ✅ fertig und live gegen eine echte Home-Assistant-Instanz verifiziert (HACS-Install, Config-Flow, Subentry-Gerät mit allen 21 Entities, Scheduling-Berechnung, echter Klingel-/Snooze-/Stop-Durchlauf inkl. Licht-Restore, keine Fehler im Log). Noch ohne Sprachsteuerung und ohne Button-Blueprint.

Geplant: Phase 2 (Sprachsteuerung), Phase 3 (Blueprint für Button-Snooze), Phase 4 (HACS-Feinschliff/CI).

## Installation (Entwicklungsstand)

Noch nicht über den HACS-Store gelistet. Lokal testen:

1. `custom_components/wecker/` in dein HA-`config/custom_components/`-Verzeichnis kopieren (oder als HACS-"Custom Repository" mit dieser GitHub-URL hinzufügen).
2. Home Assistant neu starten.
3. *Einstellungen → Geräte & Dienste → Integration hinzufügen → "Wecker"*.
4. Auf der Integrationsseite ein virtuelles Wecker-Gerät hinzufügen und konfigurieren.

## Manuelle Verifikation (Phase 1)

- Nach dem Anlegen eines Geräts erscheinen alle Entities (Wochentag-Switches/-Uhrzeiten, einmaliger Wecker, Snooze-Dauer, Lautstärke, `Klingelt`/`Schlummert`, `Nächster Alarm`, Buttons `Schlummern`/`Wecker beenden`/`Testklingeln`) auf der Geräteseite - `Testklingeln` liegt unter "Konfiguration", `Schlummern`/`Wecker beenden` unter den normalen Steuerelementen.
- Für mehrere Wochentage unterschiedliche Uhrzeiten setzen und aktivieren → `sensor.<gerät>_nachster_alarm` zeigt den korrekten, nächsten individuellen Termin.
- `button.<gerät>_testklingeln` drücken → konfigurierter Media Player spielt, konfiguriertes Licht geht an, `binary_sensor.<gerät>_klingelt` = an.
- `button.<gerät>_schlummern` (oder Service `wecker.snooze`) → Wiedergabe stoppt, `binary_sensor.<gerät>_schlummert` = an, nach der Schlummerdauer klingelt es erneut.
- `button.<gerät>_wecker_beenden` (oder Service `wecker.stop`) → alles zurück auf Ruhezustand, konfiguriertes Licht geht aus.
- HA neu starten → alle Einstellungen (Uhrzeiten, Wochentage, scharf/unscharf) bleiben erhalten.
