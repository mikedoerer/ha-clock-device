# Wecker

HACS-Integration für Home Assistant: virtuelle, sprachgesteuerte Wecker.

Nach der Installation legst du unter *Einstellungen → Geräte & Dienste → Integration hinzufügen → Wecker* einmal die Integration an. Danach fügst du auf der Integrationsseite beliebig viele **virtuelle Wecker-Geräte** hinzu ("+ Gerät hinzufügen"). Jedes Gerät ist ein vollständiger, unabhängiger Wecker mit:

- wiederkehrendem Alarm - jeder Wochentag einzeln schaltbar, mit **eigener** Uhrzeit je Wochentag
- einmaligem Alarm (Datum + Uhrzeit), unabhängig vom wiederkehrenden Alarm
- konfigurierbarem Eingabegerät (Assist-Satellit, z.B. HA Voice PE)
- Ausgabegerät + Wecker-Sound in **einem** Schritt per "Medien durchsuchen"-Auswahl (das Gerät, auf dem du den Sound aussuchst, ist zugleich das Ausgabegerät - keine doppelte Geräteauswahl) plus separat einstellbarer Lautstärke
- optionalem Licht (beliebige `light`-Entität) mit konfigurierter Farbe/Helligkeit beim Klingeln - geht beim Beenden immer aus (kein Zustands-Restore)
- Schlummern per Sprache, Button-Entity oder Voice-PE-Taste ([Blueprint](blueprints/automation/wecker/voice_pe_snooze_button.yaml))
- Beenden per Sprache oder Button-Entity

## Status

**Phase 1** ✅ fertig und live gegen eine echte Home-Assistant-Instanz verifiziert (HACS-Install, Config-Flow, Subentry-Gerät mit allen 21 Entities, Scheduling-Berechnung, echter Klingel-/Snooze-/Stop-Durchlauf inkl. Licht-Restore, keine Fehler im Log).

**Phase 2** ✅ Sprachsteuerung: "schlummern" und "wecker beenden" (siehe unten) lösen `wecker.snooze`/`wecker.stop` am richtigen Gerät aus.

**Phase 3** ✅ Blueprint für Button-Snooze (siehe unten) - z.B. für die Center-Taste einer Home Assistant Voice PE.

Geplant: Phase 4 (HACS-Feinschliff/CI).

## Sprachsteuerung

Standardmäßig funktionieren folgende Sätze (Deutsch und Englisch, siehe [`custom_components/wecker/sentences/`](custom_components/wecker/sentences/)):

- Schlummern: "schlummern", "wecker schlummern" / "snooze", "snooze the alarm"
- Beenden: "wecker beenden", "wecker aus", "wecker stoppen" / "stop the alarm", "turn off the alarm"

Die Integration kopiert diese Sätze beim ersten Setup einmalig nach `config/custom_sentences/<sprache>/wecker.yaml` (HA lädt Satzdateien nur aus diesem Verzeichnis - eigene Integrationen können sie nicht automatisch mitliefern). Bereits vorhandene Dateien werden nicht überschrieben, eigene Anpassungen oder ein Löschen der Datei (um die Sprachsteuerung abzuschalten) bleiben also erhalten.

Welches Gerät reagiert, wird über die `satellite_id` des Sprachbefehls bestimmt: Zuerst wird nach einem Wecker gesucht, dessen konfiguriertes Eingabegerät (Assist-Satellit) genau das ist, das den Befehl empfangen hat. Passt kein Gerät (z.B. Text-Eingabe ohne Satellit), wird stattdessen der einzige gerade klingelnde/schlummernde Wecker genommen - klingeln mehrere oder keiner, kommt eine gesprochene Fehlermeldung statt einer Vermutung.

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

## Manuelle Verifikation (Phase 2)

- Nach dem ersten Setup existieren `config/custom_sentences/de/wecker.yaml` und `.../en/wecker.yaml`, im Log steht dazu ein Info-Log ("Sprachbefehle nach ... installiert").
- Testklingeln auslösen, dann am konfigurierten Assist-Satelliten "schlummern" sagen → Wiedergabe stoppt, `binary_sensor.<gerät>_schlummert` = an, Satellit spricht eine Bestätigung.
- Erneut klingeln lassen, "wecker beenden" sagen → Ruhezustand, Licht aus, Bestätigung.
- Genau ein Wecker klingelt, Befehl über *Entwicklerwerkzeuge → Aktionen → `conversation.process`* ohne zugeordneten Satelliten → derselbe Wecker reagiert trotzdem (Fallback).
- Kein Wecker klingelt, "schlummern" sagen → gesprochene Fehlermeldung, kein Fehler im Log.
- Zwei Wecker klingeln gleichzeitig, Befehl über einen nicht zugeordneten Satelliten → gesprochene Mehrdeutigkeits-Fehlermeldung.

## Button-Snooze-Blueprint (Phase 3)

Löst `wecker.snooze` am gewählten Wecker-Gerät aus, sobald eine Button-`event`-Entität (z.B. `event.<gerät>_button_press` einer Home Assistant Voice PE) einen der konfigurierten Event-Typen meldet.

Erfordert **Home Assistant 2026.1 oder neuer** (führte den dafür genutzten `event.received`-Trigger ein).

1. *Einstellungen → Automatisierungen & Szenen → Blueprints → Blueprint importieren* und die Rohdatei-URL von [`blueprints/automation/wecker/voice_pe_snooze_button.yaml`](blueprints/automation/wecker/voice_pe_snooze_button.yaml) angeben (oder die Datei manuell nach `config/blueprints/automation/wecker/` kopieren).
2. Aus dem Blueprint eine Automatisierung anlegen, Button-Event-Entität und Wecker-Gerät auswählen. Die vorbelegten Event-Typen (`double_press`, `triple_press`, `long_press`, `easter_egg_press`) passen zur Voice PE - bei anderen Buttons ggf. anpassen.

Bewusst nur Schlummern, kein Beenden-Blueprint - zum Beenden Sprachsteuerung oder die `Wecker beenden`-Button-Entity nutzen.

### Manuelle Verifikation (Phase 3)

- Testklingeln auslösen, dann am Voice-PE-Button z.B. zweimal drücken (`double_press`) → Wiedergabe stoppt, `binary_sensor.<gerät>_schlummert` = an.
- Erneut klingeln lassen, direkt zweimal hintereinander denselben Press-Typ auslösen (z.B. zwei `long_press` nacheinander) → beide Male löst die Automatisierung aus (kein "hängenbleiben" wie bei einem naiven `state`-Trigger mit Attribut-Filter).
- Press-Typ auslösen, der nicht in den konfigurierten Event-Typen enthalten ist → keine Reaktion.
