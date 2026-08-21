using UnityEngine;
using UnityEngine.UI;
#if UNITY_EDITOR
using System.Collections.Generic;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine.SceneManagement;
#endif

namespace GoldfishWalking.UI
{
    [ExecuteAlways]
    public sealed class GameFontSettings : MonoBehaviour
    {
        [Tooltip("기획자가 게임 전체 UI에 사용할 폰트를 자유롭게 지정합니다.")]
        [SerializeField] private Font gameFont;

        public static GameFontSettings Instance { get; private set; }
        public Font Font => gameFont;

        private void Awake()
        {
            Instance = this;
            ApplyToAllTexts();
        }

#if UNITY_EDITOR
        private void OnValidate()
        {
            Instance = this;
            ApplyToAllTexts();
        }
#endif

        private void OnDestroy()
        {
            if (Instance == this)
                Instance = null;
        }

        public void Configure(Font font)
        {
            gameFont = font;
            Instance = this;
            ApplyToAllTexts();
        }

        public void ConfigureDefault(Font font)
        {
            if (gameFont == null)
                gameFont = font;
            Instance = this;
            ApplyToAllTexts();
        }

        public void ApplyToAllTexts()
        {
            if (gameFont == null)
                return;

            Text[] texts = FindObjectsByType<Text>(FindObjectsInactive.Include, FindObjectsSortMode.None);
#if UNITY_EDITOR
            HashSet<Scene> changedScenes = new HashSet<Scene>();
#endif
            for (int i = 0; i < texts.Length; i++)
            {
                Text text = texts[i];
                if (text == null || text.font == gameFont)
                    continue;

                text.font = gameFont;
#if UNITY_EDITOR
                if (!Application.isPlaying)
                {
                    EditorUtility.SetDirty(text);
                    if (text.gameObject.scene.IsValid() && text.gameObject.scene.isLoaded)
                        changedScenes.Add(text.gameObject.scene);
                }
#endif
            }
#if UNITY_EDITOR
            if (!Application.isPlaying)
            {
                foreach (Scene scene in changedScenes)
                    EditorSceneManager.MarkSceneDirty(scene);
            }
#endif
        }

        public static Font ResolveFont()
        {
            if (Instance == null)
                Instance = FindFirstObjectByType<GameFontSettings>(FindObjectsInactive.Include);
            return Instance != null && Instance.gameFont != null
                ? Instance.gameFont
                : Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
        }

        public static void Apply(Text text)
        {
            if (text != null)
                text.font = ResolveFont();
        }
    }
}
