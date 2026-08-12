using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Text;
using GoldfishWalking.Data;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEngine;

namespace GoldfishWalking.Editor.DataImport
{
    public static class GameplayJsonImporter
    {
        private const string SourceRoot = "Assets/Data/Json";
        private const string MonsterSourceRoot = SourceRoot + "/monsters";
        private const string PatternSourceRoot = SourceRoot + "/patterns";
        private const string FantasySourceRoot = SourceRoot + "/fantasies";
        private const string MonsterDatabasePath = "Assets/Data/Generated/MonsterDatabase.asset";
        private const string PatternDatabasePath = "Assets/Data/Generated/MonsterPatternDatabase.asset";
        private const string FantasyDatabasePath = "Assets/Data/Generated/FantasyDatabase.asset";
        private const string ReportPath = "Assets/Data/Generated/GameplayJsonImportReport.json";

        private static bool importing;

        [MenuItem("GoldfishWalking/Data/Import All Gameplay JSON")]
        public static void ImportAll()
        {
            if (importing)
                return;

            importing = true;
            try
            {
                ImportReport report = new ImportReport
                {
                    sourceRoot = SourceRoot,
                    generatedAt = DateTime.Now.ToString("yyyy-MM-dd HH:mm:ss", CultureInfo.InvariantCulture)
                };

                List<MonsterPatternData> patterns = ImportPatterns(report);
                List<MonsterData> monsters = ImportMonsters(report);
                List<FantasyData> fantasies = ImportFantasies(report);
                ValidateReferences(monsters, patterns, report);

                report.importedMonsterCount = monsters.Count;
                report.importedPatternCount = patterns.Count;
                report.importedFantasyCount = fantasies.Count;

                if (report.errors.Count > 0)
                {
                    WriteReport(report);
                    AssetDatabase.Refresh();
                    Debug.LogError($"Gameplay JSON import failed with {report.errors.Count} error(s). Existing generated databases were preserved. See {ReportPath}.");
                    return;
                }

                SaveDatabase(MonsterDatabasePath, monsters);
                SaveDatabase(PatternDatabasePath, patterns);
                SaveDatabase(FantasyDatabasePath, fantasies);
                WriteReport(report);
                AssetDatabase.SaveAssets();
                AssetDatabase.Refresh();
                Debug.Log($"Imported {monsters.Count} monsters, {patterns.Count} patterns, and {fantasies.Count} fantasies from JSON. Report: {ReportPath}");
            }
            finally
            {
                importing = false;
            }
        }

        private static List<MonsterData> ImportMonsters(ImportReport report)
        {
            List<MonsterData> result = new List<MonsterData>();
            foreach (SourceDocument source in ReadDocuments(MonsterSourceRoot, report))
            {
                JObject root = source.Root;
                if (!ReadBool(root, "enabled", true))
                    continue;

                string id = ReadString(root, "id");
                if (!RequireId(id, source.Path, report))
                    continue;

                JObject localization = Object(root, "localization");
                JObject presentation = Object(root, "presentation");
                JObject encounter = Object(root, "encounter");
                JObject stats = Object(root, "stats");
                JObject ai = Object(root, "ai");
                MonsterData monster = new MonsterData
                {
                    id = id,
                    dataName = id,
                    sourceId = ReadInt(root, "sourceId"),
                    devName = ReadString(root, "designerName"),
                    displayName = ReadString(root, "designerName"),
                    description = ReadString(root, "designerNote"),
                    nameStringId = ReadString(localization, "name"),
                    descStringId = ReadString(localization, "description"),
                    sprite = ReadString(presentation, "sprite"),
                    act = Mathf.Max(1, ReadInt(encounter, "act", 1)),
                    grade = ParseMonsterGrade(ReadString(encounter, "grade"), source.Path, report),
                    difficulty = ParseMonsterDifficulty(ReadString(encounter, "difficulty"), source.Path, report),
                    baseHealth = Mathf.Max(1, ReadInt(stats, "health", 1)),
                    baseStrength = ReadInt(stats, "strength"),
                    aiType = ParseMonsterAi(ReadString(ai, "mode"), source.Path, report),
                    patternIds = Array(ai, "patterns").Values<string>().Where(value => !string.IsNullOrWhiteSpace(value)).ToArray(),
                    aimedShotMultiplier = 1,
                    specialBoxMax = 9,
                    specialBoxValue = -1
                };
                monster.rawPatternArray = string.Join(", ", monster.patternIds);
                ApplyMonsterPassives(monster, Array(root, "passives"), source.Path, report);
                result.Add(monster);
            }

            ValidateUniqueIds(result.Select(item => item.id), "monster", report);
            return result.OrderBy(item => item.sourceId).ThenBy(item => item.id, StringComparer.OrdinalIgnoreCase).ToList();
        }

        private static void ApplyMonsterPassives(MonsterData monster, JArray passives, string path, ImportReport report)
        {
            foreach (JObject passive in passives.OfType<JObject>())
            {
                string operation = Normalize(ReadString(passive, "operation"));
                switch (operation)
                {
                    case "limitincomingdamage":
                        monster.damageCap = Mathf.Max(0, ReadInt(passive, "maximum"));
                        monster.damageCapBreakThreshold = Mathf.Max(0, ReadComparisonRight(Object(passive, "until")));
                        break;
                    case "lifesteal":
                        monster.lifestealRate = Mathf.Max(0f, ReadFloat(passive, "ratio"));
                        break;
                    case "lockbox":
                        monster.baseDamageLocked = true;
                        break;
                    case "aimedshot":
                        monster.aimedShotMultiplier = Mathf.Max(1, ReadInt(passive, "multiplier", 1));
                        break;
                    case "addformuladecoydigits":
                        monster.formulaDecoyDigitCount = Mathf.Max(0, ReadInt(passive, "count"));
                        break;
                    case "requireformulacondition":
                        ApplyPlayerAttackCondition(monster, Object(passive, "configuration"));
                        break;
                    case "countdown":
                        ApplySpecialBox(monster, Object(passive, "box"));
                        JObject onZero = Object(passive, "onZero");
                        string onZeroOperation = Normalize(ReadString(onZero, "operation"));
                        if (onZeroOperation == "executepattern")
                        {
                            monster.countdownAction = "Pattern";
                            monster.countdownPattern = ReadString(onZero, "pattern");
                        }
                        else if (onZeroOperation == "endbattle")
                        {
                            string result = Normalize(ReadString(onZero, "result"));
                            monster.countdownAction = result == "escape" || result == "monsterescape" ? "Escape" : ReadString(onZero, "result");
                        }
                        break;
                    case "createspecialbox":
                        ApplySpecialBox(monster, Object(passive, "box"));
                        break;
                    default:
                        report.warnings.Add($"{path}: unsupported monster passive operation '{ReadString(passive, "operation")}'.");
                        break;
                }
            }
        }

        private static void ApplySpecialBox(MonsterData monster, JObject box)
        {
            monster.specialBoxLabel = ReadString(box, "label");
            monster.specialBoxMin = ReadInt(box, "minimum");
            monster.specialBoxMax = ReadInt(box, "maximum", 9);
            monster.specialBoxValue = ReadInt(box, "initialValue", -1);
        }

        private static void ApplyPlayerAttackCondition(MonsterData monster, JObject config)
        {
            monster.playerAttackConditionType = ReadString(config, "Type");
            monster.conditionValueMin = ReadInt(config, "ValueMin");
            monster.conditionValueMax = ReadInt(config, "ValueMax", monster.conditionValueMin);
            monster.conditionCountMin = ReadInt(config, "CountMin");
            monster.conditionCountMax = ReadInt(config, "CountMax", monster.conditionCountMin);
            monster.conditionCountEditable = ReadBool(config, "CountEditable");
            monster.conditionOperators = Array(config, "Operators").Values<string>().ToArray();
            monster.playerAttackConditionJson = config.HasValues ? config.ToString(Formatting.None) : string.Empty;
        }

        private static List<MonsterPatternData> ImportPatterns(ImportReport report)
        {
            List<MonsterPatternData> result = new List<MonsterPatternData>();
            foreach (SourceDocument source in ReadDocuments(PatternSourceRoot, report))
            {
                JObject root = source.Root;
                if (!ReadBool(root, "enabled", true))
                    continue;

                string id = ReadString(root, "id");
                if (!RequireId(id, source.Path, report))
                    continue;

                JObject localization = Object(root, "localization");
                JObject presentation = Object(root, "presentation");
                JObject availability = Object(root, "availability");
                JObject metadata = Object(root, "metadata");
                MonsterPatternData pattern = new MonsterPatternData
                {
                    id = id,
                    dataCode = id,
                    sourceId = ReadInt(root, "sourceId"),
                    devName = ReadString(root, "designerName"),
                    displayName = Coalesce(ReadString(root, "designerName"), id),
                    description = ReadString(root, "designerNote"),
                    nameStringId = ReadString(localization, "name"),
                    sprite = ReadString(presentation, "sprite"),
                    maxUses = availability["maxUsesPerBattle"] == null || availability["maxUsesPerBattle"].Type == JTokenType.Null
                        ? -1 : Mathf.Max(0, availability["maxUsesPerBattle"].Value<int>()),
                    condition = ConditionToLegacy(availability["condition"]),
                    selfDestruct = ReadBool(metadata, "selfDestruct")
                };

                ApplyAttack(pattern, root["attack"], source.Path, report);
                pattern.effects = ConvertPatternEffects(Array(root, "effects"), metadata, source.Path, report);
                pattern.rawEffects = BuildPatternCompatibilityJson(pattern);
                result.Add(pattern);
            }

            ValidateUniqueIds(result.Select(item => item.id), "pattern", report);
            return result.OrderBy(item => item.sourceId).ThenBy(item => item.id, StringComparer.OrdinalIgnoreCase).ToList();
        }

        private static void ApplyAttack(MonsterPatternData pattern, JToken attackToken, string path, ImportReport report)
        {
            if (attackToken == null || attackToken.Type == JTokenType.Null)
            {
                MonsterPatternKeyUtility.ApplyPatternKey(pattern, string.Empty);
                return;
            }

            JObject attack = attackToken as JObject;
            if (attack == null)
            {
                report.errors.Add($"{path}: attack must be an object or null.");
                return;
            }

            string key = ReadString(attack, "formulaKey");
            JObject nonDamage = Object(attack, "nonDamageAction");
            if (string.IsNullOrWhiteSpace(key) && nonDamage.HasValues && Normalize(ReadString(nonDamage, "operation")) == "modifystat")
                key = $"Str_{ReadInt(nonDamage, "amount")}";

            JObject damage = Object(attack, "damage");
            JObject hits = Object(attack, "hits");
            if (string.IsNullOrWhiteSpace(key) && damage.HasValues)
            {
                int damageDigits = Mathf.Max(1, ReadInt(damage, "digits", 1));
                JObject initialValue = Object(damage, "initialValue");
                string dynamicExpression = ReadExpression(initialValue);
                if (!string.IsNullOrWhiteSpace(dynamicExpression))
                    key = dynamicExpression + "_Single";
                else if (hits["fixed"] != null && ReadInt(hits, "fixed", 1) == 1)
                    key = damageDigits + "_Single";
                else
                    key = $"{damageDigits}_Multi_{Mathf.Max(1, ReadInt(hits, "digits", 1))}";
            }

            MonsterPatternKeyUtility.ApplyPatternKey(pattern, key);
        }

        private static MonsterPatternEffectData[] ConvertPatternEffects(JArray sourceEffects, JObject metadata, string path, ImportReport report)
        {
            List<MonsterPatternEffectData> result = new List<MonsterPatternEffectData>();
            bool editableHeal = ReadBool(metadata, "editableHeal");
            string specialBoxMode = ReadString(metadata, "specialBoxMode");
            foreach (JObject source in sourceEffects.OfType<JObject>())
            {
                string operation = Normalize(ReadString(source, "operation"));
                MonsterPatternEffectData effect = new MonsterPatternEffectData
                {
                    timing = ReadString(Object(source, "trigger"), "event"),
                    target = PatternTargetToLegacy(Object(source, "target")),
                    action = PatternOperationToLegacy(operation),
                    type = ReadString(source, "type"),
                    condition = ConditionToLegacy(source["condition"]),
                    valueExpression = ValueToLegacy(source["amount"]),
                    duration = ReadInt(Object(source, "duration"), "turns"),
                    count = Mathf.Max(1, ReadInt(source, "repeat", 1)),
                    hitCount = Mathf.Max(1, ReadInt(source, "hitCount", 1)),
                    lockDamage = ReadBool(source, "lockDamage"),
                    mode = Coalesce(ReadString(source, "presentationMode"), operation == "createformulabox" ? specialBoxMode : string.Empty),
                    label = ReadString(source, "label"),
                    editable = ReadBool(source, "editable") || (operation == "heal" && editableHeal)
                };
                effect.timingKind = GameplayEffectTypeParser.ParseTiming(effect.timing);
                effect.targetKind = GameplayEffectTypeParser.ParseTarget(effect.target);
                effect.operationKind = GameplayEffectTypeParser.ParseOperation(effect.action);
                if (TryParseFloat(effect.valueExpression, out float numeric))
                {
                    effect.hasNumericValue = true;
                    effect.numericValue = numeric;
                }
                effect.rawJson = BuildPatternEffectCompatibilityJson(effect);
                result.Add(effect);
            }
            return result.ToArray();
        }

        private static List<FantasyData> ImportFantasies(ImportReport report)
        {
            List<FantasyData> result = new List<FantasyData>();
            foreach (SourceDocument source in ReadDocuments(FantasySourceRoot, report))
            {
                JObject root = source.Root;
                if (!ReadBool(root, "enabled", true))
                    continue;

                string id = ReadString(root, "id");
                if (!RequireId(id, source.Path, report))
                    continue;

                JObject localization = Object(root, "localization");
                JObject presentation = Object(root, "presentation");
                List<FantasyEffectData> effects = new List<FantasyEffectData>();
                foreach (JObject effectSource in Array(root, "effects").OfType<JObject>())
                    effects.Add(ConvertFantasyEffect(effectSource));

                string defaultTrigger = Array(root, "tags").Values<string>().FirstOrDefault() ?? string.Empty;
                FantasyData fantasy = new FantasyData
                {
                    id = id,
                    dataCode = id,
                    sourceId = ReadInt(root, "sourceId"),
                    devName = ReadString(root, "designerName"),
                    displayName = ReadString(root, "designerName"),
                    description = ReadString(root, "designerNote"),
                    nameStringId = ReadString(localization, "name"),
                    descStringId = ReadString(localization, "description"),
                    sprite = ReadString(presentation, "sprite"),
                    grade = ParseFantasyGrade(ReadString(root, "rarity"), source.Path, report),
                    triggerType = defaultTrigger,
                    effects = effects.ToArray()
                };
                fantasy.rawEffects = new JArray(effects.Select(effect => JObject.Parse(effect.rawJson))).ToString(Formatting.None);
                ApplyFantasyLegacyFields(fantasy);
                result.Add(fantasy);
            }

            ValidateUniqueIds(result.Select(item => item.id), "fantasy", report);
            return result.OrderBy(item => item.sourceId).ThenBy(item => item.id, StringComparer.OrdinalIgnoreCase).ToList();
        }

        private static FantasyEffectData ConvertFantasyEffect(JObject source)
        {
            string operation = Normalize(ReadString(source, "operation"));
            string calc = ReadString(source, "mode");
            if (string.IsNullOrWhiteSpace(calc))
                calc = FantasyOperationToLegacy(operation);
            string trigger = ReadString(Object(source, "trigger"), "event");
            if (Normalize(trigger) == "valueevaluation")
                trigger = string.Empty;
            FantasyEffectData effect = new FantasyEffectData
            {
                trigger = trigger,
                target = FantasyTargetToLegacy(Object(source, "target")),
                calc = calc,
                valueExpression = ValueToLegacy(source["amount"]),
                option = OptionsToLegacy(source["options"]),
                condition = ConditionToLegacy(source["condition"]),
                chance = Mathf.Clamp01(ReadFloat(Object(source, "chance"), "percent", 100f) * 0.01f),
                lifetime = ReadString(source, "lifetime"),
                execution = ReadString(source, "execution"),
                duration = ReadInt(Object(source, "duration"), "turns")
            };
            effect.timingKind = GameplayEffectTypeParser.ParseTiming(effect.trigger);
            effect.targetKind = GameplayEffectTypeParser.ParseTarget(effect.target);
            effect.operationKind = GameplayEffectTypeParser.ParseOperation(calc);
            if (TryParseFloat(effect.valueExpression, out float numeric))
            {
                effect.hasNumericValue = true;
                effect.numericValue = numeric;
            }
            effect.rawJson = BuildFantasyEffectCompatibilityJson(effect);
            return effect;
        }

        private static void ApplyFantasyLegacyFields(FantasyData fantasy)
        {
            FantasyEffectData first = fantasy.effects.FirstOrDefault();
            fantasy.trigger = ParseLegacyFantasyTrigger(first?.trigger ?? fantasy.triggerType);
            fantasy.target = ParseLegacyFantasyTarget(first?.target);
            fantasy.value = first != null && first.hasNumericValue ? Mathf.RoundToInt(first.numericValue) : 0;
            fantasy.specialHandler = first?.option ?? string.Empty;
        }

        private static string PatternOperationToLegacy(string operation)
        {
            return operation switch
            {
                "addstatus" => "AddBuff",
                "setstatus" => "SetBuff",
                "removestatus" => "RemoveBuff",
                "multiplystat" => "MultiplyBuff",
                "dealdamage" => "Damage",
                "splitbox" => "Split",
                "lockbox" => "Lock",
                "createformulabox" => "AddBox",
                "setformulavalue" => "SetValue",
                _ => operation
            };
        }

        private static string FantasyOperationToLegacy(string operation)
        {
            return operation switch
            {
                "modifyvalue" => "Add",
                "setvalue" => "Set",
                "transformvalue" => "Transform",
                "combinefantasies" => "Combine",
                _ => operation
            };
        }

        private static string PatternTargetToLegacy(JObject target)
        {
            string actor = ReadString(target, "actor");
            if (!string.IsNullOrWhiteSpace(actor)) return actor;
            string key = ReadString(target, "key");
            if (!string.IsNullOrWhiteSpace(key)) return key;
            string formula = ReadString(target, "formula");
            if (formula.StartsWith("player", StringComparison.OrdinalIgnoreCase)) return "Player";
            if (formula.StartsWith("monster", StringComparison.OrdinalIgnoreCase)) return "Self";
            return "Self";
        }

        private static string FantasyTargetToLegacy(JObject target)
        {
            string key = ReadString(target, "key");
            if (!string.IsNullOrWhiteSpace(key)) return key;
            string system = ReadString(target, "system");
            string property = ReadString(target, "property");
            if (!string.IsNullOrWhiteSpace(system) && !string.IsNullOrWhiteSpace(property))
            {
                if (system == "battle" && property == "movement_limit") return "Movement";
                if (system == "reward" && property == "fantasy_rerolls") return "Fantasy_Reroll";
                if (system == "reward" && property == "item_chance") return "Item_Chance";
                if (system == "rest" && property == "use_count") return "Rest_Count";
                if (system == "shop" && property == "movement_limit") return "Shop_Movement";
                if (system == "shop" && property == "price") return "Price";
                return property;
            }
            string stat = ReadString(target, "stat");
            if (stat == "health") return "HP";
            if (stat == "strength") return ReadString(target, "actor") == "monster" ? "Enemy_Strength" : "Strength";
            string formula = ReadString(target, "formula");
            if (formula == "player.damage") return "Base_Damage";
            if (formula == "player.hits") return "Attack_Count";
            string value = ReadString(target, "value");
            if (value == "incoming_damage") return "Damage_Taken";
            if (ReadString(target, "actor") == "attacker") return "Damage_Reflect";
            if (ReadString(target, "actor") == "monster") return "Additional_Damage";
            return ReadString(target, "context");
        }

        private static string ValueToLegacy(JToken token)
        {
            if (token == null || token.Type == JTokenType.Null) return string.Empty;
            if (token is JObject obj && obj["expression"] != null) return ReadString(obj, "expression");
            if (token is JValue value) return Convert.ToString(value.Value, CultureInfo.InvariantCulture);
            return token.ToString(Formatting.None);
        }

        private static string ConditionToLegacy(JToken token)
        {
            if (token == null || token.Type == JTokenType.Null) return string.Empty;
            if (token is not JObject condition) return token.ToString(Formatting.None);
            if (condition["expression"] != null) return ReadString(condition, "expression");
            JObject comparison = Object(condition, "comparison");
            if (comparison.HasValues)
            {
                string left = ReadString(Object(comparison, "left"), "variable").Replace("_", string.Empty);
                string op = ReadString(comparison, "operator");
                JToken right = comparison["right"];
                string rightText = right is JObject rightObject ? ReadString(rightObject, "variable").Replace("_", string.Empty) : ValueToLegacy(right);
                return left + op + rightText;
            }
            return condition.ToString(Formatting.None);
        }

        private static string OptionsToLegacy(JToken token)
        {
            if (token == null || token.Type == JTokenType.Null) return string.Empty;
            if (token is JArray array) return string.Join(",", array.Values<string>());
            return token.ToString();
        }

        private static int ReadComparisonRight(JObject condition)
        {
            return ReadInt(Object(condition, "comparison"), "right");
        }

        private static string ReadExpression(JObject value) => ReadString(value, "expression");

        private static string BuildPatternCompatibilityJson(MonsterPatternData pattern)
        {
            JObject root = new JObject
            {
                ["Attack"] = string.IsNullOrWhiteSpace(pattern.attackKey) ? null : pattern.attackKey,
                ["Condition"] = string.IsNullOrWhiteSpace(pattern.condition) ? null : pattern.condition,
                ["Count"] = pattern.maxUses < 0 ? null : pattern.maxUses,
                ["SelfDestruct"] = pattern.selfDestruct,
                ["Effects"] = new JArray(pattern.effects.Select(effect => JObject.Parse(effect.rawJson)))
            };
            return root.ToString(Formatting.None);
        }

        private static string BuildPatternEffectCompatibilityJson(MonsterPatternEffectData effect)
        {
            JObject obj = new JObject
            {
                ["Timing"] = effect.timing,
                ["Target"] = effect.target,
                ["Action"] = effect.action,
                ["Type"] = effect.type,
                ["Condition"] = effect.condition,
                ["Value"] = LegacyValueToken(effect.valueExpression),
                ["Duration"] = effect.duration,
                ["Count"] = effect.count,
                ["HitCount"] = effect.hitCount,
                ["Lock"] = effect.lockDamage,
                ["Mode"] = effect.mode,
                ["Label"] = effect.label,
                ["Editable"] = effect.editable
            };
            return obj.ToString(Formatting.None);
        }

        private static string BuildFantasyEffectCompatibilityJson(FantasyEffectData effect)
        {
            JObject obj = new JObject
            {
                ["Trigger"] = effect.trigger,
                ["Target"] = effect.target,
                ["Calc"] = effect.calc,
                ["Value"] = LegacyValueToken(effect.valueExpression),
                ["Option"] = effect.option,
                ["Condition"] = effect.condition,
                ["Chance"] = effect.chance,
                ["Lifetime"] = effect.lifetime,
                ["Execution"] = effect.execution,
                ["Duration"] = effect.duration
            };
            return obj.ToString(Formatting.None);
        }

        private static JToken LegacyValueToken(string value)
        {
            return TryParseFloat(value, out float number) ? new JValue(number) : new JValue(value ?? string.Empty);
        }

        private static IEnumerable<SourceDocument> ReadDocuments(string directory, ImportReport report)
        {
            if (!Directory.Exists(directory))
            {
                report.errors.Add($"JSON source directory not found: {directory}");
                yield break;
            }

            foreach (string path in Directory.GetFiles(directory, "*.json", SearchOption.TopDirectoryOnly).OrderBy(value => value, StringComparer.OrdinalIgnoreCase))
            {
                JObject root;
                try
                {
                    root = JObject.Parse(File.ReadAllText(path, new UTF8Encoding(false, true)));
                }
                catch (Exception ex)
                {
                    report.errors.Add($"{path}: invalid JSON ({ex.Message}).");
                    continue;
                }
                if (ReadInt(root, "schemaVersion") != 1)
                {
                    report.errors.Add($"{path}: unsupported or missing schemaVersion. Expected 1.");
                    continue;
                }
                yield return new SourceDocument(path.Replace('\\', '/'), root);
            }
        }

        private static void ValidateReferences(List<MonsterData> monsters, List<MonsterPatternData> patterns, ImportReport report)
        {
            HashSet<string> ids = new HashSet<string>(patterns.Select(item => item.id), StringComparer.OrdinalIgnoreCase);
            foreach (MonsterData monster in monsters)
            {
                foreach (string patternId in monster.patternIds ?? System.Array.Empty<string>())
                {
                    if (!ids.Contains(patternId) && !IsBuiltInPattern(patternId))
                        report.errors.Add($"Monster '{monster.id}' references missing pattern '{patternId}'.");
                }
            }
        }

        private static bool IsBuiltInPattern(string id)
        {
            MonsterPatternData pattern = MonsterPatternKeyUtility.CreateFromKey(id);
            return pattern.patternType != MonsterPatternType.Special || string.Equals(id, "Skip", StringComparison.OrdinalIgnoreCase);
        }

        private static bool RequireId(string id, string path, ImportReport report)
        {
            if (!string.IsNullOrWhiteSpace(id)) return true;
            report.errors.Add($"{path}: id is required.");
            return false;
        }

        private static void ValidateUniqueIds(IEnumerable<string> ids, string kind, ImportReport report)
        {
            HashSet<string> seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            foreach (string id in ids)
                if (!seen.Add(id)) report.errors.Add($"Duplicate {kind} id '{id}'.");
        }

        private static MonsterGrade ParseMonsterGrade(string value, string path, ImportReport report)
        {
            if (Enum.TryParse(value, true, out MonsterGrade parsed)) return parsed;
            report.errors.Add($"{path}: invalid monster grade '{value}'.");
            return MonsterGrade.Normal;
        }

        private static MonsterDifficulty ParseMonsterDifficulty(string value, string path, ImportReport report)
        {
            if (string.IsNullOrWhiteSpace(value)) return MonsterDifficulty.None;
            if (Enum.TryParse(value, true, out MonsterDifficulty parsed)) return parsed;
            report.errors.Add($"{path}: invalid monster difficulty '{value}'.");
            return MonsterDifficulty.None;
        }

        private static MonsterAiType ParseMonsterAi(string value, string path, ImportReport report)
        {
            if (Enum.TryParse(value, true, out MonsterAiType parsed)) return parsed;
            report.errors.Add($"{path}: invalid monster AI mode '{value}'.");
            return MonsterAiType.Static;
        }

        private static FantasyGrade ParseFantasyGrade(string value, string path, ImportReport report)
        {
            if (Enum.TryParse(value, true, out FantasyGrade parsed)) return parsed;
            report.errors.Add($"{path}: invalid fantasy rarity '{value}'.");
            return FantasyGrade.White;
        }

        private static FantasyTrigger ParseLegacyFantasyTrigger(string value)
        {
            return Normalize(value) switch
            {
                "passive" => FantasyTrigger.Always,
                "battlestart" => FantasyTrigger.BattleStart,
                "turnend" => FantasyTrigger.TurnEnd,
                "dealdamage" or "attack" => FantasyTrigger.OnHit,
                "battlereward" => FantasyTrigger.BattleReward,
                "rest" => FantasyTrigger.Rest,
                "shopenter" or "shoppurchase" => FantasyTrigger.Shop,
                "" or "none" => FantasyTrigger.None,
                _ => FantasyTrigger.Special
            };
        }

        private static FantasyTarget ParseLegacyFantasyTarget(string value)
        {
            return Normalize(value) switch
            {
                "hp" => FantasyTarget.Health,
                "item" or "extramatch" or "eraser" => FantasyTarget.Item,
                "damage" or "additionaldamage" or "basedamage" or "strengthdamage" => FantasyTarget.Damage,
                "attackcount" => FantasyTarget.Multiplier,
                "strength" or "enemystrength" => FantasyTarget.Strength,
                "fantasy" or "fantasyreroll" or "changefantasy" => FantasyTarget.Formula,
                "restcount" => FantasyTarget.Rest,
                "shopmovement" or "price" or "itemcost" => FantasyTarget.Shop,
                "" or "none" => FantasyTarget.None,
                _ => FantasyTarget.Special
            };
        }

        private static void SaveDatabase(string path, List<MonsterData> values)
        {
            MonsterDatabase database = AssetDatabase.LoadAssetAtPath<MonsterDatabase>(path) ?? CreateAsset<MonsterDatabase>(path);
            database.monsters = values;
            EditorUtility.SetDirty(database);
        }

        private static void SaveDatabase(string path, List<MonsterPatternData> values)
        {
            MonsterPatternDatabase database = AssetDatabase.LoadAssetAtPath<MonsterPatternDatabase>(path) ?? CreateAsset<MonsterPatternDatabase>(path);
            database.patterns = values;
            EditorUtility.SetDirty(database);
        }

        private static void SaveDatabase(string path, List<FantasyData> values)
        {
            FantasyDatabase database = AssetDatabase.LoadAssetAtPath<FantasyDatabase>(path) ?? CreateAsset<FantasyDatabase>(path);
            database.fantasies = values;
            EditorUtility.SetDirty(database);
        }

        private static T CreateAsset<T>(string path) where T : ScriptableObject
        {
            Directory.CreateDirectory(Path.GetDirectoryName(path) ?? "Assets/Data/Generated");
            T asset = ScriptableObject.CreateInstance<T>();
            AssetDatabase.CreateAsset(asset, path);
            return asset;
        }

        private static void WriteReport(ImportReport report)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(ReportPath) ?? "Assets/Data/Generated");
            File.WriteAllText(ReportPath, JsonConvert.SerializeObject(report, Formatting.Indented), new UTF8Encoding(false));
            AssetDatabase.ImportAsset(ReportPath);
        }

        private static JObject Object(JObject root, string name) => root?[name] as JObject ?? new JObject();
        private static JArray Array(JObject root, string name) => root?[name] as JArray ?? new JArray();
        private static string ReadString(JObject root, string name) => root?[name]?.Type == JTokenType.Null ? string.Empty : root?[name]?.ToString() ?? string.Empty;
        private static int ReadInt(JObject root, string name, int fallback = 0) => root?[name] != null && int.TryParse(root[name].ToString(), NumberStyles.Integer, CultureInfo.InvariantCulture, out int value) ? value : fallback;
        private static float ReadFloat(JObject root, string name, float fallback = 0f) => root?[name] != null && float.TryParse(root[name].ToString(), NumberStyles.Float, CultureInfo.InvariantCulture, out float value) ? value : fallback;
        private static bool ReadBool(JObject root, string name, bool fallback = false) => root?[name] != null && bool.TryParse(root[name].ToString(), out bool value) ? value : fallback;
        private static bool TryParseFloat(string value, out float result) => float.TryParse(value, NumberStyles.Float, CultureInfo.InvariantCulture, out result);
        private static string Coalesce(string value, string fallback) => string.IsNullOrWhiteSpace(value) ? fallback : value;
        private static string Normalize(string value) => (value ?? string.Empty).Trim().ToLowerInvariant().Replace("_", string.Empty).Replace("-", string.Empty).Replace(" ", string.Empty);

        private readonly struct SourceDocument
        {
            public SourceDocument(string path, JObject root) { Path = path; Root = root; }
            public string Path { get; }
            public JObject Root { get; }
        }

        [Serializable]
        private sealed class ImportReport
        {
            public string sourceRoot;
            public string generatedAt;
            public int importedMonsterCount;
            public int importedPatternCount;
            public int importedFantasyCount;
            public List<string> warnings = new List<string>();
            public List<string> errors = new List<string>();
        }
    }

    public sealed class GameplayJsonAssetPostprocessor : AssetPostprocessor
    {
        private static bool queued;

        private static void OnPostprocessAllAssets(string[] importedAssets, string[] deletedAssets, string[] movedAssets, string[] movedFromAssetPaths)
        {
            if (queued || !importedAssets.Concat(deletedAssets).Concat(movedAssets).Any(IsGameplayJson))
                return;

            queued = true;
            EditorApplication.delayCall += () =>
            {
                queued = false;
                GameplayJsonImporter.ImportAll();
            };
        }

        private static bool IsGameplayJson(string path)
        {
            return path != null && path.StartsWith("Assets/Data/Json/", StringComparison.OrdinalIgnoreCase) && path.EndsWith(".json", StringComparison.OrdinalIgnoreCase);
        }
    }
}
