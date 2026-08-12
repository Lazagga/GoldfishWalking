using System;
using System.Collections.Generic;
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

            for (int i = 0; i < effects.Count; i++)
            {
                if (!(effects[i] is JObject effect))
                    continue;

                using (new EditorGUILayout.VerticalScope(EditorStyles.helpBox))
                {
                    using (new EditorGUILayout.HorizontalScope())
                    {
                        EditorGUILayout.LabelField($"효과 {i + 1}", EditorStyles.boldLabel);
                        if (GUILayout.Button("삭제", GUILayout.Width(55f)))
                        {
                            effects.RemoveAt(i--);
                            dirty = true;
                            continue;
                        }
                    }

                    JObject trigger = EnsureObject(effect, "trigger");
                    JObject target = EnsureObject(effect, "target");
                    trigger["event"] = DrawKnownString("실행 시점", ReadString(trigger, "event"), Events);
                    effect["operation"] = DrawKnownString("연산", ReadString(effect, "operation"), Operations);
                    target["actor"] = DrawKnownString("대상 Actor", ReadString(target, "actor"), Actors);
                    target["key"] = DrawKnownString("대상 Key", ReadString(target, "key"), TargetKeys);
                    SetOptionalString(effect, "type", EditorGUILayout.TextField("세부 타입", ReadString(effect, "type")));
                    SetOptionalString(effect, "amount", EditorGUILayout.TextField("값/표현식", ReadToken(effect, "amount")));
                    SetOptionalString(effect, "condition", EditorGUILayout.TextField("조건", ReadToken(effect, "condition")));
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
                List<string> errors = Validate(parsed);
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

        private static List<string> Validate(JObject root)
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

        private static string DrawKnownString(string label, string value, string[] knownValues)
        {
            List<string> options = new List<string>(knownValues);
            if (!string.IsNullOrWhiteSpace(value) && !options.Contains(value))
                options.Insert(0, value);
            int index = Mathf.Max(0, options.IndexOf(value));
            return options[EditorGUILayout.Popup(label, index, options.ToArray())];
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

        private static string ReadString(JObject root, string key) { return root?.Value<string>(key) ?? string.Empty; }
        private static string ReadToken(JObject root, string key) { return root?[key]?.ToString(Formatting.None) ?? string.Empty; }
    }
}
