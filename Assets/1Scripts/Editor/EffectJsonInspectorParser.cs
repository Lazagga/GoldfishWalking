using System;
using System.Collections.Generic;
using System.Globalization;
using GoldfishWalking.Data;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace GoldfishWalking.Editor
{
    internal static class EffectJsonInspectorParser
    {
        public static bool TryApply(FantasyData fantasy, out string error)
        {
            error = string.Empty;
            if (fantasy == null)
                return true;

            try
            {
                JToken root = JToken.Parse(fantasy.rawEffects ?? string.Empty);
                JArray array = root as JArray ?? new JArray(root);
                List<FantasyEffectData> parsed = new List<FantasyEffectData>();
                foreach (JToken token in array)
                {
                    if (token is not JObject obj)
                        throw new JsonException("Each fantasy effect must be a JSON object.");

                    FantasyEffectData effect = new FantasyEffectData
                    {
                        trigger = ReadString(obj, "Trigger"),
                        target = ReadString(obj, "Target"),
                        calc = ReadString(obj, "Calc"),
                        valueExpression = ReadValue(obj["Value"]),
                        option = ReadString(obj, "Option"),
                        condition = ReadString(obj, "Condition"),
                        chance = ParseChance(obj["Chance"]),
                        lifetime = ReadString(obj, "Lifetime"),
                        execution = ReadString(obj, "Execution"),
                        duration = ParseInt(ReadValue(obj["Duration"]), 0),
                        rawJson = obj.ToString(Formatting.None)
                    };
                    SetNumericValue(effect, obj["Value"]);
                    parsed.Add(effect);
                }

                fantasy.effects = parsed.ToArray();
                return true;
            }
            catch (Exception exception)
            {
                error = exception.Message;
                return false;
            }
        }

        public static bool TryApply(MonsterPatternData pattern, out string error)
        {
            error = string.Empty;
            if (pattern == null)
                return true;

            try
            {
                JObject root = JObject.Parse(pattern.rawEffects ?? string.Empty);
                pattern.condition = ReadString(root, "Condition");
                pattern.maxUses = root["Count"] == null || root["Count"].Type == JTokenType.Null
                    ? -1 : Mathf.Max(0, root["Count"].Value<int>());
                pattern.selfDestruct = root["SelfDestruct"]?.Value<bool>() ?? false;
                MonsterPatternKeyUtility.ApplyPatternKey(pattern, ReadString(root, "Attack"));

                JToken effectsToken = root["Effects"] ?? root["Effect"];
                if (effectsToken == null || effectsToken.Type == JTokenType.Null)
                {
                    pattern.effects = Array.Empty<MonsterPatternEffectData>();
                    return true;
                }

                JArray array = effectsToken as JArray ?? new JArray(effectsToken);
                List<MonsterPatternEffectData> parsed = new List<MonsterPatternEffectData>();
                foreach (JToken token in array)
                {
                    if (token is not JObject obj)
                        throw new JsonException("Each monster-pattern effect must be a JSON object.");

                    MonsterPatternEffectData effect = new MonsterPatternEffectData
                    {
                        timing = ReadString(obj, "Timing"),
                        target = ReadString(obj, "Target"),
                        action = ReadString(obj, "Action"),
                        type = ReadString(obj, "Type"),
                        condition = ReadString(obj, "Condition"),
                        valueExpression = ReadValue(obj["Value"]),
                        duration = ParseInt(ReadValue(obj["Duration"]), 0),
                        count = Mathf.Max(1, ParseInt(ReadValue(obj["Count"]), 1)),
                        hitCount = Mathf.Max(1, ParseInt(ReadValue(obj["HitCount"]), 1)),
                        lockDamage = ParseBool(obj["Lock"]),
                        mode = ReadString(obj, "Mode"),
                        label = ReadString(obj, "Label"),
                        editable = ParseBool(obj["Editable"]),
                        rawJson = obj.ToString(Formatting.None)
                    };
                    SetNumericValue(effect, obj["Value"]);
                    parsed.Add(effect);
                }

                pattern.effects = parsed.ToArray();
                return true;
            }
            catch (Exception exception)
            {
                error = exception.Message;
                return false;
            }
        }

        private static string ReadString(JObject obj, string key) => ReadValue(obj[key]);

        private static string ReadValue(JToken token)
        {
            if (token == null || token.Type == JTokenType.Null)
                return string.Empty;
            if (token is JValue value)
                return Convert.ToString(value.Value, CultureInfo.InvariantCulture);
            return token.ToString(Formatting.None);
        }

        private static int ParseInt(string value, int fallback)
        {
            if (int.TryParse(value, NumberStyles.Integer, CultureInfo.InvariantCulture, out int integer))
                return integer;
            return float.TryParse(value, NumberStyles.Float, CultureInfo.InvariantCulture, out float number)
                ? Mathf.RoundToInt(number) : fallback;
        }

        private static float ParseChance(JToken token)
        {
            if (!float.TryParse(ReadValue(token), NumberStyles.Float, CultureInfo.InvariantCulture, out float value))
                return 1f;
            return Mathf.Clamp01(value > 1f ? value * 0.01f : value);
        }

        private static bool ParseBool(JToken token)
        {
            string value = ReadValue(token).Trim().ToLowerInvariant();
            return value == "true" || value == "1" || value == "yes";
        }

        private static void SetNumericValue(FantasyEffectData effect, JToken token)
        {
            effect.hasNumericValue = token != null && (token.Type == JTokenType.Integer || token.Type == JTokenType.Float);
            if (effect.hasNumericValue)
                effect.numericValue = token.Value<float>();
        }

        private static void SetNumericValue(MonsterPatternEffectData effect, JToken token)
        {
            effect.hasNumericValue = token != null && (token.Type == JTokenType.Integer || token.Type == JTokenType.Float);
            if (effect.hasNumericValue)
                effect.numericValue = token.Value<float>();
        }
    }
}
