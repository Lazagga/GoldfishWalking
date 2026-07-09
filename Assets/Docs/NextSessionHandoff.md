# Next Session Handoff

Last updated: 2026-07-08

## Project

- Root: `C:/Users/USER/Documents/GitHub/GoldfishWalking`
- Unity project: `GoldfishWalking`
- Previous main scene: `Assets/Scenes/Game.unity`
- New rebuild scene: `Assets/Scenes/GumBwing_Er.unity`
- New gameplay code location: `Assets/1Scripts`
- Former legacy gameplay code location: `Assets/Scripts` (removed by user)

## Current Direction

The project is being rebuilt from scratch under `Assets/1Scripts`.
The user removed the old legacy `Assets/Scripts` gameplay code and kept only
BGM under `Assets/Audio`. Treat `Assets/1Scripts` as the gameplay source of
truth.

Temporary alias-heavy code was removed after the legacy type conflicts were
cleared. Do not reintroduce aliases such as `GWMonsterData`, `GWGameState`, or
`GWFormulaBox` unless there is a concrete new conflict.

The user decided that the old `Game.unity` scene is outdated and not Canvas
based enough for the rebuild. Continue new gameplay scene work in
`Assets/Scenes/GumBwing_Er.unity`. Keep `Game.unity` only as old reference unless
the user explicitly asks to modify it.

## Confirmed Standing Rules

- Read/write `.cs` files in this project when the task requires it.
- New gameplay scripts must go under `Assets/1Scripts`.
- Do not delete old files unless explicitly requested. In the immediate next
  session, the user will handle legacy cleanup manually.
- New Unity rebuild scene is `Assets/Scenes/GumBwing_Er.unity`.
- Do not replace build settings with the new scene until the user asks.

## Confirmed Formula Rules

- Formula operators are limited to `+`, `-`, `*`, and `/`.
- Negative number input is not allowed directly.
- Negative values can only be produced by calculation results such as
  subtraction.
- Division by zero is invalid.
- Division uses floor behavior.
- Damage values of `0` or lower do not count as hits.
- Damage values below `0` still apply their HP effect. For battle resolution,
  negative player damage heals the monster, but does not count as a hit and
  should not trigger on-hit effects.
- Multiplication is treated as multi-hit count in battle formulas.
- Battle formula is represented as separate damage and hit-count expressions.
- Battle damage is now resolved as `[BaseDamage] * [HitCount]`.
- Player base damage starts as a 2-digit box.
- Player strength increases the base damage digit count by 1 per strength.
- Player hit count starts at 1 and is not directly editable by match movement;
  it should change only through fantasy effects.
- Monster hit count starts at 1 for normal patterns, but an editable monster
  hit-count box may be changed to `0`. Hit count `0` means the monster does not
  attack.
- Monster multi-hit patterns can increase monster hit count, and monster
  hit-count boxes can be editable when the active pattern allows it.
- `Skip` monster patterns perform no action.
- `Str_n` monster patterns only change monster strength and do not attack.
- Monster strength increases the monster base-damage digit count. Strength
  buffs with no duration are permanent until the battle ends.

## Confirmed Battle Flow

- The player formula and monster formula are shown at the same time.
- The player can adjust numbers inside both formulas.
- Pressing the turn-progress/resolve button starts battle resolution.
- The player formula resolves first.
- If the monster dies from the player attack, the monster does not attack.
- If the monster survives and the active monster pattern is an attack pattern,
  the monster formula resolves and damages the player.
- If the active monster pattern is non-attack, such as `Skip` or `Str_n`, no
  monster damage is applied for that turn.
- If both combatants survive, battle returns to formula editing.
- Monster formulas are generated from the current monster's pattern sequence.
  Pattern selection currently cycles by battle turn.

## Confirmed Seeded Number Direction

Only these runtime numbers should be generated from the run seed:

- Player base damage
- Monster base damage
- Rest-room heal amount
- Shop prices

Monster patterns are predetermined by data. Monster hit count is determined by
the active pattern, not by seeded number rolling.

Seeded numbers must be stable for the same seed. Use independent deterministic
rolls from:

```text
RunSeed + Act + Room/Floor + NodeId + PurposeKey + OptionalIndex
```

Purpose key examples:

- `battle.player.base_damage`
- `battle.monster.base_damage`
- `battle.player.base_damage.{digitCount}digits.turn.{turnNumber}`
- `battle.monster.base_damage.{patternId}.{turnNumber}`
- `battle.monster.hit_count.{patternId}.{turnNumber}`
- `rest.heal_amount`
- `shop.price.{itemId}`

Do not use `UnityEngine.Random` or one shared sequential `System.Random` for
these values, because adding a new roll elsewhere would change later results.
Recommended future implementation location is a small deterministic value helper
under `Assets/1Scripts/Core`, then battle/rest/shop callers can request values
by context and purpose key.

Current implementation exists under `Assets/1Scripts/Core`:

- `DeterministicValue`
- `RoomNumberStates`
- `BattleNumberState`
- `RestNumberState`
- `ShopNumberState`

`RunContext` now stores the current room number state for battle/rest/shop and
clears it when advancing to a new map node. Battle base damage, monster base
damage, monster hit count, rest heal amount, and shop prices are generated
independently from the run seed and room context. Battle player damage and
monster pattern values also include the battle turn number, so the same seed,
act, room, pattern, and turn reproduce the same values while later turns can
change.

## Confirmed Match Rules

- Match movement is always pick-up-and-place.
- Matches can move between digits inside the same formula box.
- Matches can never move to another formula box.
- Added matches use a distinct visual state.
- Added matches can move.
- Added matches are returned/refunded when erased or dragged outside the table.
- In the 7-segment popup, pressing the extra match item immediately consumes
  one extra match and puts an added match in the player's hand. The held match
  follows the mouse cursor. Clicking outside the popup panel while holding this
  added match cancels it and refunds the item.
- Locked matches are burned/black.
- Locked matches cannot move and cannot be erased.
- Popup close validation failure must warn the player and keep the popup open.
- A 7-segment box stores both the parsed numeric value and the current segment
  shape. Battle screen display uses the parsed numeric value only, so leading
  zeroes or emptied leading digit slots collapse visually to the remaining
  value. Reopening the popup restores the saved segment shape so the player can
  continue editing the exact previous arrangement.

## Confirmed Data Import State

Current raw data source files are under `Assets/Data/Raw`:

- `Monster.tsv`
- `Pattern.tsv`
- `Fantasies.tsv`

The old `Assets/xlsx` folder was removed by the user. Do not read from it in
future import work.

Original workbook/runtime sheet mapping before conversion:

- `Fantasies.xlsx` / `Fantasies` -> `Assets/Data/Raw/Fantasies.tsv`
- `MonsterData.xlsx` / `Monster` -> `Assets/Data/Raw/Monster.tsv`
- `PatternData.xlsx` / `Pattern` -> `Assets/Data/Raw/Pattern.tsv`

Definition/planning sheets such as `Definition`, `기획용`, and `시트3` are
reference-only and should not be treated as runtime data.

Fantasy TSV import is implemented:

- Menu: `GoldfishWalking > Data > Import Fantasy TSV`
- Source: `Assets/Data/Raw/Fantasies.tsv`
- Output database: `Assets/Data/Generated/FantasyDatabase.asset`
- Output report: `Assets/Data/Generated/FantasyImportReport.json`
- Imported fantasies: 60
- Current report errors/warnings: 0
- Skipped rows: 8 incomplete rows with missing `DataCode` and missing `Effects`

`FantasyData` now stores parsed `effects[]` through `FantasyEffectData`, while
keeping legacy `trigger`, `target`, `value`, and `specialHandler` fields for
temporary compatibility.

Important fantasy effect fields:

- `Trigger`: exact timing/event name.
- `Target`: affected stat/system.
- `Calc`: `Add`, `Multiply`, `Set`, or `Execute`.
- `Value`: numeric value or expression string. Preserve as `valueExpression`.
- `Option`: optional string parameter.

Known fantasy trigger/target/calc values and monster pattern parsing rules are
documented in `Assets/Docs/DataImportGuide.md`. Read that file before the next
data import or fantasy-effect implementation pass.

Monster and pattern TSV import is implemented:

- Menu: `GoldfishWalking > Data > Import Monster TSV`
- Sources:
  - `Assets/Data/Raw/Monster.tsv`
  - `Assets/Data/Raw/Pattern.tsv`
- Output databases:
  - `Assets/Data/Generated/MonsterDatabase.asset`
  - `Assets/Data/Generated/MonsterPatternDatabase.asset`
- Output report:
  - `Assets/Data/Generated/MonsterImportReport.json`
- Imported monster data includes act, difficulty, grade/type, base HP, base
  strength, pattern array, AI type, and sprite id.
- Imported pattern data parses top-level `Attack`, optional `Condition`, and
  `Effects`/`Effect` entries into `MonsterPatternData`.
- Known pattern key rules:
  - `{DamageDigitCount}_Single`
  - `{DamageDigitCount}_Multi_{HitDigitCount}`
  - `Str_{Amount}`
  - `Skip`
- Current runtime uses exact current data. Do not add typo-normalization or
  legacy exception handling unless the source data requires it again.

## Work Completed In This Session

### Environment / Codex

- Diagnosed Codex Windows sandbox helper issue.
- Found `codex-windows-sandbox-setup.exe` existed under standalone resources
  but was missing from the active PATH lookup directory.
- Copied the helper into:
  - `.codex/.sandbox-bin`
  - user home as a test location
  - `.codex/packages/standalone/releases/0.142.4-x86_64-pc-windows-msvc/codex-path`
- Added a PowerShell `codex` wrapper function to:
  - `C:/Users/USER/Documents/WindowsPowerShell/Microsoft.PowerShell_profile.ps1`
- The wrapper temporarily prepends `codex-resources` and `codex-path` to PATH
  before launching Codex.
- Set PowerShell `CurrentUser` execution policy to `RemoteSigned` so the profile
  loads.

### Project Notes

- Added `AGENTS.md` at project root.
- Recorded project rules, `.cs` read/write standing permission, and formula/match
  rules.
- User removed legacy gameplay code under `Assets/Scripts`.
- User moved BGM to `Assets/Audio`.

### Cleanup And Current Battle Work

- Removed temporary alias-heavy references from `Assets/1Scripts`.
- Added `BattleFormulaBuilder`.
- Changed `BattleContext` to hold both player and monster formulas.
- Replaced player-turn/monster-turn state names with editing/resolving states.
- Updated `BattleController.ResolveBattle()` to resolve the player first, then
  resolve the monster only if it survives.
- Updated `BattleView` to call `ResolveBattle()`.

### New Scene / UI Layout Work

- Created `Assets/Scenes/BattleUILayout.unity` as an isolated battle layout
  draft scene.
- Created `Assets/Scenes/GumBwing_Er.unity` as the new Canvas-based full game
  rebuild scene.
- `GumBwing_Er.unity` contains:
  - `Main Camera`
  - `Directional Light`
  - `EventSystem`
  - `GameRoot/Systems`
    - `GameBootstrap`
    - `MapController`
    - `BattleController`
    - `RestController`
    - `ShopController`
  - `GameRoot/UIRoot/MainCanvas`
    - `TitleScreen`
    - `MapScreen`
    - `BattleScreen`
    - `RewardScreen`
    - `RestScreen`
    - `ShopScreen`
    - `GameOverScreen`
- `TitleScreen/StartRunButton` is connected to `GameBootstrap.StartNewRun()`.
- `MainCanvas/GameScreenRouter` is connected to all screen panels.
- `BattleScreen/BattleView` is connected to `BattleController`.
- `BattleScreen` current layout:
  - top left: `FANTASY -`
  - top right: `ITEMS -`
  - left formula panel: player damage, locked hit count, `MOVES 0 / 2`
  - center stage: player and monster placeholder sprites, HP labels above them
  - right formula panel: monster damage, monster hit count, pattern preview
  - bottom bar: `RESET` button on left, `TURN` button on right
- `BattleScreen` is only a placeholder layout for now. User wants to postpone
  battle implementation until monster/fantasy data parsing is done.

### Current Implemented Screen Flow

The current rebuild scene uses runtime-created uGUI layouts from
`Assets/1Scripts/UI`. Most visuals are deliberately simple single-color
placeholder panels because final sprites will be substituted later.

Important UI direction: runtime-created layouts are a temporary implementation
shortcut for rapid feature validation. The target structure is to pre-place the
screen and popup UI under the scene Canvas or prefabs, toggle screens with
`SetActive`/`CanvasGroup`, and have view scripts bind to `SerializeField`
references. Unity MCP can be used to create the objects, wire serialized fields,
adjust RectTransforms, and save the scene.

Implemented flow:

```text
Title -> Map -> Battle -> Reward -> Map
             -> Rest -> Map
             -> Shop -> Map
```

`GameScreenRouter` keeps `BattleScreen` visible underneath `RewardScreen`, so
reward UI behaves as a battle overlay.

Boss battles still grant rewards. After the reward flow completes:

- If the defeated boss was in Act 1 or Act 2, the run advances to the next act.
- If the defeated boss was in Act 3, the run enters `RunClear`.
- `GameScreenRouter` currently shows the existing `GameOverScreen` for both
  `GameOver` and `RunClear`; a dedicated clear screen is still future polish.

### Map Implementation State

- One act currently has 15 floors.
- A full run has 3 acts.
- `RunMap` stores the act number.
- `MapGenerator.Generate(seed, act, roomCount)` includes act in the deterministic
  map seed, so the same run seed produces a different deterministic map per act.
- Floor 1 is always a single battle node.
- Floor 2 is always battle.
- Floors 3-14 can contain battle, elite, rest, or shop nodes.
- Floor 15 is always boss.
- Each floor can contain up to 3 nodes.
- Shop, elite, and rest rooms do not appear consecutively.
- Battle:Elite:Rest:Shop weighted generation is currently `4:3:2:1`.
- If no shop exists through floor 13, floor 14 is forced to shop.
- Connections only advance to the next floor.
- Next-floor connections must be contiguous, e.g. `4-1, 4-2` is valid but
  `4-1, 4-3` is not.
- Seed is currently treated as a pure integer value. There is no encoded seed
  structure.
- `MapView` moves the whole map content instead of fading individual nodes.
- Current floor is centered, with nearby floors enlarged for readable
  navigation.
- Completed/current/selectable node coloring has been corrected.
- Act transition currently resets the room index and generated map while
  preserving run resources such as health, items, and fantasies.

### Rest Implementation State

- `RestView` is runtime-created.
- The center heal number is drawn using the matchstick 7-segment style.
- The heal value is generated from the run seed and current room context.
- Pressing the rest button heals by that value.
- The healed amount floats upward above health and fades out.
- The old lower-left coffee-choice placeholder was removed.
- `Next region` returns to Map through `RestController.CompleteRest()`.

### Shop Implementation State

- `ShopView` is runtime-created.
- Shop item prices are drawn with the matchstick 7-segment style.
- Shop prices are generated from the run seed, current room context, and item
  id. Edited prices are stored in current shop room state.
- Current placeholder layout has six items.
- Buying spends health through `ShopController.TrySpendHealth()`.
- Buying the extra match item adds to `RunContext.itemInventory`.
- Buying the eraser item adds to `RunContext.itemInventory`.
- Purchase health loss floats upward above health and fades out.
- Item grid was moved upward to avoid overlap with the next-region button.
- 7-segment digit spacing was widened slightly so `1` reads more clearly.
- Fantasy inventory slots start empty and are filled only by shop or reward
  acquisition.
- `Next region` returns to Map through `ShopController.CloseShop()`.

### Battle UI Implementation State

- `BattleView` is runtime-created.
- The top-left fantasy area is a horizontal `ScrollRect`, not an explanatory
  text label.
- Monster formula content is right-anchored and pivots from the right, so longer
  formulas can expand left.
- Player battle formula currently shows only player base damage as an editable
  7-segment box. Player hit count is intentionally not displayed; future
  fantasy-triggered extra hits should flash the corresponding fantasy and apply
  another damage instance.
- Monster damage and monster hit count are editable 7-segment boxes.
- Monster name and current/max HP are shown in the existing top-right monster
  status panel.
- Player base damage, monster base damage, and monster hit count are shared
  through current battle room state instead of being only local UI values.
- Player base damage is rolled per battle turn and player damage digit count.
- Monster base damage and monster hit count are rolled per battle turn and
  active monster pattern.
- 7-segment edited numeric values are used for damage calculation. The saved
  segment shape is used only when reopening the popup, so leading zeroes and
  empty leading digit slots can be edited again without forcing the battle UI to
  show them.
- 7-segment popup editing uses pick-up-and-place movement and shows a held match
  following the mouse cursor.
- Popup/battle move count is based on the current shape difference from the
  original shape divided by 2 with floor behavior, so returning a match to its
  original position refunds the move count.
- The popup item panel supports extra match and eraser counts from
  `RunContext.itemInventory`. Extra match starts as a held added match and is
  refunded when clicked outside the popup panel before placement. Eraser removes
  a clicked non-locked match and refunds an added match when erasing one.
- The bottom-left circular arrow button is a battle reset button. It calls
  `BattleController.ResetBattle()` and does not return to Map.
- The bottom-right `E` button calls `BattleController.ResolveBattle()`.
- Runtime duplicate `BattleRuntimeLayout` creation was fixed.

### Monster Runtime Implementation State

- Monster selection reads `MonsterDatabase`.
- Monsters are filtered by current act. There is no cross-act fallback.
- Monster grade/type is selected from the current map node type.
- Monster display name and base HP come from monster data.
- `MonsterRuntime` tracks current health and strength.
- Monster patterns are selected by cycling through the monster's `PatternArray`
  by battle turn. Random AIType is parsed but not yet the active behavior.
- Built-in pattern keys currently handled:
  - `Skip`: no action.
  - `{n}_Single`: one attack with an `n`-digit damage box.
  - `{n}_Multi_{m}`: attack with an `n`-digit damage box and editable
    `m`-digit hit-count box.
  - `Str_n`: gain strength only, no attack.
- Referenced custom patterns are looked up in `MonsterPatternDatabase`. Their
  top-level `Attack` key drives the attack formula when present.
- Simple immediate self effects are partially handled for heal and strength.
- Full pattern effects are still not implemented: `Condition`, `Duration`,
  `Split`, `Lock`, `Stun`, `Bleed`, `Poison`, `Shield`, stack mechanics, lock
  damage, and dynamic value evaluation remain future work.

### Reward Implementation State

- Reward is an overlay on top of Battle.
- Battle victory opens a reward list first, not the 3-card fantasy choice
  screen directly.
- The reward list always contains one fantasy reward row.
- Extra match and eraser reward rows each appear independently at 50% chance.
- Clicking extra match or eraser immediately adds `+1` to
  `RunContext.itemInventory` and removes that row.
- Item count changes raise `GameEventHub.ItemInventoryChanged` so visible item
  UI can refresh.
- Clicking the fantasy row opens the existing 3-card fantasy choice UI.
- Selecting one fantasy adds it to `RunContext.fantasyInventory`.
- If more reward rows remain after fantasy selection, the UI returns to the
  reward list.
- If no reward rows remain, the reward list/card UI closes and the player sees
  the battle background with the next-region button.
- `Close` closes the reward list and skips any unclaimed reward rows.
- `Next region` can be clicked at any time and returns to Map through
  `GameEventHub.RaiseRewardCompleted()`.

### Fantasy Runtime Implementation State

Fantasy TSV data is imported into `Assets/Data/Generated/FantasyDatabase.asset`
and the first runtime execution pass is connected.

Implemented generic handling:

- `FantasyEffectRunner` executes parsed `FantasyEffectData[]`.
- Generic targets currently handled by execution:
  - `HP`
  - `Item`
  - `Extra_Match`
  - `Eraser`
  - `Strength`
  - `Base_Damage`
  - `Damage`
  - `Additional_Damage`
  - `Damage_Reflect`
- Generic modifier lookups are currently used for:
  - battle movement
  - shop movement
  - shop price
  - reward item chance
  - attack count
  - incoming damage reduction
  - rest healing
  - rest count
  - base damage override
- Simple runtime expressions are supported:
  - numeric values
  - one-operation arithmetic strings
  - `HP` / `PlayerHP`
  - `DamageDealt`
  - `DamageTaken`

Implemented or currently testable fantasy effects:

- Shop/rest/reward/item:
  - `fan_shop_pen`
  - `fan_shop_heal`
  - `fan_shop_discount`
  - `fan_reward_rabbitfoot`
  - `fan_acquire_pencil`
  - `fan_shop_stickyglove`
  - `fan_shop_stampcoupon`
  - `fan_use_musicbox`
  - `fan_rest_coffee`
  - `fan_rest_mug`
  - `fan_rest_pillow`
  - `fan_rest_sleepmask`
  - `fan_rest_marshmallow`
  - `fan_acquire_Candy`
  - `fan_acquire_watermelon`
- Battle movement/item/strength:
  - `fan_start_match`
  - `fan_start_eraser`
  - `fan_turn_boots`
  - `fan_end_trumpcard`
  - `fan_turn_pisces`
  - `fan_upgrade_aquarius` movement penalty only
  - `fan_start_capricorn`
  - `fan_start_papercrane`
  - `fan_turn4_clockwork`
  - `fan_damage_abacus`
- Battle damage/hit-count/defense:
  - `fan_end_8ball`
  - `fan_eventurn_pipe`
  - `fan_damage_anchor`
  - `fan_reflect_sail`
  - `fan_damage_slingshot`
  - `fan_end_hourglass`
  - `fan_end_strawberry`
  - `fan_end_grape`
  - `fan_damage_libra`
  - `fan_attack_animalfriends`
  - `fan_turn_syringe`
  - `fan_defend_paperboat`
  - `fan_damage_scythe`
  - `fan_end_fan`
  - `fan_end_firecracker`
  - `fan_end_paperplane`
  - `fan_start_cuestick`
  - `fan_damage_grapeshot`
  - `fan_damage_Bottle`
  - `fan_damage_mirror`
  - `fan_damage_poinsettia`

Current caveats:

- Additional-damage and reflection effects currently apply through
  `pendingMonsterDamage`. This is functionally testable, but final presentation
  should later flash the matching fantasy and apply extra damage packets at the
  intended timing.
- Temporary item grants currently use the same `ItemInventory` as normal items.
  If temporary battle-only items need cleanup, split temporary and owned item
  inventories later.
- `fan_upgrade_aquarius` only applies the movement penalty. Advanced operator
  boxes are not implemented.
- `fan_turn1_doll` trigger dispatch exists, but enemy strength has no combat
  effect until monster strength/pattern runtime is expanded.

Unimplemented fantasies and reasons:

- `fan_rabbit_head`, `fan_turtle_head`, `fan_cat_head`, `fan_parrot_head`:
  cosmetic visuals need player/avatar attachment UI.
- `fan_shop_stencil`: needs an extra dynamic shop fantasy slot and once-per-shop
  purchase state.
- `fan_start_paperfrog`: needs monster strength runtime and formula/pattern
  recalculation.
- `fan_start_stamp`: needs temporary fantasy copy instances and battle cleanup.
- `fan_end_dice`: needs reward/fantasy reroll UI and state handling.
- `fan_upgrade_aquarius`: advanced operator box part needs operator-box
  infrastructure.
- `fan_erase_sagittarius`: needs split boxes and whole-box erase behavior.
- `fan_odd_gemini`: needs parse-time digit/value transform hooks.
- `fan_turn1_doll`: needs monster strength runtime before it changes battle
  behavior.
- `fan_acquire_blueprint`: needs owned-fantasy choice UI and permanent fantasy
  transform logic.
- `fan_number_domino`, `fan_number_applepie`: need formula digit replacement
  rules before evaluation.
- Source rows `61` through `66`: skipped because the source data has no
  `DataCode` and no `Effects`.

### New Architecture Skeleton

Created new code under `Assets/1Scripts`:

- `Core`
  - `GameBootstrap`
  - `GameState`
  - `GameStateMachine`
  - `GameEventHub`
  - `RunContext`
  - `DeterministicValue`
  - `RoomNumberStates`
- `Data`
  - `MonsterData`, `MonsterDatabase`
  - `MonsterPatternData`, `MonsterPatternDatabase`
  - `FantasyData`, `FantasyDatabase`
  - `ItemData`
- `Map`
  - `MapNodeType`
  - `MapNode`
  - `RunMap`
  - `MapGenerator`
  - `MapController`
- `Battle`
  - `BattleController`
  - `BattleContext`
  - `BattleState`
  - `MonsterRuntime`
  - `MonsterSelector`
  - `MonsterPatternRunner`
- `Formula`
  - `FormulaBoxType`
  - `FormulaBox`
  - `FormulaState`
  - `FormulaResult`
  - `FormulaEvaluator`
  - `BattleFormulaState`
  - `BattleFormulaResult`
  - `BattleFormulaBuilder`
- `Match`
  - `MatchBoxController`
  - `MatchDigitView`
  - `MatchstickView`
  - `MatchEditSession`
  - `MatchPieceKind`
  - `MatchPiece`
  - `MatchSlot`
  - `MatchEditResult`
  - `MatchSegment`
  - `MatchPattern`
  - `MatchPatternTable`
  - `MatchPatternInterpreter`
  - `MatchPatternParseResult`
- `Fantasy`
  - `FantasyInventory`
  - `FantasyRewardSelector`
  - `FantasyEffectRunner`
- `Item`
  - `ItemInventory`
  - `ItemUseController`
- `Rest`
  - `RestController`
- `Shop`
  - `ShopController`
- `UI`
  - `GameScreenRouter`
  - `PlayerHudView`
  - `BattleView`
  - `MapView`
  - `RewardView`
  - `RestView`
  - `ShopView`

## Formula / Match Implementation State

`FormulaEvaluator` now supports:

- left-to-right expression evaluation
- negative direct input rejection
- division-by-zero rejection
- floor division
- `BattleFormulaState` evaluation into `BattleFormulaResult`
- `BattleFormulaResult.countsAsHit` false when damage or hit count is `<= 0`
- `BattleFormulaResult.totalDamage` preserves negative damage when hit count is
  positive, so healing is not lost.

`BattleFormulaBuilder` now supports:

- building player battle formulas with separate damage and hit-count expressions
- increasing player base damage digit count from strength
- locking the player hit-count box
- building a placeholder monster formula from monster strength
- allowing future monster pattern logic to decide whether monster hit count is
  editable

`BattleController` now supports:

- separate `playerFormula` and `monsterFormula`
- `ResolveBattle()` instead of player-turn/monster-turn methods
- player-first resolution
- skipping the monster attack if the player attack kills the monster
- returning to `BattleState.Editing` if both combatants survive

`MatchEditSession` now supports:

- pick-up-and-place movement
- same-box slot movement
- locked match movement rejection
- locked match erase rejection
- added match creation as held piece
- added match refund count when erased or dropped outside table
- close validation through pattern parsing

`EditableSevenSegmentBox` now supports:

- common number popup editing for Battle, Rest, and Shop values
- held match preview following the mouse cursor
- extra match and eraser item use inside the popup
- popup-local item refund on cancel/reset
- extra match refund when the held added match is clicked outside the popup
  panel before placement
- move count based on current shape difference from the original shape divided
  by 2 with floor behavior

`MatchPatternInterpreter` now supports:

- parsing digit slots into numbers using 7-segment-style patterns
- parsing operator slots into `+`, `-`, `*`, `/`
- ignoring empty digit indices
- joining parsed digits by `digitIndex` order

Segment index convention:

```text
0 Top
1 UpperRight
2 LowerRight
3 Bottom
4 LowerLeft
5 UpperLeft
6 Middle
7 VerticalCenter
8 SlashForward
9 SlashBack
```

## Important Caveat

Legacy global type conflicts were removed with the old `Assets/Scripts` cleanup.
Temporary aliases in `Assets/1Scripts` were removed. A search for `GW...`,
`using ... =`, and `global::` in `Assets/1Scripts` should remain clean.

## Validation

- `dotnet build Assembly-CSharp.csproj` passed with `0` errors.
- Existing warnings remain:
  - `System.Net.Http` version conflict
  - `System.IO.Compression` version conflict
- These warnings come from Unity/MCP references and predate the new code.
- Unity MCP `refresh_unity` succeeds.
- Unity editor state reports `ready_for_tools: true`.
- Unity console error/warning query reports `0` entries.

## MCP Status

Unity MCP config exists in `C:/Users/USER/.codex/config.toml`:

```toml
[mcp_servers.unityMCP]
url = "http://127.0.0.1:8080/mcp"

[features]
rmcp_client = true
```

Unity MCP tools are now exposed and working.

- Connected instance: `GoldfishWalking@9c7bd15e170629bb`
- Unity version: `6000.3.11f1`
- Active scene may be `Assets/Scenes/GumBwing_Er.unity` after recent work.
- Previous active/reference scene: `Assets/Scenes/Game.unity`
- Current editor state resource path: `mcpforunity://editor/state`
- Old path `mcpforunity://editor_state` is not valid for this server version.
- `mcpforunity://custom-tools` lists Unity tools including `refresh_unity`,
  `read_console`, `manage_scene`, `manage_gameobject`, and `manage_asset`.

## Next Recommended Steps

1. Keep tests deferred for now per user direction unless the user asks for test
   coverage.
2. Convert runtime-created screen UI into pre-placed Canvas/prefab UI with
   serialized field bindings. Start with Battle, then apply the same pattern to
   Rest, Shop, Reward, and the 7-segment popup.
3. Continue replacing placeholder visuals with real data binding before final
   art.
4. Fantasy inventory and the first fantasy effect trigger pass are connected
   across Battle, Shop, Reward, Rest, item acquisition, and item use.
5. Recommended next gameplay target: choose one of the remaining missing
   support systems before implementing more fantasies:
   - monster strength/pattern runtime
   - split/advanced operator/value-transform formula infrastructure
   - fantasy copy/reroll/transform UI
   - cosmetic attachment visuals
6. Deeper battle content work should still wait until monster data and monster
   pattern data runtime are expanded.

## Git Note

No commit was made. The working tree is dirty and contains user cleanup,
`Assets/1Scripts`, docs, data, audio, and project setting changes. Review with
`git status --short` before committing.
