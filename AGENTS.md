# GoldfishWalking Codex Notes

Project path:

```text
C:\Users\USER\Documents\GitHub\GoldfishWalking
```

## Standing Permissions

- Reading `.cs` files in this project is always allowed.
- Writing `.cs` files in this project is always allowed when the requested task requires code changes.
- Do not ask for repeated confirmation before reading or writing project `.cs` files.
- New gameplay code should be written under `Assets/1Scripts`.
- Existing `Assets/Scripts` code is legacy/prototype reference code until the user finishes manual cleanup.
- Do not delete or rewrite existing `Assets/Scripts` files unless explicitly requested.

## Current Direction

- Rebuild gameplay architecture from scratch under `Assets/1Scripts`.
- The user will manually clean legacy scripts before the next coding pass.
- After legacy cleanup, treat `Assets/1Scripts` as the source of truth.
- Remove temporary alias-heavy code once legacy global type conflicts are gone.
- Main Unity scene: `Assets/Scenes/Game.unity`.

## Data-Driven Gameplay Rule

- Monster, fantasy, and pattern behavior must minimize monster/fantasy ID or display-name checks.
- Prefer authored JSON plus generic parsers/runners for timing, targets, conditions, counts, values, ranges, operators, duration, locking, splitting, and special boxes.
- A designer changing an existing supported mechanic in JSON should not require a C# change.
- Add C# only for a genuinely new reusable operation or subsystem, then expose it through the common JSON schema.
- TSV rule columns may carry JSON configuration, but generated assets and parsed runtime fields remain the runtime source after import.

## Confirmed Formula And Match Rules

- Formula operators are limited to `+`, `-`, `*`, and `/`.
- Negative number input is not allowed directly; negative values can only come from calculation results.
- Division by zero is invalid.
- Division uses floor behavior.
- Damage values of `0` or lower do not count as hits.
- Multiplication is treated as multi-hit count in battle formulas.
- Match movement is always pick-up-and-place.
- Matches can move between digits inside the same box.
- Matches can never move to another box.
- Added matches use a distinct visual state, can be moved, and are returned when erased or dragged outside the table.
- Locked matches are burned/black, cannot move, and cannot be erased.
- Popup close validation failure must warn the player and keep the popup open.

## Restart Handoff

Before continuing, read:

- `Assets/Docs/NextSessionHandoff.md`
- `Assets/Docs/PlanningArchitecture.md`

Continue from the latest handoff and regression-check recently implemented monster patterns before adding the next content pass.
