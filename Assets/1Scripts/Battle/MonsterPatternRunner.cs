using System;
using System.Collections.Generic;
using GoldfishWalking.Data;
using GoldfishWalking.Core;
using GoldfishWalking.Formula;
using UnityEngine;

namespace GoldfishWalking.Battle
{
    public sealed class MonsterPatternRunner
    {
        private const string FallbackPatternKey = "2_Single";
        private readonly FormulaStructuralEffectExecutor structuralEffects = new FormulaStructuralEffectExecutor();
        private readonly MonsterEffectExpressionEvaluator effectValues = new MonsterEffectExpressionEvaluator();

        public MonsterPatternData SelectPattern(MonsterRuntime monster, MonsterPatternDatabase database, RunContext runContext)
        {
            if (monster == null || monster.Data == null)
                return MonsterPatternKeyUtility.CreateFromKey(FallbackPatternKey);

            int turn = runContext != null ? Math.Max(1, runContext.battleTurnNumber) : 1;
            if (monster.SelectedPatternTurn == turn && monster.SelectedPattern != null)
                return monster.SelectedPattern;

            string[] patternIds = monster.Data.patternIds;
            if (patternIds == null || patternIds.Length == 0)
                return MonsterPatternKeyUtility.CreateFromKey(FallbackPatternKey);

            List<MonsterPatternData> patterns = new List<MonsterPatternData>();
            for (int i = 0; i < patternIds.Length; i++)
                patterns.Add(ResolvePattern(database, patternIds[i]));

            if (patterns.Count == 0)
                return MonsterPatternKeyUtility.CreateFromKey(FallbackPatternKey);

            if (monster.Data.aiType == MonsterAiType.Random)
            {
                List<MonsterPatternData> candidates = new List<MonsterPatternData>();
                for (int i = 0; i < patterns.Count; i++)
                {
                    MonsterPatternData candidate = patterns[i];
                    if (monster.CanUsePattern(candidate) && effectValues.EvaluateCondition(candidate.condition, monster, runContext))
                        candidates.Add(candidate);
                }

                if (candidates.Count > 0)
                {
                    int index = runContext != null
                        ? runContext.RollValue($"monster.pattern.random.{monster.Data.id}.turn.{turn}", 0, candidates.Count - 1)
                        : 0;
                    MonsterPatternData selected = candidates[Mathf.Clamp(index, 0, candidates.Count - 1)];
                    monster.SelectPatternForTurn(selected, turn);
                    return selected;
                }
            }

            int startIndex = Math.Max(0, turn - 1) % patterns.Count;
            for (int offset = 0; offset < patterns.Count; offset++)
            {
                MonsterPatternData candidate = patterns[(startIndex + offset) % patterns.Count];
                if (!monster.CanUsePattern(candidate) || !effectValues.EvaluateCondition(candidate.condition, monster, runContext))
                    continue;

                monster.SelectPatternForTurn(candidate, turn);
                return candidate;
            }

            return MonsterPatternKeyUtility.CreateFromKey(FallbackPatternKey);
        }

        public MonsterPatternData ResolvePattern(MonsterPatternDatabase database, string patternKey)
        {
            string normalized = MonsterPatternKeyUtility.NormalizePatternKey(patternKey);
            if (string.IsNullOrWhiteSpace(normalized))
                normalized = FallbackPatternKey;

            MonsterPatternData builtIn = MonsterPatternKeyUtility.CreateFromKey(normalized);
            if (builtIn.patternType != MonsterPatternType.Special)
                return builtIn;

            MonsterPatternData found = FindPattern(database, normalized);
            if (found == null)
                return MonsterPatternKeyUtility.CreateFromKey(FallbackPatternKey);

            if (!string.IsNullOrWhiteSpace(found.attackKey))
                MonsterPatternKeyUtility.ApplyPatternKey(found, found.attackKey);
            else
                MonsterPatternKeyUtility.ApplyPatternKey(found, string.Empty);

            return found;
        }

        public bool IsAttackPattern(MonsterPatternData pattern)
        {
            return pattern != null && (pattern.patternType == MonsterPatternType.SingleHit || pattern.patternType == MonsterPatternType.MultiHit);
        }

        public bool CanMonsterAct(MonsterRuntime monster)
        {
            return monster == null || !monster.IsStunned;
        }

        public bool TryGetEditableHealDigitCount(
            MonsterPatternData pattern,
            MonsterRuntime monster,
            RunContext runContext,
            out int digitCount)
        {
            digitCount = 0;
            if (pattern == null || pattern.effects == null || !UsesEditableHealBox(pattern))
                return false;

            for (int i = 0; i < pattern.effects.Length; i++)
            {
                MonsterPatternEffectData effect = pattern.effects[i];
                if (effect == null
                    || ResolveAction(effect) != "heal"
                    || NormalizeLookup(effect.target) == "player")
                    continue;

                digitCount = Mathf.Max(1, Mathf.FloorToInt(effectValues.EvaluateValue(effect.valueExpression, monster, runContext, 0)));
                return true;
            }

            return false;
        }

        public int ResolveDamage(MonsterRuntime monster, MonsterPatternData pattern)
        {
            if (monster == null || pattern == null)
                return 0;

            switch (pattern.patternType)
            {
                case MonsterPatternType.MultiHit:
                    return pattern.value * pattern.hitCount;
                case MonsterPatternType.StrengthUp:
                    monster.ChangeStrength(pattern.strengthDelta != 0 ? pattern.strengthDelta : pattern.value);
                    return 0;
                case MonsterPatternType.StrengthDown:
                    monster.ChangeStrength(pattern.strengthDelta != 0 ? pattern.strengthDelta : -pattern.value);
                    return 0;
                case MonsterPatternType.Heal:
                    monster.Heal(pattern.value);
                    return 0;
                case MonsterPatternType.None:
                    return 0;
                case MonsterPatternType.SingleHit:
                default:
                    return pattern.value;
            }
        }

        public int EvaluateValueExpression(string expression, MonsterRuntime monster, RunContext runContext)
        {
            return Mathf.FloorToInt(effectValues.EvaluateValue(expression, monster, runContext, 0));
        }

        public void ApplyImmediateNonAttack(MonsterRuntime monster, MonsterPatternData pattern)
        {
            if (monster == null || pattern == null)
                return;

            switch (pattern.patternType)
            {
                case MonsterPatternType.StrengthUp:
                    monster.ChangeStrength(pattern.strengthDelta != 0 ? pattern.strengthDelta : pattern.value);
                    break;
                case MonsterPatternType.StrengthDown:
                    monster.ChangeStrength(pattern.strengthDelta != 0 ? pattern.strengthDelta : -pattern.value);
                    break;
                case MonsterPatternType.Heal:
                    monster.Heal(pattern.value);
                    break;
            }
        }

        public void ApplyPatternEffects(
            MonsterRuntime monster,
            RunContext runContext,
            MonsterPatternData pattern,
            BattleFormulaState playerFormula,
            BattleFormulaState monsterFormula,
            string timing,
            int damageDealt,
            int editableHealValue = -1)
        {
            if (monster == null || pattern == null || pattern.effects == null)
                return;

            string normalizedTiming = NormalizeTiming(timing);
            for (int i = 0; i < pattern.effects.Length; i++)
            {
                MonsterPatternEffectData effect = pattern.effects[i];
                if (effect == null)
                    continue;

                string effectTiming = NormalizeTiming(effect.timing);
                if (effectTiming != normalizedTiming && !(normalizedTiming == "immediate" && effectTiming == "nextturn"))
                    continue;

                if (!effectValues.EvaluateCondition(effect.condition, monster, runContext))
                    continue;

                if (effectTiming == "nextturn")
                {
                    monster.ScheduledEffects.Add(new ScheduledMonsterPatternEffect
                    {
                        effect = effect,
                        triggerTurn = runContext != null ? Mathf.Max(1, runContext.battleTurnNumber) + 1 : 1
                    });
                    continue;
                }

                ApplyEffect(monster, runContext, effect, playerFormula, monsterFormula, damageDealt, editableHealValue);
            }
        }

        public void ApplyScheduledEffects(
            MonsterRuntime monster,
            RunContext runContext,
            BattleFormulaState playerFormula,
            BattleFormulaState monsterFormula)
        {
            if (monster == null || monster.ScheduledEffects.Count == 0)
                return;

            int turn = runContext != null ? Mathf.Max(1, runContext.battleTurnNumber) : 1;
            for (int i = monster.ScheduledEffects.Count - 1; i >= 0; i--)
            {
                ScheduledMonsterPatternEffect scheduled = monster.ScheduledEffects[i];
                if (scheduled == null || scheduled.effect == null || scheduled.triggerTurn > turn)
                    continue;

                ApplyEffect(monster, runContext, scheduled.effect, playerFormula, monsterFormula, 0, -1);
                monster.ScheduledEffects.RemoveAt(i);
            }
        }

        public void AdvanceTurnDurations(MonsterRuntime monster)
        {
            monster?.AdvanceTurnDurations();
        }

        private static MonsterPatternData FindPattern(MonsterPatternDatabase database, string normalizedKey)
        {
            if (database == null || database.patterns == null)
                return null;

            string normalizedLookup = NormalizeLookup(normalizedKey);
            for (int i = 0; i < database.patterns.Count; i++)
            {
                MonsterPatternData pattern = database.patterns[i];
                if (pattern == null)
                    continue;

                if (NormalizeLookup(pattern.id) == normalizedLookup || NormalizeLookup(pattern.dataCode) == normalizedLookup)
                    return pattern;
            }

            return null;
        }

        private void ApplyEffect(
            MonsterRuntime monster,
            RunContext runContext,
            MonsterPatternEffectData effect,
            BattleFormulaState playerFormula,
            BattleFormulaState monsterFormula,
            int damageDealt,
            int editableHealValue)
        {
            string action = ResolveAction(effect);
            string type = NormalizeLookup(effect.type);
            string target = NormalizeLookup(effect.target);
            int value = Mathf.FloorToInt(effectValues.EvaluateValue(effect.valueExpression, monster, runContext, damageDealt));
            if (string.IsNullOrWhiteSpace(effect.valueExpression) && effect.duration > 0)
                value = effect.duration;
            if (action == "addbox")
                value = BuildSpecialBoxValue(effect.valueExpression, effect.count, runContext);

            if (action == "split")
            {
                structuralEffects.SetSplit(target, playerFormula, monsterFormula);
                return;
            }

            if (action == "lock")
            {
                structuralEffects.SetLocked(target, playerFormula, monsterFormula);
                return;
            }

            if (action == "heal")
            {
                if (editableHealValue >= 0 && target != "player")
                    value = editableHealValue;

                if (target == "player")
                    runContext.health += Mathf.Max(0, value);
                else
                    monster.Heal(Mathf.Max(0, value));
                return;
            }

            if (action == "damage")
            {
                if (NormalizeLookup(effect.valueExpression) == "playerformularandomnumber")
                    value = SelectPlayerFormulaNumber(playerFormula, runContext);

                if (target == "self")
                    monster.ApplyDamage(value);
                else
                {
                    for (int hitIndex = 0; hitIndex < Mathf.Max(1, effect.hitCount); hitIndex++)
                        ApplyMonsterDamageToPlayer(monster, runContext, value);
                }
                return;
            }

            if (action == "addstack")
            {
                ApplyStack(monster, runContext, target, value, set: false);
                return;
            }

            if (action == "setvalue")
            {
                ApplyStack(monster, runContext, target, value, set: true);
                return;
            }

            if (action == "addbox")
            {
                if (NormalizeLookup(effect.mode) == "append" && effect.count == 1)
                    monster.AppendSpecialBoxDigit(value, effect.label);
                else
                    monster.SetSpecialBox(value, effect.count, effect.label);
                return;
            }

            if (action == "clearbox")
            {
                monster.ClearSpecialBox();
                return;
            }

            if (action == "removebuff")
            {
                SetBuff(monster, runContext, type, 0);
                if (type == "shield")
                    monster.ClearDamageCap();
                return;
            }
            if (action == "addbuff")
            {
                if (type == "minusbox" || type == "dividebox")
                {
                    AddPlayerDebuffBox(runContext, type, Mathf.Max(1, value), effect.duration);
                    return;
                }
                if (type == "boxlock")
                {
                    structuralEffects.LockLeadingDigits(target, playerFormula, monsterFormula, Mathf.Max(1, value));
                    return;
                }

                AddBuff(monster, runContext, type, value);
                return;
            }

            if (action == "setbuff")
            {
                SetBuff(monster, runContext, type, value);
                return;
            }

            if (action == "multiplybuff")
                MultiplyBuff(monster, runContext, type, value);
        }

        private static void AddBuff(MonsterRuntime monster, RunContext runContext, string type, int value)
        {
            switch (type)
            {
                case "strength":
                    monster.ChangeStrength(value);
                    break;
                case "stun":
                    monster.ChangeStun(value);
                    break;
                case "shield":
                    monster.ChangeShield(value);
                    break;
                case "fortunestack":
                    monster.ChangeFortuneStack(value);
                    break;
                case "prophecystack":
                case "prophetstack":
                    monster.ChangeProphecyStack(value);
                    if (runContext != null)
                        runContext.prophecyStack = monster.ProphecyStack;
                    break;
                case "bleed":
                    if (runContext != null)
                        runContext.pendingPlayerBleed = Mathf.Max(0, runContext.pendingPlayerBleed + value);
                    break;
                case "poison":
                    if (runContext != null)
                        runContext.pendingPlayerPoison = Mathf.Max(0, runContext.pendingPlayerPoison + value);
                    break;
                case "minusbox":
                    if (runContext != null)
                        runContext.strength -= Mathf.Max(0, value);
                    break;
                case "phase2":
                    monster.SetPhase(2);
                    break;
            }
        }

        private static void ApplyMonsterDamageToPlayer(MonsterRuntime monster, RunContext runContext, int damage)
        {
            if (runContext == null)
                return;

            int actualDamage = Mathf.Max(0, damage);
            runContext.health -= actualDamage;
            runContext.lastDamageTaken = actualDamage;
            runContext.battleDamageTaken += actualDamage;
            runContext.AddPlayerDamageDebug("Pattern Damage", actualDamage);

        }

        private static int SelectPlayerFormulaNumber(BattleFormulaState playerFormula, RunContext runContext)
        {
            List<int> numbers = new List<int>();
            AddFormulaNumbers(playerFormula != null ? playerFormula.damageExpression : null, numbers);
            AddFormulaNumbers(playerFormula != null ? playerFormula.hitCountExpression : null, numbers);
            if (numbers.Count == 0)
                return 0;

            int index = runContext != null
                ? runContext.RollValue($"monster.librarian.pick.{runContext.battleTurnNumber}", 0, numbers.Count - 1)
                : 0;
            return Mathf.Max(0, numbers[Mathf.Clamp(index, 0, numbers.Count - 1)]);
        }

        private static void AddFormulaNumbers(FormulaState formula, List<int> numbers)
        {
            if (formula == null || formula.boxes == null)
                return;

            for (int i = 0; i < formula.boxes.Count; i++)
            {
                FormulaBox box = formula.boxes[i];
                if (box != null && box.boxType == FormulaBoxType.Number)
                    numbers.Add(box.numberValue);
            }
        }





        private static void SetBuff(MonsterRuntime monster, RunContext runContext, string type, int value)
        {
            switch (type)
            {
                case "strength":
                    monster.SetStrength(value);
                    break;
                case "stun":
                    monster.SetStun(value);
                    break;
                case "shield":
                    monster.SetShield(value);
                    break;
                case "fortunestack":
                    monster.SetFortuneStack(value);
                    break;
                case "prophecystack":
                case "prophetstack":
                    monster.SetProphecyStack(value);
                    if (runContext != null)
                        runContext.prophecyStack = monster.ProphecyStack;
                    break;
                case "bleed":
                    if (runContext != null)
                        runContext.pendingPlayerBleed = Mathf.Max(0, value);
                    break;
                case "poison":
                    if (runContext != null)
                        runContext.pendingPlayerPoison = Mathf.Max(0, value);
                    break;
                case "phase":
                case "phase2":
                    monster.SetPhase(Mathf.Max(1, value));
                    break;
            }
        }

        private static void MultiplyBuff(MonsterRuntime monster, RunContext runContext, string type, int value)
        {
            int multiplier = Mathf.Max(0, value);
            switch (type)
            {
                case "strength":
                    monster.SetStrength(monster.Strength * multiplier);
                    break;
                case "shield":
                    monster.SetShield(monster.Shield * multiplier);
                    break;
                case "fortunestack":
                    monster.SetFortuneStack(monster.FortuneStack * multiplier);
                    break;
                case "prophecystack":
                case "prophetstack":
                    monster.SetProphecyStack(monster.ProphecyStack * multiplier);
                    if (runContext != null)
                        runContext.prophecyStack = monster.ProphecyStack;
                    break;
                case "bleed":
                    if (runContext != null)
                        runContext.playerBleed = Mathf.Max(0, runContext.playerBleed * multiplier);
                    break;
                case "poison":
                    if (runContext != null)
                        runContext.playerPoison = Mathf.Max(0, runContext.playerPoison * multiplier);
                    break;
            }
        }

        private static void ApplyStack(MonsterRuntime monster, RunContext runContext, string target, int value, bool set)
        {
            if (target == "fortunebox")
            {
                if (set)
                    monster.SetFortuneStack(value);
                else
                    monster.ChangeFortuneStack(value);
                return;
            }

            if (target == "prophecybox" || target == "self" || string.IsNullOrWhiteSpace(target))
            {
                if (set)
                    monster.SetProphecyStack(value);
                else
                    monster.ChangeProphecyStack(value);
                if (runContext != null)
                    runContext.prophecyStack = monster.ProphecyStack;
                return;
            }

            if (set)
                monster.SetProphecyStack(value);
            else
                monster.ChangeProphecyStack(value);
            if (runContext != null)
                runContext.prophecyStack = monster.ProphecyStack;
        }


        private int BuildSpecialBoxValue(string valueExpression, int count, RunContext runContext)
        {
            int result = 0;
            for (int i = 0; i < Mathf.Max(1, count); i++)
            {
                int digit = NormalizeLookup(valueExpression) == "random" && runContext != null
                    ? runContext.RollValue($"monster.special_box.{runContext.battleTurnNumber}.{i}", 0, 9)
                    : Mathf.FloorToInt(effectValues.EvaluateValue(valueExpression, null, runContext, 0));
                result = result * 10 + Mathf.Clamp(digit, 0, 9);
            }

            return result;
        }

private static bool UsesEditableHealBox(MonsterPatternData pattern)
        {
            if (pattern?.effects == null)
                return false;
            for (int i = 0; i < pattern.effects.Length; i++)
            {
                MonsterPatternEffectData effect = pattern.effects[i];
                if (effect != null && effect.editable && ResolveAction(effect) == "heal")
                    return true;
            }
            return false;
        }

        private static string NormalizeTiming(string value)
        {
            string normalized = NormalizeLookup(value);
            return string.IsNullOrWhiteSpace(normalized) ? "immediate" : normalized;
        }

        private static string NormalizeLookup(string value)
        {
            return (value ?? string.Empty).Trim().Replace("_", string.Empty).Replace("-", string.Empty).Replace(" ", string.Empty).ToLowerInvariant();
        }

        private static string ResolveAction(MonsterPatternEffectData effect)
        {
            if (effect == null)
                return string.Empty;

            switch (effect.operationKind)
            {
                case GameplayEffectOperation.DealDamage: return "damage";
                case GameplayEffectOperation.Heal: return "heal";
                case GameplayEffectOperation.AddStatus: return "addbuff";
                case GameplayEffectOperation.SetStatus: return "setbuff";
                case GameplayEffectOperation.RemoveStatus: return "removebuff";
                case GameplayEffectOperation.MultiplyStat: return "multiplybuff";
                case GameplayEffectOperation.AddStack: return "addstack";
                case GameplayEffectOperation.SplitBox: return "split";
                case GameplayEffectOperation.LockBox: return "lock";
                case GameplayEffectOperation.CreateFormulaBox: return "addbox";
                case GameplayEffectOperation.SetFormulaValue: return "setvalue";
                default: return NormalizeLookup(effect.action);
            }
        }
    
private static void AddPlayerDebuffBox(RunContext runContext, string type, int digitCount, int duration)
        {
            BattleNumberState numbers = runContext?.currentBattle;
            if (numbers == null)
                return;

            string debuffOperator = type == "dividebox" ? "Divide" : "Subtract";
            if (string.IsNullOrWhiteSpace(numbers.playerDebuffOperator))
                numbers.playerDebuffOperator = debuffOperator;
            else if (numbers.playerDebuffOperator != debuffOperator)
                return;

            numbers.playerDebuffDigitCount = Mathf.Max(1, digitCount);
            numbers.playerDebuffExpiresAfterTurn = duration > 0
                ? Mathf.Max(1, runContext.battleTurnNumber) + duration
                : -1;
            numbers.playerDebuffRollTurn = 0;
            numbers.playerDebuffSegmentState = string.Empty;
        }
}
}
