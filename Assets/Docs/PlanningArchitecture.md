# GoldfishWalking Planning Architecture

This document maps the current Unity prototype to the uploaded design notes.
It is intended as the implementation baseline before large code changes.

## Current Project Shape

The old prototype ran mostly inside `Assets/Scenes/Game.unity`. During the
rebuild, the user decided that scene was outdated and not Canvas-based enough.
New full-game scene work should continue in:

```text
Assets/Scenes/GumBwing_Er.unity
```

`Game.unity` should be treated as old reference unless the user explicitly asks
to modify it.

The new rebuild direction uses one Canvas-based scene with multiple screen
panels instead of loading separate scenes for each game state.

New scene roots:

- `Main Camera`
- `Directional Light`
- `EventSystem`
- `GameRoot`

New `GameRoot` structure:

- `Systems`
  - `GameBootstrap`
  - `MapController`
  - `BattleController`
  - `RestController`
  - `ShopController`
- `UIRoot`
  - `MainCanvas`

Canvas screen panels:

- `TitleScreen`
- `MapScreen`
- `BattleScreen`
- `RewardScreen`
- `RestScreen`
- `ShopScreen`
- `GameOverScreen`

The current flow is:

1. Title starts a new run through `GameBootstrap.StartNewRun()`.
2. `RunContext` resets health, map, item inventory, and fantasy inventory.
3. `MapGenerator` creates the 15-floor branching act map.
4. `MapView` renders generated nodes and contiguous next-floor connections.
5. Selecting a node raises `GameEventHub.MapNodeSelected`.
6. `GameBootstrap` routes the selected node to Map, Battle, Rest, Shop, Reward,
   or GameOver state.

Current progression note:

- The run has 3 acts.
- Each act has a deterministic 15-floor map generated from the run seed plus
  act number.
- Clearing a boss opens rewards first. Reward completion advances to the next
  act for Act 1 and Act 2, and enters `RunClear` after the Act 3 boss.
- Monsters are restricted to the act stored on their imported monster data.

## UI Implementation Direction

Current Battle, Rest, Shop, Reward, and popup UI are mostly runtime-created by
view scripts. This was useful for fast gameplay validation, but it is not the
target final structure.

Final UI direction:

- Screen objects should be pre-placed under the scene Canvas or built as
  prefabs.
- Screen routing should toggle existing screen roots with `SetActive` or
  `CanvasGroup`.
- View scripts should bind to existing UI through `SerializeField` references
  instead of creating every RectTransform at runtime.
- Shared UI such as the 7-segment popup should eventually be a prebuilt scene
  object or prefab that is opened, initialized, and hidden/reused.
- Unity MCP can handle scene-side work: creating GameObjects, assigning
  components, wiring serialized fields, adjusting RectTransforms, and saving
  the scene.

The recommended migration is Battle first, then Rest/Shop/Reward, then the
7-segment popup once the shared popup behavior is stable.

## Target Game Pillars

The uploaded design expands the prototype into these main systems:

- Battle formula system
- Match box editing system
- Item system
- Fantasy passive system
- Monster data and monster pattern system
- Run map progression
- Shop system
- Rest formula system
- Runtime/localization data tables

These systems should be implemented in layers. The match editing UI should not
directly own battle rules, and battle rules should not directly own Unity UI
objects.

## Battle Rules

Combat is always 1:1.

On turn end:

1. Evaluate the player formula from left to right.
2. Apply player damage to the monster.
3. Trigger fantasy effects for each hit when applicable.
4. Repeat for the calculated hit count.
5. If the monster dies, skip the monster attack and win the battle.
6. If the monster survives, evaluate the monster formula/attack pattern and
   apply it to the player.
7. If any combatant reaches 0 or less health, that combatant dies.

Damage can be negative. Negative damage heals the target.
Damage values of `0` or lower do not count as hits and should not trigger
on-hit effects. Negative damage still applies its HP effect when the hit count
is positive.
All fractional values are floored.
There is no max health concept in the uploaded combat design.

Current confirmed interaction:

- The player formula and monster formula are visible at the same time.
- The player can modify numbers inside both formulas before resolving.
- Pressing the turn-progress/resolve button starts resolution.
- Player resolution always happens first.
- Monster resolution only happens if the monster survives the player result.
- Monster formula details currently come from the active monster pattern.
- `Skip` and `Str_n` are non-attack patterns. `Skip` does nothing; `Str_n`
  changes monster strength only.
- An editable monster hit-count value of `0` is valid and means no monster
  attack is applied.

### Target Player Formula

The base structure is:

```text
[BaseDamage] * [HitCount]
```

`BaseDamage` and `HitCount` are separate formula expressions. Multiplication is
treated as the hit-count relationship between those expressions.

Important notes:

- Player base damage starts as a 2-digit box.
- Player strength increases the base damage digit count by 1 per strength.
- Strength cannot go below -3.
- Player hit count starts at 1 and is not directly editable by match movement.
- Player hit count should change only through fantasy effects.
- Monster hit count starts at 1 for normal attack patterns.
- Monster multi-hit patterns can increase monster hit count.
- Monster hit-count boxes can be editable when the active monster pattern allows
  it.
- Fantasy-controlled boxes are locked unless a specific fantasy says otherwise.
- Multiplication means hit count.
- Division means damage division.
- `/ 0` must block closing the box.
- Multiplication/division boxes imply parentheses around both sides.

## Match Box System

The current implementation has number panels made from `MatchManager`,
`DigitManager`, and `Matchstick`. The target design needs a higher-level box
model above those classes.

Recommended model:

```text
FormulaBox
  id
  boxType
  locked
  split
  digits
  operatorValue
  originalState
  currentState

MatchBoxPopup
  opens one FormulaBox
  validates close
  supports reset
  supports undo if implemented

FormulaEditor
  owns all boxes for the current formula
  evaluates final formula
  coordinates global reset
```

### Box Interaction Rules

- A box opens as a popup when clicked.
- Matchsticks can be moved, added, or removed only inside the open popup.
- A popup can close only when the current state forms a valid number or valid
  operator.
- Empty digit slots are ignored. Example: `[315]` changed to `[8  5]` is `85`.
- The runtime stores the parsed numeric value separately from the segment
  arrangement. Battle formula display shows the parsed numeric value only, but
  reopening the popup restores the saved segment arrangement. This preserves
  leading zeroes and empty leading digit slots for continued editing.
- A box cannot close if it becomes completely empty.
- Reset outside a popup resets the whole formula action state.
- Reset inside a popup resets only that box.
- Undo can be skipped initially if it risks item refund or move-count bugs.

### Lock

Locked matchsticks are displayed as burned matchsticks.

Rules:

- A locked matchstick cannot be moved, added to, or removed.
- A locked box prevents all matchstick edits inside it.
- Fantasy boxes are locked by default.

### Split

Split turns a multi-digit box into separate 1-digit boxes.

Example:

```text
[75] -> [7][5]
```

Split boxes:

- Cannot share matchsticks between the split boxes.
- Are still concatenated as one number for calculation.

## Items

Combat rewards can drop one of these items:

- Extra match
- Eraser

Item UI should show owned count as `x N`.

Current reward-list implementation:

- Extra match appears with 50% probability.
- Eraser appears with 50% probability.
- Clicking either reward row immediately adds `+1` to `RunContext.itemInventory`
  and removes that row from the reward list.

### Extra Match

Flow:

1. Click extra match item.
2. Consume one extra match and hold an added match under the mouse cursor.
3. Click an empty segment slot to place it.
4. If the player clicks outside the popup panel while still holding that added
   match, cancel the held match and refund the item.

The box may become invalid after use. Invalid states block closing, not the
operation itself.

Reset must refund consumed extra matches.

### Eraser

Flow:

1. Click eraser item.
2. Click a matchstick.
3. Consume one eraser.

The box may become invalid after use. Invalid states block closing, not the
operation itself.

Reset must refund consumed erasers.

## Fantasy System

Fantasy is the passive perk resource.

Sources:

- Battle reward
- Shop
- Special fantasy effects may add more sources later

Reward rule:

- After battle, show a reward list overlay first.
- The reward list always includes one fantasy reward row.
- Clicking the fantasy row opens 3 fantasy choices.
- The player chooses 1 fantasy from those 3.
- If other reward rows remain, return to the reward list after choosing a
  fantasy.
- If no reward rows remain, close the reward list/card UI.
- The next-region button can skip remaining rewards and return to Map.
- Owned fantasies should not appear again in rewards or shops.

Fantasy grades:

- White: normal battle
- Blue: elite battle
- Red: boss battle

Fantasy effects can:

- Insert locked boxes into the battle formula.
- Modify combat rules.
- Modify rest, shop, item, or map rules.

Generic fantasy data can use condition, target, and value fields.
Special fantasy data may leave those fields empty and route through a custom
effect handler.

Current imported fantasy data uses `Fantasies.tsv` with:

- `TriggerType`: broad trigger category.
- `Effects`: JSON array of effect objects.
- `RARITY`: `White`, `Blue`, or `Red`.

Each fantasy effect has:

- `Trigger`
- `Target`
- `Calc`
- `Value`
- `Option`

`Value` must be preserved as a string expression even when it can also be parsed
as a number. Runtime execution should use `FantasyData.effects[]`, not only the
temporary legacy `trigger/target/value` compatibility fields.

### Current Fantasy Runtime Coverage

The first fantasy runtime pass is implemented under
`Assets/1Scripts/Fantasy/FantasyEffectRunner.cs`.

Currently connected trigger sources:

- reward item chance
- item acquisition
- item use
- shop entry
- shop purchase
- shop price/movement modifiers
- rest heal/rest-count modifiers
- rest coffee fantasy claim
- battle start
- turn start
- turn number such as `Turn_1` and `Turn_4`
- even turn
- attack / deal damage / take damage
- turn end
- battle end
- fantasy acquisition

Current implementation is enough to test most simple numeric and item effects.
It is not the final presentation model: extra damage and reflection effects are
currently queued through `RunContext.pendingMonsterDamage`, then resolved as
additional damage packets. Later battle polish should flash the matching fantasy
and apply those packets at the intended animation/timing point.

Implemented fantasy effect groups:

- Item gain/use/reward/shop effects:
  - reward item chance multiplier
  - duplicate acquired item
  - deterministic 50% used-item copy
  - shop consumable once-free purchase
  - shop discount and shop-entry heal
  - shop movement count increase
- Rest effects:
  - passive rest heal modifiers
  - rest heal multiplier
  - extra rest count
  - coffee choice that claims a deterministic random unowned White fantasy
- Battle effects:
  - extra match/eraser/strength on battle start
  - movement count modifiers
  - unused movement conversion
  - movement-to-item conversion
  - attack-count modifiers
  - incoming damage reduction
  - reflected/additional/turn-end damage
  - simple base-damage special cases
  - HP gain on acquire/battle end/turn end/deal damage

Known unimplemented fantasy/system gaps:

- Cosmetic head fantasies require a player cosmetic/avatar attachment system.
- Stencil requires a dynamic extra shop fantasy slot with once-per-shop state.
- Enemy strength effects require real monster strength runtime and pattern
  recalculation.
- Stamp and blueprint require temporary/permanent fantasy copy or transform
  logic plus selection UI.
- Dice requires reward/fantasy reroll UI and state handling.
- Aquarius requires advanced operator boxes. Only its movement penalty works.
- Sagittarius requires split boxes and whole-box erase behavior.
- Gemini, domino, and apple pie require parse-time digit/value transformation
  before formula evaluation.
- Skipped Red source rows `61` through `66` require filled `DataCode` and
  `Effects` source data before import/runtime implementation.

## Monster System

The design target per act is:

- 7 normal monsters
- 3 elite monsters
- 3 boss monsters

Minimum allowed after cuts:

- 3 normal
- 1 elite
- 1 boss

Cut priority:

1. Boss 2
2. Elite 2
3. Normal 2
4. Then normal one by one

Monster HP may need compact formatting such as `13k` or `32k`.

### Monster Data

Target fields:

- `ID`
- `Act`
- `Difficulty`
- `dev_name`
- `data_name`
- `NAME`
- `DESC`
- `Type`
- `BaseHP`
- `BaseStrength`
- `PatternArray`
- `AIType`
- `Sprite`

ID format:

```text
10001 = Act 1, Normal, number 1
10102 = Act 1, Elite, number 2
10203 = Act 1, Boss, number 3
20001 = Act 2, Normal, number 1
```

Difficulty applies to normal monsters:

- First 3 combats: Easy only
- Afterwards: random encounter logic

AI type:

- `Static`: use patterns in a fixed sequence
- `Random`: choose from the pattern array

Current runtime:

- `Static` sequencing by battle turn is implemented.
- `Random` is parsed but not yet used as runtime selection behavior.
- Monster selection filters by current act and node grade/type.
- Monster display name and HP are bound to the battle UI.
- Player starting HP is currently `150`.

### Monster Patterns

Pattern categories:

- Single hit
- Multi hit
- Strength up
- Strength down
- Heal
- Special pattern

Patterns should be separate data from monster data. Monsters should reference
pattern IDs, not duplicate pattern definitions.

Confirmed pattern-key rules:

- `{DamageDigitCount}_Single` means a single-hit attack with that many damage
  digits, e.g. `3_Single`.
- `{DamageDigitCount}_Multi_{HitDigitCount}` means a multi-hit attack with that
  many damage digits and hit-count digits, e.g. `2_Multi_2`.
- `Str_{Amount}` means the monster gains that much strength, e.g. `Str_1`.
- If monster data has no pattern data, or a referenced pattern has no usable
  content, default to `2_Single`.

Current runtime behavior:

- Built-in keys `Skip`, `{n}_Single`, `{n}_Multi_{m}`, and `Str_n` are handled.
- Custom pattern rows are looked up in `MonsterPatternDatabase`; their top-level
  `Attack` key is used to derive the attack formula when present.
- Monster strength increases the damage digit count for later attack patterns.
- Strength effects with no duration last until the battle ends.
- Full JSON effect processing is still partial. Simple self heal/strength can
  be applied, but `Condition`, `Duration`, `Split`, `Lock`, `Stun`, `Bleed`,
  `Poison`, `Shield`, stack mechanics, lock damage, and dynamic formula values
  still need dedicated runtime systems.

Pattern effects should support JSON-like authoring with:

- top-level `Attack`, `Effects`, and `Condition`
- effect fields such as `Timing`, `Target`, `Action`, `Type`, `Value`,
  `Duration`, and `Lock`
- runtime dynamic values such as `DamageDealt`, `DamageTaken`, `FortuneStack`,
  `ProphecyStack`, `PlayerBleed`, `PlayerPoison`, and `PlayerHP`

`MonsterPatternData` has been expanded enough to store parsed attack/effects
data from the TSV importer, but the battle runtime still implements only a
small subset of those effects.

## Map Progression

Implemented map structure:

- One act has 15 rooms.
- A complete run has 3 acts.
- Room/floor 1 is a single battle node.
- Room/floor 2 is battle.
- Room/floor 15 is always a boss room.
- Nodes can be normal battle, elite battle, shop, rest, or boss.
- Floors can have up to 3 nodes.
- Normal battle, elite, rest, and shop weighting is currently `4:3:2:1`.
- If no shop appears through floor 13, floor 14 is forced to shop.
- Shop, elite, and rest do not appear consecutively.
- Connections advance only to the next floor.
- Next-floor connections must be contiguous.
- Map layout and node placement are generated from a pure integer seed plus act
  number.
- The player chooses from branching paths.

The current `MapView` moves one whole map content container. It does not fade
individual nodes. The current floor is centered and nearby floors are shown at a
readable zoom level.

## Seeded Runtime Numbers

Only a small set of gameplay numbers should be generated from the run seed:

- Player base damage
- Monster base damage
- Monster hit count
- Rest-room heal amount
- Shop prices

Monster patterns are data-driven and should not be randomly generated here.
Monster hit-count digit shape is determined by the active monster pattern, but
the initial hit-count value for an editable multi-hit box is rolled from the
seed, room, pattern, and battle turn.

Seeded values must be deterministic for the same run seed. Avoid using
`UnityEngine.Random` or a shared sequential `System.Random` for these values,
because adding a new random call elsewhere would shift later results.

Recommended approach:

```text
RunSeed
Act
Room/Floor index
Node id
Purpose key
Optional item/index key
  -> independent deterministic integer range
```

Purpose key examples:

```text
battle.player.base_damage
battle.monster.base_damage
battle.player.base_damage.{digitCount}digits.turn.{turnNumber}
battle.monster.base_damage.{patternId}.{turnNumber}
battle.monster.hit_count.{patternId}.{turnNumber}
rest.heal_amount
shop.price.{itemId}
```

Each generated value should create its own deterministic RNG from the full
context above. This keeps existing battle, rest, and shop numbers stable even
if future systems add more seeded rolls.

Current implementation:

- `DeterministicValue` provides independent deterministic integer rolls.
- `RoomNumberStates` stores battle/rest/shop room numbers.
- `RunContext` owns the current battle/rest/shop number state and clears it
  when advancing to a new room.
- Edited battle values, rest heal amount, and shop prices are stored back into
  the current room state.
- Battle values that can change by turn include the battle turn in their
  deterministic purpose key.

## Shop

The shop spends health to buy items and fantasies.

Item rules:

- Item price is a 2-digit match box.
- Item price changes after every purchase.
- No purchase limit.

Fantasy rules:

- Fantasy price uses 2, 3, or 4 digits depending on grade.
- Purchased fantasies become sold out.
- One purchasable fantasy per grade.

Match manipulation in shop:

- Move count is fixed at 2.
- If the player changes a price and buys that product, reset is no longer
  allowed for that purchase.

Current placeholder implementation:

- Shop UI is runtime-created.
- Prices are drawn using matchstick 7-segment digits.
- Prices are seeded per room and per item id.
- Edited prices are stored in the current shop room state.
- Buying spends health.
- Buying item products adds extra matches or erasers to
  `RunContext.itemInventory`.
- Purchase cost floats upward above the health value and fades out.
- Final purchasable content and price manipulation are still placeholder-level.

## Rest

Rest uses a special healing formula.

Target formula:

```text
[+][BaseHeal] + [FantasyBonusHeal] * [FantasyHealMultiplier]
```

The operator box at entry is locked to `+`.
Pressing the rest button heals by the formula value.

Current placeholder implementation:

- Rest UI is runtime-created.
- The center heal value is drawn with matchstick 7-segment digits.
- The heal value is seeded per room and can be edited through the shared
  7-segment popup.
- Pressing rest heals by that value and shows a floating/fading heal number over
  health.

## Data Table Direction

Excel or Google Sheets should be treated as the authoring source for
content-heavy systems:

- Monster data
- Monster pattern data
- Fantasy data
- String table

Recommended pipeline:

```text
Excel or Google Sheet
  -> editor/import step
  -> generated Unity runtime data
  -> game systems read generated data
```

The game should not depend on manually hardcoded monster or fantasy lists.

Recommended generated runtime format:

- JSON in `Assets/Resources/Data`, or
- ScriptableObject database assets under `Assets/Data/Generated`

Keep the spreadsheet as the source of truth. Generated runtime data can be
rebuilt whenever the spreadsheet changes.

### Excel Parsing Options

Option A: CSV/TSV export from Excel or Google Sheets.

- Lowest risk.
- No third-party Unity package required.
- Easy to diff in Git.
- Good first implementation path.

Option B: Direct `.xlsx` import in the Unity Editor.

- Requires an Excel reader library such as ExcelDataReader or a custom editor
  conversion step.
- Should be editor-only, then converted into JSON or ScriptableObject assets.
- Runtime `.xlsx` parsing is not recommended unless there is a strong reason.

Option C: External conversion script.

- A Python or toolchain script reads `.xlsx`.
- It writes JSON/CSV into `Assets/Resources/Data` or `Assets/Data/Generated`.
- Unity only imports the generated files.

Potential later format:

- Addressables for content assets

Current TSV source files:

- `Assets/Data/Raw/Fantasies.tsv`
- `Assets/Data/Raw/Monster.tsv`
- `Assets/Data/Raw/Pattern.tsv`

The old `Assets/xlsx` folder was removed by the user. Current implemented
importers:

- `GoldfishWalking > Data > Import Fantasy TSV`
- Generates `Assets/Data/Generated/FantasyDatabase.asset`
- Generates `Assets/Data/Generated/FantasyImportReport.json`
- `GoldfishWalking > Data > Import Monster TSV`
- Generates `Assets/Data/Generated/MonsterDatabase.asset`
- Generates `Assets/Data/Generated/MonsterPatternDatabase.asset`
- Generates `Assets/Data/Generated/MonsterImportReport.json`

Monster and pattern TSV parsing rules, including Effects JSON meanings, are
recorded in `Assets/Docs/DataImportGuide.md`. Current runtime expects exact
source keys and does not intentionally maintain old typo-normalization paths.

## Current Code Mapping

### Keep and Extend

- `GameBootstrap`
  - Keep as the high-level run/state coordinator.
  - It owns `RunContext`, starts new runs, and routes map node selection and
    room-completion events to the next `GameState`.

- `GameEventHub`
  - Keep as a lightweight event bus.
  - Add strongly named events for formula completion, item use, monster death,
    fantasy selection, and shop purchase when needed.

- `RunContext`
  - Keep as the current run data holder.
  - It currently owns act, room index, seed, map, health, item inventory, and
    fantasy inventory.

- `MapGenerator`
  - Keep as the act-map generation entry point.
  - Current rules already cover the 15-floor act, forced boss, early battles,
    weighted room types, forced shop fallback, and contiguous next-floor
    connections.

- `RewardView`
  - Keep the current two-step reward overlay:
    reward list first, then 3-card fantasy choice only when the fantasy row is
    clicked.
  - Later work should replace placeholder icons/text with data-driven rewards.

### Refactor Heavily

- `GameManager`
  - Currently owns battle flow, random numbers, UI button listeners, enemy HP,
    and match panel coordination.
  - Split into battle controller, formula builder/evaluator, monster runtime,
    and UI binder.

- `MatchManager`
  - Currently represents a digit group and directly reports move count.
  - Convert or wrap into a reusable match-box editor.

- `Matchstick`
  - Currently uses click-select-click behavior and follows `Input.mousePosition`.
  - Needs item modes, lock states, and popup-local editing boundaries.

- `RestManager`
  - Currently heals based on a single number editor.
  - Replace with the shared formula box system.

### Replace or Expand

- `CountUpReward`
  - Works as a prototype reward.
  - Real reward system should use fantasy data plus effect handlers.

## Suggested Implementation Order

1. Add serializable data models.
   - `MonsterData`
   - `MonsterPatternData`
   - `FantasyData`
   - `FormulaBoxData`
   - `FormulaRuntimeState`

2. Create a pure C# formula evaluator.
   - No Unity UI references.
   - Unit-testable outside scene setup.
   - Supports numbers, operators, locked fantasy boxes, multiplication hit
     count, division, and floor behavior.

3. Wrap existing match UI into box-level editing.
   - One box opens at a time.
   - Validate close.
   - Reset one box.

4. Refactor battle flow.
   - Replace `PlayerNumber`, `PlayerMultNumber`, and `EnemyNumber` with
     generated player and monster formulas.
   - Resolve player formula first.
   - Resolve monster formula only if the monster survives.
   - Add monster runtime state and pattern execution.

5. Add item inventory and item modes.
   - Extra match.
   - Eraser.
   - Reset refund.

6. Add fantasy inventory and reward selection.
   - Prevent duplicates.
   - Insert locked formula boxes.

7. Expand map generation when needed.
   - Current 15-floor act, forced early battle floors, boss floor, weighted
     room types, forced shop fallback, and contiguous connections are
     implemented.
   - Later work should focus on content balancing and visual polish rather than
     the basic map structure.

8. Expand shop.
   - Runtime placeholder shop, health payment, seeded 7-segment prices, and
     item inventory purchases exist.
   - Purchase-reset locking is still future work.

9. Expand rest.
   - Runtime placeholder rest screen and seeded editable 7-segment heal value
     exist.
   - Shared full formula logic is still future work.

10. Migrate runtime-created UI to prebuilt Canvas/prefab UI.
   - Start with Battle screen references.
   - Then apply the pattern to Rest, Shop, Reward, and the 7-segment popup.
   - Keep view scripts responsible for data binding and behavior, not layout
     construction.

## Immediate Risks

- Legacy split scenes and the broken `GameSceneStructure.md` document were removed after `Game.unity` became the single active scene.
- The current battle code stores too much unrelated responsibility in
  `GameManager`.
- Runtime-created UI makes layout tuning awkward and should be migrated to
  prebuilt Canvas/prefab UI before final visual polish.
- Item refund logic must remain popup-local and state-aware as undo/reset
  behavior expands.
- Division and invalid operator states require validation before popup close.
- Locked and split boxes are structural concepts, not just visual flags.

## Immediate Next Step

Battle now has imported monster/pattern data connected at a basic runtime
level, but full monster effect resolution and several formula-box systems are
still incomplete. The main non-battle state placeholders exist in
`Assets/Scenes/GumBwing_Er.unity`.

Recommended next target:

1. Expand monster pattern effect runtime for `Condition`, `Duration`, `Split`,
   `Lock`, statuses, stacks, lock damage, and dynamic values.
2. Add the missing formula infrastructure used by monster/fantasy effects:
   split boxes, locked segments/boxes, advanced operators, and digit/value
   transforms.
3. Migrate Battle UI from runtime-created layout to prebuilt Canvas objects with
   serialized field bindings.
4. Apply the same UI binding pattern to Rest, Shop, Reward, and the 7-segment
   popup after Battle is stable.

## Confirmed Formula And Match Rules

Confirmed after architecture planning:

- The battle formula follows the explicit parenthesized structure in the design.
- Players cannot directly input negative numbers. Negative values can only be produced by subtraction or other calculation results.
- Operators are limited to `+`, `-`, `*`, and `/`.
- Damage values of `0` or lower do not count as hits.
- Negative damage still applies its HP effect but does not count as a hit.
- Strength increases player base damage digit count instead of adding a damage
  bonus.
- Player hit count is normally locked at 1 and changed only by fantasy effects.
- Monster hit count can be editable when a monster pattern allows multi-hit
  manipulation.
- Multiplication is treated as a multi-hit count in battle formulas.
- Match movement is always pick-up-and-place.
- A match can move between digits inside the same formula box.
- A match can never move from one formula box to another formula box.
- Added matches use a distinct visual state.
- Added matches can be moved.
- Added matches are returned/refunded when erased or dragged outside the table.
- Extra match items start as a held added match in the popup and refund when
  clicked outside the popup panel before placement.
- Locked matchsticks are visually burned/black.
- Locked matchsticks cannot move and cannot be erased.
- Close validation failure shows a warning popup and does not close the editor popup.
