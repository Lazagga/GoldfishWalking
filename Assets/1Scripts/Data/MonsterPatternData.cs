using System;
using System.Text.RegularExpressions;
using UnityEngine;

namespace GoldfishWalking.Data
{
    public enum MonsterPatternType
    {
        None,
        SingleHit,
        MultiHit,
        StrengthUp,
        StrengthDown,
        Heal,
        Special
    }

    [Serializable]
    public sealed class MonsterPatternData
    {
        public string id;
        public int sourceId;
        public string dataCode;
        public string devName;
        public string nameStringId;
        public string displayName;
        [TextArea] public string description;
        public MonsterPatternType patternType;
        public int value;
        public int hitCount = 1;
        public string attackKey;
        public int damageDigitCount;
        public int hitDigitCount;
        public int strengthDelta;
        public string condition;
        public string rawEffects;
        public MonsterPatternEffectData[] effects = Array.Empty<MonsterPatternEffectData>();
        public string sprite;
        public string specialHandler;
    }

    [Serializable]
    public sealed class MonsterPatternEffectData
    {
        public string timing;
        public string target;
        public string action;
        public string type;
        public string condition;
        public string valueExpression;
        public bool hasNumericValue;
        public float numericValue;
        public int duration;
        public bool lockDamage;
        public string rawJson;
    }

    public static class MonsterPatternKeyUtility
    {
        private static readonly Regex SingleRegex = new Regex(@"^(\d+)_single$", RegexOptions.IgnoreCase);
        private static readonly Regex MultiRegex = new Regex(@"^(\d+)_multi(?:_(\d+))?$", RegexOptions.IgnoreCase);
        private static readonly Regex StrengthRegex = new Regex(@"^str_(\-?\d+)$", RegexOptions.IgnoreCase);

        public static string NormalizePatternKey(string value)
        {
            string text = (value ?? string.Empty).Trim();
            if (string.IsNullOrWhiteSpace(text))
                return string.Empty;

            return text;
        }

        public static void ApplyPatternKey(MonsterPatternData pattern, string key)
        {
            if (pattern == null)
                return;

            string normalized = NormalizePatternKey(key);
            pattern.attackKey = normalized;
            pattern.patternType = MonsterPatternType.None;
            pattern.damageDigitCount = 0;
            pattern.hitDigitCount = 0;
            pattern.value = 0;
            pattern.hitCount = 1;
            pattern.strengthDelta = 0;

            if (string.IsNullOrWhiteSpace(normalized) || normalized.Equals("Skip", StringComparison.OrdinalIgnoreCase))
                return;

            System.Text.RegularExpressions.Match single = SingleRegex.Match(normalized);
            if (single.Success)
            {
                pattern.patternType = MonsterPatternType.SingleHit;
                pattern.damageDigitCount = ParsePositive(single.Groups[1].Value, 2);
                pattern.hitDigitCount = 0;
                pattern.hitCount = 1;
                return;
            }

            System.Text.RegularExpressions.Match multi = MultiRegex.Match(normalized);
            if (multi.Success)
            {
                pattern.patternType = MonsterPatternType.MultiHit;
                pattern.damageDigitCount = ParsePositive(multi.Groups[1].Value, 2);
                pattern.hitDigitCount = multi.Groups[2].Success ? ParsePositive(multi.Groups[2].Value, 1) : 1;
                return;
            }

            System.Text.RegularExpressions.Match strength = StrengthRegex.Match(normalized);
            if (strength.Success)
            {
                int amount = ParseInt(strength.Groups[1].Value, 0);
                pattern.patternType = amount >= 0 ? MonsterPatternType.StrengthUp : MonsterPatternType.StrengthDown;
                pattern.strengthDelta = amount;
                pattern.value = Math.Abs(amount);
                return;
            }

            pattern.patternType = MonsterPatternType.Special;
            pattern.specialHandler = normalized;
        }

        public static MonsterPatternData CreateFromKey(string key)
        {
            string normalized = NormalizePatternKey(key);
            MonsterPatternData pattern = new MonsterPatternData
            {
                id = string.IsNullOrWhiteSpace(normalized) ? "2_Single" : normalized,
                dataCode = normalized,
                displayName = normalized,
                attackKey = normalized
            };
            ApplyPatternKey(pattern, normalized);
            return pattern;
        }

        public static int MinForDigits(int digitCount)
        {
            if (digitCount <= 1)
                return 1;

            int value = 1;
            for (int i = 1; i < digitCount; i++)
                value *= 10;
            return value;
        }

        public static int MaxForDigits(int digitCount)
        {
            if (digitCount <= 0)
                return 0;

            int value = 1;
            for (int i = 0; i < digitCount; i++)
                value *= 10;
            return value - 1;
        }

        private static int ParsePositive(string value, int fallback)
        {
            return Math.Max(1, ParseInt(value, fallback));
        }

        private static int ParseInt(string value, int fallback)
        {
            return int.TryParse(value, out int result) ? result : fallback;
        }
    }
}
