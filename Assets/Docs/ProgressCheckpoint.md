# Progress Checkpoint

Last updated: 2026-07-17

## 2026-07-17 Monster Pattern Checkpoint

- Little Witch and Witch use editable player debuff scene UI beside the player
  formula. Little Witch subtract lasts two turns; Witch divide persists.
  Values reroll deterministically each turn. Divide-by-zero blocks popup close.
- Elf has one seeded `AIM` digit per turn. A match in player-owned number
  boxes, including a displayed leading zero, multiplies Elf base damage by the
  data-authored amount (`3`).
- Magician reads `FormulaDecoyDigitCount`: monster number boxes split and one
  seeded extra digit is excluded from calculation. Singles may look like a
  three-digit single or a two-digit attack with fake hit count. The fake digit
  does not yet have a distinct visual color.
- Conductor and Pied Piper read generic `PlayerAttackCondition` JSON and use
  `MonsterSpecialBoxPanel`. Conductor shows `[digit] x [editable count]`, with
  both values generated from `0..9`; condition boxes are excluded from the
  count. Pied Piper shows a locked two-digit threshold using only `<` or `>`.
  Failed conditions set player base damage to `0`.
- Hunter partial lock is now `NextTurn`, preventing Cue Stick formula rebuilds
  from immediately discarding it.
- Generated monster attacks are revalidated against their digit range
  (`10..99`, `100..999`, etc.). Singles reset hit value/display width to `1`,
  preventing stale `01`.
- Same-seed reward item rolls are cached per battle. Movement modifiers no
  longer apply twice, fixing Boots displaying `6/4`.

Permanent authoring rule: minimize ID/name hardcoding for monsters, fantasies,
and patterns. Prefer JSON parsing and reusable operations so designers can
change supported timing, values, ranges, counts, operators, duration, targets,
and flags without C# edits.

Latest validation: monster import reports `39` monsters and `38` patterns;
command-line build reports `0` errors. Two existing Unity/MCP reference
warnings remain, and the Unity console reports `0` errors/warnings.

## 2026-07-15 Battle Structure And Fantasy Checkpoint

- Current gameplay source: `Assets/1Scripts`; current main scene:
  `Assets/Scenes/GumBwing_Er.unity`. References below to `Game.unity` describe
  earlier rebuild history.

- Added state-driven turn resolution with per-hit player/monster processing,
  per-step damage-log refresh, fantasy hit attribution, status phases, cleanup,
  and outcome checks.
- Reflection now triggers and logs after each damaging monster hit. A reflected
  kill or player death stops the remaining multi-hit sequence immediately.
- Implemented runtime split, whole-box lock, and partial leftmost-digit lock
  behavior, including visual separation/black locks and edit/item restrictions.
- Slime, Ghost, Mushroom, and Hunter structural patterns are connected. Their
  structure survives number edits and whole-turn reset.
- Turn reset restores only current editing state and refunds committed edit
  items; it preserves the active turn's split/lock flags rather than replaying
  the previous turn.
- Completed Cue Stick post-roll leftmost-`8`, Libra final-zero-to-`200`, and
  Sagittarius all-box splitting plus one whole-digit eraser per battle.
- Sticky Glove now displays eligible consumables at price `0` before their free
  purchase is used.
- Fixed copied battle-start fantasy execution, next-turn number refresh, second
  node turn-end interaction, and state-by-state damage-log refresh.

Latest validation: C# build errors `0`; Unity script-console errors `0`.

## Latest Checkpoint

Recent work moved the project from "systems are partially connected" to "most
current TSV content can be imported and exercised in the gameplay loop."

Latest verified state:

- `dotnet build Assembly-CSharp.csproj -v:q` passes with `0` errors.
- Unity refresh/compile succeeds.
- Unity console error/warning query reports `0` entries.
- Fantasy import: 60 imported, 12 incomplete skipped rows, 0 warnings, 0
  errors.
- Monster import: 39 monsters, 33 patterns, 0 warnings, 0 errors.

Latest 2026-07-13 regression pass:

- Corrected closed 7-segment rendering for real leading zeroes, erased leading
  positions, and fully empty boxes while preserving popup segment state.
- Fantasy inventory UI now creates an unlimited number of slots and sizes its
  horizontal content to the number of owned fantasies.
- Damage logs remain available during Game Over; incoming player damage is red;
  the development console and damage debug panel intentionally remain present.
- Match/item holding modes support right-click cancel, and movement remains
  based on net segment-shape difference.
- Fixed current-attack `DamageDealt` handling so zero monster damage cannot
  reuse player damage for bleed/poison stacks.
- Implemented editable healing boxes for Giant Rat and Cosmic Tree; corrected
  Jellyfish flooring/status healing, Knight cap removal, Stargazer digit
  accumulation and three-hit Meteor Shower, and final-step countdown outcomes.
- White Rabbit escape and Heart Queen doom now occur after all normal turn-end
  processing. Heart Queen executes `HeartQueenSkill` through the pattern runner.
- Consumable shop purchases regenerate price and clear the prior price edit's
  movement difference.
- `fan_end_dice` reroll is complete: charges are granted/consumed, each roll has
  a deterministic index, and the previous three choices are avoided when the
  candidate pool permits it.
- Runtime regression check for Dice produced two three-card sets with `0`
  overlapping cards.
- `fan_start_stamp` creates a deterministic temporary owned-fantasy duplicate
  at battle start, and normal battle cleanup removes temporary copies.

Recent completed items:

- Static screen chrome migration started:
  - Battle, Rest, Shop, Title seed input, Seed display, and shared fantasy-list
    UI bind to scene objects instead of creating full screen layouts at
    runtime.
  - Reward screen background/overlay chrome was removed or disabled so Battle
    remains visible under the reward overlay.
  - Reward rows/cards are dynamic again because the reward set is variable and
    fixed slots produced awkward empty spaces.
  - `EditableSevenSegmentBox` and `MapView` still create data-driven repeated
    content at runtime; this is intentional for now and should later become
    pooled/prefab-backed only if needed.
- Monster pattern runtime supports the current data set's condition/phase,
  dynamic damage expression, timed strength, status, stack, and special-box
  needs.
- Pattern sequencing is confirmed as sequential cycling through `PatternArray`,
  not random selection.
- Act 1 early floors are constrained: floor 1 uses the fairy, floors 2-3 use
  Easy monsters.
- Damage debug output distinguishes direct player damage from fantasy damage.
- Player and monster buff/debuff displays exist under their damage/formula
  areas.
- Fantasy tooltip behavior is present across battle/reward/shop/rest inventory
  lists and shop product hover.
- Console fantasy addition triggers acquisition effects and post-acquire
  transforms.
- Fantasy data values are read from `FantasyData` generated by TSV import;
  current hardcoded fallbacks are used only as defensive fallback values.
- `duration` values are imported and applied where the current runtime supports
  timed effects.
- Temporary extra match/eraser grants are cleaned up at their intended
  temporary lifetime.
- Shop fantasy display now uses the actual selected shop fantasy instead of
  reusing stale first-shop data.
- Player bleed/poison from monsters is implemented as player debuffs. Existing
  stacks tick after the monster action near turn end; newly pending stacks are
  activated afterward so they do not tick immediately. Both clear after battle.
- `fan_shop_stencil` is implemented as the sixth shop slot. It offers one owned
  White fantasy excluding stencil itself, uses a 2-digit price, supports hover
  tooltip, and is buyable once per shop.
- `fan_rest_coffee` lets the player skip resting and claim a deterministic
  random unowned White fantasy.
- `fan_attack_animalfriends` is excluded from reward/shop pools and is obtained
  by replacing the four animal cosmetic fantasies when all are owned.

## Completed

- Confirmed Unity MCP connection for `GoldfishWalking`.
- Confirmed active rebuild Unity scene is `Assets/Scenes/GumBwing_Er.unity`.
- Confirmed MCP tool calls work without the previous sandbox issue.
- Confirmed current Unity MCP editor state path is
  `mcpforunity://editor/state`.
- Legacy gameplay code under `Assets/Scripts` was removed by the user.
- BGM was moved under `Assets/Audio`.
- Cleaned `Assets/1Scripts` temporary aliases after legacy global type conflicts
  were removed.
- Added and compiled the new gameplay architecture skeleton under
  `Assets/1Scripts`.
- Added pure formula evaluation:
  - left-to-right expression evaluation
  - direct negative input rejection
  - division-by-zero rejection
  - floor division
  - separate battle damage and hit-count expressions
- Added battle formula result semantics:
  - hit is counted only when damage per hit and hit count are both positive
  - negative damage still applies as HP change/healing when hit count is positive
- Added `BattleFormulaBuilder`.
- Updated battle formula generation for the new damage rule:
  - damage resolves as base damage times hit count
  - player strength increases base damage digit count instead of adding damage
  - player hit count is locked at 1 for now
  - monster hit count can be made editable later for multi-hit patterns
- Changed battle context to hold both player and monster formulas.
- Replaced the mistaken player-turn/monster-turn state naming with:
  - `NotStarted`
  - `Editing`
  - `Resolving`
  - `Won`
  - `Lost`
- Updated battle resolution:
  - player formula resolves first
  - monster does not attack if killed by the player result
  - monster attacks only if it survives
  - battle returns to editing if both survive
- Added match editing model support:
  - pick-up-and-place movement
  - locked match move/erase rejection
  - added match refund count on erase/drop outside
  - number/operator match pattern parsing
- Verified `dotnet build Assembly-CSharp.csproj` succeeds.
- Verified Unity MCP refresh succeeds and console error/warning count is `0`.
- Created `Assets/Scenes/BattleUILayout.unity` as a battle layout draft scene.
- Created `Assets/Scenes/GumBwing_Er.unity` as the new Canvas-based full game
  rebuild scene.
- Built initial `GumBwing_Er.unity` scene structure:
  - `GameRoot/Systems` with new architecture controllers
  - `GameRoot/UIRoot/MainCanvas` with Title, Map, Battle, Reward, Rest, Shop,
    and GameOver screens
  - `GameScreenRouter` connected to all screens
  - Title start button connected to `GameBootstrap.StartNewRun()`
  - Battle screen `TURN` button connected through `BattleView`
- Revised Battle screen placeholder layout:
  - top bar has `FANTASY -` and `ITEMS -`
  - player HP and monster HP sit above their placeholder sprites
  - player formula lower shelf shows `MOVES 0 / 2`
  - bottom bar has `RESET` and `TURN`
- Deeper battle implementation resumed after monster/fantasy data parsing was
  connected; remaining battle work is now mostly regression QA, presentation,
  and missing formula infrastructure.
- Implemented current map generation rules:
  - 15 floors
  - floor 1 single battle
  - floor 2 battle
  - floor 15 boss
  - up to 3 nodes per floor
  - battle/elite/rest/shop weight `4:3:2:1`
  - no consecutive shop/elite/rest special rooms
  - force floor 14 shop if no shop appears through floor 13
  - next-floor connections only, with contiguous destination indices
- Implemented `MapView` whole-content movement, current-floor centering, and
  corrected current/completed/selectable node coloring.
- Implemented runtime `RestView`:
  - 7-segment matchstick heal value
  - rest button heals by the shown value
  - floating/fading heal number over health
  - next-region return to Map
- Implemented runtime `ShopView`:
  - 7-segment matchstick prices
  - health payment
  - floating/fading purchase cost over health
  - empty fantasy slots at run start
  - next-region return to Map
- Implemented runtime `BattleView` layout revision:
  - horizontal fantasy inventory `ScrollRect`
  - right-anchored monster formula that can expand left
  - player base damage displayed as an editable 7-segment box
  - player hit count hidden from the formula UI by design
  - monster base damage and monster hit count displayed as editable 7-segment
    boxes
  - 7-segment popup editing with held match following the mouse cursor
  - move count calculated from current-vs-original shape difference divided by
    2 with floor behavior
  - popup item panel supports extra match and eraser item use from
    `RunContext.itemInventory`
  - extra match starts as a held added match; clicking outside the popup panel
    before placement refunds the item
  - bottom-left reset button calls `BattleController.ResetBattle()`
  - bottom-right `E` resolves battle
  - duplicate runtime layout creation fixed
- Implemented `RewardView` as a Battle overlay:
  - reward screen background is disabled so the battle state remains visible
    behind the overlay
  - reward list appears before fantasy choice cards
  - fantasy reward row always appears
  - extra match row appears at 50% chance
  - eraser row appears at 50% chance
  - reward rows are generated dynamically and packed without empty gaps
  - extra match/eraser rows immediately add `+1` to item inventory on click
  - fantasy row opens dynamically generated 3-card fantasy choices
  - selecting a fantasy adds it to fantasy inventory
  - returns to the reward list if more rewards remain
  - closes the reward UI if no rewards remain or `Close` is pressed
  - next-region button returns to Map at any time
- Added item inventory sharing:
  - extra match and eraser rewards add to `RunContext.itemInventory`
  - shop item purchases add extra matches or erasers
  - battle/rest/shop 7-segment popups can use the item inventory
  - `GameEventHub.ItemInventoryChanged` refreshes visible item counts
- Added deterministic room number sharing:
  - `DeterministicValue`
  - `RoomNumberStates`
  - current battle/rest/shop room number state in `RunContext`
  - seeded player base damage, monster base damage, rest heal amount, and shop
    prices
  - edited 7-segment values are stored back into the current room state
- Updated deterministic battle number rolling:
  - player base damage includes battle turn and digit count in its seed key
  - monster base damage includes active pattern and battle turn in its seed key
  - monster hit count includes active pattern and battle turn in its seed key
  - the same seed/act/room/pattern/turn reproduces the same battle numbers
    while later turns can roll different values
- Added 7-segment numeric/shape state separation:
  - parsed numeric value is used for calculation and compact battle display
  - popup reopening restores the saved segment arrangement
  - leading zeroes and empty leading digit slots can be edited again even when
    the battle screen displays only the remaining numeric value
- Fixed monster hit-count `0`:
  - `0` is now a valid editable monster hit count
  - `0` hit count means no monster attack is applied
  - battle UI no longer falls back to placeholder hit count `4` when the real
    value is `0`
- Implemented monster TSV import:
  - current raw sources are `Assets/Data/Raw/Monster.tsv` and
    `Assets/Data/Raw/Pattern.tsv`
  - editor importer menu added:
    `GoldfishWalking > Data > Import Monster TSV`
  - generated `Assets/Data/Generated/MonsterDatabase.asset`
  - generated `Assets/Data/Generated/MonsterPatternDatabase.asset`
  - generated `Assets/Data/Generated/MonsterImportReport.json`
- Implemented current monster runtime pass:
  - monster selection reads imported monster database
  - monsters are filtered by current act and map-node grade/type
  - monster display name and HP are reflected in the existing top-right battle
    UI
  - monster patterns cycle by battle turn
  - built-in `Skip`, `{n}_Single`, `{n}_Multi_{m}`, and `Str_n` keys are
    handled
  - `Skip` does nothing
  - `Str_n` only changes monster strength and does not attack
  - monster strength increases later attack damage digit count
  - strength effects without duration currently last until battle end
- Implemented act progression:
  - run has Act 1, Act 2, and Act 3
  - each act generates a deterministic 15-floor map from the same run seed plus
    act number
  - boss victory opens rewards first
  - reward completion after Act 1 or Act 2 boss advances to the next act
  - reward completion after Act 3 boss enters `RunClear`
- Set player starting health to `150`.
- Added fantasy TSV data import:
  - current raw source is `Assets/Data/Raw/Fantasies.tsv`
  - previous `Assets/xlsx` folder was removed by the user
  - `FantasyData` now stores source ids, data codes, trigger text, raw effects,
    and parsed `FantasyEffectData[]`
  - editor importer menu added:
    `GoldfishWalking > Data > Import Fantasy TSV`
  - generated `Assets/Data/Generated/FantasyDatabase.asset`
  - generated `Assets/Data/Generated/FantasyImportReport.json`
  - imported 60 fantasies
  - skipped 8 incomplete rows with missing `DataCode` and missing `Effects`
  - fixed `fan_acquire_Candy` by adding the missing closing JSON braces/bracket
    and backtick
  - current fantasy import report has `0` errors and `0` warnings
- Implemented the first fantasy effect runtime pass:
  - `FantasyEffectRunner` now executes parsed `FantasyEffectData[]` instead of
    relying only on old legacy enum fields.
  - Supported generic effect targets now include `HP`, `Item`,
    `Extra_Match`, `Eraser`, `Strength`, `Base_Damage`, `Damage`,
    `Additional_Damage`, and `Damage_Reflect`.
  - Supported modifier lookups now cover battle movement, shop movement, shop
    price, reward item chance, attack count, incoming damage reduction, rest
    heal, rest count, and base damage overrides.
  - Supported runtime value expressions now include numeric values, simple
    arithmetic, `HP`/`PlayerHP`, `DamageDealt`, and `DamageTaken`.
  - Added run-time context fields for recent item acquisition/use, recent shop
    purchase cost, battle damage totals, remaining movement, temporary movement
    bonus, and passive attack-count bonus.
- Implemented immediately testable fantasy behaviors:
  - `fan_shop_pen`: shop movement count increase.
  - `fan_shop_heal`: heal on shop entry.
  - `fan_shop_discount`: passive shop price multiplier.
  - `fan_start_match`: battle-start extra match.
  - `fan_start_eraser`: battle-start eraser.
  - `fan_reward_rabbitfoot`: battle reward item chance multiplier.
  - `fan_acquire_pencil`: duplicated item gain on item acquisition.
  - `fan_end_8ball`: turn-end damage based on visible `8` digits.
  - `fan_eventurn_pipe`: even-turn attack-count increase.
  - `fan_damage_anchor`: incoming damage reduction.
  - `fan_reflect_sail`: damage reflection through pending monster damage.
  - `fan_turn_boots`: turn-start movement increase.
  - `fan_end_trumpcard`: converts unused movement into next-turn temporary
    movement.
  - `fan_damage_slingshot`: additional damage after dealing damage.
  - `fan_end_hourglass`: fixed turn-end monster damage.
  - `fan_start_papercrane`: battle-start strength.
  - `fan_acquire_watermelon`: HP on acquire.
  - `fan_end_strawberry`: HP on battle end.
  - `fan_end_grape`: turn-end HP from remaining movement.
  - `fan_rest_coffee`: rest-screen fantasy button that claims a deterministic
    random unowned White fantasy instead of resting.
  - `fan_rest_mug`: rest heal amount modifier through passive `HP`.
  - `fan_rest_pillow`: rest heal amount modifier through passive `HP`.
  - `fan_damage_libra`: base damage special case, `00` becomes `200`, otherwise
    `0`.
  - `fan_turn_pisces`: converts remaining movement into extra matches and
    erasers.
  - `fan_upgrade_aquarius`: movement penalty is applied. Operator-box upgrade
    is still not implemented.
  - `fan_attack_animalfriends`: player attack count `+4`.
  - `fan_shop_stencil`: sixth shop slot offers an owned White fantasy excluding
    stencil itself, with a 2-digit price and once-per-shop purchase state.
  - `fan_start_capricorn`: battle-start movement, strength, eraser, and extra
    match.
  - `fan_shop_stickyglove`: shop consumable items can each be bought once for
    free.
  - `fan_shop_stampcoupon`: spending at least `999` health in shop increments
    passive player attack count.
  - `fan_turn_syringe`: passive attack-count increase.
  - `fan_defend_paperboat`: conditional incoming damage halving when monster
    base damage is at least player base damage.
  - `fan_turn1_doll`: turn-1 enemy strength modifier is queued through the
    current monster strength runtime.
  - `fan_use_musicbox`: item use has a deterministic 50% chance to copy the
    used item.
  - `fan_damage_scythe`: current HP gain from dealt damage.
  - `fan_end_fan`: turn-end damage based on current player HP.
  - `fan_end_firecracker`: turn-end damage based on item-use count this battle.
  - `fan_end_paperplane`: doubles pending damage when player and monster base
    damage match.
  - `fan_start_cuestick`: battle-start first digit forced to `8`.
  - `fan_turn4_clockwork`: turn-4 strength.
  - `fan_rest_sleepmask`: rest healing multiplier.
  - `fan_rest_marshmallow`: additional rest use count.
  - `fan_damage_grapeshot`: additional damage after dealing damage.
  - `fan_damage_Bottle`: fixed damage reflection.
  - `fan_damage_mirror`: same-digit base damage attack-count bonus.
  - `fan_acquire_Candy`: on acquire, adds 10% of current HP.
  - `fan_damage_abacus`: turn-start movement increase.
  - `fan_damage_poinsettia`: incoming damage reduction.
- Current fantasy runtime caveats:
  - Additional-damage and reflection effects currently use
    `pendingMonsterDamage`, so they resolve as extra damage packets rather than
    final polished per-hit animation/fantasy flash behavior.
  - Trigger timing is functional for available systems, but not every design
    trigger has a dedicated UI or battle subsystem yet.
  - Temporary item grants currently use the same inventory container as normal
    items. A later pass should separate run-owned items from battle-temporary
    grants if design requires cleanup after battle.

## Known Unimplemented Or Partial Fantasies

These entries are imported from `Fantasies.tsv` but still require systems that
do not exist yet, or are only partially mapped:

- `fan_rabbit_head`, `fan_turtle_head`, `fan_cat_head`, `fan_parrot_head`:
  cosmetic head visuals are not implemented. Need player cosmetic/avatar
  attachment UI before these can do anything visible. They now still contribute
  to the animalfriends transform rule.
- `fan_upgrade_aquarius`: movement penalty works, but operator-box upgrade is
  intentionally deferred because the effect is expected to change.
- `fan_acquire_blueprint`: currently copies a random owned fantasy on acquire.
  Add an explicit choice UI later if design requires player agency.
- Cosmetic sprite application and aquarius redesign are intentionally deferred.
- Source rows `62` through `73`: imported source has rows with
  missing `DataCode` and missing `Effects`, so they are skipped by the importer
  until the source data is filled.

## Key Files

- `Assets/Docs/PlanningArchitecture.md`
- `Assets/Docs/NextSessionHandoff.md`
- `Assets/Docs/DataImportGuide.md`
- `Assets/1Scripts/Core`
- `Assets/1Scripts/Data`
- `Assets/1Scripts/Battle`
- `Assets/1Scripts/Formula`
- `Assets/1Scripts/Match`
- `Assets/1Scripts/UI`
- `Assets/Scenes/GumBwing_Er.unity`
- `Assets/Scenes/BattleUILayout.unity`
- `Assets/Screenshots/GumBwing_Er_title_preview.png`
- `Assets/Screenshots/GumBwing_Er_battle_moves_reset_turn.png`
- `Assets/Data/Raw`
- `Assets/Data/Generated`
- `Assets/1Scripts/Editor/DataImport/FantasyTsvImporter.cs`

## Current State

The project is now using `Assets/1Scripts` as the gameplay source of truth.
`GumBwing_Er.unity` is the Canvas-based rebuild scene. Battle, Rest, Shop,
Title seed input, Seed display, and shared fantasy-list chrome now bind to
scene UI. Reward uses a hybrid overlay: stable scene containers/buttons plus
dynamic rows/cards under those containers. Map nodes/lines and 7-segment
digits/segments remain data-driven runtime content. Battle has core formula
logic, shared 7-segment popup editing, item inventory usage, and seeded room
number state.

Deterministic seeded number generation is implemented for player base damage,
monster base damage, monster hit count, rest heal amount, and shop prices.
Battle player damage, monster damage, and monster hit count include battle turn
where needed. Monster patterns are fixed by data, and monster hit-count digit
shape comes from the active pattern.

Monster and pattern TSV import is implemented. Runtime monster behavior now
covers the current TSV set at a practical testing level: act-restricted monster
selection, HP/name display, sequential pattern cycling, attack digit counts,
editable multi-hit counts, `Skip`, `Str_n`, conditions, phases, dynamic damage
expressions, timed strength modifiers, player bleed/poison, stack mechanics,
and special editable monster boxes. Remaining monster/pattern work is mostly
polish for split/lock/shield presentation and final animation/timing. Split and
lock rules themselves are now functional.

Fantasy data is imported from TSV into `FantasyDatabase.asset`, and the first
runtime effect pass is now connected to battle, reward, shop, rest, acquisition,
and item-use flows. Most simple numeric/item/combat modifiers are usable. The
remaining fantasy work is concentrated around systems that are intentionally
deferred or need UI polish: cosmetic visuals, aquarius redesign, advanced
operator boxes, split/lock presentation polish, and explicit fantasy
copy/transform choice UI.

Important UI direction: static screen chrome should be prebuilt in the scene or
prefabs and bound by view scripts. Variable repeated content can stay dynamic or
be converted to pools when appropriate. Current accepted dynamic areas are
reward rows/cards, map nodes/lines, and 7-segment digit/segment content.

## Next Step

Next:

1. Keep tests deferred for now unless the user asks for test coverage.
2. Work in `Assets/Scenes/GumBwing_Er.unity` as the rebuild scene.
3. Run regression QA against the accumulated bug report before adding more
   content.
4. Verify imported monster/pattern/fantasy data in play mode.
5. Recommended cleanup target: regression-test Reward overlay after the dynamic
   row/card correction.
6. Continue static UI chrome cleanup, but keep variable repeated content
   dynamic or pooled when fixed UI hurts layout.
7. Improve reward cards to show imported fantasy name/description/effect data
   more cleanly once string/localization data is settled.
8. Decide the next fantasy-system target:
   - cosmetic attachment visuals, or
   - split/advanced operator/value-transform formula infrastructure, or
   - temporary fantasy copy/transform choice UI.
