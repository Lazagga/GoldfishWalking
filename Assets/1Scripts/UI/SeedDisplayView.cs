using GoldfishWalking.Core;
using UnityEngine;
using UnityEngine.UI;
#if UNITY_EDITOR
using UnityEditor;
#endif

namespace GoldfishWalking.UI
{
    public sealed class SeedDisplayView : MonoBehaviour
    {
        [SerializeField] private GameBootstrap bootstrap;
        [SerializeField] private Text seedText;
        [SerializeField] private Font labelFont;

        private void Awake()
        {
            ResolveReferences();
            EnsureLayout();
            Refresh();
        }

        private void OnEnable()
        {
            GameEventHub.StateChanged += OnStateChanged;
            ResolveReferences();
            EnsureLayout();
            Refresh();
        }

        private void OnDisable()
        {
            GameEventHub.StateChanged -= OnStateChanged;
        }

        private void Update()
        {
            RefreshText();
        }

        private void ResolveReferences()
        {
            if (bootstrap == null)
                Debug.LogError("[SeedDisplayView] GameBootstrap must be assigned in GumBwing_Er.unity.", this);
            if (labelFont == null)
                labelFont = GameFontSettings.ResolveFont();
        }

        private void EnsureLayout()
        {
            if (seedText == null)
                seedText = GetComponentInChildren<Text>(true);

            if (seedText != null)
                return;

            Debug.LogError("[SeedDisplayView] Missing prebuilt SeedText. Build the UI in the scene instead of creating it from script.");
        }

        private void OnStateChanged(GameState previous, GameState next)
        {
            Refresh(next);
        }

        private void Refresh()
        {
            GameState current = bootstrap != null && bootstrap.StateMachine != null
                ? bootstrap.StateMachine.CurrentState
                : GameState.Title;
            Refresh(current);
        }

        private void Refresh(GameState current)
        {
            if (seedText != null)
                seedText.enabled = current != GameState.Boot && current != GameState.Title;
            RefreshText();
        }

        private void RefreshText()
        {
            if (seedText == null || bootstrap == null)
                return;

            seedText.text = $"SEED {bootstrap.CurrentSeed}";
        }

#if UNITY_EDITOR
        [ContextMenu("Rebuild Scene UI Layout")]
        public void RebuildSceneUILayout()
        {
            for (int i = transform.childCount - 1; i >= 0; i--)
                DestroyImmediate(transform.GetChild(i).gameObject);

            seedText = null;
            ResolveReferences();
            EnsureLayout();
            RefreshText();
            EditorUtility.SetDirty(gameObject);
            UnityEditor.SceneManagement.EditorSceneManager.MarkSceneDirty(gameObject.scene);
        }
#endif
    }
}
