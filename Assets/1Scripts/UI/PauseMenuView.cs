using GoldfishWalking.Core;
using UnityEngine;
using UnityEngine.UI;
#if UNITY_EDITOR
using UnityEditor;
using UnityEditor.SceneManagement;
#endif

namespace GoldfishWalking.UI
{
    public sealed class PauseMenuView : MonoBehaviour
    {
        private GameBootstrap bootstrap;
        private RectTransform overlayRoot;
        private Button homeButton;
        private Button restartButton;
        private Button settingsButton;
        private Button backButton;
        private bool isOpen;

        private void Awake()
        {
            ResolveReferences();
            EnsureLayout();
            BindButtons();
            SetOpen(false);
        }

        private void OnEnable()
        {
            GameEventHub.StateChanged += OnStateChanged;
            ResolveReferences();
            EnsureLayout();
            BindButtons();
            SetOpen(false);
        }

        private void OnDisable()
        {
            GameEventHub.StateChanged -= OnStateChanged;
            UnbindButtons();
            if (isOpen)
                Time.timeScale = 1f;
            isOpen = false;
        }

        private void Update()
        {
            if (!Input.GetKeyDown(KeyCode.Escape))
                return;

            if (isOpen)
            {
                SetOpen(false);
                return;
            }

            if (CanOpen())
                SetOpen(true);
        }

        private bool CanOpen()
        {
            if (bootstrap == null || bootstrap.StateMachine == null)
                return false;

            switch (bootstrap.StateMachine.CurrentState)
            {
                case GameState.Map:
                case GameState.Battle:
                case GameState.Reward:
                case GameState.Rest:
                case GameState.Shop:
                    return true;
                default:
                    return false;
            }
        }

        private void ResolveReferences()
        {
            if (bootstrap == null)
                bootstrap = FindFirstObjectByType<GameBootstrap>(FindObjectsInactive.Include);
        }

        private void EnsureLayout()
        {
            Transform existing = transform.Find("PauseMenuOverlay");
            if (existing == null)
                return;

            overlayRoot = existing as RectTransform;
            homeButton = FindButton("PauseMenuOverlay/MenuPanel/HomeButton");
            restartButton = FindButton("PauseMenuOverlay/MenuPanel/RestartButton");
            settingsButton = FindButton("PauseMenuOverlay/MenuPanel/SettingsButton");
            backButton = FindButton("PauseMenuOverlay/MenuPanel/BackButton");
            if (settingsButton != null)
                settingsButton.interactable = true;
        }

        private Button FindButton(string path)
        {
            Transform found = transform.Find(path);
            return found != null ? found.GetComponent<Button>() : null;
        }

        private void BindButtons()
        {
            UnbindButtons();
            homeButton?.onClick.AddListener(OnHomeClicked);
            restartButton?.onClick.AddListener(OnRestartClicked);
            backButton?.onClick.AddListener(OnBackClicked);
        }

        private void UnbindButtons()
        {
            homeButton?.onClick.RemoveListener(OnHomeClicked);
            restartButton?.onClick.RemoveListener(OnRestartClicked);
            backButton?.onClick.RemoveListener(OnBackClicked);
        }

        private void SetOpen(bool open)
        {
            isOpen = open;
            if (overlayRoot != null)
            {
                overlayRoot.gameObject.SetActive(open);
                if (open)
                    overlayRoot.SetAsLastSibling();
            }
            Time.timeScale = open ? 0f : 1f;
        }

        private void OnHomeClicked()
        {
            SetOpen(false);
            bootstrap?.ReturnToTitle();
        }

        private void OnRestartClicked()
        {
            SetOpen(false);
            bootstrap?.RestartWithCurrentSeed();
        }

        private void OnBackClicked()
        {
            SetOpen(false);
        }

        private void OnStateChanged(GameState previous, GameState next)
        {
            if (isOpen)
                SetOpen(false);
        }

#if UNITY_EDITOR
        [ContextMenu("Build Scene UI Layout")]
        public void BuildSceneUILayout()
        {
            GameObject overlay = GetOrCreate("PauseMenuOverlay", transform, typeof(Image));
            RectTransform overlayRect = overlay.GetComponent<RectTransform>();
            Stretch(overlayRect);
            Image overlayImage = overlay.GetComponent<Image>();
            overlayImage.color = new Color(0f, 0f, 0f, 0.68f);
            overlayImage.raycastTarget = true;

            GameObject panel = GetOrCreate("MenuPanel", overlay.transform, typeof(Image));
            RectTransform panelRect = panel.GetComponent<RectTransform>();
            panelRect.anchorMin = panelRect.anchorMax = panelRect.pivot = new Vector2(0.5f, 0.5f);
            panelRect.anchoredPosition = Vector2.zero;
            panelRect.sizeDelta = new Vector2(600f, 680f);
            Image panelImage = panel.GetComponent<Image>();
            UiArtSettings art = UiArtSettings.Resolve();
            if (art != null && art.ExpandedPanel != null)
            {
                panelImage.sprite = art.ExpandedPanel;
                panelImage.type = Image.Type.Simple;
                panelImage.color = Color.white;
            }

            CreateButton(panel.transform, "HomeButton", "HOME", 210f);
            CreateButton(panel.transform, "RestartButton", "RESTART", 70f);
            Button settings = CreateButton(panel.transform, "SettingsButton", "SETTINGS", -70f);
            settings.interactable = true;
            CreateButton(panel.transform, "BackButton", "BACK", -210f);

            overlay.SetActive(false);
            overlay.transform.SetAsLastSibling();
            EnsureLayout();
            EditorUtility.SetDirty(gameObject);
            EditorUtility.SetDirty(overlay);
            EditorSceneManager.MarkSceneDirty(gameObject.scene);
        }

        private static GameObject GetOrCreate(string name, Transform parent, params System.Type[] extraComponents)
        {
            Transform existing = parent.Find(name);
            if (existing != null)
                return existing.gameObject;

            System.Type[] components = new System.Type[extraComponents.Length + 2];
            components[0] = typeof(RectTransform);
            components[1] = typeof(CanvasRenderer);
            for (int i = 0; i < extraComponents.Length; i++)
                components[i + 2] = extraComponents[i];
            GameObject created = new GameObject(name, components);
            created.transform.SetParent(parent, false);
            return created;
        }

        private static Button CreateButton(Transform parent, string name, string label, float y)
        {
            GameObject buttonObject = GetOrCreate(name, parent, typeof(Image), typeof(Button));
            RectTransform rect = buttonObject.GetComponent<RectTransform>();
            rect.anchorMin = rect.anchorMax = rect.pivot = new Vector2(0.5f, 0.5f);
            rect.anchoredPosition = new Vector2(0f, y);
            rect.sizeDelta = new Vector2(400f, 108f);
            Image image = buttonObject.GetComponent<Image>();
            Match.MatchstickVisualSettings.ApplySoloButton(image);

            GameObject labelObject = GetOrCreate("Label", buttonObject.transform, typeof(Text));
            Text text = labelObject.GetComponent<Text>();
            text.text = label;
            text.font = GameFontSettings.ResolveFont();
            text.fontSize = 30;
            text.alignment = TextAnchor.MiddleCenter;
            text.color = Color.white;
            text.raycastTarget = false;
            Stretch(text.rectTransform);
            return buttonObject.GetComponent<Button>();
        }

        private static void Stretch(RectTransform rect)
        {
            rect.anchorMin = Vector2.zero;
            rect.anchorMax = Vector2.one;
            rect.offsetMin = Vector2.zero;
            rect.offsetMax = Vector2.zero;
        }
#endif
    }
}
