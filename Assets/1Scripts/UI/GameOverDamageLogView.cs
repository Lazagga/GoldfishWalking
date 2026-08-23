using GoldfishWalking.Core;
using UnityEngine;
using UnityEngine.UI;
#if UNITY_EDITOR
using UnityEditor;
using UnityEditor.SceneManagement;
#endif

namespace GoldfishWalking.UI
{
    public sealed class GameOverDamageLogView : MonoBehaviour
    {
        private GameBootstrap bootstrap;
        private Text logText;
        private Button restartButton;
        private Button homeButton;

        private void Awake()
        {
            bootstrap = FindFirstObjectByType<GameBootstrap>(FindObjectsInactive.Include);
            EnsureLogPanel();
            EnsureActionButtons();
            BindButtons();
        }

        private void OnEnable()
        {
            if (bootstrap == null)
                bootstrap = FindFirstObjectByType<GameBootstrap>(FindObjectsInactive.Include);

            EnsureLogPanel();
            EnsureActionButtons();
            BindButtons();
            Refresh();
        }

        private void OnDestroy()
        {
            UnbindButtons();
        }

        private void EnsureLogPanel()
        {
            Transform existing = transform.Find("DamageLogPanel/DamageLogText");
            if (existing != null)
            {
                logText = existing.GetComponent<Text>();
                return;
            }

            GameObject panelObject = new GameObject("DamageLogPanel", typeof(RectTransform), typeof(CanvasRenderer), typeof(Image));
            RectTransform panel = panelObject.GetComponent<RectTransform>();
            panel.SetParent(transform, false);
            panel.anchorMin = panel.anchorMax = new Vector2(1f, 0f);
            panel.anchoredPosition = new Vector2(-300f, 250f);
            panel.sizeDelta = new Vector2(430f, 150f);
            panelObject.GetComponent<Image>().color = new Color(0.08f, 0.09f, 0.12f, 0.92f);

            GameObject textObject = new GameObject("DamageLogText", typeof(RectTransform), typeof(CanvasRenderer), typeof(Text));
            RectTransform textRect = textObject.GetComponent<RectTransform>();
            textRect.SetParent(panel, false);
            textRect.anchorMin = Vector2.zero;
            textRect.anchorMax = Vector2.one;
            textRect.offsetMin = new Vector2(14f, 10f);
            textRect.offsetMax = new Vector2(-14f, -10f);

            logText = textObject.GetComponent<Text>();
            logText.font = GameFontSettings.ResolveFont();
            logText.fontSize = 18;
            logText.alignment = TextAnchor.UpperLeft;
            logText.color = Color.white;
            logText.supportRichText = true;
            logText.horizontalOverflow = HorizontalWrapMode.Wrap;
            logText.verticalOverflow = VerticalWrapMode.Truncate;
        }

        private void Refresh()
        {
            if (logText == null)
                return;

            RunContext run = bootstrap != null ? bootstrap.RunContext : null;
            string summary = run != null && run.battleDamageDebugLines != null && run.battleDamageDebugLines.Count > 0
                ? string.Join("\n", run.battleDamageDebugLines)
                : "Damage log -";
            logText.text = "Damage Log\n" + summary;
        }

        private void EnsureActionButtons()
        {
            restartButton = GetOrCreateButton("RestartButton", "RESTART", new Vector2(-180f, 100f));
            homeButton = GetOrCreateButton("HomeButton", "HOME", new Vector2(180f, 100f));
        }

        private Button GetOrCreateButton(string objectName, string label, Vector2 position)
        {
            Transform existing = transform.Find(objectName);
            GameObject buttonObject = existing != null ? existing.gameObject
                : new GameObject(objectName, typeof(RectTransform), typeof(CanvasRenderer), typeof(Image), typeof(Button));
            if (existing == null)
                buttonObject.transform.SetParent(transform, false);

            RectTransform rect = buttonObject.GetComponent<RectTransform>();
            rect.anchorMin = rect.anchorMax = new Vector2(0.5f, 0f);
            rect.pivot = new Vector2(0.5f, 0.5f);
            rect.anchoredPosition = position;
            rect.sizeDelta = new Vector2(300f, 100f);

            Image image = buttonObject.GetComponent<Image>();
            image.color = Color.white;
            GoldfishWalking.Match.MatchstickVisualSettings.ApplySoloButton(image);

            Transform labelTransform = buttonObject.transform.Find("Label");
            GameObject labelObject = labelTransform != null ? labelTransform.gameObject
                : new GameObject("Label", typeof(RectTransform), typeof(CanvasRenderer), typeof(Text));
            if (labelTransform == null)
                labelObject.transform.SetParent(buttonObject.transform, false);

            Text text = labelObject.GetComponent<Text>();
            text.text = label;
            text.font = GameFontSettings.ResolveFont();
            text.fontSize = 30;
            text.alignment = TextAnchor.MiddleCenter;
            text.color = Color.white;
            text.raycastTarget = false;
            RectTransform textRect = text.rectTransform;
            textRect.anchorMin = Vector2.zero;
            textRect.anchorMax = Vector2.one;
            textRect.offsetMin = Vector2.zero;
            textRect.offsetMax = Vector2.zero;

            return buttonObject.GetComponent<Button>();
        }

        private void BindButtons()
        {
            if (restartButton != null)
            {
                restartButton.onClick.RemoveListener(OnRestartClicked);
                restartButton.onClick.AddListener(OnRestartClicked);
            }
            if (homeButton != null)
            {
                homeButton.onClick.RemoveListener(OnHomeClicked);
                homeButton.onClick.AddListener(OnHomeClicked);
            }
        }

        private void UnbindButtons()
        {
            if (restartButton != null)
                restartButton.onClick.RemoveListener(OnRestartClicked);
            if (homeButton != null)
                homeButton.onClick.RemoveListener(OnHomeClicked);
        }

        private void OnRestartClicked()
        {
            bootstrap?.RestartWithNewSeed();
        }

        private void OnHomeClicked()
        {
            bootstrap?.ReturnToTitle();
        }

#if UNITY_EDITOR
        [ContextMenu("Build Scene UI Layout")]
        public void BuildSceneUILayout()
        {
            if (bootstrap == null)
                bootstrap = FindFirstObjectByType<GameBootstrap>(FindObjectsInactive.Include);
            EnsureLogPanel();
            EnsureActionButtons();
            EditorUtility.SetDirty(gameObject);
            EditorUtility.SetDirty(restartButton.gameObject);
            EditorUtility.SetDirty(homeButton.gameObject);
            EditorSceneManager.MarkSceneDirty(gameObject.scene);
        }
#endif
    }
}
