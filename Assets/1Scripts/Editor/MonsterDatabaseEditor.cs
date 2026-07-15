using GoldfishWalking.Data;
using UnityEditor;
using UnityEngine;

namespace GoldfishWalking.Editor
{
    [CustomEditor(typeof(MonsterDatabase))]
    public sealed class MonsterDatabaseEditor : UnityEditor.Editor
    {
        private SerializedProperty monsters;
        private string search = "";
        private int selected;
        private Vector2 scroll;
        private bool showSpecial = true;
        private bool showImport;

        private void OnEnable() => monsters = serializedObject.FindProperty("monsters");

        public override void OnInspectorGUI()
        {
            serializedObject.Update();
            EditorGUILayout.LabelField("Monster Database", EditorStyles.boldLabel);
            EditorGUILayout.LabelField("Edit runtime values here. TSV import can overwrite this asset.", EditorStyles.miniLabel);
            search = EditorGUILayout.TextField("Search", search);
            DrawList();
            EditorGUILayout.Space(8);
            DrawSelected();
            serializedObject.ApplyModifiedProperties();
        }

        private void DrawList()
        {
            EditorGUILayout.LabelField($"Monsters ({monsters.arraySize})", EditorStyles.boldLabel);
            scroll = EditorGUILayout.BeginScrollView(scroll, GUILayout.MinHeight(150), GUILayout.MaxHeight(230));
            bool any = false;
            for (int i = 0; i < monsters.arraySize; i++)
            {
                SerializedProperty monster = monsters.GetArrayElementAtIndex(i);
                if (!Matches(monster)) continue;
                any = true;
                GUIStyle style = selected == i ? EditorStyles.toolbarButton : EditorStyles.miniButton;
                if (GUILayout.Button(Label(monster, i), style)) selected = i;
            }
            if (!any) EditorGUILayout.HelpBox("No monsters match the search.", MessageType.Info);
            EditorGUILayout.EndScrollView();
        }

        private void DrawSelected()
        {
            if (monsters.arraySize == 0) return;
            selected = Mathf.Clamp(selected, 0, monsters.arraySize - 1);
            SerializedProperty m = monsters.GetArrayElementAtIndex(selected);
            EditorGUILayout.LabelField("Selected Monster", EditorStyles.boldLabel);
            using (new EditorGUILayout.VerticalScope(EditorStyles.helpBox))
            {
                ReadonlyText("ID", P(m, "id"));
                ReadonlyText("Data Name", P(m, "dataName"));
                Section("Identity & Encounter");
                Field(m, "displayName", "Display Name"); Field(m, "description", "Description");
                Field(m, "act", "Act"); Field(m, "grade", "Grade"); Field(m, "difficulty", "Difficulty"); Field(m, "sprite", "Sprite");

                Section("Battle Stats");
                Field(m, "baseHealth", "Base HP"); Field(m, "baseStrength", "Base Strength");
                Field(m, "damageCap", "Damage Cap"); Field(m, "damageCapBreakThreshold", "Damage Cap Break");
                Field(m, "lifestealRate", "Lifesteal Rate"); Field(m, "baseDamageLocked", "Base Damage Locked");

                Section("Pattern AI");
                Field(m, "aiType", "AI Type");
                EditorGUILayout.PropertyField(P(m, "patternIds"), new GUIContent("Pattern IDs"), true);

                EditorGUILayout.Space(5);
                showSpecial = EditorGUILayout.Foldout(showSpecial, "Special Rules", true);
                if (showSpecial) Indented(() => {
                    Field(m, "specialBoxLabel", "Special Box Label"); Field(m, "specialBoxMin", "Special Box Min");
                    Field(m, "specialBoxMax", "Special Box Max"); Field(m, "specialBoxValue", "Special Box Value");
                    Field(m, "countdownAction", "Countdown Action"); Field(m, "countdownPattern", "Countdown Pattern");
                });

                EditorGUILayout.Space(5);
                showImport = EditorGUILayout.Foldout(showImport, "Advanced / Import Data", true);
                if (showImport) using (new EditorGUI.DisabledScope(true)) Indented(() => {
                    Field(m, "sourceId", "Source ID"); Field(m, "devName", "Dev Name");
                    Field(m, "nameStringId", "Name String ID"); Field(m, "descStringId", "Desc String ID");
                    Field(m, "rawPatternArray", "Raw Pattern Array");
                });
            }
        }

        private bool Matches(SerializedProperty m)
        {
            string q = search.Trim().ToLowerInvariant();
            return q.Length == 0 || Has(m, "id", q) || Has(m, "dataName", q) || Has(m, "devName", q) || Has(m, "displayName", q);
        }

        private static string Label(SerializedProperty m, int i)
        {
            string name = S(P(m, "displayName")); if (name.Length == 0) name = S(P(m, "devName")); if (name.Length == 0) name = S(P(m, "id"));
            SerializedProperty grade = P(m, "grade");
            string g = grade.enumValueIndex >= 0 && grade.enumValueIndex < grade.enumDisplayNames.Length ? grade.enumDisplayNames[grade.enumValueIndex] : "-";
            return $"{i + 1:000}. {name}  [Act {P(m, "act").intValue} / {g}]";
        }

        private static void Section(string label) { EditorGUILayout.Space(6); EditorGUILayout.LabelField(label, EditorStyles.miniBoldLabel); }
        private static void Field(SerializedProperty m, string name, string label) => EditorGUILayout.PropertyField(P(m, name), new GUIContent(label));
        private static void ReadonlyText(string label, SerializedProperty p) { using (new EditorGUI.DisabledScope(true)) EditorGUILayout.TextField(label, S(p)); }
        private static void Indented(System.Action draw) { EditorGUI.indentLevel++; draw(); EditorGUI.indentLevel--; }
        private static bool Has(SerializedProperty m, string name, string q) => S(P(m, name)).ToLowerInvariant().Contains(q);
        private static string S(SerializedProperty p) => p?.stringValue ?? "";
        private static SerializedProperty P(SerializedProperty root, string name) => root?.FindPropertyRelative(name);
    }
}
