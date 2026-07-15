using GoldfishWalking.Data;
using UnityEditor;
using UnityEngine;

namespace GoldfishWalking.Editor
{
    [CustomEditor(typeof(MonsterPatternDatabase))]
    public sealed class MonsterPatternDatabaseEditor : UnityEditor.Editor
    {
        private int selectedIndex;
        private Vector2 scroll;
        private string jsonError;

        public override void OnInspectorGUI()
        {
            serializedObject.Update();
            SerializedProperty patterns = serializedObject.FindProperty("patterns");
            if (patterns == null || patterns.arraySize == 0)
            {
                EditorGUILayout.HelpBox("No monster patterns.", MessageType.Info);
                serializedObject.ApplyModifiedProperties();
                return;
            }

            EditorGUILayout.LabelField("Monster Pattern Database", EditorStyles.boldLabel);
            EditorGUILayout.LabelField("Effects JSON is the runtime source. TSV import can overwrite this asset.", EditorStyles.miniLabel);
            scroll = EditorGUILayout.BeginScrollView(scroll, GUILayout.Height(180f));
            for (int i = 0; i < patterns.arraySize; i++)
            {
                SerializedProperty item = patterns.GetArrayElementAtIndex(i);
                string id = item.FindPropertyRelative("id")?.stringValue ?? $"Pattern {i + 1}";
                if (GUILayout.Button(id, selectedIndex == i ? EditorStyles.toolbarButton : EditorStyles.miniButton))
                    selectedIndex = i;
            }
            EditorGUILayout.EndScrollView();

            selectedIndex = Mathf.Clamp(selectedIndex, 0, patterns.arraySize - 1);
            SerializedProperty pattern = patterns.GetArrayElementAtIndex(selectedIndex);
            using (new EditorGUI.DisabledScope(true))
                EditorGUILayout.PropertyField(pattern.FindPropertyRelative("id"), new GUIContent("ID"));

            EditorGUILayout.LabelField("Effects JSON (Runtime Source)", EditorStyles.boldLabel);
            SerializedProperty rawEffects = pattern.FindPropertyRelative("rawEffects");
            EditorGUI.BeginChangeCheck();
            EditorGUILayout.PropertyField(rawEffects, GUIContent.none, GUILayout.MinHeight(140f));
            bool changed = EditorGUI.EndChangeCheck();
            serializedObject.ApplyModifiedProperties();

            if (changed)
            {
                MonsterPatternDatabase database = (MonsterPatternDatabase)target;
                if (EffectJsonInspectorParser.TryApply(database.patterns[selectedIndex], out jsonError))
                {
                    jsonError = string.Empty;
                    EditorUtility.SetDirty(database);
                    serializedObject.Update();
                }
            }

            if (!string.IsNullOrWhiteSpace(jsonError))
                EditorGUILayout.HelpBox($"JSON was not applied: {jsonError}", MessageType.Error);

            EditorGUILayout.LabelField("Parsed Runtime Preview", EditorStyles.boldLabel);
            using (new EditorGUI.DisabledScope(true))
            {
                EditorGUILayout.PropertyField(pattern.FindPropertyRelative("attackKey"));
                EditorGUILayout.PropertyField(pattern.FindPropertyRelative("condition"));
                EditorGUILayout.PropertyField(pattern.FindPropertyRelative("maxUses"));
                EditorGUILayout.PropertyField(pattern.FindPropertyRelative("selfDestruct"));
                EditorGUILayout.PropertyField(pattern.FindPropertyRelative("effects"), true);
            }
        }
    }
}
