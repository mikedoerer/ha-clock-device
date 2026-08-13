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

**Phase 2** ✅ Sprachsteuerung: Schlummern/Beenden sowie Wochentags- und einmaligen Wecker per Sprache stellen (siehe unten).

**Phase 3** ✅ Blueprint für Button-Snooze (siehe unten) - z.B. für die Center-Taste einer Home Assistant Voice PE.

**Phase 4** ✅ HACS-Feinschliff (diese Installationsanleitung) und CI ([`validate.yml`](.github/workflows/validate.yml) prüft `hassfest` + HACS-Anforderungen bei jedem Push/PR).

## Sprachsteuerung

Standardmäßig funktionieren folgende Sätze (Deutsch und Englisch, siehe [`custom_components/wecker/sentences/`](custom_components/wecker/sentences/)):

- Schlummern: "schlummern", "wecker schlummern" / "snooze", "snooze the alarm"
- Beenden: "wecker beenden", "wecker aus", "wecker stoppen" / "stop the alarm", "turn off the alarm"
- Wochentag stellen (aktiviert den Tag automatisch mit): "wecker montags auf sieben uhr stellen", "stelle den wecker für montag auf sieben uhr dreißig", "wecker jeden tag auf sieben uhr stellen" / "set the alarm for monday to 7", "set alarm for monday to 7 30"
- Einmaligen Wecker stellen: "wecker heute um zweiundzwanzig uhr stellen", "stelle den wecker morgen auf sieben uhr" / "set the alarm for tomorrow at 7", "set a one time alarm for today at 22"

Die Integration kopiert diese Sätze bei jedem Setup nach `config/custom_sentences/<sprache>/wecker.yaml` (HA lädt Satzdateien nur aus diesem Verzeichnis - eigene Integrationen können sie nicht automatisch mitliefern), überschreibt dabei aber nur eine Datei, deren Inhalt noch exakt dem entspricht, was sie selbst zuletzt dorthin geschrieben hat. Eigene Anpassungen oder ein Löschen der Datei (um die Sprachsteuerung abzuschalten) bleiben damit dauerhaft erhalten - auch über Integrations-Updates hinweg -, während echte Änderungen an den mitgelieferten Sätzen (wie die Wochentags-/Einmal-Befehle in dieser Version) trotzdem ankommen, solange die Datei seit der letzten Installation unangetastet war.

Welches Gerät reagiert, wird über die `satellite_id` des Sprachbefehls bestimmt: Zuerst wird nach einem Wecker gesucht, dessen konfiguriertes Eingabegerät (Assist-Satellit) genau das ist, das den Befehl empfangen hat. Für Schlummern/Beenden wird sonst der einzige gerade klingelnde/schlummernde Wecker genommen; für die Wochentags-/Einmal-Befehle gibt es kein "klingelt gerade" als Anker, deshalb stattdessen der einzige überhaupt konfigurierte Wecker. Bleibt es in beiden Fällen mehrdeutig oder gibt es keinen passenden Wecker, kommt eine gesprochene Fehlermeldung statt einer Vermutung.

## Installation

Noch nicht im offiziellen HACS-Store gelistet - als HACS-"Custom Repository" hinzufügen:

1. In HACS → *Integrationen* → oben rechts *⋮* → *Benutzerdefinierte Repositories* → diese GitHub-URL mit Kategorie "Integration" eintragen (alternativ `custom_components/wecker/` manuell nach `config/custom_components/` kopieren).
2. "Wecker" über HACS installieren.
3. Home Assistant neu starten.
4. *Einstellungen → Geräte & Dienste → Integration hinzufügen → "Wecker"* - legt die Integration einmalig an (ohne Konfigurationsdialog).
5. Auf der neuen Integrationsseite über "+ Gerät hinzufügen" ein virtuelles Wecker-Gerät als Subentry anlegen und konfigurieren (Wochentage/Uhrzeiten, Ausgabegerät + Sound, optional Licht und Eingabegerät). Beliebig oft wiederholen für weitere Wecker.

Beim ersten Start kopiert die Integration außerdem automatisch die Sprachbefehle nach `config/custom_sentences/` (siehe [Sprachsteuerung](#sprachsteuerung)) - dafür ist kein weiterer Schritt nötig. Für Schlummern per Hardware-Taste (z.B. Home Assistant Voice PE) den [Button-Snooze-Blueprint](#button-snooze-blueprint-phase-3) separat importieren.

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
- "wecker montags auf sieben uhr stellen" → Montag-Switch geht an, Montag-Uhrzeit zeigt 07:00, gesprochene Bestätigung nennt Gerät/Tag/Uhrzeit.
- "wecker montags auf sieben uhr dreißig stellen" → 07:30 statt 07:00.
- "wecker jeden tag auf sieben uhr stellen" → alle sieben Wochentag-Switches an, alle Zeiten 07:00.
- "wecker heute um `<Uhrzeit nach jetzt>` uhr stellen" → "Einmaliger Wecker"-Datetime zeigt heutiges Datum, "Einmaliger Wecker aktiv"-Switch an.
- "wecker heute um `<Uhrzeit, die gerade eben schon vorbei ist>` uhr stellen" → springt auf morgen, Bestätigung sagt "morgen" statt "heute".
- "wecker morgen um sieben uhr stellen" → morgiges Datum, 07:00.
- Integration erneut installieren (z.B. Update) → `config/custom_sentences/de/wecker.yaml` wird automatisch aktualisiert (neues Info-Log), solange die Datei seit der letzten Installation unverändert war.
- Datei `config/custom_sentences/de/wecker.yaml` manuell bearbeiten oder löschen, dann HA neu starten → Datei bleibt unangetastet bzw. gelöscht, wird nicht wiederhergestellt.

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
