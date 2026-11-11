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
        [SerializeField] private Button continueButton;

        private bool suppressChange;

        private void Awake()
        {
            ResolveReferences();
            EnsureLayout();
            BindInput();
            BindContinueButton();
        }

        private void OnEnable()
        {
            ResolveReferences();
            EnsureLayout();
            BindInput();
            BindContinueButton();
            Refresh();
        }

        private void OnDestroy()
        {
            if (seedInput != null)
                seedInput.onValueChanged.RemoveListener(OnSeedChanged);
            continueButton?.onClick.RemoveListener(OnContinueClicked);
        }

        private void ResolveReferences()
        {
            if (bootstrap == null)
                Debug.LogError("[TitleSeedInputView] GameBootstrap must be assigned in GumBwing_Er.unity.", this);
            if (labelFont == null)
                labelFont = GameFontSettings.ResolveFont();
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
            if (continueButton == null)
                continueButton = FindComponent<Button>("ContinueButton");
        }

        private void BindContinueButton()
        {
            if (continueButton == null)
                return;
            continueButton.onClick.RemoveListener(OnContinueClicked);
            continueButton.onClick.AddListener(OnContinueClicked);
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
            if (continueButton != null)
                continueButton.interactable = bootstrap.HasSavedRun;
        }

        private void OnContinueClicked()
        {
            if (bootstrap != null && bootstrap.ContinueSavedRun())
                Refresh();
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
        public void BuildContinueButton()
        {
            Transform existing = transform.Find("ContinueButton");
            GameObject buttonObject = existing != null ? existing.gameObject
                : new GameObject("ContinueButton", typeof(RectTransform), typeof(CanvasRenderer), typeof(Image), typeof(Button));
            if (existing == null)
                buttonObject.transform.SetParent(transform, false);
            RectTransform rect = buttonObject.GetComponent<RectTransform>();
            rect.anchorMin = rect.anchorMax = rect.pivot = new Vector2(0.5f, 0.5f);
            rect.anchoredPosition = new Vector2(0f, 70f);
            rect.sizeDelta = new Vector2(360f, 80f);
            Match.MatchstickVisualSettings.ApplySoloButton(buttonObject.GetComponent<Image>());

            Transform labelTransform = buttonObject.transform.Find("Label");
            GameObject labelObject = labelTransform != null ? labelTransform.gameObject
                : new GameObject("Label", typeof(RectTransform), typeof(CanvasRenderer), typeof(Text));
            if (labelTransform == null)
                labelObject.transform.SetParent(buttonObject.transform, false);
            Text label = labelObject.GetComponent<Text>();
            label.text = "CONTINUE";
            label.font = labelFont != null ? labelFont : GameFontSettings.ResolveFont();
            label.fontSize = 28;
            label.alignment = TextAnchor.MiddleCenter;
            label.color = Color.white;
            label.raycastTarget = false;
            RectTransform labelRect = label.rectTransform;
            labelRect.anchorMin = Vector2.zero;
            labelRect.anchorMax = Vector2.one;
            labelRect.offsetMin = labelRect.offsetMax = Vector2.zero;
            continueButton = buttonObject.GetComponent<Button>();
            BindContinueButton();
            Refresh();
            EditorUtility.SetDirty(gameObject);
            UnityEditor.SceneManagement.EditorSceneManager.MarkSceneDirty(gameObject.scene);
        }

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
