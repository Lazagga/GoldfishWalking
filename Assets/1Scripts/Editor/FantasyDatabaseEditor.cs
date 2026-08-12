using GoldfishWalking.Data;
using UnityEditor;
using UnityEngine;

namespace GoldfishWalking.Editor
{
    [CustomEditor(typeof(FantasyDatabase))]
    public sealed class FantasyDatabaseEditor : UnityEditor.Editor
    {
        private SerializedProperty fantasies;
        private string searchText = string.Empty;
        private int selectedIndex;
        private Vector2 listScroll;
        private bool showAdvanced;
        private string jsonError;

        private void OnEnable()
        {
            fantasies = serializedObject.FindProperty("fantasies");
        }

        public override void OnInspectorGUI()
        {
            serializedObject.Update();

            DrawHeader();
            EditorGUILayout.Space(6f);
            DrawFantasyList();
            EditorGUILayout.Space(8f);
            DrawSelectedFantasy();

            serializedObject.ApplyModifiedProperties();
        }

        private void DrawHeader()
        {
            EditorGUILayout.LabelField("Fantasy Database", EditorStyles.boldLabel);
            EditorGUILayout.LabelField("Generated from Assets/Data/Json/fantasies. Edit the source JSON, not this asset.", EditorStyles.miniLabel);
            searchText = EditorGUILayout.TextField("Search", searchText);
        }

        private void DrawFantasyList()
        {
            if (fantasies == null)
                return;

            EditorGUILayout.LabelField($"Fantasies ({fantasies.arraySize})", EditorStyles.boldLabel);
            listScroll = EditorGUILayout.BeginScrollView(listScroll, GUILayout.MinHeight(140f), GUILayout.MaxHeight(220f));

            bool foundAny = false;
            for (int i = 0; i < fantasies.arraySize; i++)
            {
                SerializedProperty fantasy = fantasies.GetArrayElementAtIndex(i);
                if (!MatchesSearch(fantasy))
                    continue;

                foundAny = true;
                string label = BuildListLabel(fantasy, i);
                GUIStyle style = selectedIndex == i ? EditorStyles.toolbarButton : EditorStyles.miniButton;
                if (GUILayout.Button(label, style))
                    selectedIndex = i;
            }

            if (!foundAny)
                EditorGUILayout.HelpBox("No fantasies match the current search.", MessageType.Info);

            EditorGUILayout.EndScrollView();
        }

        private void DrawSelectedFantasy()
        {
            if (fantasies == null || fantasies.arraySize == 0)
                return;

            selectedIndex = Mathf.Clamp(selectedIndex, 0, fantasies.arraySize - 1);
            SerializedProperty fantasy = fantasies.GetArrayElementAtIndex(selectedIndex);
            if (fantasy == null)
                return;

            EditorGUILayout.LabelField("Selected Fantasy", EditorStyles.boldLabel);
            using (new EditorGUILayout.VerticalScope(EditorStyles.helpBox))
            {
                DrawReadonlyText("ID", Find(fantasy, "id"));
                DrawReadonlyText("Data Code", Find(fantasy, "dataCode"));
                EditorGUILayout.PropertyField(Find(fantasy, "displayName"), new GUIContent("Display Name"));
                EditorGUILayout.PropertyField(Find(fantasy, "grade"), new GUIContent("Grade"));
                EditorGUILayout.PropertyField(Find(fantasy, "description"), new GUIContent("Description"));
                EditorGUILayout.PropertyField(Find(fantasy, "triggerType"), new GUIContent("Default Trigger"));

                EditorGUILayout.Space(4f);
                EditorGUILayout.LabelField("Generated Compatibility JSON", EditorStyles.boldLabel);
                EditorGUILayout.HelpBox("Read-only runtime preview. Edit the matching file under Assets/Data/Json/fantasies.", MessageType.Info);
                SerializedProperty rawEffects = Find(fantasy, "rawEffects");
                using (new EditorGUI.DisabledScope(true))
                    EditorGUILayout.PropertyField(rawEffects, GUIContent.none, GUILayout.MinHeight(100f));
                if (!string.IsNullOrWhiteSpace(jsonError))
                    EditorGUILayout.HelpBox($"JSON was not applied: {jsonError}", MessageType.Error);

                EditorGUILayout.Space(4f);
                EditorGUILayout.LabelField("Parsed Runtime Preview", EditorStyles.boldLabel);
                using (new EditorGUI.DisabledScope(true))
                    DrawEffects(Find(fantasy, "effects"));

                EditorGUILayout.Space(4f);
                showAdvanced = EditorGUILayout.Foldout(showAdvanced, "Advanced / Import Data", true);
                if (showAdvanced)
                {
                    EditorGUILayout.PropertyField(Find(fantasy, "sourceId"));
                    EditorGUILayout.PropertyField(Find(fantasy, "devName"));
                    EditorGUILayout.PropertyField(Find(fantasy, "nameStringId"));
                    EditorGUILayout.PropertyField(Find(fantasy, "descStringId"));
                    EditorGUILayout.PropertyField(Find(fantasy, "sprite"));
                    EditorGUILayout.PropertyField(Find(fantasy, "trigger"));
                    EditorGUILayout.PropertyField(Find(fantasy, "target"));
                    EditorGUILayout.PropertyField(Find(fantasy, "value"));
                    EditorGUILayout.PropertyField(Find(fantasy, "specialHandler"));
                }
            }
        }

        private static void DrawEffects(SerializedProperty effects)
        {
            if (effects == null)
                return;

            EditorGUILayout.LabelField("Effects", EditorStyles.boldLabel);
            EditorGUI.indentLevel++;
            effects.arraySize = Mathf.Max(0, EditorGUILayout.IntField("Count", effects.arraySize));

            for (int i = 0; i < effects.arraySize; i++)
            {
                SerializedProperty effect = effects.GetArrayElementAtIndex(i);
                using (new EditorGUILayout.VerticalScope(EditorStyles.helpBox))
                {
                    EditorGUILayout.LabelField($"Effect {i + 1}", EditorStyles.miniBoldLabel);
                    EditorGUILayout.PropertyField(Find(effect, "trigger"), new GUIContent("Trigger"));
                    EditorGUILayout.PropertyField(Find(effect, "target"), new GUIContent("Target"));
                    EditorGUILayout.PropertyField(Find(effect, "calc"), new GUIContent("Calc"));

                    SerializedProperty hasNumericValue = Find(effect, "hasNumericValue");
                    EditorGUILayout.PropertyField(hasNumericValue, new GUIContent("Use Numeric Value"));
                    if (hasNumericValue != null && hasNumericValue.boolValue)
                    {
                        EditorGUILayout.PropertyField(Find(effect, "numericValue"), new GUIContent("Value"));
                    }
                    else
                    {
                        EditorGUILayout.PropertyField(Find(effect, "valueExpression"), new GUIContent("Value Expression"));
                    }

                    EditorGUILayout.PropertyField(Find(effect, "option"), new GUIContent("Option"));
                }
            }

            EditorGUI.indentLevel--;
        }

        private bool MatchesSearch(SerializedProperty fantasy)
        {
            string search = (searchText ?? string.Empty).Trim().ToLowerInvariant();
            if (string.IsNullOrEmpty(search))
                return true;

            return Contains(Find(fantasy, "id"), search)
                || Contains(Find(fantasy, "dataCode"), search)
                || Contains(Find(fantasy, "devName"), search)
                || Contains(Find(fantasy, "displayName"), search)
                || Contains(Find(fantasy, "description"), search);
        }

        private static string BuildListLabel(SerializedProperty fantasy, int index)
        {
            string name = ReadString(Find(fantasy, "displayName"));
            if (string.IsNullOrWhiteSpace(name))
                name = ReadString(Find(fantasy, "devName"));
            if (string.IsNullOrWhiteSpace(name))
                name = ReadString(Find(fantasy, "id"));

            string id = ReadString(Find(fantasy, "id"));
            SerializedProperty grade = Find(fantasy, "grade");
            string gradeName = grade != null && grade.enumValueIndex >= 0 && grade.enumValueIndex < grade.enumDisplayNames.Length
                ? grade.enumDisplayNames[grade.enumValueIndex]
                : "-";
            return $"{index + 1:000}. {name}  [{gradeName}]  {id}";
        }

        private static void DrawReadonlyText(string label, SerializedProperty property)
        {
            using (new EditorGUI.DisabledScope(true))
                EditorGUILayout.TextField(label, ReadString(property));
        }

        private static bool Contains(SerializedProperty property, string search)
        {
            return ReadString(property).ToLowerInvariant().Contains(search);
        }

        private static string ReadString(SerializedProperty property)
        {
            return property != null ? property.stringValue : string.Empty;
        }

        private static SerializedProperty Find(SerializedProperty root, string name)
        {
            return root?.FindPropertyRelative(name);
        }
    }
}
