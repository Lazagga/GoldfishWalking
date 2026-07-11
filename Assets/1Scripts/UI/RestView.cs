using System.Collections;
using System.Collections.Generic;
using GoldfishWalking.Data;
using GoldfishWalking.Match;
using GoldfishWalking.Rest;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace GoldfishWalking.UI
{
    public sealed class RestView : MonoBehaviour
    {
        private const int DefaultHealAmount = 91;

        [SerializeField] private RestController restController;
        [SerializeField] private int healAmount = DefaultHealAmount;

        private readonly Color backgroundColor = new Color(0.58f, 0.66f, 0.72f, 1f);
        private readonly Color panelColor = new Color(0.14f, 0.16f, 0.20f, 0.92f);
        private readonly Color fantasySlotColor = new Color(0.20f, 0.22f, 0.29f, 0.96f);
        private readonly Color matchColor = new Color(1.0f, 0.74f, 0.33f, 1f);
        private readonly Color textColor = new Color(0.95f, 0.97f, 1f, 1f);
        private readonly Color healColor = new Color(0.16f, 0.90f, 0.48f, 1f);

        private RectTransform layoutRoot;
        private RectTransform statusPanel;
        private RectTransform fantasyContentRoot;
        private RectTransform matchNumberRoot;
        private RectTransform fantasyTooltipRoot;
        private Text healthText;
        private Text healFloatText;
        private Text fantasyTooltipName;
        private Text fantasyTooltipDescription;
        private Text fantasyTooltipEffect;
        private Button restButton;
        private Button coffeeButton;
        private Button nextButton;
        private Coroutine healFloatRoutine;
        private int restUseCount;

        private void Awake()
        {
            ResolveReferences();
            HideScenePlaceholders();
            EnsureLayout();
            BindButtons();
        }

        private void OnEnable()
        {
            restUseCount = 0;
            ResolveReferences();
            HideScenePlaceholders();
            EnsureLayout();
            Refresh();
        }

        private void OnDestroy()
        {
            UnbindButtons();
        }

        private void ResolveReferences()
        {
            if (restController == null)
                restController = FindFirstObjectByType<RestController>(FindObjectsInactive.Include);
        }

        private void HideScenePlaceholders()
        {
            for (int i = 0; i < transform.childCount; i++)
            {
                Transform child = transform.GetChild(i);
                if (layoutRoot != null && child == layoutRoot)
                    continue;
                if (child.name == "RestRuntimeLayout")
                {
                    layoutRoot = child as RectTransform;
                    continue;
                }

                child.gameObject.SetActive(false);
            }
        }

        private void EnsureLayout()
        {
            if (layoutRoot != null)
                return;

            layoutRoot = CreateRect("RestRuntimeLayout", transform, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
            layoutRoot.offsetMin = Vector2.zero;
            layoutRoot.offsetMax = Vector2.zero;

            CreateBackground();
            CreateStatusArea();
            CreateMatchNumberArea();
            CreateFantasyTooltip();
            CreateRestButton();
            CreateCoffeeButton();
            CreateNextButton();
        }

        private void CreateBackground()
        {
            Image background = CreateImage("Background", layoutRoot, backgroundColor);
            RectTransform rect = background.rectTransform;
            rect.anchorMin = Vector2.zero;
            rect.anchorMax = Vector2.one;
            rect.offsetMin = Vector2.zero;
            rect.offsetMax = Vector2.zero;
        }

        private void CreateStatusArea()
        {
            statusPanel = CreatePanel("StatusPanel", layoutRoot, panelColor, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(300f, -105f), new Vector2(484f, 112f));

            Text nameText = CreateText("Name", statusPanel, "성냥팔이 소녀", 28, textColor, TextAnchor.MiddleLeft);
            SetRect(nameText.rectTransform, new Vector2(0f, 0f), new Vector2(0f, 1f), new Vector2(160f, 0f), new Vector2(260f, 112f));

            healthText = CreateText("Health", statusPanel, string.Empty, 34, textColor, TextAnchor.MiddleRight);
            SetRect(healthText.rectTransform, new Vector2(1f, 0f), new Vector2(1f, 1f), new Vector2(-74f, 0f), new Vector2(90f, 112f));

            healFloatText = CreateText("HealFloat", statusPanel, string.Empty, 34, healColor, TextAnchor.MiddleCenter);
            SetRect(healFloatText.rectTransform, new Vector2(1f, 1f), new Vector2(1f, 1f), new Vector2(-78f, 26f), new Vector2(130f, 46f));
            healFloatText.gameObject.SetActive(false);

            CreateFantasyScroll();
        }

        private void CreateFantasyScroll()
        {
            RectTransform fantasyPanel = CreatePanel("FantasySlots", layoutRoot, panelColor, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(299f, -228f), new Vector2(482f, 88f));
            ScrollRect scrollRect = fantasyPanel.gameObject.AddComponent<ScrollRect>();
            scrollRect.horizontal = true;
            scrollRect.vertical = false;
            scrollRect.inertia = true;
            scrollRect.movementType = ScrollRect.MovementType.Clamped;

            RectTransform viewport = CreateRect("Viewport", fantasyPanel, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
            viewport.offsetMin = new Vector2(10f, 10f);
            viewport.offsetMax = new Vector2(-10f, -10f);
            viewport.gameObject.AddComponent<RectMask2D>();

            fantasyContentRoot = CreateRect("Content", viewport, new Vector2(0f, 0.5f), new Vector2(0f, 0.5f), Vector2.zero, Vector2.zero);
            fantasyContentRoot.pivot = new Vector2(0f, 0.5f);
            fantasyContentRoot.anchoredPosition = Vector2.zero;
            fantasyContentRoot.sizeDelta = new Vector2(746f, 68f);

            scrollRect.viewport = viewport;
            scrollRect.content = fantasyContentRoot;
            RefreshFantasySlots();
        }

        private void CreateMatchNumberArea()
        {
            matchNumberRoot = CreateRect("MatchNumber", layoutRoot, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), Vector2.zero, Vector2.zero);
            matchNumberRoot.anchoredPosition = new Vector2(0f, 130f);
            matchNumberRoot.sizeDelta = new Vector2(420f, 220f);
            DrawMatchNumber(healAmount);
        }

        private void CreateFantasyTooltip()
        {
            fantasyTooltipRoot = CreatePanel("FantasyTooltip", layoutRoot, new Color(0.08f, 0.09f, 0.12f, 0.98f), new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(-560f, -38f), new Vector2(380f, 250f));
            fantasyTooltipName = CreateText("Name", fantasyTooltipRoot, string.Empty, 20, textColor, TextAnchor.UpperCenter);
            SetRect(fantasyTooltipName.rectTransform, new Vector2(0f, 0.72f), Vector2.one, new Vector2(0f, -14f), new Vector2(-24f, -12f));
            fantasyTooltipDescription = CreateText("Description", fantasyTooltipRoot, string.Empty, 16, textColor, TextAnchor.UpperLeft);
            SetRect(fantasyTooltipDescription.rectTransform, new Vector2(0f, 0.32f), new Vector2(1f, 0.76f), new Vector2(0f, -8f), new Vector2(-28f, -8f));
            fantasyTooltipEffect = CreateText("Effect", fantasyTooltipRoot, string.Empty, 14, new Color(0.24f, 0.74f, 0.90f, 1f), TextAnchor.UpperLeft);
            SetRect(fantasyTooltipEffect.rectTransform, Vector2.zero, new Vector2(1f, 0.33f), new Vector2(0f, 8f), new Vector2(-28f, -8f));
            fantasyTooltipRoot.gameObject.SetActive(false);
        }

        private void CreateRestButton()
        {
            restButton = CreateButton("RestButton", "휴식", new Vector2(132f, 122f), new Vector2(148f, 96f), 30);
        }

        private void CreateCoffeeButton()
        {
            coffeeButton = CreateButton("CoffeeButton", "Fantasy", new Vector2(300f, 122f), new Vector2(172f, 96f), 26);
        }

        private void CreateNextButton()
        {
            nextButton = CreateButton("NextButton", "다음 지역으로 이동 →", new Vector2(-281f, 103f), new Vector2(486f, 96f), 28, true);
        }

        private Button CreateButton(string name, string label, Vector2 anchoredPosition, Vector2 size, int fontSize, bool rightAnchor = false)
        {
            Vector2 anchor = rightAnchor ? new Vector2(1f, 0f) : new Vector2(0f, 0f);
            RectTransform panel = CreatePanel(name, layoutRoot, panelColor, anchor, anchor, anchoredPosition, size);
            Button button = panel.gameObject.AddComponent<Button>();

            ColorBlock colors = button.colors;
            colors.normalColor = Color.white;
            colors.highlightedColor = new Color(0.90f, 0.94f, 1f, 1f);
            colors.pressedColor = new Color(0.76f, 0.84f, 0.92f, 1f);
            colors.disabledColor = new Color(0.45f, 0.47f, 0.50f, 1f);
            button.colors = colors;

            Text buttonText = CreateText("Label", panel, label, fontSize, textColor, TextAnchor.MiddleCenter);
            SetRect(buttonText.rectTransform, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
            return button;
        }

        private void BindButtons()
        {
            if (restButton != null)
                restButton.onClick.AddListener(ApplyRest);
            if (coffeeButton != null)
                coffeeButton.onClick.AddListener(ClaimCoffeeFantasy);
            if (nextButton != null)
                nextButton.onClick.AddListener(CompleteRest);
        }

        private void UnbindButtons()
        {
            if (restButton != null)
                restButton.onClick.RemoveListener(ApplyRest);
            if (coffeeButton != null)
                coffeeButton.onClick.RemoveListener(ClaimCoffeeFantasy);
            if (nextButton != null)
                nextButton.onClick.RemoveListener(CompleteRest);
        }

        private void ApplyRest()
        {
            if (restController == null || restUseCount >= restController.MaxRestCount)
                return;

            int amount = Mathf.Max(0, restController.CurrentHealAmount);
            restController.Heal(amount);
            restUseCount++;
            Refresh();
            PlayHealFloat(amount);
        }

        private void CompleteRest()
        {
            if (restController != null)
                restController.CompleteRest();
        }

        private void ClaimCoffeeFantasy()
        {
            if (restController == null || restUseCount > 0 || !restController.TryClaimCoffeeFantasy())
                return;

            restUseCount = restController.MaxRestCount;
            Refresh();
        }

        private void Refresh()
        {
            if (healthText != null)
                healthText.text = restController != null ? restController.CurrentHealth.ToString() : "0";
            if (restButton != null)
                restButton.interactable = restController != null && restUseCount < restController.MaxRestCount;
            if (coffeeButton != null)
                coffeeButton.interactable = restController != null && restUseCount == 0 && restController.CanClaimCoffeeFantasy;
            if (healFloatText != null && restUseCount == 0)
                healFloatText.gameObject.SetActive(false);

            RefreshFantasySlots();
            HideFantasyTooltip();
            healAmount = restController != null ? restController.CurrentHealAmount : healAmount;
            DrawMatchNumber(healAmount);
        }

        private void RefreshFantasySlots()
        {
            if (fantasyContentRoot == null)
                return;

            ClearChildren(fantasyContentRoot);
            IReadOnlyList<FantasyData> owned = restController != null ? restController.OwnedFantasies : null;
            int ownedCount = owned != null ? owned.Count : 0;
            int slotCount = Mathf.Max(10, ownedCount);
            fantasyContentRoot.sizeDelta = new Vector2(Mathf.Max(746f, slotCount * 74f + 6f), 68f);

            for (int i = 0; i < slotCount; i++)
            {
                RectTransform slot = CreatePanel($"FantasySlot{i + 1}", fantasyContentRoot, fantasySlotColor, new Vector2(0f, 0.5f), new Vector2(0f, 0.5f), new Vector2(34f + i * 74f, 0f), new Vector2(60f, 60f));
                if (owned == null || i >= owned.Count || owned[i] == null)
                    continue;

                FantasyData fantasy = owned[i];
                Text icon = CreateText("FantasyIcon", slot, "★", 29, GradeColor(fantasy.grade), TextAnchor.MiddleCenter);
                SetRect(icon.rectTransform, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
                FantasyTooltipTrigger trigger = slot.gameObject.AddComponent<FantasyTooltipTrigger>();
                trigger.Initialize(this, fantasy);
            }
        }

        private void PlayHealFloat(int amount)
        {
            if (healFloatText == null)
                return;

            if (healFloatRoutine != null)
                StopCoroutine(healFloatRoutine);
            healFloatRoutine = StartCoroutine(HealFloatRoutine(amount));
        }

        private IEnumerator HealFloatRoutine(int amount)
        {
            RectTransform rect = healFloatText.rectTransform;
            Vector2 start = new Vector2(-78f, 26f);
            Vector2 end = start + new Vector2(0f, 76f);
            float duration = 0.85f;
            float elapsed = 0f;

            healFloatText.text = $"+{amount}";
            healFloatText.color = healColor;
            rect.anchoredPosition = start;
            healFloatText.gameObject.SetActive(true);

            while (elapsed < duration)
            {
                elapsed += Time.deltaTime;
                float t = Mathf.Clamp01(elapsed / duration);
                rect.anchoredPosition = Vector2.Lerp(start, end, t);
                Color color = healColor;
                color.a = 1f - t;
                healFloatText.color = color;
                yield return null;
            }

            healFloatText.gameObject.SetActive(false);
            healFloatRoutine = null;
        }

        private void DrawMatchNumber(int value)
        {
            if (matchNumberRoot == null)
                return;

            ClearChildren(matchNumberRoot);
            EditableSevenSegmentBox box = matchNumberRoot.GetComponent<EditableSevenSegmentBox>();
            if (box == null)
                box = matchNumberRoot.gameObject.AddComponent<EditableSevenSegmentBox>();

            box.Configure(value, 0, matchColor, OnHealAmountEdited);
        }

        private void OnHealAmountEdited(int newValue)
        {
            healAmount = Mathf.Max(0, newValue);
            if (restController != null)
                restController.SetHealAmount(healAmount);
        }

        private void ShowFantasyTooltip(FantasyData fantasy)
        {
            if (fantasyTooltipRoot == null || fantasy == null)
                return;

            fantasyTooltipName.text = DisplayName(fantasy);
            fantasyTooltipDescription.text = DescriptionText(fantasy);
            fantasyTooltipEffect.text = EffectSummary(fantasy);
            fantasyTooltipRoot.gameObject.SetActive(true);
        }

        private void HideFantasyTooltip()
        {
            if (fantasyTooltipRoot != null)
                fantasyTooltipRoot.gameObject.SetActive(false);
        }

        private static string DisplayName(FantasyData fantasy)
        {
            if (fantasy == null)
                return string.Empty;
            if (!string.IsNullOrWhiteSpace(fantasy.displayName))
                return fantasy.displayName;
            if (!string.IsNullOrWhiteSpace(fantasy.devName))
                return fantasy.devName;
            return fantasy.id;
        }

        private static string DescriptionText(FantasyData fantasy)
        {
            if (fantasy == null)
                return string.Empty;
            if (!string.IsNullOrWhiteSpace(fantasy.description))
                return fantasy.description;
            return fantasy.descStringId;
        }

        private static string EffectSummary(FantasyData fantasy)
        {
            if (fantasy == null || fantasy.effects == null || fantasy.effects.Length == 0)
                return string.Empty;

            FantasyEffectData effect = fantasy.effects[0];
            string trigger = !string.IsNullOrWhiteSpace(effect.trigger) ? effect.trigger : fantasy.triggerType;
            string target = !string.IsNullOrWhiteSpace(effect.target) ? effect.target : "Effect";
            string calc = !string.IsNullOrWhiteSpace(effect.calc) ? effect.calc : "Apply";
            string value = effect.hasNumericValue ? effect.numericValue.ToString(System.Globalization.CultureInfo.InvariantCulture) : (!string.IsNullOrWhiteSpace(effect.valueExpression) ? effect.valueExpression : "0");
            return $"{trigger} / {target} / {calc} {value}";
        }

        private Color GradeColor(FantasyGrade grade)
        {
            switch (grade)
            {
                case FantasyGrade.Blue:
                    return new Color(0.24f, 0.74f, 0.90f, 1f);
                case FantasyGrade.Red:
                    return new Color(1f, 0.32f, 0.32f, 1f);
                default:
                    return textColor;
            }
        }

        private void DrawDigit(RectTransform digitRoot, int digit)
        {
            MatchPattern pattern = null;
            foreach (MatchPattern candidate in MatchPatternTable.DigitPatterns)
            {
                if (candidate.value == digit)
                {
                    pattern = candidate;
                    break;
                }
            }

            if (pattern == null)
                return;

            for (int i = 0; i < pattern.segments.Length; i++)
                CreateMatchSegment(digitRoot, (MatchSegment)pattern.segments[i]);
        }

        private void CreateMatchSegment(RectTransform digitRoot, MatchSegment segment)
        {
            RectTransform match = CreatePanel($"Segment{segment}", digitRoot, matchColor, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), SegmentPosition(segment), SegmentSize(segment));
            match.gameObject.AddComponent<MatchstickView>();
            match.localEulerAngles = new Vector3(0f, 0f, SegmentRotation(segment));
        }

        private static Vector2 SegmentPosition(MatchSegment segment)
        {
            switch (segment)
            {
                case MatchSegment.Top:
                    return new Vector2(0f, 74f);
                case MatchSegment.UpperRight:
                    return new Vector2(45f, 38f);
                case MatchSegment.LowerRight:
                    return new Vector2(45f, -38f);
                case MatchSegment.Bottom:
                    return new Vector2(0f, -74f);
                case MatchSegment.LowerLeft:
                    return new Vector2(-45f, -38f);
                case MatchSegment.UpperLeft:
                    return new Vector2(-45f, 38f);
                case MatchSegment.Middle:
                    return new Vector2(0f, 0f);
                default:
                    return Vector2.zero;
            }
        }

        private static Vector2 SegmentSize(MatchSegment segment)
        {
            switch (segment)
            {
                case MatchSegment.UpperRight:
                case MatchSegment.LowerRight:
                case MatchSegment.LowerLeft:
                case MatchSegment.UpperLeft:
                    return new Vector2(14f, 72f);
                default:
                    return new Vector2(78f, 14f);
            }
        }

        private static float SegmentRotation(MatchSegment segment)
        {
            return 0f;
        }

        private static void ClearChildren(Transform root)
        {
            for (int i = root.childCount - 1; i >= 0; i--)
                Destroy(root.GetChild(i).gameObject);
        }

        private static Image CreateImage(string name, Transform parent, Color color)
        {
            GameObject go = new GameObject(name, typeof(RectTransform), typeof(CanvasRenderer), typeof(Image));
            go.transform.SetParent(parent, false);
            Image image = go.GetComponent<Image>();
            image.color = color;
            return image;
        }

        private static RectTransform CreatePanel(string name, Transform parent, Color color, Vector2 anchorMin, Vector2 anchorMax, Vector2 anchoredPosition, Vector2 sizeDelta)
        {
            Image image = CreateImage(name, parent, color);
            RectTransform rect = image.rectTransform;
            rect.anchorMin = anchorMin;
            rect.anchorMax = anchorMax;
            rect.pivot = new Vector2(0.5f, 0.5f);
            rect.anchoredPosition = anchoredPosition;
            rect.sizeDelta = sizeDelta;
            return rect;
        }

        private static Text CreateText(string name, Transform parent, string value, int fontSize, Color color, TextAnchor alignment)
        {
            GameObject go = new GameObject(name, typeof(RectTransform), typeof(CanvasRenderer), typeof(Text));
            go.transform.SetParent(parent, false);
            Text text = go.GetComponent<Text>();
            text.text = value;
            text.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            text.fontSize = fontSize;
            text.fontStyle = FontStyle.Bold;
            text.alignment = alignment;
            text.color = color;
            text.raycastTarget = false;
            return text;
        }

        private static RectTransform CreateRect(string name, Transform parent, Vector2 anchorMin, Vector2 anchorMax, Vector2 offsetMin, Vector2 offsetMax)
        {
            GameObject go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(parent, false);
            RectTransform rect = go.GetComponent<RectTransform>();
            rect.anchorMin = anchorMin;
            rect.anchorMax = anchorMax;
            rect.offsetMin = offsetMin;
            rect.offsetMax = offsetMax;
            return rect;
        }

        private static void SetRect(RectTransform rect, Vector2 anchorMin, Vector2 anchorMax, Vector2 anchoredPosition, Vector2 sizeDelta)
        {
            rect.anchorMin = anchorMin;
            rect.anchorMax = anchorMax;
            rect.pivot = new Vector2(0.5f, 0.5f);
            rect.anchoredPosition = anchoredPosition;
            rect.sizeDelta = sizeDelta;
        }

        private sealed class FantasyTooltipTrigger : MonoBehaviour, IPointerEnterHandler, IPointerExitHandler
        {
            private RestView owner;
            private FantasyData fantasy;

            public void Initialize(RestView tooltipOwner, FantasyData tooltipFantasy)
            {
                owner = tooltipOwner;
                fantasy = tooltipFantasy;
            }

            public void OnPointerEnter(PointerEventData eventData)
            {
                owner?.ShowFantasyTooltip(fantasy);
            }

            public void OnPointerExit(PointerEventData eventData)
            {
                owner?.HideFantasyTooltip();
            }
        }
    }
}
