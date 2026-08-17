using System;
using System.Globalization;
using GoldfishWalking.Core;
using UnityEngine;

namespace GoldfishWalking.Battle
{
    public sealed class MonsterEffectExpressionEvaluator
    {
        public bool EvaluateCondition(string expression, MonsterRuntime monster, RunContext runContext)
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

        public float EvaluateValue(string expression, MonsterRuntime monster, RunContext runContext, int damageDealt)
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
                case "playerhpmulti2":
                {
                    int percent = runContext != null
                        ? runContext.RollValue($"monster.player_hp_percent.turn.{Mathf.Max(1, runContext.battleTurnNumber)}", 10, 99)
                        : 10;
                    monster?.SetSpecialBox(percent, 2, "HP %", false);
                    return runContext != null ? Mathf.Floor(runContext.health * percent / 100f) : 0f;
                }
                case "stargazingmulti3":
                    return monster != null && monster.HasSpecialBox ? monster.SpecialBoxValue : 0f;
                case "cosmictreeheal":
                    return 1f;
                case "damagedealt": return Mathf.Max(0, damageDealt);
                case "damagetaken":
                    return monster != null ? monster.DamageCapAccumulatedDamage
                        : runContext != null ? runContext.battleSession.totalDamageDealt : 0f;
                case "damagecapbreakthreshold": return monster?.Data != null ? monster.Data.damageCapBreakThreshold : 0f;
                case "fortunestack": return monster != null ? monster.FortuneStack : 0f;
                case "prophecystack":
                case "prophetstack":
                    return monster != null ? monster.ProphecyStack : (runContext != null ? runContext.battleSession.prophecyStack : 0f);
                case "playerbleed": return runContext != null ? runContext.battleSession.playerBleed : 0f;
                case "playerpoison":
                case "playerpoision": return runContext != null ? runContext.battleSession.playerPoison : 0f;
                case "playerhp":
                case "hp": return runContext != null ? runContext.health : 0f;
                case "specialboxvalue": return monster != null && monster.HasSpecialBox ? monster.SpecialBoxValue : 0f;
                case "strength": return monster != null ? monster.Strength : 0f;
                case "hprate":
                    return monster != null && monster.Data != null && monster.Data.baseHealth > 0
                        ? (float)monster.CurrentHealth / monster.Data.baseHealth
                        : 1f;
                case "phase": return monster != null ? monster.Phase : 1f;
                case "random": return runContext != null ? runContext.RollValue("monster.pattern.random_digit", 0, 9) : 0f;
            }

            if (text.StartsWith("DigitCount(", StringComparison.OrdinalIgnoreCase) && text.EndsWith(")", StringComparison.Ordinal))
                return DigitCount(Mathf.FloorToInt(EvaluateValue(text.Substring(11, text.Length - 12), monster, runContext, damageDealt)));

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

        private static string NormalizeLookup(string value)
        {
            return (value ?? string.Empty).Trim().Replace("_", string.Empty).Replace(" ", string.Empty).ToLowerInvariant();
        }
    }
}
