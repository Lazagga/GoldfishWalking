param(
    [string]$ProjectRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = 'Stop'
$rawRoot = Join-Path $ProjectRoot 'Assets/Data/Raw'
$outputRoot = Join-Path $ProjectRoot 'Assets/Data/Json'

function Read-Tsv([string]$name) {
    $lines = [IO.File]::ReadAllLines((Join-Path $rawRoot $name), [Text.Encoding]::UTF8)
    $firstContentLine = 0
    while ($firstContentLine -lt $lines.Length -and [string]::IsNullOrWhiteSpace(($lines[$firstContentLine] -replace "`t", ''))) {
        $firstContentLine++
    }
    if ($firstContentLine -ge $lines.Length) { return @() }
    return @(($lines[$firstContentLine..($lines.Length - 1)] -join "`n") | ConvertFrom-Csv -Delimiter "`t")
}

function To-FileName([string]$id) {
    $name = $id.Trim().ToLowerInvariant() -replace '[^a-z0-9._-]+', '_'
    return $name.Trim('_') + '.json'
}

function To-Snake([string]$value) {
    if ([string]::IsNullOrWhiteSpace($value)) { return $null }
    $text = $value.Trim() -creplace '([a-z0-9])([A-Z])', '$1_$2'
    return ($text -replace '[^A-Za-z0-9]+', '_').Trim('_').ToLowerInvariant()
}

function As-Int($value, [int]$fallback = 0) {
    $parsed = 0
    if ([int]::TryParse(([string]$value).Trim(), [ref]$parsed)) { return $parsed }
    return $fallback
}

function As-Double($value, [double]$fallback = 0) {
    $parsed = 0.0
    if ([double]::TryParse(([string]$value).Trim(), [Globalization.NumberStyles]::Float, [Globalization.CultureInfo]::InvariantCulture, [ref]$parsed)) { return $parsed }
    return $fallback
}

function As-Bool($value) {
    return ([string]$value).Trim().Equals('true', [StringComparison]::OrdinalIgnoreCase)
}

function As-NullableInt($value) {
    if ([string]::IsNullOrWhiteSpace([string]$value)) { return $null }
    return As-Int $value
}

function Split-Ids($value) {
    if ([string]::IsNullOrWhiteSpace([string]$value)) { return @() }
    return @(($value -split '[,;|]') | ForEach-Object { $_.Trim() } | Where-Object { $_ })
}

function Write-Json([string]$path, $value) {
    $json = $value | ConvertTo-Json -Depth 40
    [IO.File]::WriteAllText($path, $json + "`n", [Text.UTF8Encoding]::new($false))
}

function Convert-Scalar($value) {
    if ($null -eq $value) { return $null }
    if ($value -is [int] -or $value -is [long] -or $value -is [double] -or $value -is [decimal] -or $value -is [bool]) { return $value }
    $text = ([string]$value).Trim()
    $number = 0.0
    if ([double]::TryParse($text, [Globalization.NumberStyles]::Float, [Globalization.CultureInfo]::InvariantCulture, [ref]$number)) {
        if ($number -eq [math]::Truncate($number)) { return [int]$number }
        return $number
    }
    return $text
}

function Convert-Condition($condition) {
    if ($null -eq $condition -or [string]::IsNullOrWhiteSpace([string]$condition)) { return $null }
    $text = ([string]$condition).Trim()
    if ($text -match '^\s*([A-Za-z_][A-Za-z0-9_.]*)\s*(>=|<=|==|!=|>|<)\s*(-?\d+(?:\.\d+)?|[A-Za-z_][A-Za-z0-9_.]*)\s*$') {
        $right = Convert-Scalar $Matches[3]
        if ($right -is [string]) { $right = [ordered]@{ variable = To-Snake $right } }
        return [ordered]@{
            comparison = [ordered]@{
                left = [ordered]@{ variable = To-Snake $Matches[1] }
                operator = $Matches[2]
                right = $right
            }
        }
    }
    return [ordered]@{ expression = $text }
}

function Convert-Value($value) {
    if ($null -eq $value) { return $null }
    if ($value -isnot [string]) { return $value }
    $text = $value.Trim()
    $scalar = Convert-Scalar $text
    if ($scalar -isnot [string]) { return $scalar }
    return [ordered]@{ expression = $text }
}

function Convert-Target([string]$target) {
    $key = To-Snake $target
    if (-not $key) { return $null }
    switch ($key) {
        'self' { return [ordered]@{ actor = 'self' } }
        'player' { return [ordered]@{ actor = 'player' } }
        'monster' { return [ordered]@{ actor = 'monster' } }
        'hp' { return [ordered]@{ actor = 'player'; stat = 'health' } }
        'strength' { return [ordered]@{ actor = 'player'; stat = 'strength' } }
        'enemy_strength' { return [ordered]@{ actor = 'monster'; stat = 'strength' } }
        'base_damage' { return [ordered]@{ formula = 'player.damage'; box = 'base' } }
        'attack_count' { return [ordered]@{ formula = 'player.hits' } }
        'damage_taken' { return [ordered]@{ value = 'incoming_damage' } }
        'damage_reflect' { return [ordered]@{ actor = 'attacker' } }
        'additional_damage' { return [ordered]@{ actor = 'monster' } }
        'shop_movement' { return [ordered]@{ system = 'shop'; property = 'movement_limit' } }
        'price' { return [ordered]@{ system = 'shop'; property = 'price' } }
        'item_chance' { return [ordered]@{ system = 'reward'; property = 'item_chance' } }
        'fantasy_reroll' { return [ordered]@{ system = 'reward'; property = 'fantasy_rerolls' } }
        'rest_count' { return [ordered]@{ system = 'rest'; property = 'use_count' } }
        'movement' { return [ordered]@{ system = 'battle'; property = 'movement_limit' } }
        'prophecy_box' { return [ordered]@{ formula = 'monster.special'; box = 'prophecy' } }
        default { return [ordered]@{ key = $key } }
    }
}

function Convert-Effect($effect, [bool]$fantasyEffect) {
    $triggerText = if ($fantasyEffect) { $effect.Trigger } else { $effect.Timing }
    if ([string]::IsNullOrWhiteSpace([string]$triggerText)) { $triggerText = if ($fantasyEffect) { 'Passive' } else { 'Immediate' } }
    $action = if ($fantasyEffect) { $effect.Calc } else { $effect.Action }
    $type = To-Snake $effect.Type
    $operation = To-Snake $action

    if ($fantasyEffect) {
        switch ($operation) {
            'add' { $operation = 'modify_value' }
            'multiply' { $operation = 'modify_value' }
            'set' { $operation = 'set_value' }
            'execute' { $operation = if ($type) { $type } else { 'execute_capability' } }
            'combine' { $operation = 'combine_fantasies' }
            'transform' { $operation = 'transform_value' }
            'split' { $operation = 'split_box' }
        }
    } else {
        switch ($operation) {
            'add_buff' { $operation = if ($type) { 'add_status' } else { 'modify_stat' } }
            'addbuff' { $operation = if ($type) { 'add_status' } else { 'modify_stat' } }
            'set_buff' { $operation = if ($type) { 'set_status' } else { 'set_stat' } }
            'remove_buff' { $operation = 'remove_status' }
            'add_stack' { $operation = 'add_stack' }
            'multiply_buff' { $operation = 'multiply_stat' }
            'damage' { $operation = 'deal_damage' }
            'split' { $operation = 'split_box' }
            'lock' { $operation = 'lock_box' }
            'set_value' { $operation = 'set_formula_value' }
            'add_box' { $operation = 'create_formula_box' }
        }
    }

    $target = Convert-Target ([string]$effect.Target)
    if ($null -eq $target) {
        $target = if ($fantasyEffect) { [ordered]@{ context = 'current' } } else { [ordered]@{ actor = 'self' } }
    }
    $result = [ordered]@{
        trigger = [ordered]@{ event = To-Snake $triggerText }
        target = $target
        operation = $operation
    }
    if ($type) { $result.type = $type }
    if ($fantasyEffect -and $action) { $result.mode = To-Snake ([string]$action) }
    if ($null -ne $effect.Value -and -not [string]::IsNullOrWhiteSpace([string]$effect.Value)) { $result.amount = Convert-Value $effect.Value }
    if ($effect.Condition) { $result.condition = Convert-Condition $effect.Condition }
    if ($effect.Chance) {
        $chance = As-Double $effect.Chance 1
        $result.chance = [ordered]@{ percent = if ($chance -le 1) { [math]::Round($chance * 100, 4) } else { $chance } }
    }
    if ($effect.Duration -and (As-Int $effect.Duration) -gt 0) { $result.duration = [ordered]@{ turns = As-Int $effect.Duration; decreaseAt = 'turn_end' } }
    if ($effect.Lifetime) { $result.lifetime = To-Snake $effect.Lifetime }
    if ($effect.Execution) { $result.execution = To-Snake $effect.Execution }
    if ($effect.Count -and (As-Int $effect.Count 1) -ne 1) { $result.repeat = As-Int $effect.Count 1 }
    if ($effect.HitCount -and (As-Int $effect.HitCount 1) -ne 1) { $result.hitCount = As-Int $effect.HitCount 1 }
    if (As-Bool $effect.Lock) { $result.lockDamage = $true }
    if ($effect.Mode) { $result.presentationMode = To-Snake $effect.Mode }
    if ($effect.Label) { $result.label = [string]$effect.Label }
    if ($null -ne $effect.Editable) { $result.editable = [bool]$effect.Editable }
    if ($effect.Option -and -not [string]::IsNullOrWhiteSpace([string]$effect.Option)) {
        $options = Split-Ids $effect.Option
        $result.options = if ($options.Count -gt 1) { $options } else { [string]$effect.Option }
    }
    return $result
}

function Convert-Attack($attack) {
    if ($null -eq $attack -or [string]::IsNullOrWhiteSpace([string]$attack) -or ([string]$attack) -eq 'Skip') { return $null }
    $key = ([string]$attack).Trim()
    if ($key -match '^(\d+)_Single$') {
        return [ordered]@{ damage = [ordered]@{ digits = [int]$Matches[1]; editable = $true }; hits = [ordered]@{ fixed = 1 } }
    }
    if ($key -match '^(\d+)_Multi(?:_(\d+))?$') {
        $hitDigits = if ($Matches[2]) { [int]$Matches[2] } else { 1 }
        return [ordered]@{ damage = [ordered]@{ digits = [int]$Matches[1]; editable = $true }; hits = [ordered]@{ digits = $hitDigits; editable = $true; minimum = 0 } }
    }
    if ($key -match '^Str_(-?\d+)$') {
        return [ordered]@{ nonDamageAction = [ordered]@{ operation = 'modify_stat'; target = [ordered]@{ actor = 'self'; stat = 'strength' }; amount = [int]$Matches[1] } }
    }
    if ($key -match '^([A-Za-z][A-Za-z0-9_]*)_Single$') {
        return [ordered]@{ damage = [ordered]@{ digits = 1; editable = $true; initialValue = [ordered]@{ expression = $Matches[1] } }; hits = [ordered]@{ fixed = 1 } }
    }
    return [ordered]@{ formulaKey = $key }
}

function New-Directories {
    foreach ($name in @('monsters', 'patterns', 'fantasies', 'schemas')) {
        $path = Join-Path $outputRoot $name
        [IO.Directory]::CreateDirectory($path) | Out-Null
        Get-ChildItem -LiteralPath $path -Filter '*.json' -File | Remove-Item -Force
    }
}

New-Directories

$monsterRules = @{}
foreach ($row in Read-Tsv 'MonsterRules.tsv') { if ($row.DataName) { $monsterRules[$row.DataName.Trim()] = $row } }
$patternRules = @{}
foreach ($row in Read-Tsv 'PatternRules.tsv') { if ($row.DataCode) { $patternRules[$row.DataCode.Trim()] = $row } }

$monsterIds = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$patternIds = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$fantasyIds = [Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
$patternReferences = [Collections.Generic.List[object]]::new()

foreach ($row in Read-Tsv 'Monster.tsv') {
    $id = ([string]$row.DataName).Trim()
    if (-not $id) { continue }
    [void]$monsterIds.Add($id)
    $patterns = @(Split-Ids $row.PatternArray)
    foreach ($pattern in $patterns) { $patternReferences.Add([ordered]@{ monster = $id; pattern = $pattern }) }
    $passives = [Collections.Generic.List[object]]::new()
    $rule = $monsterRules[$id]
    if ($rule) {
        $cap = As-Int $rule.DamageCap
        if ($cap -gt 0) {
            $passive = [ordered]@{ operation = 'limit_incoming_damage'; maximum = $cap }
            $breakValue = As-Int $rule.DamageCapBreak
            if ($breakValue -gt 0) { $passive.until = Convert-Condition "monster.damage_taken_this_battle>=$breakValue" }
            $passives.Add($passive)
        }
        $lifesteal = As-Double $rule.Lifesteal
        if ($lifesteal -gt 0) { $passives.Add([ordered]@{ operation = 'lifesteal'; trigger = 'after_dealing_damage'; ratio = $lifesteal }) }
        if (As-Bool $rule.BaseDamageLocked) { $passives.Add([ordered]@{ operation = 'lock_box'; target = [ordered]@{ formula = 'monster.damage'; box = 'base' } }) }
        if ($rule.AimedShotMultiplier -and (As-Double $rule.AimedShotMultiplier) -ne 0) { $passives.Add([ordered]@{ operation = 'aimed_shot'; multiplier = As-Double $rule.AimedShotMultiplier }) }
        if ($rule.FormulaDecoyDigitCount -and (As-Int $rule.FormulaDecoyDigitCount) -gt 0) { $passives.Add([ordered]@{ operation = 'add_formula_decoy_digits'; count = As-Int $rule.FormulaDecoyDigitCount }) }
        if ($rule.PlayerAttackCondition) {
            $conditionJson = ([string]$rule.PlayerAttackCondition).Trim().Trim('`')
            $conditionData = $conditionJson | ConvertFrom-Json
            $passives.Add([ordered]@{ operation = 'require_formula_condition'; configuration = $conditionData })
        }
        if ($rule.SpecialBoxLabel -or $rule.CountdownAction) {
            $box = [ordered]@{ label = [string]$rule.SpecialBoxLabel; minimum = As-Int $rule.SpecialBoxMin; maximum = As-Int $rule.SpecialBoxMax; initialValue = As-Int $rule.SpecialBoxValue; editable = $true }
            if ($rule.CountdownAction) {
                $onZero = if ($rule.CountdownAction -eq 'Pattern') { [ordered]@{ operation = 'execute_pattern'; pattern = [string]$rule.CountdownPattern } } else { [ordered]@{ operation = 'end_battle'; result = To-Snake $rule.CountdownAction } }
                $passives.Add([ordered]@{ operation = 'countdown'; box = $box; decrease = [ordered]@{ trigger = 'turn_end'; amount = 1 }; onZero = $onZero })
            } else { $passives.Add([ordered]@{ operation = 'create_special_box'; box = $box }) }
        }
    }
    $monster = [ordered]@{
        schemaVersion = 1
        id = $id
        sourceId = As-Int $row.ID
        designerName = [string]$row.DevName
        designerNote = ''
        enabled = $true
        localization = [ordered]@{ name = [string]$row.NameStringID; description = [string]$row.DescStringID }
        presentation = [ordered]@{ sprite = [string]$row.Sprite }
        encounter = [ordered]@{ act = As-Int $row.Act; grade = To-Snake $row.Type; difficulty = To-Snake $row.Difficulty }
        stats = [ordered]@{ health = As-Int $row.BaseHP; strength = As-Int $row.BaseStrength }
        ai = [ordered]@{ mode = To-Snake $row.AIType; patterns = $patterns }
        passives = @($passives)
    }
    Write-Json (Join-Path $outputRoot ('monsters/' + (To-FileName $id))) $monster
}

foreach ($row in Read-Tsv 'Pattern.tsv') {
    $id = ([string]$row.DataCode).Trim()
    if (-not $id) { continue }
    [void]$patternIds.Add($id)
    $raw = ([string]$row.Effects).Trim().Trim('`')
    $definition = if ($raw) { $raw | ConvertFrom-Json } else { [pscustomobject]@{} }
    $effects = @()
    $sourceEffects = if ($null -ne $definition.Effects) { @($definition.Effects) } elseif ($null -ne $definition.Effect) { @($definition.Effect) } else { @() }
    foreach ($effect in $sourceEffects) { if ($null -ne $effect) { $effects += ,(Convert-Effect $effect $false) } }
    $rule = $patternRules[$id]
    $metadata = [ordered]@{}
    if ($rule) {
        if (As-Bool $rule.SelfDestruct) { $metadata.selfDestruct = $true }
        if ($rule.AddBoxMode) { $metadata.specialBoxMode = To-Snake $rule.AddBoxMode }
        if ($null -ne $rule.EditableHeal -and -not [string]::IsNullOrWhiteSpace([string]$rule.EditableHeal)) { $metadata.editableHeal = As-Bool $rule.EditableHeal }
    }
    $condition = if ($definition.Condition) { Convert-Condition $definition.Condition } elseif ($rule -and $rule.Condition) { Convert-Condition $rule.Condition } else { $null }
    $maxUses = if ($null -ne $definition.Count) { As-Int $definition.Count } else { $null }
    $pattern = [ordered]@{
        schemaVersion = 1
        id = $id
        sourceId = As-NullableInt $row.ID
        designerName = [string]$row.DevName
        designerNote = [string]$row.PSObject.Properties.Value[-1]
        enabled = $true
        localization = [ordered]@{ name = [string]$row.NameStringID }
        presentation = [ordered]@{ sprite = [string]$row.SpriteRes }
        availability = [ordered]@{ maxUsesPerBattle = $maxUses; condition = $condition }
        attack = Convert-Attack $definition.Attack
        effects = $effects
        metadata = $metadata
    }
    Write-Json (Join-Path $outputRoot ('patterns/' + (To-FileName $id))) $pattern
}

foreach ($row in Read-Tsv 'Fantasies.tsv') {
    $id = ([string]$row.DataCode).Trim()
    $raw = ([string]$row.Effects).Trim().Trim('`')
    if (-not $id -and -not $raw) { continue }
    if (-not $id) { throw "Fantasy row '$($row.ID)' has effects but no DataCode." }
    [void]$fantasyIds.Add($id)
    $sourceEffects = if ($raw) { @($raw | ConvertFrom-Json) } else { @() }
    $effects = @()
    foreach ($effect in $sourceEffects) { $effects += ,(Convert-Effect $effect $true) }
    $fantasy = [ordered]@{
        schemaVersion = 1
        id = $id
        sourceId = As-Int $row.ID
        designerName = [string]$row.DevName
        designerNote = [string]$row.DescStringID
        enabled = $true
        localization = [ordered]@{ name = [string]$row.NameStringID; description = '' }
        presentation = [ordered]@{ sprite = [string]$row.Sprite }
        rarity = To-Snake $row.RARITY
        tags = @((To-Snake $row.TriggerType) | Where-Object { $_ })
        effects = $effects
    }
    Write-Json (Join-Path $outputRoot ('fantasies/' + (To-FileName $id))) $fantasy
}

$effectSchema = [ordered]@{
    '$schema' = 'https://json-schema.org/draft/2020-12/schema'
    '$id' = 'effect.schema.json'
    title = 'GoldfishWalking Effect'
    type = 'object'
    required = @('target', 'operation')
    properties = [ordered]@{
        designerNote = [ordered]@{ type = 'string' }
        trigger = [ordered]@{ type = 'object'; required = @('event'); properties = [ordered]@{ event = [ordered]@{ type = 'string'; minLength = 1 } } }
        target = [ordered]@{ type = 'object'; minProperties = 1 }
        operation = [ordered]@{ type = 'string'; minLength = 1 }
        condition = [ordered]@{ type = @('object', 'null') }
        amount = [ordered]@{}
        duration = [ordered]@{ type = 'object' }
        chance = [ordered]@{ type = 'object'; properties = [ordered]@{ percent = [ordered]@{ type = 'number'; minimum = 0; maximum = 100 } } }
    }
    additionalProperties = $true
}

function New-EntitySchema([string]$title, [string[]]$required, $extraProperties) {
    $properties = [ordered]@{
        schemaVersion = [ordered]@{ const = 1 }
        id = [ordered]@{ type = 'string'; pattern = '^[A-Za-z0-9_.-]+$' }
        designerName = [ordered]@{ type = 'string' }
        designerNote = [ordered]@{ type = 'string' }
        enabled = [ordered]@{ type = 'boolean' }
    }
    foreach ($property in $extraProperties.GetEnumerator()) { $properties[$property.Key] = $property.Value }
    return [ordered]@{ '$schema' = 'https://json-schema.org/draft/2020-12/schema'; title = $title; type = 'object'; required = $required; properties = $properties; additionalProperties = $false }
}

$monsterSchema = New-EntitySchema 'GoldfishWalking Monster' @('schemaVersion','id','stats','ai') ([ordered]@{
    sourceId = [ordered]@{ type = 'integer' }; localization = [ordered]@{ type = 'object' }; presentation = [ordered]@{ type = 'object' }; encounter = [ordered]@{ type = 'object' }
    stats = [ordered]@{ type = 'object'; required = @('health','strength'); properties = [ordered]@{ health = [ordered]@{ type = 'integer'; minimum = 1 }; strength = [ordered]@{ type = 'integer' } } }
    ai = [ordered]@{ type = 'object'; required = @('mode','patterns'); properties = [ordered]@{ mode = [ordered]@{ enum = @('static','random') }; patterns = [ordered]@{ type = 'array'; items = [ordered]@{ type = 'string' } } } }
    passives = [ordered]@{ type = 'array'; items = [ordered]@{ type = 'object'; required = @('operation') } }
})
$patternSchema = New-EntitySchema 'GoldfishWalking Pattern' @('schemaVersion','id','availability','effects') ([ordered]@{
    sourceId = [ordered]@{ type = @('integer','null') }; localization = [ordered]@{ type = 'object' }; presentation = [ordered]@{ type = 'object' }
    availability = [ordered]@{ type = 'object' }; attack = [ordered]@{ type = @('object','null') }; effects = [ordered]@{ type = 'array'; items = [ordered]@{ type = 'object'; required = @('target','operation') } }; metadata = [ordered]@{ type = 'object' }
})
$fantasySchema = New-EntitySchema 'GoldfishWalking Fantasy' @('schemaVersion','id','rarity','effects') ([ordered]@{
    sourceId = [ordered]@{ type = 'integer' }; localization = [ordered]@{ type = 'object' }; presentation = [ordered]@{ type = 'object' }
    rarity = [ordered]@{ enum = @('white','blue','red') }; tags = [ordered]@{ type = 'array'; items = [ordered]@{ type = 'string' } }; effects = [ordered]@{ type = 'array'; items = [ordered]@{ type = 'object'; required = @('target','operation') } }
})

Write-Json (Join-Path $outputRoot 'schemas/effect.schema.json') $effectSchema
Write-Json (Join-Path $outputRoot 'schemas/monster.schema.json') $monsterSchema
Write-Json (Join-Path $outputRoot 'schemas/pattern.schema.json') $patternSchema
Write-Json (Join-Path $outputRoot 'schemas/fantasy.schema.json') $fantasySchema

$builtIns = @('Skip')
$missingReferences = @($patternReferences | Where-Object { -not $patternIds.Contains($_.pattern) -and $_.pattern -notmatch '^\d+_(Single|Multi(?:_\d+)?)$' -and $_.pattern -notmatch '^Str_-?\d+$' -and $_.pattern -notin $builtIns })
$manifest = [ordered]@{
    schemaVersion = 1
    generatedFrom = 'Assets/Data/Raw/*.tsv'
    generatedAtUtc = [DateTime]::UtcNow.ToString('o')
    counts = [ordered]@{ monsters = $monsterIds.Count; patterns = $patternIds.Count; fantasies = $fantasyIds.Count }
    validation = [ordered]@{ missingPatternReferences = $missingReferences }
}
Write-Json (Join-Path $outputRoot 'manifest.json') $manifest

Write-Output "Generated $($monsterIds.Count) monsters, $($patternIds.Count) patterns, and $($fantasyIds.Count) fantasies in $outputRoot."
if ($missingReferences.Count -gt 0) { throw "Missing pattern references were found. See manifest.json." }
