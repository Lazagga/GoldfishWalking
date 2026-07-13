using System;
using System.Collections.Generic;
using System.Globalization;
using GoldfishWalking.Data;
using GoldfishWalking.Core;
using GoldfishWalking.Formula;
using UnityEngine;

namespace GoldfishWalking.Battle
{
    public sealed class MonsterPatternRunner
    {
        private const string FallbackPatternKey = "2_Single";

        public MonsterPatternData SelectPattern(MonsterRuntime monster, MonsterPatternDatabase database, RunContext runContext)
        {
            if (monster == null || monster.Data == null)
                return MonsterPatternKeyUtility.CreateFromKey(FallbackPatternKey);

            string[] patternIds = monster.Data.patternIds;
            if (patternIds == null || patternIds.Length == 0)
                return MonsterPatternKeyUtility.CreateFromKey(FallbackPatternKey);

            List<MonsterPatternData> eligiblePatterns = new List<MonsterPatternData>();
            for (int i = 0; i < patternIds.Length; i++)
            {
                MonsterPatternData candidate = ResolvePattern(database, patternIds[i]);
                if (EvaluateCondition(candidate.condition, monster, runContext))
                    eligiblePatterns.Add(candidate);
            }

            if (eligiblePatterns.Count == 0)
                return MonsterPatternKeyUtility.CreateFromKey(FallbackPatternKey);

            int index = runContext != null ? Math.Max(0, runContext.battleTurnNumber - 1) % eligiblePatterns.Count : 0;

            return eligiblePatterns[Math.Max(0, Math.Min(index, eligiblePatterns.Count - 1))];
        }

        public MonsterPatternData ResolvePattern(MonsterPatternDatabase database, string patternKey)
        {
            string normalized = MonsterPatternKeyUtility.NormalizePatternKey(patternKey);
            if (string.IsNullOrWhiteSpace(normalized))
                normalized = FallbackPatternKey;

            MonsterPatternData builtIn = MonsterPatternKeyUtility.CreateFromKey(normalized);
            if (builtIn.patternType != MonsterPatternType.Special || normalized.Equals("Skip", StringComparison.OrdinalIgnoreCase))
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
                    || NormalizeLookup(effect.action) != "heal"
                    || NormalizeLookup(effect.target) == "player")
                    continue;

                digitCount = Mathf.Max(1, Mathf.FloorToInt(EvaluateValue(effect.valueExpression, monster, runContext, 0)));
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
            return Mathf.FloorToInt(EvaluateValue(expression, monster, runContext, 0));
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

                if (!EvaluateCondition(effect.condition, monster, runContext))
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

        private static void ApplyEffect(
            MonsterRuntime monster,
            RunContext runContext,
            MonsterPatternEffectData effect,
            BattleFormulaState playerFormula,
            BattleFormulaState monsterFormula,
            int damageDealt,
            int editableHealValue)
        {
            string action = NormalizeLookup(effect.action);
            string type = NormalizeLookup(effect.type);
            string target = NormalizeLookup(effect.target);
            int value = Mathf.FloorToInt(EvaluateValue(effect.valueExpression, monster, runContext, damageDealt));
            if (string.IsNullOrWhiteSpace(effect.valueExpression) && effect.duration > 0)
                value = effect.duration;
            if (action == "addbox")
                value = BuildSpecialBoxValue(effect.valueExpression, effect.rawJson, runContext);

            if (action == "split")
            {
                if (damageDealt > 0 && runContext != null)
                {
                    monster.ScheduledEffects.Add(new ScheduledMonsterPatternEffect
                    {
                        effect = effect,
                        triggerTurn = Mathf.Max(1, runContext.battleTurnNumber) + 1
                    });
                    return;
                }

                ApplyBoxFlag(target, playerFormula, monsterFormula, split: true, locked: false);
                return;
            }

            if (action == "lock")
            {
                if (damageDealt > 0 && runContext != null)
                {
                    monster.ScheduledEffects.Add(new ScheduledMonsterPatternEffect
                    {
                        effect = effect,
                        triggerTurn = Mathf.Max(1, runContext.battleTurnNumber) + 1
                    });
                    return;
                }

                ApplyBoxFlag(target, playerFormula, monsterFormula, split: false, locked: true);
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
                if (target == "self")
                    monster.ApplyDamage(value);
                else if (NormalizeLookup(effect.valueExpression) == "stargazingmulti3")
                {
                    for (int hitIndex = 0; hitIndex < 3; hitIndex++)
                        ApplyMonsterDamageToPlayer(monster, runContext, value);
                }
                else
                    ApplyMonsterDamageToPlayer(monster, runContext, value);
                return;
            }

            if (action == "librarianskill")
            {
                int damage = SelectPlayerFormulaNumber(playerFormula, runContext);
                ApplyMonsterDamageToPlayer(monster, runContext, damage);
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
                int count = ExtractCount(effect.rawJson);
                string label = SpecialBoxLabel(target);
                if (IsStargazer(monster) && count == 1)
                    monster.AppendSpecialBoxDigit(value, label);
                else
                    monster.SetSpecialBox(value, count, label);
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
                if (type == "boxlock")
                {
                    ApplyBoxFlag(target, playerFormula, monsterFormula, split: false, locked: true);
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

            if (actualDamage > 0 && IsVampire(monster))
                monster.Heal(Mathf.FloorToInt(actualDamage * 0.3f));
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

        private static bool IsVampire(MonsterRuntime monster)
        {
            string dataName = monster != null && monster.Data != null ? monster.Data.dataName ?? string.Empty : string.Empty;
            return dataName.Contains("Vampire");
        }

        private static bool IsStargazer(MonsterRuntime monster)
        {
            string dataName = monster != null && monster.Data != null ? monster.Data.dataName ?? string.Empty : string.Empty;
            return dataName.Contains("Stargazer");
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
                case "whalebuff":
                    monster.ClearSpecialBox();
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

        private static void ApplyBoxFlag(string target, BattleFormulaState playerFormula, BattleFormulaState monsterFormula, bool split, bool locked)
        {
            BattleFormulaState targetFormula = target == "self" ? monsterFormula : playerFormula;
            if (targetFormula == null)
                return;

            ApplyBoxFlag(targetFormula.damageExpression, split, locked);
            ApplyBoxFlag(targetFormula.hitCountExpression, split, locked);
        }

        private static void ApplyBoxFlag(FormulaState state, bool split, bool locked)
        {
            if (state == null || state.boxes == null)
                return;

            for (int i = 0; i < state.boxes.Count; i++)
            {
                FormulaBox box = state.boxes[i];
                if (box == null || box.boxType != FormulaBoxType.Number)
                    continue;

                if (split)
                    box.split = true;
                if (locked)
                    box.locked = true;
            }
        }

        private static bool EvaluateCondition(string expression, MonsterRuntime monster, RunContext runContext)
        {
            string text = (expression ?? string.Empty).Trim();
            if (string.IsNullOrWhiteSpace(text))
                return true;

            string[] andParts = text.Split(new[] { "&&" }, StringSplitOptions.None);
            if (andParts.Length > 1)
            {
                for (int i = 0; i < andParts.Length; i++)
                {
                    if (!EvaluateCondition(andParts[i], monster, runContext))
                        return false;
                }

                return true;
            }

            string[] operators = { ">=", "<=", "==", "!=", ">", "<" };
            for (int i = 0; i < operators.Length; i++)
            {
                string op = operators[i];
                int index = text.IndexOf(op, StringComparison.Ordinal);
                if (index < 0)
                    continue;

                float left = EvaluateValue(text.Substring(0, index), monster, runContext, 0);
                float right = EvaluateValue(text.Substring(index + op.Length), monster, runContext, 0);
                switch (op)
                {
                    case ">=": return left >= right;
                    case "<=": return left <= right;
                    case "==": return Mathf.Approximately(left, right);
                    case "!=": return !Mathf.Approximately(left, right);
                    case ">": return left > right;
                    case "<": return left < right;
                }
            }

            return EvaluateValue(text, monster, runContext, 0) > 0f;
        }

        private static float EvaluateValue(string expression, MonsterRuntime monster, RunContext runContext, int damageDealt)
        {
            string text = (expression ?? string.Empty).Trim();
            if (string.IsNullOrWhiteSpace(text))
                return 0f;

            if (float.TryParse(text, NumberStyles.Float, CultureInfo.InvariantCulture, out float literal))
                return literal;

            int opIndex = FindArithmeticOperator(text);
            if (opIndex > 0)
            {
                float left = EvaluateValue(text.Substring(0, opIndex), monster, runContext, damageDealt);
                float right = EvaluateValue(text.Substring(opIndex + 1), monster, runContext, damageDealt);
                switch (text[opIndex])
                {
                    case '+': return left + right;
                    case '-': return left - right;
                    case '*': return left * NormalizePercent(right);
                    case '/': return Mathf.Approximately(right, 0f) ? 0f : Mathf.Floor(left / right);
                }
            }

            switch (NormalizeLookup(text))
            {
                case "damagedealt":
                    return Mathf.Max(0, damageDealt);
                case "damagetaken":
                    return runContext != null ? runContext.battleDamageDealt : 0f;
                case "fortunestack":
                    return monster != null ? monster.FortuneStack : 0f;
                case "prophecystack":
                case "prophetstack":
                    return monster != null ? monster.ProphecyStack : (runContext != null ? runContext.prophecyStack : 0f);
                case "playerbleed":
                    return runContext != null ? runContext.playerBleed : 0f;
                case "playerpoison":
                case "playerpoision":
                    return runContext != null ? runContext.playerPoison : 0f;
                case "playerhp":
                case "hp":
                    return runContext != null ? runContext.health : 0f;
                case "playerhpmulti2":
                    return runContext != null ? Mathf.Floor(runContext.health * 0.2f) : 0f;
                case "stargazingmulti3":
                    if (monster != null && monster.HasSpecialBox)
                        return monster.SpecialBoxValue;
                    return runContext != null ? runContext.RollValue("monster.stargazing.multi3", 100, 999) : 333f;
                case "strength":
                    return monster != null ? monster.Strength : 0f;
                case "cosmictreeheal":
                    return monster != null ? DigitCount(monster.Strength) : 0f;
                case "hprate":
                    return monster != null && monster.Data != null && monster.Data.baseHealth > 0
                        ? (float)monster.CurrentHealth / monster.Data.baseHealth
                        : 1f;
                case "phase":
                    return monster != null ? monster.Phase : 1f;
                case "random":
                    return runContext != null ? runContext.RollValue("monster.pattern.random_digit", 0, 9) : 0f;
            }

            return 0f;
        }

        private static int DigitCount(int value)
        {
            int absolute = Mathf.Abs(value);
            if (absolute == 0)
                return 1;

            int digits = 0;
            while (absolute > 0)
            {
                digits++;
                absolute /= 10;
            }

            return digits;
        }

        private static int FindArithmeticOperator(string text)
        {
            for (int i = 1; i < text.Length; i++)
            {
                char c = text[i];
                if (c == '+' || c == '-' || c == '*' || c == '/')
                    return i;
            }

            return -1;
        }

        private static float NormalizePercent(float value)
        {
            return value > 1f ? value / 100f : value;
        }

        private static int BuildSpecialBoxValue(string valueExpression, string rawJson, RunContext runContext)
        {
            int count = ExtractCount(rawJson);
            int result = 0;
            for (int i = 0; i < Mathf.Max(1, count); i++)
            {
                int digit = NormalizeLookup(valueExpression) == "random" && runContext != null
                    ? runContext.RollValue($"monster.special_box.{runContext.battleTurnNumber}.{i}", 0, 9)
                    : Mathf.FloorToInt(EvaluateValue(valueExpression, null, runContext, 0));
                result = result * 10 + Mathf.Clamp(digit, 0, 9);
            }

            return result;
        }

        private static bool UsesEditableHealBox(MonsterPatternData pattern)
        {
            string key = NormalizeLookup(!string.IsNullOrWhiteSpace(pattern.dataCode) ? pattern.dataCode : pattern.id);
            return key == "giantratskill" || key == "cosmictreeheal";
        }

        private static int ExtractCount(string rawJson)
        {
            if (string.IsNullOrWhiteSpace(rawJson))
                return 1;

            const string key = "\"Count\":";
            int index = rawJson.IndexOf(key, StringComparison.OrdinalIgnoreCase);
            if (index < 0)
                return 1;

            int start = index + key.Length;
            while (start < rawJson.Length && char.IsWhiteSpace(rawJson[start]))
                start++;

            int end = start;
            while (end < rawJson.Length && char.IsDigit(rawJson[end]))
                end++;

            return int.TryParse(rawJson.Substring(start, end - start), NumberStyles.Integer, CultureInfo.InvariantCulture, out int count)
                ? Mathf.Max(1, count)
                : 1;
        }

        private static string SpecialBoxLabel(string target)
        {
            string normalized = NormalizeLookup(target);
            if (normalized == "whalebox")
                return "WHALE";
            if (normalized == "stargazerbox" || normalized == "starbox" || normalized == "self")
                return "STAR";
            return "SPECIAL";
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
    }
}
