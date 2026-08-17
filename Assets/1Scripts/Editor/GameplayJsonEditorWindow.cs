using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using GoldfishWalking.Editor.DataImport;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEngine;

namespace GoldfishWalking.Editor
{
    public sealed class GameplayJsonEditorWindow : EditorWindow
    {
        private enum ContentKind { Monsters, Patterns, Fantasies }

        private static readonly string[] Operations =
        {
            "add_status", "copy_temporary", "create_formula_box", "deal_damage", "enable", "heal",
            "librarian_skill", "lock_box", "modify_value", "remove_status", "set_first_digit",
            "set_status", "set_value", "split_box"
        };

        private static readonly string[] PassiveOperations =
        {
            "add_formula_decoy_digits", "aimed_shot", "countdown", "lifesteal",
            "limit_incoming_damage", "lock_box", "require_formula_condition"
        };

        private static readonly string[] Events =
        {
            "acquire", "acquire_item", "battle_end", "battle_start", "deal_damage", "immediate",
            "next_turn", "on_acquire", "passive", "rest", "shop_enter", "turn_1", "turn_end",
            "turn_start", "value_evaluation"
        };

        private static readonly string[] Actors = { "", "monster", "player", "self" };
        private static readonly string[] TargetKeys =
        {
            "", "cosmetic", "damage", "eraser", "extra_match", "fantasy", "item",
            "player_base_damage", "player_boxes", "split_digit_erase", "temporary_movement", "whale_box"
        };

        private ContentKind kind;
        private readonly List<string> files = new List<string>();
        private string selectedPath;
        private JObject document;
        private string search = string.Empty;
        private string rawJson = string.Empty;
        private string message = string.Empty;
        private MessageType messageType = MessageType.None;
        private Vector2 listScroll;
        private Vector2 detailScroll;
        private bool showRawJson;
        private bool dirty;

        [MenuItem("GoldfishWalking/Data/기획자 JSON 편집기")]
        public static void Open()
        {
            GameplayJsonEditorWindow window = GetWindow<GameplayJsonEditorWindow>("게임 JSON 편집기");
            window.minSize = new Vector2(900f, 580f);
            window.RefreshFiles();
        }

        private void OnEnable()
        {
            RefreshFiles();
        }

        private void OnGUI()
        {
            DrawToolbar();
            EditorGUILayout.Space(4f);

            using (new EditorGUILayout.HorizontalScope())
            {
                DrawFileList();
                DrawDocument();
            }
        }

        private void DrawToolbar()
        {
            using (new EditorGUILayout.HorizontalScope(EditorStyles.toolbar))
            {
                ContentKind nextKind = (ContentKind)EditorGUILayout.EnumPopup(kind, EditorStyles.toolbarPopup, GUILayout.Width(110f));
                if (nextKind != kind)
                {
                    if (!CanDiscardChanges())
                        return;
                    kind = nextKind;
                    selectedPath = null;
                    document = null;
                    RefreshFiles();
                }

                search = GUILayout.TextField(search, GUI.skin.FindStyle("ToolbarSearchTextField"), GUILayout.MinWidth(180f));
                if (GUILayout.Button("새로고침", EditorStyles.toolbarButton, GUILayout.Width(70f)))
                    RefreshFiles();
                if (GUILayout.Button("전체 JSON 임포트", EditorStyles.toolbarButton, GUILayout.Width(110f)))
                    GameplayJsonImporter.ImportAll();
            }
        }

        private void DrawFileList()
        {
            using (new EditorGUILayout.VerticalScope(GUILayout.Width(270f)))
            {
                EditorGUILayout.LabelField($"{KindLabel()} ({files.Count})", EditorStyles.boldLabel);
                listScroll = EditorGUILayout.BeginScrollView(listScroll, GUI.skin.box);
                foreach (string path in files)
                {
                    string label = Path.GetFileNameWithoutExtension(path);
                    if (!string.IsNullOrWhiteSpace(search)
                        && label.IndexOf(search, StringComparison.OrdinalIgnoreCase) < 0)
                        continue;

                    GUIStyle style = path == selectedPath ? EditorStyles.toolbarButton : EditorStyles.miniButton;
                    if (GUILayout.Button(label, style) && path != selectedPath)
                        SelectFile(path);
                }
                EditorGUILayout.EndScrollView();
            }
        }

        private void DrawDocument()
        {
            using (new EditorGUILayout.VerticalScope(GUILayout.ExpandWidth(true)))
            {
                if (document == null)
                {
                    EditorGUILayout.HelpBox("왼쪽 목록에서 편집할 JSON을 선택하세요.", MessageType.Info);
                    return;
                }

                detailScroll = EditorGUILayout.BeginScrollView(detailScroll);
                EditorGUI.BeginChangeCheck();
                DrawCommonFields();
                EditorGUILayout.Space(8f);
                if (kind == ContentKind.Monsters)
                    DrawPassives();
                else
                    DrawEffects();
                EditorGUILayout.Space(8f);
                DrawRawJson();
                if (EditorGUI.EndChangeCheck())
                {
                    dirty = true;
                    rawJson = document.ToString(Formatting.Indented);
                    message = string.Empty;
                }
                EditorGUILayout.EndScrollView();

                if (!string.IsNullOrWhiteSpace(message))
                    EditorGUILayout.HelpBox(message, messageType);

                using (new EditorGUILayout.HorizontalScope())
                {
                    GUILayout.FlexibleSpace();
                    GUI.enabled = dirty;
                    if (GUILayout.Button("되돌리기", GUILayout.Width(90f)))
                        LoadSelected();
                    if (GUILayout.Button("검증 후 저장", GUILayout.Width(120f)))
                        SaveSelected();
                    GUI.enabled = true;
                }
            }
        }

        private void DrawCommonFields()
        {
            EditorGUILayout.LabelField(Path.GetFileName(selectedPath), EditorStyles.boldLabel);
            EditorGUILayout.LabelField(selectedPath, EditorStyles.miniLabel);
            SetString("id", EditorGUILayout.TextField("ID", ReadString(document, "id")));
            SetString("designerName", EditorGUILayout.TextField("기획자 이름", ReadString(document, "designerName")));
            EditorGUILayout.LabelField("기획 메모");
            SetString("designerNote", EditorGUILayout.TextArea(ReadString(document, "designerNote"), GUILayout.MinHeight(48f)));
            document["enabled"] = EditorGUILayout.Toggle("사용", document.Value<bool?>("enabled") ?? true);
        }

        private void DrawEffects()
        {
            EditorGUILayout.LabelField("효과", EditorStyles.boldLabel);
            JArray effects = document["effects"] as JArray;
            if (effects == null)
            {
                effects = new JArray();
                document["effects"] = effects;
            }

            if (effects.Count == 0)
                EditorGUILayout.HelpBox("등록된 효과가 없습니다. 아래 버튼으로 새 효과를 추가할 수 있습니다.", MessageType.Info);

            for (int i = 0; i < effects.Count; i++)
            {
                if (!(effects[i] is JObject effect))
                    continue;

                using (new EditorGUILayout.VerticalScope(EditorStyles.helpBox))
                {
                    using (new EditorGUILayout.HorizontalScope())
                    {
                        string operation = ReadString(effect, "operation");
                        EditorGUILayout.LabelField($"효과 {i + 1} · {KoreanLabel(operation)}", EditorStyles.boldLabel);
                        if (GUILayout.Button("삭제", GUILayout.Width(55f)))
                        {
                            effects.RemoveAt(i--);
                            dirty = true;
                            continue;
                        }
                    }

                    JObject trigger = EnsureObject(effect, "trigger");
                    JObject target = EnsureObject(effect, "target");
                    trigger["event"] = DrawKnownString("실행 시점", ReadString(trigger, "event"), Events, true);
                    effect["operation"] = DrawKnownString("연산", ReadString(effect, "operation"), Operations);
                    target["actor"] = DrawKnownString("대상 Actor", ReadString(target, "actor"), Actors);
                    target["key"] = DrawKnownString("대상 Key", ReadString(target, "key"), TargetKeys);
                    SetOptionalString(effect, "type", EditorGUILayout.TextField("세부 타입", ReadString(effect, "type")));
                    DrawOptionalTokenField(effect, "amount", "값/표현식");
                    DrawOptionalTokenField(effect, "condition", "조건");
                }
            }

            if (GUILayout.Button("+ 효과 추가"))
            {
                effects.Add(new JObject
                {
                    ["trigger"] = new JObject { ["event"] = "immediate" },
                    ["target"] = new JObject { ["actor"] = "player" },
                    ["operation"] = "modify_value"
                });
                dirty = true;
            }
        }

        private void DrawPassives()
        {
            EditorGUILayout.LabelField("몬스터 패시브", EditorStyles.boldLabel);
            JArray passives = document["passives"] as JArray;
            if (passives == null)
            {
                passives = new JArray();
                document["passives"] = passives;
            }

            if (passives.Count == 0)
                EditorGUILayout.HelpBox("등록된 패시브가 없습니다. 아래 버튼으로 새 패시브를 추가할 수 있습니다.", MessageType.Info);

            for (int i = 0; i < passives.Count; i++)
            {
                if (!(passives[i] is JObject passive))
                    continue;

                using (new EditorGUILayout.VerticalScope(EditorStyles.helpBox))
                {
                    using (new EditorGUILayout.HorizontalScope())
                    {
                        string operation = ReadString(passive, "operation");
                        EditorGUILayout.LabelField($"패시브 {i + 1} · {KoreanLabel(operation)}", EditorStyles.boldLabel);
                        if (GUILayout.Button("삭제", GUILayout.Width(55f)))
                        {
                            passives.RemoveAt(i--);
                            dirty = true;
                            continue;
                        }
                    }

                    passive["operation"] = DrawKnownString("패시브 종류", ReadString(passive, "operation"), PassiveOperations);
                    foreach (JProperty property in passive.Properties().Where(item => item.Name != "operation").ToArray())
                        DrawPassiveProperty(property);
                }
            }

            if (GUILayout.Button("+ 패시브 추가"))
            {
                passives.Add(new JObject { ["operation"] = "aimed_shot", ["multiplier"] = 1 });
                dirty = true;
            }
        }

        private static void DrawPassiveProperty(JProperty property)
        {
            string label = KoreanLabel(property.Name);
            switch (property.Value.Type)
            {
                case JTokenType.Integer:
                    property.Value = EditorGUILayout.IntField(label, property.Value.Value<int>());
                    break;
                case JTokenType.Float:
                    property.Value = EditorGUILayout.FloatField(label, property.Value.Value<float>());
                    break;
                case JTokenType.Boolean:
                    property.Value = EditorGUILayout.Toggle(label, property.Value.Value<bool>());
                    break;
                case JTokenType.String:
                    property.Value = EditorGUILayout.TextField(label, property.Value.Value<string>() ?? string.Empty);
                    break;
                default:
                    EditorGUILayout.LabelField(label, EditorStyles.miniBoldLabel);
                    EditorGUILayout.SelectableLabel(property.Value.ToString(Formatting.Indented), EditorStyles.textArea, GUILayout.MinHeight(38f));
                    break;
            }
        }

        private void DrawRawJson()
        {
            showRawJson = EditorGUILayout.Foldout(showRawJson, "고급: 원본 JSON", true);
            if (!showRawJson)
                return;

            string nextRaw = EditorGUILayout.TextArea(rawJson, GUILayout.MinHeight(220f));
            if (nextRaw == rawJson)
                return;

            rawJson = nextRaw;
            dirty = true;
            try
            {
                document = JObject.Parse(rawJson);
                message = "원본 JSON 문법이 정상입니다.";
                messageType = MessageType.Info;
            }
            catch (JsonException exception)
            {
                message = "JSON 문법 오류: " + exception.Message;
                messageType = MessageType.Error;
            }
        }

        private void SaveSelected()
        {
            try
            {
                JObject parsed = JObject.Parse(rawJson);
                List<string> errors = Validate(parsed, kind);
                if (errors.Count > 0)
                {
                    message = string.Join("\n", errors);
                    messageType = MessageType.Error;
                    return;
                }

                File.WriteAllText(selectedPath, parsed.ToString(Formatting.Indented) + Environment.NewLine);
                document = parsed;
                rawJson = document.ToString(Formatting.Indented);
                dirty = false;
                AssetDatabase.ImportAsset(selectedPath, ImportAssetOptions.ForceUpdate);
                GameplayJsonImporter.ImportAll();
                message = "JSON 저장과 런타임 데이터 재생성이 완료되었습니다.";
                messageType = MessageType.Info;
            }
            catch (Exception exception)
            {
                message = "저장 실패: " + exception.Message;
                messageType = MessageType.Error;
            }
        }

        private static List<string> Validate(JObject root, ContentKind contentKind)
        {
            List<string> errors = new List<string>();
            if (string.IsNullOrWhiteSpace(ReadString(root, "id")))
                errors.Add("ID는 비워둘 수 없습니다.");

            if (root["effects"] is JArray effects)
            {
                for (int i = 0; i < effects.Count; i++)
                {
                    if (!(effects[i] is JObject effect) || string.IsNullOrWhiteSpace(ReadString(effect, "operation")))
                        errors.Add($"효과 {i + 1}의 연산이 비어 있습니다.");
                }
            }

            if (contentKind == ContentKind.Monsters && root["passives"] is JArray passives)
            {
                for (int i = 0; i < passives.Count; i++)
                {
                    if (!(passives[i] is JObject passive) || string.IsNullOrWhiteSpace(ReadString(passive, "operation")))
                        errors.Add($"패시브 {i + 1}의 종류가 비어 있습니다.");
                }
            }

            return errors;
        }

        private void SelectFile(string path)
        {
            if (!CanDiscardChanges())
                return;
            selectedPath = path;
            LoadSelected();
        }

        private void LoadSelected()
        {
            try
            {
                rawJson = File.ReadAllText(selectedPath);
                document = JObject.Parse(rawJson);
                rawJson = document.ToString(Formatting.Indented);
                dirty = false;
                message = string.Empty;
            }
            catch (Exception exception)
            {
                document = null;
                message = "파일 열기 실패: " + exception.Message;
                messageType = MessageType.Error;
            }
        }

        private bool CanDiscardChanges()
        {
            return !dirty || EditorUtility.DisplayDialog("저장되지 않은 변경", "변경 내용을 버리고 이동할까요?", "버리기", "취소");
        }

        private void RefreshFiles()
        {
            files.Clear();
            string directory = "Assets/Data/Json/" + kind.ToString().ToLowerInvariant();
            if (Directory.Exists(directory))
                files.AddRange(Directory.GetFiles(directory, "*.json", SearchOption.TopDirectoryOnly).OrderBy(path => path));
            Repaint();
        }

        private string KindLabel()
        {
            switch (kind)
            {
                case ContentKind.Monsters: return "몬스터";
                case ContentKind.Patterns: return "패턴";
                default: return "Fantasy";
            }
        }

        private static string DrawKnownString(string label, string value, string[] knownValues, bool eventLabels = false)
        {
            List<string> options = new List<string>(knownValues);
            if (!string.IsNullOrWhiteSpace(value) && !options.Contains(value))
                options.Insert(0, value);
            int index = Mathf.Max(0, options.IndexOf(value));
            string[] labels = options.Select(item => $"{(eventLabels ? KoreanEventLabel(item) : KoreanLabel(item))}  [{item}]").ToArray();
            return options[EditorGUILayout.Popup(label, index, labels)];
        }

        private static string KoreanEventLabel(string value)
        {
            switch (value)
            {
                case "deal_damage": return "피해를 줄 때";
                default: return KoreanLabel(value);
            }
        }

        private static string KoreanLabel(string value)
        {
            switch (value)
            {
                case "": return "없음";
                case "add_formula_decoy_digits": return "수식 미끼 숫자 추가";
                case "add_status": return "상태 추가";
                case "aimed_shot": return "조준 사격";
                case "copy_temporary": return "일시 복사";
                case "countdown": return "카운트다운";
                case "create_formula_box": return "수식 박스 생성";
                case "deal_damage": return "피해 주기";
                case "enable": return "활성화";
                case "heal": return "회복";
                case "lifesteal": return "흡혈";
                case "librarian_skill": return "사서 특수 효과";
                case "limit_incoming_damage": return "받는 피해 제한";
                case "lock_box": return "박스 잠금";
                case "modify_value": return "값 변경";
                case "remove_status": return "상태 제거";
                case "require_formula_condition": return "수식 조건 요구";
                case "set_first_digit": return "첫 자리 숫자 설정";
                case "set_status": return "상태 설정";
                case "set_value": return "값 설정";
                case "split_box": return "박스 분할";
                case "acquire": return "획득 시";
                case "acquire_item": return "아이템 획득 시";
                case "battle_end": return "전투 종료 시";
                case "battle_start": return "전투 시작 시";
                case "immediate": return "즉시";
                case "next_turn": return "다음 턴";
                case "on_acquire": return "획득 직후";
                case "passive": return "상시";
                case "rest": return "휴식 시";
                case "shop_enter": return "상점 입장 시";
                case "turn_1": return "첫 번째 턴";
                case "turn_end": return "턴 종료 시";
                case "turn_start": return "턴 시작 시";
                case "value_evaluation": return "값 계산 시";
                case "monster": return "몬스터";
                case "player": return "플레이어";
                case "self": return "자신";
                case "multiplier": return "배율";
                case "maximum": return "최댓값";
                case "count": return "개수";
                case "ratio": return "비율";
                case "trigger": return "실행 시점";
                case "target": return "대상";
                case "box": return "박스 설정";
                case "decrease": return "감소 설정";
                case "onZero": return "0 도달 시";
                case "until": return "종료 조건";
                case "configuration": return "상세 설정";
                default: return value;
            }
        }

        private static JObject EnsureObject(JObject parent, string key)
        {
            if (parent[key] is JObject child)
                return child;
            child = new JObject();
            parent[key] = child;
            return child;
        }

        private void SetString(string key, string value) { document[key] = value ?? string.Empty; }

        private static void SetOptionalString(JObject target, string key, string value)
        {
            if (string.IsNullOrWhiteSpace(value))
                target.Remove(key);
            else
                target[key] = value;
        }

        private static void DrawOptionalTokenField(JObject target, string key, string label)
        {
            JToken token = target?[key];
            if (token != null && !(token is JValue))
            {
                EditorGUILayout.LabelField(label, EditorStyles.miniBoldLabel);
                EditorGUILayout.SelectableLabel(token.ToString(Formatting.Indented), EditorStyles.textArea, GUILayout.MinHeight(38f));
                return;
            }

            string current = ReadToken(target, key);
            string next = EditorGUILayout.TextField(label, current);
            if (next == current)
                return;

            if (string.IsNullOrWhiteSpace(next))
            {
                target.Remove(key);
                return;
            }

            if (token?.Type == JTokenType.Integer && long.TryParse(next, NumberStyles.Integer, CultureInfo.InvariantCulture, out long integer))
                target[key] = integer;
            else if (token?.Type == JTokenType.Float && double.TryParse(next, NumberStyles.Float, CultureInfo.InvariantCulture, out double number))
                target[key] = number;
            else if (token?.Type == JTokenType.Boolean && bool.TryParse(next, out bool boolean))
                target[key] = boolean;
            else
                target[key] = next;
        }

        private static string ReadString(JObject root, string key) { return root?.Value<string>(key) ?? string.Empty; }
        private static string ReadToken(JObject root, string key)
        {
            JToken token = root?[key];
            if (token == null)
                return string.Empty;
            if (token is JValue value)
                return Convert.ToString(value.Value, CultureInfo.InvariantCulture) ?? string.Empty;
            return token.ToString(Formatting.None);
        }
    }
}
