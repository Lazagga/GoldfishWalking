using GoldfishWalking.Core;
using UnityEngine;
using UnityEngine.UI;
#if UNITY_EDITOR
using UnityEditor;
#endif

namespace GoldfishWalking.UI
{
    public sealed class TitleSeedInputView : MonoBehaviour
    {
        [SerializeField] private GameBootstrap bootstrap;
        [SerializeField] private RectTransform layoutRoot;
        [SerializeField] private InputField seedInput;
        [SerializeField] private Font labelFont;

        private bool suppressChange;

        private void Awake()
        {
            ResolveReferences();
            EnsureLayout();
            BindInput();
        }

        private void OnEnable()
        {
            ResolveReferences();
            EnsureLayout();
            BindInput();
            Refresh();
        }

        private void OnDestroy()
        {
            if (seedInput != null)
                seedInput.onValueChanged.RemoveListener(OnSeedChanged);
        }

        private void ResolveReferences()
        {
            if (bootstrap == null)
                bootstrap = FindFirstObjectByType<GameBootstrap>(FindObjectsInactive.Include);
            if (labelFont == null)
                labelFont = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
        }

        private void EnsureLayout()
        {
            if (layoutRoot == null)
            {
                Transform existing = transform.Find("SeedInputPanel");
                if (existing is RectTransform existingRect)
                    layoutRoot = existingRect;
            }

            if (layoutRoot == null)
            {
                Debug.LogError("[TitleSeedInputView] Missing prebuilt SeedInputPanel. Build the UI in the scene instead of creating it from script.");
                return;
            }

            if (seedInput == null)
                seedInput = FindComponent<InputField>("SeedInputPanel/SeedInput");
        }

        private void BindInput()
        {
            if (seedInput == null)
                return;

            seedInput.onValueChanged.RemoveListener(OnSeedChanged);
            seedInput.onValueChanged.AddListener(OnSeedChanged);
        }

        private void Refresh()
        {
            if (seedInput == null || bootstrap == null)
                return;

            suppressChange = true;
            seedInput.text = bootstrap.SeedInputText;
            suppressChange = false;
        }

        private void OnSeedChanged(string value)
        {
            if (suppressChange || bootstrap == null)
                return;

            bootstrap.SetSeedFromText(value);
        }

        private T FindComponent<T>(string path) where T : Component
        {
            Transform found = transform.Find(path);
            return found != null ? found.GetComponent<T>() : null;
        }

#if UNITY_EDITOR
        [ContextMenu("Rebuild Scene UI Layout")]
        public void RebuildSceneUILayout()
        {
            Transform existing = transform.Find("SeedInputPanel");
            if (existing != null)
                DestroyImmediate(existing.gameObject);

            layoutRoot = null;
            seedInput = null;
            ResolveReferences();
            EnsureLayout();
            BindInput();
            Refresh();
            EditorUtility.SetDirty(gameObject);
            UnityEditor.SceneManagement.EditorSceneManager.MarkSceneDirty(gameObject.scene);
        }
#endif
    }
}
