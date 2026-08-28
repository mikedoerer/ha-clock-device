# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A HACS custom integration for Home Assistant (`custom_components/alarm_clock/`): virtual, voice-controlled alarm clock devices. One-person hobby project, actively breaking (no migration guarantees for config fields). All source lives under that single directory - there is no separate package/build layout.

## Commands

There is no test suite, linter config, or build step in this repo. The only validation is CI (`.github/workflows/validate.yml`, runs on every push/PR):

- **hassfest** (`home-assistant/actions/hassfest@master`) - validates manifest.json, service schemas, translations etc. against Home Assistant's integration requirements.
- **HACS validation** (`hacs/action@main`, category `integration`) - validates HACS repository/manifest requirements.

There's no local way to run either exactly as CI does; the closest equivalent is installing this repo into a real (or dev) Home Assistant instance and checking `home-assistant.log` for errors after restart. Manual, on-device verification against a live HA instance is how this project has actually been tested so far (see the Phase-by-phase "Manual verification" sections in README.md) - there is no automated test suite to run instead.

Bump `version` in `manifest.json` when shipping a user-visible change (HACS/hassfest expects it to move).

## Architecture

**One config entry, many subentries.** The integration is a HA *singleton* (`single_instance_allowed`-style config flow in `config_flow.py`): one top-level config entry with no fields of its own. Each virtual alarm clock is a **config subentry** of that entry, and one subentry always owns exactly one device. Adding/editing/removing a subentry triggers `_async_update_listener` in `__init__.py`, which reloads the *entire* entry - there's no surgical per-subentry reload, on the theory that a brief moment of entity unavailability is simpler and more robust than diffing subentries.

**Coordinator per device.** `coordinator.py`'s `AlarmClockCoordinator` is the owner of all runtime state for one alarm clock: its schedule (`alarms: list[Alarm]`), ringing/snoozed/idle state, snooze timer, and the "next trigger" computation/timer. `__init__.py` builds one coordinator per subentry into `hass.data[DOMAIN][subentry_id]`. All entity platforms (`sensor.py`, `binary_sensor.py`, `button.py`, `number.py`) are thin: `entity.py`'s `AlarmClockEntity` base class renders straight from the coordinator with no cached state of its own, and every entity re-renders on the coordinator's per-device dispatcher signal (`signal_update(subentry_id)`, sent via `_push_update()`). Writes go coordinator -> dispatcher signal -> entities re-render; there is no separate "update entity, then sync coordinator" direction.

**Schedule storage: SQLite, not entities.** `store.py`'s `AlarmSqliteStore` persists arbitrary-many recurring (per-weekday) and one-time alarms in a flat SQLite table (`.storage/alarm_clock_alarms.db`), keyed by device_id. This replaced an older one-entity-per-weekday-slot model (Phase 5) - there is no per-alarm entity any more. The full schedule is only readable/writable via services/voice, and is exposed read-only as the `alarms` attribute on the `sensor.<device>_next_trigger` entity (consumed by the bundled dashboard card). `__init__.py` still runs a one-time migration (`_async_migrate_schedule_to_sqlite_once`) that reads any pre-Phase-5 legacy per-subentry `Store` data and removes the now-orphaned weekday/switch/time/datetime entities from the entity registry. Snooze duration and volume are the only settings still persisted in the old per-subentry `Store` (`AlarmClockCoordinator._store`), separate from the SQLite schedule store.

**Voice control (Assist intents), not just services.** `intent.py` registers HA Assist intent handlers (`AlarmClockSnooze/Stop/SetRecurring/SetOnetime/DeleteRecurring/DeleteOnetime`) and, on every setup, syncs bundled sentence files (`sentences/de.yaml`, `sentences/en.yaml`) into `config/custom_sentences/<lang>/alarm_clock.yaml`. This sync is careful not to clobber user edits or a deliberate deletion: it tracks the exact text it last wrote (via a `Store`) and only overwrites a file that still matches that exact text. Device resolution for a voice command (no "input device" field exists - see README Phase 7) is: **named device slot** > **satellite's HA area matching exactly one alarm clock's device area** > a per-intent-family fallback (snooze/stop fall back to "the single ringing/snoozed device"; schedule-setting intents fall back to "the single configured device"). Ambiguous or zero matches raise a spoken error rather than guessing.

**Services exist for the LLM/dashboard fallback path, not primarily for voice.** `services.py` registers `alarm_clock.snooze/stop/set_onetime/set_recurring/delete_onetime/delete_recurring/delete_alarm`. Voice commands go through `intent.py`'s sentence-matched intents directly and don't call these; the services exist as a stable, atomic target for (a) an LLM conversation agent that fails to match the sentence grammar, and (b) the bundled dashboard card (`www/alarm-clock-card.js`), which calls `delete_alarm` by row id. Services accept both `device_id` and `entity_id` as targets (`_coordinators_for_call`) since an LLM fallback's device table may only expose `entity_id`.

**Media/light side effects live on the coordinator.** `async_start_ringing`/`async_snooze`/`async_stop` in `coordinator.py` call `media_player`/`light` services directly against whatever `entity_id` was picked via the config flow's media selector (the *output* media_player is implicitly whichever device the alarm sound was "browsed" on - there's no separate output-device field). Snooze/stop push the dispatcher update *before* the slow blocking hardware calls, so the UI reflects the new state immediately even if a real device is slow/unresponsive.

## Key files

| File | Responsibility |
|---|---|
| `__init__.py` | Entry setup/teardown, coordinator lifecycle, one-time migrations (SQLite schedule, Assist exposure defaults), static path for the dashboard card |
| `config_flow.py` | Singleton entry + per-device subentry create/reconfigure forms |
| `coordinator.py` | Per-device runtime state: schedule mutations, next-trigger scheduling, ring/snooze/stop, snooze-button listener |
| `store.py` | SQLite-backed alarm schedule (recurring + one-time rows) |
| `models.py` | `Weekday` enum (+ `WEEKDAY_ORDER`) and `AlarmState` enum |
| `intent.py` | Assist voice intents, sentence-file sync, device resolution by area |
| `services.py` | `alarm_clock.*` domain services (LLM fallback + dashboard card target) |
| `entity.py` | Shared entity base class (coordinator-driven state, dispatcher subscription) |
| `sensor.py` / `binary_sensor.py` / `button.py` / `number.py` | Entity platforms, all thin wrappers over the coordinator |
| `sentences/{de,en}.yaml` | Bundled Assist sentence templates, synced into `config/custom_sentences/` |
| `www/alarm-clock-card.js` | Bundled Lovelace dashboard card (served at `/alarm_clock_static/`, must be added as a Lovelace resource manually) |

## Conventions to follow

- New persisted config fields go in `const.py` as `CONF_*` / `DEFAULT_*` constants, referenced from `config_flow.py`'s schema and read via `subentry.data.get(...)` in the coordinator - follow the existing fields as the template.
- Any new domain-level service or Assist intent should be added to *both* `services.py` and `intent.py`'s sentence files consistently if it's meant to be reachable by voice, per the existing "services are the LLM-fallback/dashboard target, intents are the primary voice path" split described above.
- Entities never hold their own copy of state - always read through `self.coordinator` and rely on the dispatcher signal for updates (see `entity.py`).
- All SQLite access must go through `AlarmSqliteStore`'s `async_*` wrappers (`hass.async_add_executor_job`) - never call `sqlite3` synchronously on the event loop.
- Comments in this codebase explain *why* (constraints discovered from real hardware behavior, HA API quirks, prior bugs), not *what* - match that style rather than adding narrative comments.
- German and English are both first-class throughout (sentences, translations, speech responses) - a new user-facing string needs both `translations/de.json`/`translations/en.json` (or `strings.json`) and, if it's spoken, a `_localized(...)`-style dict in `intent.py`.
