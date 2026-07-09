using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Text;
using GoldfishWalking.Data;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEngine;

namespace GoldfishWalking.Editor.DataImport
{
    public static class FantasyTsvImporter
    {
        private const string SourcePath = "Assets/Data/Raw/Fantasies.tsv";
        private const string DatabasePath = "Assets/Data/Generated/FantasyDatabase.asset";
        private const string ReportPath = "Assets/Data/Generated/FantasyImportReport.json";

        [MenuItem("GoldfishWalking/Data/Import Fantasy TSV")]
        public static void ImportFantasyTsv()
        {
            FantasyImportReport report = new FantasyImportReport
            {
                sourcePath = SourcePath,
                generatedAt = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture)
            };

            if (!File.Exists(SourcePath))
            {
                report.errors.Add($"Source file not found: {SourcePath}");
                WriteReport(report);
                Debug.LogError($"Fantasy import failed. {SourcePath} does not exist.");
                return;
            }

            List<Dictionary<string, string>> rows = ReadTsv(SourcePath);
            List<FantasyData> fantasies = new List<FantasyData>();
            HashSet<string> ids = new HashSet<string>();

            for (int i = 0; i < rows.Count; i++)
            {
                int rowNumber = i + 2;
                Dictionary<string, string> row = rows[i];

                string idText = Get(row, "ID");
                string dataCode = Get(row, "DataCode");
                string effectsText = Get(row, "Effects");
                if (string.IsNullOrWhiteSpace(dataCode) && string.IsNullOrWhiteSpace(effectsText))
                {
                    report.skippedRows.Add($"Row {rowNumber}: missing DataCode and Effects.");
                    continue;
                }

                FantasyData fantasy = new FantasyData
                {
                    sourceId = ParseInt(idText, 0),
                    dataCode = dataCode,
                    id = !string.IsNullOrWhiteSpace(dataCode) ? dataCode : idText,
                    devName = Get(row, "DevName"),
                    nameStringId = Get(row, "NameStringID"),
                    descStringId = Get(row, "DescStringID"),
                    triggerType = Get(row, "TriggerType"),
                    grade = ParseGrade(Get(row, "RARITY"), report, rowNumber),
                    displayName = Get(row, "DevName"),
                    description = Get(row, "DescStringID"),
                    sprite = Get(row, "Sprite"),
                    rawEffects = StripBackticks(effectsText)
                };

                if (string.IsNullOrWhiteSpace(fantasy.id))
                    fantasy.id = $"fantasy_row_{rowNumber}";

                if (!ids.Add(fantasy.id))
                    report.warnings.Add($"Row {rowNumber}: duplicate fantasy id '{fantasy.id}'.");

                ParseEffects(fantasy, report, rowNumber);
                ApplyLegacyFields(fantasy);
                fantasies.Add(fantasy);
            }

            FantasyDatabase database = AssetDatabase.LoadAssetAtPath<FantasyDatabase>(DatabasePath);
            if (database == null)
            {
                database = ScriptableObject.CreateInstance<FantasyDatabase>();
                EnsureDirectory(Path.GetDirectoryName(DatabasePath));
                AssetDatabase.CreateAsset(database, DatabasePath);
            }

            database.fantasies = fantasies;
            EditorUtility.SetDirty(database);
            AssetDatabase.SaveAssets();

            report.importedCount = fantasies.Count;
            report.databasePath = DatabasePath;
            WriteReport(report);
            AssetDatabase.Refresh();

            Debug.Log($"Imported {fantasies.Count} fantasies from {SourcePath}. Report: {ReportPath}");
        }

        private static void ParseEffects(FantasyData fantasy, FantasyImportReport report, int rowNumber)
        {
            if (string.IsNullOrWhiteSpace(fantasy.rawEffects))
            {
                report.warnings.Add($"Row {rowNumber} ({fantasy.id}): Effects is empty.");
                fantasy.effects = Array.Empty<FantasyEffectData>();
                return;
            }

            try
            {
                JToken root = JToken.Parse(fantasy.rawEffects);
                JArray array = root as JArray ?? new JArray(root);
                List<FantasyEffectData> effects = new List<FantasyEffectData>();

                foreach (JToken token in array)
                {
                    if (token is not JObject obj)
                    {
                        report.warnings.Add($"Row {rowNumber} ({fantasy.id}): effect entry is not an object.");
                        continue;
                    }

                    FantasyEffectData effect = new FantasyEffectData
                    {
                        trigger = ReadString(obj, "Trigger"),
                        target = ReadString(obj, "Target"),
                        calc = ReadString(obj, "Calc"),
                        valueExpression = ReadValueExpression(obj["Value"]),
                        option = ReadString(obj, "Option"),
                        rawJson = obj.ToString(Formatting.None)
                    };

                    if (TryParseFloat(effect.valueExpression, out float numericValue))
                    {
                        effect.hasNumericValue = true;
                        effect.numericValue = numericValue;
                    }

                    effects.Add(effect);
                }

                fantasy.effects = effects.ToArray();
            }
            catch (Exception ex)
            {
                fantasy.effects = Array.Empty<FantasyEffectData>();
                report.errors.Add($"Row {rowNumber} ({fantasy.id}): Effects JSON parse failed: {ex.Message}");
            }
        }

        private static void ApplyLegacyFields(FantasyData fantasy)
        {
            fantasy.trigger = ParseLegacyTrigger(fantasy.triggerType);
            fantasy.target = FantasyTarget.None;
            fantasy.value = 0;
            fantasy.specialHandler = string.Empty;

            if (fantasy.effects == null || fantasy.effects.Length == 0)
                return;

            FantasyEffectData first = fantasy.effects[0];
            fantasy.trigger = ParseLegacyTrigger(string.IsNullOrWhiteSpace(first.trigger) ? fantasy.triggerType : first.trigger);
            fantasy.target = ParseLegacyTarget(first.target);
            fantasy.value = first.hasNumericValue ? Mathf.RoundToInt(first.numericValue) : 0;
            fantasy.specialHandler = first.option;
        }

        private static FantasyGrade ParseGrade(string value, FantasyImportReport report, int rowNumber)
        {
            switch ((value ?? string.Empty).Trim().ToLowerInvariant())
            {
                case "white":
                    return FantasyGrade.White;
                case "blue":
                    return FantasyGrade.Blue;
                case "red":
                    return FantasyGrade.Red;
                default:
                    report.warnings.Add($"Row {rowNumber}: unknown RARITY '{value}', defaulted to White.");
                    return FantasyGrade.White;
            }
        }

        private static FantasyTrigger ParseLegacyTrigger(string value)
        {
            switch ((value ?? string.Empty).Trim().ToLowerInvariant())
            {
                case "passive":
                    return FantasyTrigger.Always;
                case "battle_start":
                    return FantasyTrigger.BattleStart;
                case "turn_end":
                    return FantasyTrigger.TurnEnd;
                case "deal_damage":
                case "attack":
                    return FantasyTrigger.OnHit;
                case "battle_reward":
                    return FantasyTrigger.BattleReward;
                case "rest":
                    return FantasyTrigger.Rest;
                case "shop_enter":
                case "shop_purchase":
                    return FantasyTrigger.Shop;
                case "":
                case "none":
                    return FantasyTrigger.None;
                default:
                    return FantasyTrigger.Special;
            }
        }

        private static FantasyTarget ParseLegacyTarget(string value)
        {
            switch ((value ?? string.Empty).Trim().ToLowerInvariant())
            {
                case "hp":
                    return FantasyTarget.Health;
                case "item":
                case "extra_match":
                case "eraser":
                    return FantasyTarget.Item;
                case "damage":
                case "additional_damage":
                case "base_damage":
                case "strength_damage":
                    return FantasyTarget.Damage;
                case "attack_count":
                    return FantasyTarget.Multiplier;
                case "strength":
                case "enemy_strength":
                    return FantasyTarget.Strength;
                case "fantasy":
                case "fantasy_reroll":
                case "change_fantasy":
                    return FantasyTarget.Formula;
                case "rest_count":
                    return FantasyTarget.Rest;
                case "shop_movement":
                case "price":
                case "item_cost":
                    return FantasyTarget.Shop;
                case "":
                case "none":
                    return FantasyTarget.None;
                default:
                    return FantasyTarget.Special;
            }
        }

        private static List<Dictionary<string, string>> ReadTsv(string path)
        {
            string[] lines = File.ReadAllLines(path, new UTF8Encoding(false, true));
            List<Dictionary<string, string>> rows = new List<Dictionary<string, string>>();
            if (lines.Length == 0)
                return rows;

            string[] headers = SplitTsvLine(lines[0]);
            for (int i = 1; i < lines.Length; i++)
            {
                string[] values = SplitTsvLine(lines[i]);
                Dictionary<string, string> row = new Dictionary<string, string>();
                for (int h = 0; h < headers.Length; h++)
                {
                    string header = headers[h].Trim();
                    if (string.IsNullOrEmpty(header))
                        continue;

                    row[header] = h < values.Length ? values[h].Trim() : string.Empty;
                }

                rows.Add(row);
            }

            return rows;
        }

        private static string[] SplitTsvLine(string line)
        {
            return (line ?? string.Empty).Split('\t');
        }

        private static string StripBackticks(string value)
        {
            string text = (value ?? string.Empty).Trim();
            if (text.Length > 0 && text[0] == '`')
                text = text.Substring(1).Trim();
            if (text.Length > 0 && text[text.Length - 1] == '`')
                text = text.Substring(0, text.Length - 1).Trim();

            return text;
        }

        private static string Get(Dictionary<string, string> row, string key)
        {
            return row.TryGetValue(key, out string value) ? value : string.Empty;
        }

        private static string ReadString(JObject obj, string key)
        {
            JToken token = obj[key];
            return token == null || token.Type == JTokenType.Null ? string.Empty : token.ToString();
        }

        private static string ReadValueExpression(JToken token)
        {
            if (token == null || token.Type == JTokenType.Null)
                return string.Empty;

            if (token.Type == JTokenType.Float || token.Type == JTokenType.Integer)
                return Convert.ToString(((JValue)token).Value, CultureInfo.InvariantCulture);

            return token.ToString();
        }

        private static int ParseInt(string value, int fallback)
        {
            if (int.TryParse(value, NumberStyles.Integer, CultureInfo.InvariantCulture, out int result))
                return result;

            if (float.TryParse(value, NumberStyles.Float, CultureInfo.InvariantCulture, out float floatValue))
                return Mathf.RoundToInt(floatValue);

            return fallback;
        }

        private static bool TryParseFloat(string value, out float result)
        {
            return float.TryParse(value, NumberStyles.Float, CultureInfo.InvariantCulture, out result);
        }

        private static void WriteReport(FantasyImportReport report)
        {
            EnsureDirectory(Path.GetDirectoryName(ReportPath));
            string json = JsonConvert.SerializeObject(report, Formatting.Indented);
            File.WriteAllText(ReportPath, json, new UTF8Encoding(false));
            AssetDatabase.ImportAsset(ReportPath);
        }

        private static void EnsureDirectory(string path)
        {
            if (!string.IsNullOrWhiteSpace(path) && !Directory.Exists(path))
                Directory.CreateDirectory(path);
        }

        [Serializable]
        private sealed class FantasyImportReport
        {
            public string sourcePath;
            public string databasePath;
            public string generatedAt;
            public int importedCount;
            public List<string> warnings = new List<string>();
            public List<string> errors = new List<string>();
            public List<string> skippedRows = new List<string>();
        }
    }
}
