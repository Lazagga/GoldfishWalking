using GoldfishWalking.Core;
using GoldfishWalking.Data;
using GoldfishWalking.Item;
using GoldfishWalking.Match;
using System.Collections.Generic;
using UnityEngine;

namespace GoldfishWalking.Fantasy
{
    public sealed class FantasyEffectRunner
    {
        public void AddItemWithAcquireEffects(RunContext runContext, ItemType itemType, int count)
        {
            if (runContext == null || count <= 0)
                return;

            runContext.itemInventory.Add(itemType, count);
            runContext.lastAcquiredItemType = itemType;
            runContext.lastAcquiredItemCount = count;
            ApplyTrigger(runContext, "Acquire_Item");
            runContext.lastAcquiredItemCount = 0;
            GameEventHub.RaiseItemInventoryChanged();
        }

        public void ApplyItemUsedEffects(RunContext runContext, ItemType itemType)
        {
            if (runContext == null)
                return;

            runContext.lastUsedItemType = itemType;
            ApplyTrigger(runContext, "Use_Item");
            GameEventHub.RaiseItemInventoryChanged();
        }

        public void ApplyTrigger(RunContext runContext, string trigger)
        {
            if (runContext == null || runContext.fantasyInventory == null || string.IsNullOrWhiteSpace(trigger))
                return;

            List<FantasyData> snapshot = new List<FantasyData>(runContext.fantasyInventory.ownedFantasies);
            foreach (FantasyData fantasy in snapshot)
                Apply(fantasy, runContext, trigger);
        }

        public void Apply(FantasyData fantasy, RunContext runContext)
        {
            Apply(fantasy, runContext, null);
        }

        public void Apply(FantasyData fantasy, RunContext runContext, string trigger)
        {
            if (fantasy == null || runContext == null)
                return;

            int pendingBeforeSpecial = runContext.pendingMonsterDamage;
            if (ApplySpecialFantasy(fantasy, runContext, trigger))
            {
                LogPendingDamageDelta(fantasy, runContext, pendingBeforeSpecial);
                return;
            }

            if (fantasy.effects == null || fantasy.effects.Length == 0)
            {
                ApplyLegacyEffect(fantasy, runContext);
                return;
            }

            foreach (FantasyEffectData effect in fantasy.effects)
            {
                if (effect == null)
                    continue;

                if (!string.IsNullOrWhiteSpace(trigger) && !TriggerMatches(effect.trigger, trigger))
                    continue;

                ApplyEffect(fantasy, effect, runContext);
            }
        }

        public int ModifyValue(RunContext runContext, int baseValue, string trigger, params string[] targets)
        {
            if (runContext == null || runContext.fantasyInventory == null)
                return baseValue;

            int value = baseValue;
            foreach (FantasyData fantasy in runContext.fantasyInventory.ownedFantasies)
            {
                if (fantasy == null || fantasy.effects == null)
                    continue;

                foreach (FantasyEffectData effect in fantasy.effects)
                {
                    if (effect == null)
                        continue;
                    if (TryModifySpecialFantasyValue(fantasy, runContext, trigger, targets, ref value))
                        continue;
                    if (!TriggerMatches(effect.trigger, trigger))
                        continue;
                    if (!TargetMatches(effect.target, targets))
                        continue;

                    value = ApplyCalculation(value, Normalize(effect.calc), EvaluateEffectValue(effect, runContext));
                }
            }

            return value;
        }

        private bool ApplySpecialFantasy(FantasyData fantasy, RunContext runContext, string trigger)
        {
            string id = NormalizeId(fantasy.id);
            string normalizedTrigger = NormalizeTrigger(trigger);

            switch (id)
            {
                case "fanend8ball":
                    if (normalizedTrigger == NormalizeTrigger("Turn_End"))
                    {
                        float damagePerDigit = GetEffectValue(fantasy, "Turn_End", "Damage", 20f, runContext);
                        runContext.pendingMonsterDamage += Mathf.FloorToInt(CountDigitInBattleNumbers(runContext, 8) * damagePerDigit);
                        return true;
                    }
                    break;
                case "fanendgrape":
                    if (normalizedTrigger == NormalizeTrigger("Turn_End"))
                    {
                        float healPerMove = GetEffectValue(fantasy, "Turn_End", "HP", 50f, runContext);
                        runContext.health += Mathf.FloorToInt(Mathf.Max(0, runContext.remainingMoveCount) * healPerMove);
                        return true;
                    }
                    break;
                case "fanendfan":
                    if (normalizedTrigger == NormalizeTrigger("Turn_End"))
                    {
                        float damagePercent = GetEffectValue(fantasy, "Turn_End", "Damage", 20f, runContext);
                        runContext.pendingMonsterDamage += Mathf.FloorToInt(runContext.health * NormalizePercent(damagePercent));
                        return true;
                    }
                    break;
                case "fanendfirecracker":
                    if (normalizedTrigger == NormalizeTrigger("Turn_End"))
                    {
                        float damagePerItem = GetEffectValue(fantasy, "Turn_End", "Damage", 30f, runContext);
                        runContext.pendingMonsterDamage += Mathf.FloorToInt(Mathf.Max(0, runContext.itemUseCountThisBattle) * damagePerItem);
                        return true;
                    }
                    break;
                case "fanendpaperplane":
                    if (normalizedTrigger == NormalizeTrigger("Turn_End"))
                        return true;
                    break;
                case "fanstartcuestick":
                    if (normalizedTrigger == NormalizeTrigger("Battle_Start") && runContext.currentBattle != null)
                    {
                        int digit = Mathf.FloorToInt(GetEffectValue(fantasy, "Battle_Start", "Base_Damage", 8f, runContext));
                        runContext.currentBattle.playerBaseDamage = SetFirstDigit(runContext.currentBattle.playerBaseDamage, digit);
                        return true;
                    }
                    break;
                case "fanendtrumpcard":
                    if (normalizedTrigger == NormalizeTrigger("Turn_End"))
                    {
                        runContext.temporaryMoveBonus += Mathf.Max(0, runContext.remainingMoveCount);
                        runContext.remainingMoveCount = 0;
                        return true;
                    }
                    break;
                case "fanturnpisces":
                    if (normalizedTrigger == NormalizeTrigger("Turn_Start"))
                    {
                        int convertedMoves = Mathf.Max(0, runContext.remainingMoveCount);
                        runContext.remainingMoveCount = 0;
                        runContext.itemInventory.AddTemporary(ItemType.ExtraMatch, convertedMoves);
                        runContext.itemInventory.AddTemporary(ItemType.Eraser, convertedMoves);
                        GameEventHub.RaiseItemInventoryChanged();
                        return true;
                    }
                    break;
                case "fanusemusicbox":
                    if (normalizedTrigger == NormalizeTrigger("Use_Item"))
                    {
                        if (runContext.RollValue($"fantasy.musicbox.{runContext.itemUseCountThisBattle}", 0, 99) < 50)
                            runContext.itemInventory.Add(runContext.lastUsedItemType, Mathf.FloorToInt(GetEffectValue(fantasy, "Use_Item", "Item", 1f, runContext)));
                        return true;
                    }
                    break;
                case "fanshopstampcoupon":
                    if (normalizedTrigger == NormalizeTrigger("Shop_Purchase"))
                        return true;
                    break;
                case "fanstartstamp":
                    if (normalizedTrigger == NormalizeTrigger("Battle_Start"))
                    {
                        FantasyData copied = SelectOwnedFantasyCopy(runContext, fantasy);
                        if (copied != null)
                            runContext.fantasyInventory.AddDuplicate(copied);
                        return true;
                    }
                    break;
                case "fanenddice":
                    if (normalizedTrigger == NormalizeTrigger("Battle_End"))
                    {
                        runContext.rewardRerolls += Mathf.FloorToInt(GetEffectValue(fantasy, "Battle_End", "Fantasy_Reroll", 1f, runContext));
                        return true;
                    }
                    break;
                case "fanacquireblueprint":
                    if (normalizedTrigger == NormalizeTrigger("On_Acquire"))
                    {
                        FantasyData copied = SelectOwnedFantasyCopy(runContext, fantasy, temporary: false);
                        if (copied != null)
                        {
                            runContext.fantasyInventory.Remove(fantasy);
                            runContext.fantasyInventory.AddDuplicate(copied);
                        }
                        return true;
                    }
                    break;
            }

            return false;
        }

        private bool TryModifySpecialFantasyValue(FantasyData fantasy, RunContext runContext, string trigger, string[] targets, ref int value)
        {
            string id = NormalizeId(fantasy.id);
            string normalizedTrigger = NormalizeTrigger(trigger);

            switch (id)
            {
                case "fandamagelibra":
                    if (TargetMatches("Base_Damage", targets) && runContext.currentBattle != null)
                    {
                        int replacement = Mathf.FloorToInt(GetEffectValue(fantasy, string.Empty, "Base_Damage", 200f, runContext));
                        value = runContext.currentBattle.playerBaseDamage == 0 ? replacement : 0;
                        return true;
                    }
                    break;
                case "fandefendpaperboat":
                    if (normalizedTrigger == NormalizeTrigger("Take_Damage") && TargetMatches("Damage_Taken", targets) && runContext.currentBattle != null)
                    {
                        if (runContext.currentBattle.monsterBaseDamage >= runContext.currentBattle.playerBaseDamage)
                            value = Mathf.FloorToInt(value * GetEffectValue(fantasy, string.Empty, "Damage_Taken", 0.5f, runContext));
                        return true;
                    }
                    break;
                case "fandamagemirror":
                    if (normalizedTrigger == NormalizeTrigger("Turn_End") && TargetMatches("Attack_Count", targets))
                    {
                        if (runContext.currentBattle != null && HasSameDigits(runContext.currentBattle.playerBaseDamage)
                            && HasSameVisibleDigits(runContext.currentBattle.playerBaseDamage, runContext.currentBattle.playerBaseDamageSegmentState))
                            value += Mathf.FloorToInt(GetEffectValue(fantasy, "Turn_End", "Attack_Count", 1f, runContext));
                        return true;
                    }
                    break;
                case "fanendpaperplane":
                    if (normalizedTrigger == NormalizeTrigger("Turn_End") && TargetMatches("Additional_Damage", targets))
                    {
                        if (runContext.currentBattle != null && runContext.currentBattle.playerBaseDamage == runContext.currentBattle.monsterBaseDamage)
                            value = Mathf.FloorToInt(value * GetEffectValue(fantasy, "Turn_End", "Additional_Damage", 2f, runContext));
                        return true;
                    }
                    break;
            }

            return false;
        }

        private void ApplyEffect(FantasyData fantasy, FantasyEffectData effect, RunContext runContext)
        {
            string target = NormalizeTarget(effect.target);
            string calc = Normalize(effect.calc);
            float value = EvaluateEffectValue(effect, runContext);
            int pendingBefore = runContext.pendingMonsterDamage;

            switch (target)
            {
                case "hp":
                    if (TriggerMatches(effect.trigger, "Deal_Damage") && calc == "add")
                        value = runContext.lastDamageDealt * NormalizePercent(value);
                    runContext.health = ApplyCalculation(runContext.health, calc, value);
                    break;
                case "item":
                    int itemCount = Mathf.FloorToInt(value);
                    if (TriggerMatches(effect.trigger, "Acquire_Item") && runContext.lastAcquiredItemCount > 0)
                        runContext.itemInventory.Add(runContext.lastAcquiredItemType, itemCount * runContext.lastAcquiredItemCount);
                    else if (IsTemporaryItemGrant(effect.trigger))
                    {
                        runContext.itemInventory.AddTemporary(ItemType.ExtraMatch, itemCount);
                        runContext.itemInventory.AddTemporary(ItemType.Eraser, itemCount);
                    }
                    else
                    {
                        runContext.itemInventory.Add(ItemType.ExtraMatch, itemCount);
                        runContext.itemInventory.Add(ItemType.Eraser, itemCount);
                    }
                    GameEventHub.RaiseItemInventoryChanged();
                    break;
                case "extramatch":
                    AddItemByLifetime(runContext, ItemType.ExtraMatch, Mathf.FloorToInt(value), effect.trigger);
                    GameEventHub.RaiseItemInventoryChanged();
                    break;
                case "eraser":
                    AddItemByLifetime(runContext, ItemType.Eraser, Mathf.FloorToInt(value), effect.trigger);
                    GameEventHub.RaiseItemInventoryChanged();
                    break;
                case "strength":
                    int strengthBefore = runContext.strength;
                    runContext.strength = ApplyCalculation(runContext.strength, calc, value);
                    if (effect.duration > 0)
                        runContext.AddTimedPlayerStrength(runContext.strength - strengthBefore, effect.duration);
                    break;
                case "enemystrength":
                    int enemyStrengthDelta = CalculateDelta(0, calc, value);
                    runContext.QueueEnemyStrengthModifier(enemyStrengthDelta, effect.duration);
                    break;
                case "basedamage":
                    if (runContext.currentBattle != null)
                        runContext.currentBattle.playerBaseDamage = ApplyCalculation(runContext.currentBattle.playerBaseDamage, calc, value);
                    break;
                case "damage":
                case "additionaldamage":
                    runContext.pendingMonsterDamage = ApplyCalculation(runContext.pendingMonsterDamage, calc, value);
                    LogPendingDamageDelta(fantasy, runContext, pendingBefore);
                    break;
                case "damagereflect":
                    runContext.pendingMonsterDamage += CalculateReflectDamage(runContext, calc, value);
                    LogPendingDamageDelta(fantasy, runContext, pendingBefore);
                    break;
                case "fantasyreroll":
                    runContext.rewardRerolls += Mathf.FloorToInt(value);
                    break;
            }
        }

        public static int TransformBattleNumber(RunContext runContext, int value, bool isPlayerNumber)
        {
            if (runContext == null || runContext.fantasyInventory == null)
                return value;

            int transformed = value;
            if (isPlayerNumber && runContext.fantasyInventory.Contains("fan_number_domino"))
                transformed = TransformDigits(transformed, digit => digit < 5 ? 5 : digit);
            if (!isPlayerNumber && runContext.fantasyInventory.Contains("fan_number_applepie"))
                transformed = TransformDigits(transformed, digit => digit > 5 ? 5 : digit);
            if (isPlayerNumber && runContext.fantasyInventory.Contains("fan_odd_gemini"))
                transformed = transformed % 2 != 0 ? transformed * 2 : 0;

            return Mathf.Max(0, transformed);
        }

        private void ApplyLegacyEffect(FantasyData fantasy, RunContext runContext)
        {
            switch (fantasy.target)
            {
                case FantasyTarget.Health:
                    runContext.health += fantasy.value;
                    break;
                case FantasyTarget.Strength:
                    runContext.strength += fantasy.value;
                    break;
            }
        }

        private static bool TriggerMatches(string effectTrigger, string requestedTrigger)
        {
            return NormalizeTrigger(effectTrigger) == NormalizeTrigger(requestedTrigger);
        }

        private static bool TargetMatches(string effectTarget, string[] requestedTargets)
        {
            if (requestedTargets == null || requestedTargets.Length == 0)
                return false;

            string normalizedEffectTarget = NormalizeTarget(effectTarget);
            for (int i = 0; i < requestedTargets.Length; i++)
            {
                if (normalizedEffectTarget == NormalizeTarget(requestedTargets[i]))
                    return true;
            }

            return false;
        }

        private static void AddItemByLifetime(RunContext runContext, ItemType itemType, int count, string trigger)
        {
            if (IsTemporaryItemGrant(trigger))
                runContext.itemInventory.AddTemporary(itemType, count);
            else
                runContext.itemInventory.Add(itemType, count);
        }

        private static bool IsTemporaryItemGrant(string trigger)
        {
            string normalized = NormalizeTrigger(trigger);
            return normalized == NormalizeTrigger("Battle_Start")
                || normalized == NormalizeTrigger("Turn_Start")
                || normalized.StartsWith("turn");
        }

        private static string Normalize(string value)
        {
            return (value ?? string.Empty).Trim().ToLowerInvariant();
        }

        private static string NormalizeId(string value)
        {
            return NormalizeTrigger(value);
        }

        private static string NormalizeTrigger(string value)
        {
            return Normalize(value).Replace("_", string.Empty).Replace("-", string.Empty).Replace(" ", string.Empty);
        }

        private static string NormalizeTarget(string value)
        {
            string normalized = NormalizeTrigger(value);
            switch (normalized)
            {
                case "1":
                    return "hp";
                case "2":
                    return "item";
                case "3":
                    return "damage";
                case "4":
                    return "attackcount";
                case "5":
                    return "strength";
                case "6":
                    return "fantasy";
                case "7":
                    return "restcount";
                case "8":
                    return "price";
                default:
                    return normalized;
            }
        }

        private static int ApplyCalculation(int current, string calc, float value)
        {
            switch (calc)
            {
                case "set":
                    return Mathf.FloorToInt(value);
                case "multiply":
                    return Mathf.FloorToInt(current * value);
                case "add":
                default:
                    return current + Mathf.FloorToInt(value);
            }
        }

        private static int CalculateDelta(int current, string calc, float value)
        {
            return ApplyCalculation(current, calc, value) - current;
        }

        private static FantasyData SelectOwnedFantasyCopy(RunContext runContext, FantasyData source, bool temporary = true)
        {
            if (runContext == null || runContext.fantasyInventory == null || runContext.fantasyInventory.ownedFantasies == null)
                return null;

            FantasyData selected = null;
            int seen = 0;
            for (int i = 0; i < runContext.fantasyInventory.ownedFantasies.Count; i++)
            {
                FantasyData candidate = runContext.fantasyInventory.ownedFantasies[i];
                if (candidate == null || candidate == source || candidate.isTemporary)
                    continue;
                if (NormalizeId(candidate.id) == NormalizeId(source.id))
                    continue;

                seen++;
                if (runContext.RollValue($"fantasy.copy.{NormalizeId(source.id)}.{seen}", 0, seen - 1) == 0)
                    selected = candidate;
            }

            return CloneFantasy(selected, temporary);
        }

        private static FantasyData CloneFantasy(FantasyData source, bool temporary)
        {
            if (source == null)
                return null;

            return new FantasyData
            {
                id = source.id,
                sourceId = source.sourceId,
                dataCode = source.dataCode,
                devName = source.devName,
                nameStringId = source.nameStringId,
                descStringId = source.descStringId,
                grade = source.grade,
                triggerType = source.triggerType,
                displayName = source.displayName,
                description = source.description,
                sprite = source.sprite,
                rawEffects = source.rawEffects,
                effects = source.effects,
                isTemporary = temporary,
                trigger = source.trigger,
                target = source.target,
                value = source.value,
                specialHandler = source.specialHandler
            };
        }

        private static int CalculateReflectDamage(RunContext runContext, string calc, float value)
        {
            if (runContext == null)
                return 0;

            switch (calc)
            {
                case "multiply":
                    return Mathf.FloorToInt(runContext.lastDamageTaken * NormalizePercent(value));
                case "set":
                    return Mathf.FloorToInt(value);
                case "add":
                default:
                    return Mathf.FloorToInt(value);
            }
        }

        private static void LogPendingDamageDelta(FantasyData fantasy, RunContext runContext, int pendingBefore)
        {
            if (fantasy == null || runContext == null)
                return;

            int delta = runContext.pendingMonsterDamage - pendingBefore;
            if (delta <= 0)
                return;

            runContext.AddBattleDamageDebug($"Fantasy {DisplayName(fantasy)}", delta);
        }

        private static string DisplayName(FantasyData fantasy)
        {
            if (!string.IsNullOrWhiteSpace(fantasy.displayName))
                return fantasy.displayName;
            if (!string.IsNullOrWhiteSpace(fantasy.devName))
                return fantasy.devName;
            return !string.IsNullOrWhiteSpace(fantasy.id) ? fantasy.id : "Unknown";
        }

        private static float NormalizePercent(float value)
        {
            return value > 1f ? value * 0.01f : value;
        }

        private static float GetEffectValue(FantasyData fantasy, string trigger, string target, float fallback, RunContext runContext)
        {
            if (fantasy == null || fantasy.effects == null)
                return fallback;

            for (int i = 0; i < fantasy.effects.Length; i++)
            {
                FantasyEffectData effect = fantasy.effects[i];
                if (effect == null)
                    continue;
                if (!TriggerMatches(effect.trigger, trigger))
                    continue;
                if (NormalizeTarget(effect.target) != NormalizeTarget(target))
                    continue;

                return EvaluateEffectValue(effect, runContext);
            }

            return fallback;
        }

        private static float EvaluateEffectValue(FantasyEffectData effect, RunContext runContext)
        {
            if (effect == null)
                return 0f;

            if (effect.hasNumericValue)
                return effect.numericValue;

            return EvaluateValue(effect.valueExpression, runContext);
        }

        private static float EvaluateValue(string expression, RunContext runContext)
        {
            string text = (expression ?? string.Empty).Trim();
            if (string.IsNullOrEmpty(text))
                return 0f;

            if (float.TryParse(text, System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out float numericValue))
                return numericValue;

            return EvaluateSimpleExpression(text, runContext);
        }

        private static float EvaluateSimpleExpression(string expression, RunContext runContext)
        {
            char[] operators = { '*', '/', '+', '-' };
            foreach (char op in operators)
            {
                int index = expression.IndexOf(op);
                if (index <= 0)
                    continue;

                float left = ResolveValueToken(expression.Substring(0, index), runContext);
                float right = ResolveValueToken(expression.Substring(index + 1), runContext);
                switch (op)
                {
                    case '*':
                        return left * right;
                    case '/':
                        return Mathf.Approximately(right, 0f) ? 0f : left / right;
                    case '+':
                        return left + right;
                    case '-':
                        return left - right;
                }
            }

            return ResolveValueToken(expression, runContext);
        }

        private static float ResolveValueToken(string token, RunContext runContext)
        {
            string value = (token ?? string.Empty).Trim();
            if (float.TryParse(value, System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out float numericValue))
                return numericValue;

            switch (Normalize(value))
            {
                case "hp":
                case "playerhp":
                    return runContext != null ? runContext.health : 0f;
                case "damagedealt":
                case "lastdamagedealt":
                    return runContext != null ? runContext.lastDamageDealt : 0f;
                case "totaldamagedealt":
                    return runContext != null ? runContext.battleDamageDealt : 0f;
                case "damagetaken":
                case "lastdamagetaken":
                    return runContext != null ? runContext.lastDamageTaken : 0f;
                case "totaldamagetaken":
                    return runContext != null ? runContext.battleDamageTaken : 0f;
                default:
                    return 0f;
            }
        }

        private static int CountDigitInBattleNumbers(RunContext runContext, int digit)
        {
            if (runContext == null || runContext.currentBattle == null)
                return 0;

            return CountDigit(runContext.currentBattle.playerBaseDamage, digit)
                + CountDigit(runContext.currentBattle.monsterBaseDamage, digit)
                + CountDigit(runContext.currentBattle.monsterHitCount, digit);
        }

        private static int CountDigit(int value, int digit)
        {
            string text = Mathf.Max(0, value).ToString();
            int count = 0;
            char target = (char)('0' + digit);
            for (int i = 0; i < text.Length; i++)
            {
                if (text[i] == target)
                    count++;
            }

            return count;
        }

        private static bool HasSameDigits(int value)
        {
            string text = Mathf.Max(0, value).ToString();
            if (text.Length <= 1)
                return true;

            char first = text[0];
            for (int i = 1; i < text.Length; i++)
            {
                if (text[i] != first)
                    return false;
            }

            return true;
        }

        private static bool HasSameVisibleDigits(int fallbackValue, string segmentState)
        {
            List<int> visibleDigits = ParseVisibleDigits(segmentState);
            if (visibleDigits.Count == 0)
                return HasSameDigits(fallbackValue);
            if (visibleDigits.Count <= 1)
                return true;

            int first = visibleDigits[0];
            for (int i = 1; i < visibleDigits.Count; i++)
            {
                if (visibleDigits[i] != first)
                    return false;
            }

            return true;
        }

        private static List<int> ParseVisibleDigits(string segmentState)
        {
            List<int> result = new List<int>();
            if (string.IsNullOrWhiteSpace(segmentState))
                return result;

            string[] parts = segmentState.Split('|');
            if (parts.Length < 2 || !int.TryParse(parts[0], out int digitCount))
                return result;

            Dictionary<int, List<int>> digitSegments = new Dictionary<int, List<int>>();
            string[] entries = parts[1].Split(',');
            for (int i = 0; i < entries.Length; i++)
            {
                if (string.IsNullOrWhiteSpace(entries[i]))
                    continue;

                string[] fields = entries[i].Split(':');
                if (fields.Length < 2)
                    continue;
                if (!int.TryParse(fields[0], out int digitIndex) || !int.TryParse(fields[1], out int segmentIndex))
                    continue;

                if (!digitSegments.TryGetValue(digitIndex, out List<int> segments))
                {
                    segments = new List<int>();
                    digitSegments.Add(digitIndex, segments);
                }

                segments.Add(segmentIndex);
            }

            for (int digitIndex = 0; digitIndex < digitCount; digitIndex++)
            {
                if (!digitSegments.TryGetValue(digitIndex, out List<int> segments) || segments.Count == 0)
                    continue;
                if (TryParseDigit(segments, out int digit))
                    result.Add(digit);
            }

            return result;
        }

        private static bool TryParseDigit(IReadOnlyList<int> segments, out int digit)
        {
            for (int i = 0; i < MatchPatternTable.DigitPatterns.Length; i++)
            {
                MatchPattern pattern = MatchPatternTable.DigitPatterns[i];
                if (MatchPatternTable.SameSegments(segments, pattern.segments))
                {
                    digit = pattern.value;
                    return true;
                }
            }

            digit = 0;
            return false;
        }

        private static int TransformDigits(int value, System.Func<int, int> transform)
        {
            string text = Mathf.Max(0, value).ToString();
            int result = 0;
            for (int i = 0; i < text.Length; i++)
            {
                int digit = text[i] - '0';
                result = result * 10 + Mathf.Clamp(transform != null ? transform(digit) : digit, 0, 9);
            }

            return result;
        }

        private static int SetFirstDigit(int value, int digit)
        {
            string text = Mathf.Max(0, value).ToString();
            if (string.IsNullOrEmpty(text))
                return digit;

            char[] chars = text.ToCharArray();
            chars[0] = (char)('0' + Mathf.Clamp(digit, 0, 9));
            if (int.TryParse(new string(chars), out int result))
                return result;

            return value;
        }
    }
}
