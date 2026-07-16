using System;
using System.Collections.Generic;
using System.Globalization;

using System.Linq;
using System.IO;
using System.Text;
using GoldfishWalking.Data;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEngine;

namespace GoldfishWalking.Editor.DataImport
{
    public static class MonsterTsvImporter
    {
        private const string MonsterSourcePath = "Assets/Data/Raw/Monster.tsv";
        private const string MonsterRulesSourcePath = "Assets/Data/Raw/MonsterRules.tsv";
        private const string PatternSourcePath = "Assets/Data/Raw/Pattern.tsv";
        private const string MonsterDatabasePath = "Assets/Data/Generated/MonsterDatabase.asset";
        private const string PatternDatabasePath = "Assets/Data/Generated/MonsterPatternDatabase.asset";
        private const string ReportPath = "Assets/Data/Generated/MonsterImportReport.json";

        [MenuItem("GoldfishWalking/Data/Import Monster TSV")]
        public static void ImportMonsterTsv()
        {
            MonsterImportReport report = new MonsterImportReport
            {
                generatedAt = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture),
                monsterSourcePath = MonsterSourcePath,
                patternSourcePath = PatternSourcePath,
                monsterDatabasePath = MonsterDatabasePath,
                patternDatabasePath = PatternDatabasePath
            };

            List<MonsterPatternData> patterns = ImportPatterns(report);
            List<MonsterData> monsters = ImportMonsters(report);

            SaveDatabase(PatternDatabasePath, patterns);
            SaveDatabase(MonsterDatabasePath, monsters);

            report.importedPatternCount = patterns.Count;
            report.importedMonsterCount = monsters.Count;
            WriteReport(report);
            AssetDatabase.Refresh();

            Debug.Log($"Imported {monsters.Count} monsters and {patterns.Count} monster patterns. Report: {ReportPath}");
        }

        private static List<MonsterPatternData> ImportPatterns(MonsterImportReport report)
        {
            List<MonsterPatternData> patterns = new List<MonsterPatternData>();
            if (!File.Exists(PatternSourcePath))
            {
                report.errors.Add($"Pattern source file not found: {PatternSourcePath}");
                return patterns;
            }

            List<Dictionary<string, string>> rows = ReadTsv(PatternSourcePath);
            HashSet<string> ids = new HashSet<string>();
            for (int i = 0; i < rows.Count; i++)
            {
                int rowNumber = i + 2;
                Dictionary<string, string> row = rows[i];
                string dataCode = Get(row, "DataCode");
                string rawEffects = StripBackticks(Get(row, "Effects"));

                if (string.IsNullOrWhiteSpace(dataCode) && string.IsNullOrWhiteSpace(rawEffects))
                {
                    report.skippedPatternRows.Add($"Row {rowNumber}: missing DataCode and Effects.");
                    continue;
                }

                MonsterPatternData pattern = new MonsterPatternData
                {
                    sourceId = ParseInt(Get(row, "ID"), 0),
                    dataCode = dataCode,
                    id = !string.IsNullOrWhiteSpace(dataCode) ? dataCode : $"pattern_row_{rowNumber}",
                    devName = Get(row, "DevName"),
                    nameStringId = Get(row, "NameStringID"),
                    displayName = !string.IsNullOrWhiteSpace(Get(row, "DevName")) ? Get(row, "DevName") : dataCode,
                    description = Get(row, "설명"),
                    rawEffects = rawEffects,
                    sprite = Get(row, "SpriteRes")
                };

                if (!ids.Add(pattern.id))
                    report.warnings.Add($"Pattern row {rowNumber}: duplicate pattern id '{pattern.id}'.");

                ParsePatternJson(pattern, report, rowNumber);
                patterns.Add(pattern);
            }

            return patterns;
        }

        private static List<MonsterData> ImportMonsters(MonsterImportReport report)
        {
            List<MonsterData> monsters = new List<MonsterData>();
            if (!File.Exists(MonsterSourcePath))
            {
                report.errors.Add($"Monster source file not found: {MonsterSourcePath}");
                return monsters;
            }

            List<Dictionary<string, string>> rows = ReadTsv(MonsterSourcePath);
            Dictionary<string, Dictionary<string, string>> rulesByMonster = LoadMonsterRules();
            HashSet<string> ids = new HashSet<string>();
            for (int i = 0; i < rows.Count; i++)
            {
                int rowNumber = i + 2;
                Dictionary<string, string> row = rows[i];
                string id = Get(row, "ID");
                string dataName = Get(row, "DataName");
                rulesByMonster.TryGetValue(dataName, out Dictionary<string, string> rule);
                rule ??= new Dictionary<string, string>();
                if (string.IsNullOrWhiteSpace(id) && string.IsNullOrWhiteSpace(dataName))
                {
                    report.skippedMonsterRows.Add($"Row {rowNumber}: missing ID and DataName.");
                    continue;
                }

                string rawPatterns = Get(row, "PatternArray");
                MonsterData monster = new MonsterData
                {
                    id = !string.IsNullOrWhiteSpace(dataName) ? dataName : id,
                    sourceId = ParseInt(id, 0),
                    act = Mathf.Max(1, ParseInt(Get(row, "Act"), 1)),
                    difficulty = ParseDifficulty(Get(row, "Difficulty"), report, rowNumber),
                    devName = Get(row, "DevName"),
                    dataName = dataName,
                    nameStringId = Get(row, "NameStringID"),
                    descStringId = Get(row, "DescStringID"),
                    displayName = !string.IsNullOrWhiteSpace(Get(row, "DevName")) ? Get(row, "DevName") : dataName,
                    description = Get(row, "DescStringID"),
                    grade = ParseGrade(Get(row, "Type"), report, rowNumber),
                    baseHealth = Mathf.Max(1, ParseInt(Get(row, "BaseHP"), 1)),
                    baseStrength = ParseInt(Get(row, "BaseStrength"), 0),
                    rawPatternArray = rawPatterns,
                    patternIds = SplitPatternList(rawPatterns),
                    aiType = ParseAiType(Get(row, "AIType"), report, rowNumber),
                    sprite = Get(row, "Sprite"),
                    damageCap = Mathf.Max(0, ParseInt(Get(rule, "DamageCap"), 0)),
                    damageCapBreakThreshold = Mathf.Max(0, ParseInt(Get(rule, "DamageCapBreak"), 0)),
                    lifestealRate = Mathf.Max(0f, ParseFloat(Get(rule, "Lifesteal"), 0f)),
                    baseDamageLocked = ParseBool(Get(rule, "BaseDamageLocked")),
                    specialBoxLabel = Get(rule, "SpecialBoxLabel"),
                    specialBoxMin = ParseInt(Get(rule, "SpecialBoxMin"), 0),
                    specialBoxMax = ParseInt(Get(rule, "SpecialBoxMax"), 9),
                    specialBoxValue = ParseInt(Get(rule, "SpecialBoxValue"), -1),
                    countdownAction = Get(rule, "CountdownAction"),
                    countdownPattern = Get(rule, "CountdownPattern"),
                    aimedShotMultiplier = Mathf.Max(1, ParseInt(Get(rule, "AimedShotMultiplier"), 1)),
                    formulaDecoyDigitCount = Mathf.Max(0, ParseInt(Get(rule, "FormulaDecoyDigitCount"), 0)),
                    playerAttackConditionJson = Get(rule, "PlayerAttackCondition")
                };

                ParsePlayerAttackCondition(monster, report, rowNumber);

                
if (!ids.Add(monster.id))
                    report.warnings.Add($"Monster row {rowNumber}: duplicate monster id '{monster.id}'.");
                if (monster.patternIds == null || monster.patternIds.Length == 0)
                    report.warnings.Add($"Monster row {rowNumber} ({monster.id}): empty PatternArray, runtime will use 2_Single.");

                monsters.Add(monster);
            }

            return monsters;
        }

        private static void ParsePatternJson(MonsterPatternData pattern, MonsterImportReport report, int rowNumber)
        {
            if (string.IsNullOrWhiteSpace(pattern.rawEffects))
            {
                report.warnings.Add($"Pattern row {rowNumber} ({pattern.id}): Effects is empty.");
                ApplyAttackKey(pattern, string.Empty);
                return;
            }

            try
            {
                JObject root = JObject.Parse(pattern.rawEffects);
                ApplyAttackKey(pattern, ReadString(root, "Attack"));
                pattern.condition = ReadString(root, "Condition");
                pattern.maxUses = root["Count"] != null && root["Count"].Type != JTokenType.Null
                    ? Mathf.Max(0, root["Count"].Value<int>())
                    : -1;
                pattern.selfDestruct = root["SelfDestruct"]?.Value<bool>() ?? false;

                JToken effectsToken = root["Effects"] ?? root["Effect"];
                if (effectsToken == null || effectsToken.Type == JTokenType.Null)
                {
                    pattern.effects = Array.Empty<MonsterPatternEffectData>();
                    return;
                }

                JArray array = effectsToken as JArray ?? new JArray(effectsToken);
                List<MonsterPatternEffectData> effects = new List<MonsterPatternEffectData>();
                foreach (JToken token in array)
                {
                    if (token is not JObject obj)
                    {
                        report.warnings.Add($"Pattern row {rowNumber} ({pattern.id}): effect entry is not an object.");
                        continue;
                    }

                    MonsterPatternEffectData effect = new MonsterPatternEffectData
                    {
                        timing = ReadString(obj, "Timing"),
                        target = ReadString(obj, "Target"),
                        action = ReadString(obj, "Action"),
                        type = ReadString(obj, "Type"),
                        condition = ReadString(obj, "Condition"),
                        valueExpression = ReadValueExpression(obj["Value"]),
                        duration = ParseInt(ReadValueExpression(obj["Duration"]), 0),
                        count = Mathf.Max(1, ParseInt(ReadValueExpression(obj["Count"]), 1)),
                        hitCount = Mathf.Max(1, ParseInt(ReadValueExpression(obj["HitCount"]), 1)),
                        lockDamage = ParseBool(ReadValueExpression(obj["Lock"])),
                        mode = ReadString(obj, "Mode"),
                        label = ReadString(obj, "Label"),
                        editable = ParseBool(ReadValueExpression(obj["Editable"])),
                        rawJson = obj.ToString(Formatting.None)
                    };

                    if (TryParseFloat(effect.valueExpression, out float numericValue))
                    {
                        effect.hasNumericValue = true;
                        effect.numericValue = numericValue;
                    }

                    effects.Add(effect);
                }

                pattern.effects = effects.ToArray();
            }
            catch (Exception ex)
            {
                report.errors.Add($"Pattern row {rowNumber} ({pattern.id}): Effects JSON parse failed: {ex.Message}");
                ApplyAttackKey(pattern, string.Empty);
                pattern.effects = Array.Empty<MonsterPatternEffectData>();
            }
        }

        private static void ApplyAttackKey(MonsterPatternData pattern, string attackKey)
        {
            string normalized = MonsterPatternKeyUtility.NormalizePatternKey(attackKey);
            pattern.attackKey = normalized;
            MonsterPatternKeyUtility.ApplyPatternKey(pattern, normalized);
        }

        private static void SaveDatabase(string path, List<MonsterData> monsters)
        {
            MonsterDatabase database = AssetDatabase.LoadAssetAtPath<MonsterDatabase>(path);
            if (database == null)
            {
                database = ScriptableObject.CreateInstance<MonsterDatabase>();
                EnsureDirectory(Path.GetDirectoryName(path));
                AssetDatabase.CreateAsset(database, path);
            }

            database.monsters = monsters;
            EditorUtility.SetDirty(database);
            AssetDatabase.SaveAssets();
        }

        private static void SaveDatabase(string path, List<MonsterPatternData> patterns)
        {
            MonsterPatternDatabase database = AssetDatabase.LoadAssetAtPath<MonsterPatternDatabase>(path);
            if (database == null)
            {
                database = ScriptableObject.CreateInstance<MonsterPatternDatabase>();
                EnsureDirectory(Path.GetDirectoryName(path));
                AssetDatabase.CreateAsset(database, path);
            }

            database.patterns = patterns;
            EditorUtility.SetDirty(database);
            AssetDatabase.SaveAssets();
        }

        private static Dictionary<string, Dictionary<string, string>> LoadMonsterRules()
        {
            Dictionary<string, Dictionary<string, string>> result = new Dictionary<string, Dictionary<string, string>>();
            if (!File.Exists(MonsterRulesSourcePath))
                return result;
            foreach (Dictionary<string, string> row in ReadTsv(MonsterRulesSourcePath))
            {
                string dataName = Get(row, "DataName");
                if (!string.IsNullOrWhiteSpace(dataName))
                    result[dataName] = row;
            }
            return result;
        }

        private static List<Dictionary<string, string>> ReadTsv(string path)
        {
            string[] lines = File.ReadAllLines(path, new UTF8Encoding(false, true));
            List<Dictionary<string, string>> rows = new List<Dictionary<string, string>>();
            if (lines.Length == 0)
                return rows;

            int headerIndex = 0;
            while (headerIndex < lines.Length && string.IsNullOrWhiteSpace(lines[headerIndex].Replace("\t", string.Empty)))
                headerIndex++;

            if (headerIndex >= lines.Length)
                return rows;

            string[] headers = SplitTsvLine(lines[headerIndex]);
            for (int i = headerIndex + 1; i < lines.Length; i++)
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

        private static string[] SplitPatternList(string value)
        {
            string text = value ?? string.Empty;
            string[] tokens = text.Split(new[] { ',', ';', '|' }, StringSplitOptions.RemoveEmptyEntries);
            List<string> result = new List<string>();
            for (int i = 0; i < tokens.Length; i++)
            {
                string normalized = MonsterPatternKeyUtility.NormalizePatternKey(tokens[i]);
                if (!string.IsNullOrWhiteSpace(normalized))
                    result.Add(normalized);
            }

            return result.ToArray();
        }

        private static MonsterGrade ParseGrade(string value, MonsterImportReport report, int rowNumber)
        {
            switch ((value ?? string.Empty).Trim().ToLowerInvariant())
            {
                case "normal":
                    return MonsterGrade.Normal;
                case "elite":
                    return MonsterGrade.Elite;
                case "boss":
                    return MonsterGrade.Boss;
                default:
                    report.warnings.Add($"Monster row {rowNumber}: unknown Type '{value}', defaulted to Normal.");
                    return MonsterGrade.Normal;
            }
        }

        private static MonsterDifficulty ParseDifficulty(string value, MonsterImportReport report, int rowNumber)
        {
            switch ((value ?? string.Empty).Trim().ToLowerInvariant())
            {
                case "":
                    return MonsterDifficulty.None;
                case "easy":
                    return MonsterDifficulty.Easy;
                case "normal":
                    return MonsterDifficulty.Normal;
                case "hard":
                    return MonsterDifficulty.Hard;
                default:
                    report.warnings.Add($"Monster row {rowNumber}: unknown Difficulty '{value}', defaulted to None.");
                    return MonsterDifficulty.None;
            }
        }

        private static MonsterAiType ParseAiType(string value, MonsterImportReport report, int rowNumber)
        {
            switch ((value ?? string.Empty).Trim().ToLowerInvariant())
            {
                case "random":
                    return MonsterAiType.Random;
                case "static":
                case "":
                    return MonsterAiType.Static;
                default:
                    report.warnings.Add($"Monster row {rowNumber}: unknown AIType '{value}', defaulted to Static.");
                    return MonsterAiType.Static;
            }
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
            if (token.Type == JTokenType.Float || token.Type == JTokenType.Integer || token.Type == JTokenType.Boolean)
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

        private static float ParseFloat(string value, float fallback)
        {
            return float.TryParse(value, NumberStyles.Float, CultureInfo.InvariantCulture, out float result) ? result : fallback;
        }

        private static bool TryParseFloat(string value, out float result)
        {
            return float.TryParse(value, NumberStyles.Float, CultureInfo.InvariantCulture, out result);
        }

        private static bool ParseBool(string value)
        {
            string normalized = (value ?? string.Empty).Trim().ToLowerInvariant();
            return normalized == "true" || normalized == "1" || normalized == "yes";
        }

        private static void WriteReport(MonsterImportReport report)
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
        private sealed class MonsterImportReport
        {
            public string monsterSourcePath;
            public string patternSourcePath;
            public string monsterDatabasePath;
            public string patternDatabasePath;
            public string generatedAt;
            public int importedMonsterCount;
            public int importedPatternCount;
            public List<string> warnings = new List<string>();
            public List<string> errors = new List<string>();
            public List<string> skippedMonsterRows = new List<string>();
            public List<string> skippedPatternRows = new List<string>();
        }
    

private static void ParsePlayerAttackCondition(MonsterData monster, MonsterImportReport report, int rowNumber)
        {
            if (monster == null || string.IsNullOrWhiteSpace(monster.playerAttackConditionJson))
                return;
            try
            {
                JObject root = JObject.Parse(monster.playerAttackConditionJson.Trim().Trim('`'));
                monster.playerAttackConditionType = ReadString(root, "Type");
                monster.conditionValueMin = root["ValueMin"]?.Value<int>() ?? 0;
                monster.conditionValueMax = root["ValueMax"]?.Value<int>() ?? monster.conditionValueMin;
                monster.conditionCountMin = root["CountMin"]?.Value<int>() ?? 0;
                monster.conditionCountMax = root["CountMax"]?.Value<int>() ?? monster.conditionCountMin;
                monster.conditionCountEditable = root["CountEditable"]?.Value<bool>() ?? false;
                JArray operators = root["Operators"] as JArray;
                monster.conditionOperators = operators != null ? operators.Values<string>().ToArray() : Array.Empty<string>();
            }
            catch (Exception ex)
            {
                report.warnings.Add($"Monster row {rowNumber}: invalid PlayerAttackCondition JSON ({ex.Message}).");
            }
        }
}
}
