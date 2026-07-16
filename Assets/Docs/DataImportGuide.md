# Data Import Guide

## 2026-07-16 Runtime Authoring Update

This section supersedes conflicting older notes in this guide.

TSV remains an import source and reimporting can overwrite generated assets.
For direct Unity balancing, the generated database Inspectors are also a
supported runtime-authoring path:

```text
Effects JSON (Runtime Source)
  -> immediate validation/parsing
  -> structured runtime definition
  -> gameplay
```

Invalid JSON displays an Inspector error and preserves the last valid runtime
definition. Parsed fields are read-only previews; `rawJson` and legacy fantasy
fields are not independent authoring sources. `MonsterDatabase` has a searchable
inspector grouped into encounter data, battle stats, pattern AI, special rules,
and read-only import metadata.

Top-level monster-pattern `Count` rules:

- omitted: unlimited uses;
- `0`: unavailable;
- positive: maximum selections per battle;
- usage is keyed by pattern ID, so duplicate IDs share one counter.

Effect-level `Count` is an action-specific quantity (currently used for box
construction), not pattern usage. `HitCount` is damage application count.

`Skip` is an authored special pattern resolved from
`MonsterPatternDatabase`, so its Count, Condition, and effects come from JSON:

```json
{"Attack":"Skip","Count":3,"Effect":null}
```

Formula keys such as `3_Single`, `2_Multi_2`, and `Str_1` still use the generic
key parser. Missing or unusable references fall back to `2_Single`.

`AIType` is active: `Static` cycles in order while skipping ineligible entries;
`Random` deterministically chooses among Count/Condition-eligible entries.

Current generated import status: 39 monsters, 38 patterns, 60 fantasies.

Google Sheets/Excel is the authoring source of truth for monster, pattern, and
fantasy data. Runtime systems should read generated Unity data, not raw sheet
cells.

## Current Source Files

The previous `Assets/xlsx` folder was removed by the user. Do not read from it
in future importer work.

Current source files:

```text
Assets/Data/Raw
  Monster.tsv
  MonsterRules.tsv
  Pattern.tsv
  PatternRules.tsv
  Fantasies.tsv

Assets/Data/Generated
  MonsterDatabase.asset
  MonsterPatternDatabase.asset
  FantasyDatabase.asset
  FantasyImportReport.json
  MonsterImportReport.json
```

Preferred flow:

1. Read TSV rows from `Assets/Data/Raw`.
2. Normalize raw rows into explicit intermediate records.
3. Validate missing or malformed cells and apply fallback rules.
4. Generate ScriptableObject databases under `Assets/Data/Generated`.
5. Generate an import report for warnings, errors, fallback use, and skipped rows.

## Original Workbook Structure

The xlsx files had these useful sheets before conversion to TSV:

- `Fantasies.xlsx`
  - `Definition`: column definition/reference sheet.
  - `Fantasies`: runtime source data. Converted to `Assets/Data/Raw/Fantasies.tsv`.
  - `기획용`: planning-only notes.
- `MonsterData.xlsx`
  - `Definition`: column definition/reference sheet.
  - `Monster`: runtime source data. Converted to `Assets/Data/Raw/Monster.tsv`.
  - `기획용`: planning-only notes.
- `PatternData.xlsx`
  - `Definition`: column definition/reference sheet.
  - `Pattern`: runtime source data. Converted to `Assets/Data/Raw/Pattern.tsv`.
  - `시트3`: planning/reference sheet.

Use only the runtime source sheets/files for import. Treat definition and
planning sheets as documentation, not runtime data.

## Runtime TSV Schemas

`Monster.tsv` headers:

```text
ID
Act
Difficulty
DevName
DataName
NameStringID
DescStringID
Type
BaseHP
BaseStrength
PatternArray
AIType
Sprite
```

Monster field meanings:

- `ID`: numeric monster id.
- `Act`: act number.
- `Difficulty`: normal monster difficulty. Current values: `Easy`, `Normal`.
- `DevName`: designer-facing Korean name.
- `DataName`: stable runtime key.
- `NameStringID`: future string table id for name.
- `DescStringID`: future string table id for description.
- `Type`: `Normal`, `Elite`, or `Boss`.
- `BaseHP`: base monster HP.
- `BaseStrength`: base monster strength.
- `PatternArray`: comma/semicolon/pipe separated pattern key list.
- `AIType`: `Static` or `Random`.
- `Sprite`: future sprite resource key.

`Pattern.tsv` headers:

```text
ID
DevName
DataCode
NameStringID
Effects
SpriteRes
설명
```

Pattern field meanings:

- `ID`: numeric pattern id when present.
- `DevName`: designer-facing name.
- `DataCode`: stable pattern key used by monster `PatternArray`.
- `NameStringID`: future string table id for pattern name.
- `Effects`: JSON object describing attack, effects, and condition.
- `SpriteRes`: future icon/sprite resource key.
- `설명`: designer-facing Korean explanation.

`Fantasies.tsv` headers:

```text
ID
DevName
DataCode
NameStringID
DescStringID
TriggerType
Effects
RARITY
Sprite
```

Fantasy field meanings:

- `ID`: numeric source id from the sheet.
- `DevName`: designer-facing Korean display/name note. Currently used as
  `displayName` until string tables are wired.
- `DataCode`: stable runtime key. Use this as `FantasyData.id`.
- `NameStringID`: future string table id for name.
- `DescStringID`: current description text or future string table id.
- `TriggerType`: broad trigger category from the sheet.
- `Effects`: backtick-wrapped JSON array of effect objects.
- `RARITY`: `White`, `Blue`, or `Red`.
- `Sprite`: future sprite resource key.

## Current Fantasy Import

Implemented importer:

- Source: `Assets/Data/Raw/Fantasies.tsv`
- Menu: `GoldfishWalking > Data > Import Fantasy TSV`
- Output database: `Assets/Data/Generated/FantasyDatabase.asset`
- Output report: `Assets/Data/Generated/FantasyImportReport.json`

Current behavior:

- Skips rows with neither `DataCode` nor `Effects`.
- Parses `Effects` as a JSON array.
- Preserves raw JSON in `rawEffects`.
- Stores each parsed effect in `FantasyData.effects`.
- Keeps legacy `trigger`, `target`, `value`, and `specialHandler` fields for
  temporary compatibility.
- Malformed `Effects` JSON keeps the fantasy row with `rawEffects` preserved,
  empty `effects`, and an error in the import report.

Current import result:

- Imported fantasies: 60.
- Errors: 0.
- Warnings: 0.
- Skipped rows: 12 rows with missing `DataCode` and missing `Effects`.

`fan_acquire_Candy` was repaired by adding the missing closing `}` / `]` /
backtick to its `Effects` cell:

```json
[{"Trigger":"Acquire", "Target": "HP","Calc":"Add", "Value":"HP*0.1"}]
```

## Monster Pattern Key Rules

Pattern keys can encode common monster behavior. These keys may appear inside
monster `PatternArray` or in dedicated pattern/effect data.

Attack pattern keys:

```text
{DamageDigitCount}_Single
{DamageDigitCount}_Multi_{HitDigitCount}
Str_{Amount}
```

Examples:

- `3_Single`: 3-digit single-hit damage pattern.
- `2_Multi_2`: 2-digit damage with a 2-digit hit-count pattern.
- `Str_1`: monster gains strength +1.

Fallback rule:

- If monster data has no pattern data, or a referenced pattern has no usable
  content, treat it as `2_Single`.

Pattern reference resolution order:

1. Trim surrounding whitespace.
2. Parse exact built-in keys such as `2_Single`, `2_Multi_1`, `Str_1`, and
   `Skip`.
3. Look up custom `Pattern.tsv` rows by exact `DataCode`.
4. If no usable pattern exists, warn in the import report and use `2_Single`.

Do not silently correct typo-like pattern keys in code. The current direction is
that monster and pattern sheets should contain canonical keys directly.

Recommended normalized pattern model:

```text
MonsterPatternDefinition
  id
  displayName
  description
  attackKey
  attackKind
  damageDigitCount
  hitDigitCount
  strengthDelta
  effects[]
  condition
  rawSource
```

`attackKind` should be one of:

- `None`
- `Single`
- `Multi`
- `Strength`
- `Special`

Current runtime `MonsterPatternData` is simpler than this target model. Expand
it before importing the full monster/pattern TSV set.

Current import/runtime note:

- Current Monster TSV import result: 39 monsters, 33 patterns, 0 warnings, 0
  errors.
- Current pattern selection behavior is sequential cycling through each
  monster's `PatternArray`.
- `AIType` is parsed, but runtime random pattern selection is not active.
- Do not add code-side typo correction for pattern keys unless the source data
  intentionally changes again.

## Pattern Effects JSON

Pattern effects are authored as JSON objects. The top-level object determines
the attack shape, effect list, and appearance condition.

Top-level fields:

- `Attack`: physical attack pattern key such as `2_Single` or `2_Multi_1`.
  `null`, empty, or missing means this pattern is a non-attack skill.
- `Effects`: ordered array of effect objects. Multiple effects execute in
  sequence.
- `Condition`: prerequisite expression for the pattern to appear. Until the
  condition is satisfied, the pattern should not be selected.

Effect object fields:

- `Timing`: activation timing. Missing means `Immediate`.
- `Target`: effect target such as `Self`, `Player`, or `ProphecyBox`.
- `Action`: mechanic such as `Split`, `Lock`, `AddBuff`, `Damage`, `Heal`,
  `MultiplyBuff`, `RemoveBuff`, or `SetValue`.
- `Type`: buff/debuff or special state type such as `Strength`, `Stun`,
  `Bleed`, `Poison`, or `FortuneStack`.
- `Value`: numeric value or dynamic expression string.
- `Duration`: turn duration for temporary effects.
- `Lock`: boolean-like flag for lock damage or lock-related damage behavior.

Known pattern effect values from the source sheets:

- `Timing`: `Immediate` when omitted, `NextTurn`.
- `Target`: `Self`, `Player`, `ProphecyBox`.
- `Action`: `Split`, `Lock`, `AddBuff`, `SetBuff`, `Heal`, `Damage`,
  `MultiplyBuff`, `AddStack`, `SetValue`, `RemoveBuff`.
- `Type`: `Strength`, `Stun`, `Bleed`, `Poison`, `FortuneStack`, `BoxLock`,
  `Shield`, and special mechanic-specific values.
- `Lock`: when true on `Damage`, treat the damage as lock-related damage.

Recommended normalized effect model:

```text
PatternEffectDefinition
  timing
  target
  action
  type
  valueExpression
  numericValue
  duration
  lockDamage
  rawJson
```

Keep `valueExpression` even when `numericValue` can be parsed. Dynamic values
need runtime evaluation during battle.

## Fantasy Effects JSON

Fantasy `Effects` is a JSON array. Each entry is an effect object.

Effect object fields:

- `Trigger`: exact timing/event name for the effect.
- `Target`: affected stat/system.
- `Calc`: operation to apply.
- `Value`: numeric value or expression string.
- `Option`: optional string parameter for cosmetic or special handlers.
- `Condition`: optional runtime condition such as `CurrentValue==0` or
  `MonsterBaseDamage>=PlayerBaseDamage`.
- `Chance`: activation probability, written as `0..1` or `0..100`.
- `Lifetime`: `Battle` for temporary battle-only grants; omitted for permanent
  grants.
- `Execution`: `Modifier`, `Action`, or `Capability`. Omitted means the effect
  may participate in the normal action/modifier paths.

Runtime content must not branch on `DataCode`. `DataCode` is identity and save
data only. Mechanics are selected by `Trigger + Target + Calc`, with optional
`Condition`, `Chance`, `Lifetime`, and `Execution`. Changing values, conditions,
divisors, recipes, thresholds, or referenced fantasy IDs therefore requires
only a TSV/JSON edit and reimport.

Examples:

```json
{"Trigger":"Passive","Target":"Attack_Count","Calc":"Add","Value":"ConsumableCount/10","Execution":"Modifier"}
{"Trigger":"","Target":"Base_Damage","Calc":"Multiply","Value":0.5,"Condition":"CurrentValue!=0","Execution":"Modifier"}
{"Trigger":"On_Acquire","Target":"Collection","Calc":"Combine","Option":"id_a,id_b,id_c","Execution":"Capability"}
```

`MonsterRules.tsv` contains identity-independent monster properties that do
not belong to a turn pattern: damage caps, lifesteal, locked base damage,
special-box setup, and countdown outcome. `PatternRules.tsv` contains pattern
metadata that the current sheet JSON did not previously expose: self-destruct,
append-mode special boxes, and editable healing. These tables are keyed by
stable data keys and are imported into generated data; runtime code never
checks monster or pattern names.

Fantasy effect `Trigger` values observed:

- `Passive`
- `Shop_Enter`
- `Battle_Start`
- `Battle_Reward`
- `Acquire_Item`
- `Turn_End`
- `Turn_Even`
- `Take_Damage`
- `Turn_Start`
- `Deal_Damage`
- `On_Acquire`
- `Battle_End`
- `Attack`
- `Shop_Purchase`
- `Turn_1`
- `Use_Item`
- `Turn_4`
- `Rest`
- `Acquire`

Fantasy effect `Target` values observed:

- `Cosmetic`
- `Shop_Movement`
- `HP`
- `Price`
- `fan_shop_stencil`
- `Extra_Match`
- `Eraser`
- `Item_Chance`
- `Item`
- `Damage`
- `Attack_Count`
- `Damage_Taken`
- `Damage_Reflect`
- `Movement`
- `Additional_Damage`
- `Strength`
- `Enemy_Strength`
- `Fantasy`
- `Fantasy_Reroll`
- `Base_Damage`
- `Operator_Box`
- `Value`
- `Item_Cost`
- `Strength_Damage`
- `Change_Fantasy`
- `Rest_Count`

Fantasy effect `Calc` values observed:

- `Add`
- `Multiply`
- `Set`
- `Execute`

Always preserve `Value` as `valueExpression`. Parse and store `numericValue`
additionally only when possible.

## Dynamic Value Expressions

The following keywords may appear in effect `Value` expressions and must be
available from battle runtime state:

- `DamageDealt`: actual damage dealt to the monster by the current attack.
- `DamageTaken`: total damage the monster has taken during this battle.
- `FortuneStack`: fortune-teller style mechanic stack.
- `ProphecyStack`: prophecy mechanic stack.
- `PlayerBleed`: current player bleed amount.
- `PlayerPoison`: current player poison amount.
- `PlayerHP`: current player health.
- `HP`: current player health in fantasy data expressions such as `HP*0.1`.
- `PlayerHP_Multi_2`: table-defined player-health multiplier trigger.
- `Stargazing_Multi_3`: Stargazing mechanic-specific multiplier trigger.

Supported expression direction:

- Fixed integers and floats should parse directly.
- Simple arithmetic strings such as `DamageDealt*0.5`, `PlayerHP*0.3`, or
  `HP*0.1` should be evaluated at runtime as 10% of current HP.
- Special trigger strings such as `PlayerHP_Multi_2` and
  `Stargazing_Multi_3` should resolve through a named formula/effect handler,
  not through generic arithmetic parsing.

Recommended battle runtime state additions:

```text
BattleEffectContext
  damageDealtThisAttack
  monsterDamageTakenThisBattle
  fortuneStack
  prophecyStack
  playerBleed
  playerPoison
  playerCurrentHp
  namedFormulaResolver
```

Condition expressions such as `DamageTaken>=400` should use the same runtime
context and be evaluated before pattern selection.

## Current Data Notes

Monster data distribution:

- 39 monsters total.
- Act 1, Act 2, and Act 3 each have 13 monsters.
- 21 normal monsters, 9 elite monsters, and 9 boss monsters.
- 23 static-AI monsters and 16 random-AI monsters.

Current pattern JSON status:

- 33 pattern rows imported.
- 0 pattern import warnings.
- 0 pattern import errors.

Current fantasy TSV status:

- 68 source rows.
- 60 imported fantasy rows.
- 12 skipped incomplete rows with missing `DataCode` and missing `Effects`.
- `fan_acquire_Candy` fixed and imports without JSON errors.

List fields such as `PatternArray` can use comma, semicolon, or pipe separators:

```text
PATTERN_001,PATTERN_002
PATTERN_001;PATTERN_002
PATTERN_001|PATTERN_002
```
