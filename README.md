# Alarm Clock

HACS integration for Home Assistant: virtual, voice-controlled alarm clocks.

After installation, set up the integration once under *Settings → Devices & services → Add integration → Alarm Clock*. Then add as many **virtual alarm clock devices** as you like from the integration's page ("+ Add device"). Each device is a complete, independent alarm clock with:

- recurring alarms - any number per weekday, each added or removed independently by voice or service call (e.g. two different times on the same day both ring)
- one-time alarms - any number, each its own date + time, independent of the recurring alarms
- configurable input device (Assist satellite, e.g. HA Voice PE)
- output device + alarm sound in **one** step via "browse media" (the device you pick the sound on doubles as the output device - no separate device selection) plus separately adjustable volume
- optional light (any `light` entity) with configured color/brightness while ringing - always turns off when stopped (no state restore)
- snooze via voice, button entity, or Voice PE button ([blueprint](blueprints/automation/alarm_clock/voice_pe_snooze_button.yaml))
- stop via voice or button entity

## Status

**Phase 1** ✅ done and verified live against a real Home Assistant instance (HACS install, config flow, subentry device, scheduling calculation, real ring/snooze/stop cycle including light restore, no errors in the log).

**Phase 2** ✅ Voice control: snooze/stop, plus setting weekday and one-time alarms by voice (see below).

**Phase 3** ✅ Blueprint for button snooze (see below) - e.g. for the center button of a Home Assistant Voice PE.

**Phase 4** ✅ HACS polish (this installation guide) and CI ([`validate.yml`](.github/workflows/validate.yml) checks `hassfest` + HACS requirements on every push/PR).

**Phase 5** ✅ Schedule moved to a SQLite-backed store (`custom_components/alarm_clock/store.py`) instead of one entity per weekday/one-time slot. This removed the old "one alarm per weekday, one pending one-time alarm" limit - setting a schedule now *adds* an alarm rather than overwriting a fixed slot - and cut each device down to **8 entities** (`Ringing`, `Snoozed`, `Next alarm`, the `Snooze`/`Stop`/`Test ring` buttons, `Snooze duration`, `Volume`). There's no per-alarm entity any more; the full schedule is only ever set via voice/services and is visible as the `alarms` attribute of `sensor.<device>_next_trigger`. Upgrading from an older version migrates each device's existing schedule into SQLite automatically on first start and removes the now-unused weekday/switch/time/datetime entities. Naming a date now disambiguates deleting a one-time alarm when several are set ("wecker am 20. august löschen"); naming a specific *time* to delete on a weekday that has more than one alarm isn't supported by voice yet - `delete_recurring` still removes every alarm on that weekday at once.

## Voice control

The following sentences work out of the box (German and English, see [`custom_components/alarm_clock/sentences/`](custom_components/alarm_clock/sentences/)):

- Snooze: "schlummern", "wecker schlummern" / "snooze", "snooze the alarm"
- Stop: "wecker beenden", "wecker aus", "wecker stoppen" / "stop the alarm", "turn off the alarm"
- Set weekday(s) (arms the day(s) automatically): "wecker montags auf sieben uhr stellen", "stelle den wecker für montag auf sieben uhr dreißig", "wecker jeden tag auf sieben uhr stellen", "wecker jeden montag bis mittwoch auf sieben uhr stellen" / "set the alarm for monday to 7", "set alarm for monday to 7 30", "set the alarm for every monday through wednesday to 7" - saying this again for a weekday that already has an alarm at a *different* time **adds** a second alarm for that day rather than replacing the first (repeating the exact same time is a no-op, not a duplicate)
- Set one-time alarm: "wecker sieben uhr stellen" (no date → next possible time: today if the time hasn't passed yet, otherwise tomorrow), "wecker heute um zweiundzwanzig uhr stellen", "stelle den wecker morgen auf sieben uhr", "wecker montag um sieben uhr stellen" (next Monday), "wecker am 15. august um sieben uhr stellen" (next occurrence of that date, otherwise next year) / "set the alarm at 7" (no date → next possible time), "set the alarm for tomorrow at 7", "set a one time alarm for today at 22", "set the alarm for monday at 7", "set the alarm for the 15th of august at 7" - any number of one-time alarms can be armed at once, each on its own date
- Delete weekday(s) (removes every alarm set for that weekday, at any time): "wecker montag löschen", "wecker jeden montag bis mittwoch löschen", "lösche den wecker für montag" / "delete the alarm for monday", "delete the alarm for every monday through wednesday"
- Delete one-time alarm: "wecker löschen", "lösche den wecker" / "delete the alarm", "delete alarm" - deletes it if exactly one is currently set; if none are set, or more than one is set, you get a spoken message instead of a guess. Name a date to target a specific one when several are set: "wecker am 20. august löschen", "lösche den wecker für den 20. august" / "delete the alarm for the 20th of august", "delete the one time alarm for the 20th of august"
- Terse German forms also work, dropping "auf/um ... stellen" entirely: "wecker 8 uhr" (one-time), "wecker freitag 8 uhr" (one-time, next Friday), "wecker freitags 8 uhr" (recurring, every Friday) - the trailing "-s" on the weekday is what tells one-time and recurring apart here, since neither a preposition nor "stellen" is present to disambiguate otherwise.

The full current schedule for a device - every recurring and one-time alarm, armed or not - is always readable as the `alarms` attribute of its `sensor.<device>_next_trigger` entity (Developer Tools → States, or a dashboard template); there's no per-alarm entity to look at instead.

The integration copies these sentences into `config/custom_sentences/<language>/alarm_clock.yaml` on every setup (HA only loads sentence files from that directory - a custom integration can't ship them so they're picked up automatically), but only ever overwrites a file whose content still matches exactly what it last wrote there itself. Your own edits, or deleting the file (to disable voice control), are therefore preserved permanently - even across integration updates - while genuine changes to the bundled sentences still land, as long as the file hasn't been touched since the last install.

Which device responds is determined by the voice command's `satellite_id`: first, it looks for an alarm clock whose configured input device (Assist satellite) is exactly the one that received the command. For snooze/stop, it otherwise falls back to the single alarm clock currently ringing/snoozed; for the weekday/one-time/delete commands there's no "currently ringing" anchor, so it falls back to the single configured alarm clock instead. If it's still ambiguous in either case, or there's no matching alarm clock, a spoken error message is given instead of a guess.

## Installation

Not yet listed in the official HACS store - add it as a HACS "custom repository":

1. In HACS → *Integrations* → top-right *⋮* → *Custom repositories* → enter this GitHub URL with category "Integration" (alternatively, copy `custom_components/alarm_clock/` manually to `config/custom_components/`).
2. Install "Alarm Clock" via HACS.
3. Restart Home Assistant.
4. *Settings → Devices & services → Add integration → "Alarm Clock"* - sets up the integration once (no configuration dialog).
5. On the new integration page, use "+ Add device" to create and configure a virtual alarm clock device as a subentry (name, output device + sound, optionally light and input device, snooze duration, volume). Repeat as often as you like for more alarm clocks.
6. Arm the actual schedule (which weekday(s), which time(s), which one-time date(s)) via voice or the `alarm_clock.set_recurring`/`set_onetime` services - see [Voice control](#voice-control). There's no schedule field in the device form itself.

On first start, the integration also automatically copies the voice commands to `config/custom_sentences/` (see [Voice control](#voice-control)) - no further step needed. For snooze via a hardware button (e.g. Home Assistant Voice PE), import the [button snooze blueprint](#button-snooze-blueprint-phase-3) separately.

## Manual verification (Phase 1)

- After creating a device, its 8 entities (`Snooze duration`, `Volume`, `Ringing`, `Snoozed`, `Next alarm`, buttons `Snooze`/`Stop`/`Test ring`) appear on the device page - the three buttons are under "Controls", `Snooze duration`/`Volume` under "Configuration". There's no schedule entity to configure here - arm the schedule via voice/services (see Phase 2 below).
- Call `alarm_clock.set_recurring` for two different weekdays at different times → `sensor.<device>_next_trigger` shows the nearest occurrence, and its `alarms` attribute lists both.
- Press `button.<device>_test_ring` → the configured media player plays, the configured light turns on, `binary_sensor.<device>_ringing` = on.
- `button.<device>_snooze` (or service `alarm_clock.snooze`) → playback stops, `binary_sensor.<device>_snoozed` = on, it rings again after the snooze duration.
- `button.<device>_stop` (or service `alarm_clock.stop`) → everything back to idle, the configured light turns off.
- Restart HA → the schedule, snooze duration, and volume are all preserved.

## Manual verification (Phase 2)

- After the first setup, `config/custom_sentences/de/alarm_clock.yaml` and `.../en/alarm_clock.yaml` exist, with an info log about it ("voice commands installed to ...").
- Trigger test ring, then say "schlummern" on the configured Assist satellite → playback stops, `binary_sensor.<device>_snoozed` = on, the satellite speaks a confirmation.
- Let it ring again, say "wecker beenden" → idle, light off, confirmation.
- Exactly one alarm clock is ringing, command issued via *Developer tools → Actions → `conversation.process`* without an associated satellite → the same alarm clock still responds (fallback).
- No alarm clock is ringing, say "schlummern" → spoken error message, no error in the log.
- Two alarm clocks ring simultaneously, command issued via an unassociated satellite → spoken ambiguity error message.
- "wecker montags auf sieben uhr stellen" → `sensor.<device>_next_trigger`'s `alarms` attribute gains a `{"kind": "recurring", "weekday": "mon", "time": "07:00", "enabled": true}` row, the spoken confirmation names device/day/time.
- "wecker montags auf sieben uhr dreißig stellen" said next (a *different* Monday time) → a **second** Monday row (`"time": "07:30"`) is added alongside the first - both now fire, `next_trigger` picks whichever comes first.
- Saying the exact same "wecker montags auf sieben uhr stellen" again → no new row (idempotent), not a duplicate.
- "wecker jeden tag auf sieben uhr stellen" → one row per weekday, all `07:00`.
- "wecker heute um `<time after now>` uhr stellen" → a new `{"kind": "onetime", "date": "<today>", "time": "..."}` row appears.
- "wecker heute um `<time that has already just passed>` uhr stellen" → jumps to tomorrow's date instead, the confirmation says "morgen" instead of "heute".
- "wecker morgen um sieben uhr stellen" → tomorrow's date, 07:00.
- "wecker jeden montag bis mittwoch auf sieben uhr stellen" → one row each for Monday/Tuesday/Wednesday, all 07:00, the confirmation names "Montag bis Mittwoch".
- "wecker `<time after now>` uhr stellen" (without "um", without a day) → a one-time row dated today.
- "wecker `<time that has already just passed>` uhr stellen" (without a day) → jumps to tomorrow, the confirmation says "morgen".
- "wecker montag um sieben uhr stellen" → a one-time row dated next Monday, not a recurring Monday row.
- "wecker am 15. august um sieben uhr stellen" → a one-time row dated August 15th (this year or next, depending on whether the date has already passed).
- "wecker am 30. februar um sieben uhr stellen" (invalid date) → spoken error message, no error in the log.
- Two one-time alarms already set (e.g. two different dates), then "wecker löschen" (without a day) → spoken ambiguity error, neither is deleted.
- Exactly one one-time alarm set, "wecker löschen" → that row is deleted, confirmation speech.
- No one-time alarm set, "wecker löschen" → spoken "kein einmaliger Wecker gestellt" message, no error in the log.
- Two one-time alarms set on different dates, "wecker am `<one of the two dates>` löschen" → only the matching row is deleted, the other one-time alarm is untouched.
- "wecker am `<date with no one-time alarm>` löschen" → spoken "kein einmaliger Wecker an diesem Datum" message, no error in the log.
- `alarm_clock.delete_onetime` called with a `date` field (e.g. by an LLM conversation fallback that can't match the sentence grammar) behaves the same as the voice form above - this was the actual fix for a real bug: without a `date` field, a fallback assistant calling `delete_onetime` while 2+ one-time alarms were set got a `ServiceValidationError` and nothing happened, which looked like "the display doesn't update" from the outside.
- "wecker montag löschen" → **every** row currently armed for Monday is removed at once (not just disabled) - the confirmation names device/day.
- "wecker jeden montag bis mittwoch löschen" → every Monday/Tuesday/Wednesday row removed.
- "wecker 8 uhr" (real spoken voice input, no "um"/"stellen") → sets a one-time alarm, not misrecognized as a generic entity-control command.
- "wecker freitag 8 uhr" vs "wecker freitags 8 uhr" (real spoken voice input) → the first adds a one-time row for next Friday, the second adds a recurring Friday row - the "-s" is what tells them apart.
- Reinstall the integration (e.g. update) → `config/custom_sentences/de/alarm_clock.yaml` is automatically updated (new info log), as long as the file hasn't changed since the last install.
- Manually edit or delete the file `config/custom_sentences/de/alarm_clock.yaml`, then restart HA → the file stays untouched or deleted, respectively - it's not recreated.
- Upgrading from a version before the SQLite schedule (Phase 5): any weekday/one-time schedule already armed migrates into the new `alarms` attribute automatically on first start, and the old weekday/switch/time/datetime entities disappear from the device page entirely (not left behind as "unavailable").

## Button snooze blueprint (Phase 3)

Triggers `alarm_clock.snooze` on the selected alarm clock device whenever a button `event` entity (e.g. `event.<device>_button_press` of a Home Assistant Voice PE) reports one of the configured event types.

Requires **Home Assistant 2026.1 or newer** (introduced the `event.received` trigger this uses).

1. *Settings → Automations & scenes → Blueprints → Import blueprint* and provide the raw file URL of [`blueprints/automation/alarm_clock/voice_pe_snooze_button.yaml`](blueprints/automation/alarm_clock/voice_pe_snooze_button.yaml) (or copy the file manually to `config/blueprints/automation/alarm_clock/`). Note: when importing by URL, Home Assistant names the local folder after the GitHub username (`mikedoerer`), not after the repository or integration - that's how HA's blueprint importer always works and isn't something this repo's layout can influence; rename the local folder afterward if you'd rather it read differently.
2. Create an automation from the blueprint, select the button event entity and alarm clock device. The preset event types (`double_press`, `triple_press`, `long_press`, `easter_egg_press`) match the Voice PE - adjust as needed for other buttons.

Deliberately snooze-only, no stop blueprint - use voice control or the `Stop` button entity to stop.

### Manual verification (Phase 3)

- Trigger test ring, then e.g. double-press the Voice PE button (`double_press`) → playback stops, `binary_sensor.<device>_snoozed` = on.
- Let it ring again, trigger the same press type twice in a row right away (e.g. two `long_press` in a row) → the automation fires both times (no "getting stuck" like with a naive `state` trigger with an attribute filter).
- Trigger a press type that's not among the configured event types → no reaction.
