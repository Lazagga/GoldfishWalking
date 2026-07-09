using System;
using GoldfishWalking.Data;
using GoldfishWalking.Core;

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

            int index = runContext != null ? Math.Max(0, runContext.battleTurnNumber - 1) % patternIds.Length : 0;

            return ResolvePattern(database, patternIds[Math.Max(0, Math.Min(index, patternIds.Length - 1))]);
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
            else if (found.patternType == MonsterPatternType.Special)
                MonsterPatternKeyUtility.ApplyPatternKey(found, FallbackPatternKey);

            return found;
        }

        public bool IsAttackPattern(MonsterPatternData pattern)
        {
            return pattern != null && (pattern.patternType == MonsterPatternType.SingleHit || pattern.patternType == MonsterPatternType.MultiHit);
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

            ApplySimpleEffects(monster, pattern);
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

        private static void ApplySimpleEffects(MonsterRuntime monster, MonsterPatternData pattern)
        {
            if (pattern.effects == null)
                return;

            for (int i = 0; i < pattern.effects.Length; i++)
            {
                MonsterPatternEffectData effect = pattern.effects[i];
                if (effect == null)
                    continue;

                string action = NormalizeLookup(effect.action);
                string type = NormalizeLookup(effect.type);
                int value = effect.hasNumericValue ? UnityEngine.Mathf.FloorToInt(effect.numericValue) : 0;
                if (action == "heal")
                    monster.Heal(value);
                else if (action == "addbuff" && type == "strength")
                    monster.ChangeStrength(value);
                else if (action == "setbuff" && type == "strength")
                    monster.SetStrength(value);
            }
        }

        private static string NormalizeLookup(string value)
        {
            return (value ?? string.Empty).Trim().Replace("_", string.Empty).Replace("-", string.Empty).Replace(" ", string.Empty).ToLowerInvariant();
        }
    }
}
