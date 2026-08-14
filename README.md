# Alarm Clock

HACS integration for Home Assistant: virtual, voice-controlled alarm clocks.

After installation, set up the integration once under *Settings → Devices & services → Add integration → Alarm Clock*. Then add as many **virtual alarm clock devices** as you like from the integration's page ("+ Add device"). Each device is a complete, independent alarm clock with:

- recurring alarm - each weekday individually switchable, with its **own** time per weekday
- one-time alarm (date + time), independent of the recurring alarm
- configurable input device (Assist satellite, e.g. HA Voice PE)
- output device + alarm sound in **one** step via "browse media" (the device you pick the sound on doubles as the output device - no separate device selection) plus separately adjustable volume
- optional light (any `light` entity) with configured color/brightness while ringing - always turns off when stopped (no state restore)
- snooze via voice, button entity, or Voice PE button ([blueprint](blueprints/automation/alarm_clock/voice_pe_snooze_button.yaml))
- stop via voice or button entity

## Status

**Phase 1** ✅ done and verified live against a real Home Assistant instance (HACS install, config flow, subentry device with all 21 entities, scheduling calculation, real ring/snooze/stop cycle including light restore, no errors in the log).

**Phase 2** ✅ Voice control: snooze/stop, plus setting weekday and one-time alarms by voice (see below).

**Phase 3** ✅ Blueprint for button snooze (see below) - e.g. for the center button of a Home Assistant Voice PE.

**Phase 4** ✅ HACS polish (this installation guide) and CI ([`validate.yml`](.github/workflows/validate.yml) checks `hassfest` + HACS requirements on every push/PR).

## Voice control

The following sentences work out of the box (German and English, see [`custom_components/alarm_clock/sentences/`](custom_components/alarm_clock/sentences/)):

- Snooze: "schlummern", "wecker schlummern" / "snooze", "snooze the alarm"
- Stop: "wecker beenden", "wecker aus", "wecker stoppen" / "stop the alarm", "turn off the alarm"
- Set weekday(s) (activates the day(s) automatically): "wecker montags auf sieben uhr stellen", "stelle den wecker für montag auf sieben uhr dreißig", "wecker jeden tag auf sieben uhr stellen", "wecker jeden montag bis mittwoch auf sieben uhr stellen" / "set the alarm for monday to 7", "set alarm for monday to 7 30", "set the alarm for every monday through wednesday to 7"
- Set one-time alarm: "wecker sieben uhr stellen" (no date → next possible time: today if the time hasn't passed yet, otherwise tomorrow), "wecker heute um zweiundzwanzig uhr stellen", "stelle den wecker morgen auf sieben uhr", "wecker montag um sieben uhr stellen" (next Monday), "wecker am 15. august um sieben uhr stellen" (next occurrence of that date, otherwise next year) / "set the alarm at 7" (no date → next possible time), "set the alarm for tomorrow at 7", "set a one time alarm for today at 22", "set the alarm for monday at 7", "set the alarm for the 15th of august at 7"
- Delete weekday(s) (disables, time is kept): "wecker montag löschen", "wecker jeden montag bis mittwoch löschen", "lösche den wecker für montag" / "delete the alarm for monday", "delete the alarm for every monday through wednesday"
- Delete one-time alarm: "wecker löschen", "lösche den wecker" / "delete the alarm", "delete alarm"
- Terse German forms also work, dropping "auf/um ... stellen" entirely: "wecker 8 uhr" (one-time), "wecker freitag 8 uhr" (one-time, next Friday), "wecker freitags 8 uhr" (recurring, every Friday) - the trailing "-s" on the weekday is what tells one-time and recurring apart here, since neither a preposition nor "stellen" is present to disambiguate otherwise.

The integration copies these sentences into `config/custom_sentences/<language>/alarm_clock.yaml` on every setup (HA only loads sentence files from that directory - a custom integration can't ship them so they're picked up automatically), but only ever overwrites a file whose content still matches exactly what it last wrote there itself. Your own edits, or deleting the file (to disable voice control), are therefore preserved permanently - even across integration updates - while genuine changes to the bundled sentences still land, as long as the file hasn't been touched since the last install.

Which device responds is determined by the voice command's `satellite_id`: first, it looks for an alarm clock whose configured input device (Assist satellite) is exactly the one that received the command. For snooze/stop, it otherwise falls back to the single alarm clock currently ringing/snoozed; for the weekday/one-time/delete commands there's no "currently ringing" anchor, so it falls back to the single configured alarm clock instead. If it's still ambiguous in either case, or there's no matching alarm clock, a spoken error message is given instead of a guess.

## Installation

Not yet listed in the official HACS store - add it as a HACS "custom repository":

1. In HACS → *Integrations* → top-right *⋮* → *Custom repositories* → enter this GitHub URL with category "Integration" (alternatively, copy `custom_components/alarm_clock/` manually to `config/custom_components/`).
2. Install "Alarm Clock" via HACS.
3. Restart Home Assistant.
4. *Settings → Devices & services → Add integration → "Alarm Clock"* - sets up the integration once (no configuration dialog).
5. On the new integration page, use "+ Add device" to create and configure a virtual alarm clock device as a subentry (weekdays/times, output device + sound, optionally light and input device). Repeat as often as you like for more alarm clocks.

On first start, the integration also automatically copies the voice commands to `config/custom_sentences/` (see [Voice control](#voice-control)) - no further step needed. For snooze via a hardware button (e.g. Home Assistant Voice PE), import the [button snooze blueprint](#button-snooze-blueprint-phase-3) separately.

## Manual verification (Phase 1)

- After creating a device, all entities (weekday switches/times, one-time alarm, snooze duration, volume, `Ringing`/`Snoozed`, `Next alarm`, buttons `Snooze`/`Stop`/`Test ring`) appear on the device page - the three buttons are under "Controls", everything else configurable (weekday switches/times, one-time alarm, snooze duration, volume) is under "Configuration".
- Set different times for multiple weekdays and enable them → `sensor.<device>_next_alarm` shows the correct, nearest individual appointment.
- Press `button.<device>_test_ring` → the configured media player plays, the configured light turns on, `binary_sensor.<device>_ringing` = on.
- `button.<device>_snooze` (or service `alarm_clock.snooze`) → playback stops, `binary_sensor.<device>_snoozed` = on, it rings again after the snooze duration.
- `button.<device>_stop` (or service `alarm_clock.stop`) → everything back to idle, the configured light turns off.
- Restart HA → all settings (times, weekdays, armed/disarmed) are preserved.

## Manual verification (Phase 2)

- After the first setup, `config/custom_sentences/de/alarm_clock.yaml` and `.../en/alarm_clock.yaml` exist, with an info log about it ("voice commands installed to ...").
- Trigger test ring, then say "schlummern" on the configured Assist satellite → playback stops, `binary_sensor.<device>_snoozed` = on, the satellite speaks a confirmation.
- Let it ring again, say "wecker beenden" → idle, light off, confirmation.
- Exactly one alarm clock is ringing, command issued via *Developer tools → Actions → `conversation.process`* without an associated satellite → the same alarm clock still responds (fallback).
- No alarm clock is ringing, say "schlummern" → spoken error message, no error in the log.
- Two alarm clocks ring simultaneously, command issued via an unassociated satellite → spoken ambiguity error message.
- "wecker montags auf sieben uhr stellen" → the Monday switch turns on, the Monday time shows 07:00, the spoken confirmation names device/day/time.
- "wecker montags auf sieben uhr dreißig stellen" → 07:30 instead of 07:00.
- "wecker jeden tag auf sieben uhr stellen" → all seven weekday switches turn on, all times 07:00.
- "wecker heute um `<time after now>` uhr stellen" → the "One-time alarm" datetime shows today's date, the "One-time alarm active" switch turns on.
- "wecker heute um `<time that has already just passed>` uhr stellen" → jumps to tomorrow, the confirmation says "morgen" instead of "heute".
- "wecker morgen um sieben uhr stellen" → tomorrow's date, 07:00.
- "wecker jeden montag bis mittwoch auf sieben uhr stellen" → the Monday, Tuesday, and Wednesday switches turn on, all times 07:00, the confirmation names "Montag bis Mittwoch".
- "wecker `<time after now>` uhr stellen" (without "um", without a day) → the "One-time alarm" datetime shows today's date.
- "wecker `<time that has already just passed>` uhr stellen" (without a day) → jumps to tomorrow, the confirmation says "morgen".
- "wecker montag um sieben uhr stellen" → the "One-time alarm" datetime shows the date of next Monday, not the recurring Monday switch.
- "wecker am 15. august um sieben uhr stellen" → the "One-time alarm" datetime shows August 15th (this year or next, depending on whether the date has already passed).
- "wecker am 30. februar um sieben uhr stellen" (invalid date) → spoken error message, no error in the log.
- "wecker montag löschen" → the Monday switch turns off, the Monday time stays unchanged, the confirmation names device/day.
- "wecker jeden montag bis mittwoch löschen" → the Monday, Tuesday, and Wednesday switches turn off.
- "wecker löschen" (without a day) → the "One-time alarm active" switch turns off, the stored date stays unchanged.
- "wecker 8 uhr" (real spoken voice input, no "um"/"stellen") → sets the one-time alarm, not misrecognized as a generic entity-control command.
- "wecker freitag 8 uhr" vs "wecker freitags 8 uhr" (real spoken voice input) → the first sets the one-time alarm for next Friday, the second arms the recurring Friday switch - the "-s" is what tells them apart.
- Reinstall the integration (e.g. update) → `config/custom_sentences/de/alarm_clock.yaml` is automatically updated (new info log), as long as the file hasn't changed since the last install.
- Manually edit or delete the file `config/custom_sentences/de/alarm_clock.yaml`, then restart HA → the file stays untouched or deleted, respectively - it's not recreated.

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
