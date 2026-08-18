using GoldfishWalking.Core;
using UnityEngine;
using UnityEngine.UI;

namespace GoldfishWalking.UI
{
    public sealed class GameOverDamageLogView : MonoBehaviour
    {
        private GameBootstrap bootstrap;
        private Text logText;

        private void Awake()
        {
            bootstrap = FindFirstObjectByType<GameBootstrap>(FindObjectsInactive.Include);
            EnsureLogPanel();
        }

        private void OnEnable()
        {
            if (bootstrap == null)
                bootstrap = FindFirstObjectByType<GameBootstrap>(FindObjectsInactive.Include);

            EnsureLogPanel();
            Refresh();
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
    }
}
