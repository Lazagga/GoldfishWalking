using GoldfishWalking.Data;
using System.Globalization;
using UnityEngine;

namespace GoldfishWalking.UI
{
    public static class FantasyText
    {
        public static string DisplayName(FantasyData fantasy)
        {
            if (fantasy == null)
                return string.Empty;
            if (!string.IsNullOrWhiteSpace(fantasy.displayName))
                return fantasy.displayName;
            if (!string.IsNullOrWhiteSpace(fantasy.devName))
                return fantasy.devName;
            return fantasy.id;
        }

        public static string Description(FantasyData fantasy)
        {
            if (fantasy == null)
                return string.Empty;
            if (!string.IsNullOrWhiteSpace(fantasy.description))
                return fantasy.description;
            return fantasy.descStringId;
        }

        public static string EffectSummary(FantasyData fantasy)
        {
            if (fantasy == null || fantasy.effects == null || fantasy.effects.Length == 0)
                return string.Empty;

            FantasyEffectData effect = fantasy.effects[0];
            string trigger = !string.IsNullOrWhiteSpace(effect.trigger) ? effect.trigger : fantasy.triggerType;
            string target = !string.IsNullOrWhiteSpace(effect.target) ? effect.target : "Effect";
            string calc = !string.IsNullOrWhiteSpace(effect.calc) ? effect.calc : "Apply";
            string value = effect.hasNumericValue
                ? effect.numericValue.ToString(CultureInfo.InvariantCulture)
                : (!string.IsNullOrWhiteSpace(effect.valueExpression) ? effect.valueExpression : "0");
            return $"{trigger} / {target} / {calc} {value}";
        }

        public static Color GradeColor(FantasyGrade grade, Color whiteColor, Color blueColor, Color redColor)
        {
            switch (grade)
            {
                case FantasyGrade.Blue:
                    return blueColor;
                case FantasyGrade.Red:
                    return redColor;
                default:
                    return whiteColor;
            }
        }
    }
}
