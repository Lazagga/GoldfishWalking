using System.Collections.Generic;
using GoldfishWalking.Core;
using GoldfishWalking.Data;
using GoldfishWalking.Fantasy;
using UnityEngine;
using UnityEngine.UI;

namespace GoldfishWalking.UI
{
    public sealed class RewardView : MonoBehaviour
    {
        private const int RewardCount = 3;

        [SerializeField] private GameBootstrap bootstrap;
        [SerializeField] private FantasyDatabase fantasyDatabase;

        private readonly FantasyRewardSelector rewardSelector = new FantasyRewardSelector();
        private readonly FantasyEffectRunner fantasyEffectRunner = new FantasyEffectRunner();
        private readonly List<FantasyData> currentRewards = new List<FantasyData>();
        private readonly Color overlayColor = new Color(0.03f, 0.035f, 0.05f, 0.78f);
        private readonly Color panelColor = new Color(0.14f, 0.16f, 0.20f, 0.94f);
        private readonly Color slotColor = new Color(0.20f, 0.22f, 0.29f, 0.96f);
        private readonly Color textColor = new Color(0.95f, 0.97f, 1f, 1f);
        private readonly Color greenColor = new Color(0.13f, 0.86f, 0.43f, 1f);
        private readonly Color cyanColor = new Color(0.24f, 0.74f, 0.90f, 1f);
        private readonly Color healthColor = new Color(1f, 0.32f, 0.32f, 1f);

        private RectTransform layoutRoot;
        private RectTransform rewardListRoot;
        private RectTransform rewardCardRoot;
        private RectTransform fantasySlotsRoot;
        private RectTransform consumablePanel;
        private Text healthText;
        private Button nextButton;
        private bool hasFantasyReward;
        private bool hasExtraMatchReward;
        private bool hasEraserReward;

        private void Awake()
        {
            ResolveReferences();
            HideScenePlaceholders();
            EnsureLayout();
            BindButtons();
        }

        private void OnEnable()
        {
            transform.SetAsLastSibling();
            ResolveReferences();
            HideScenePlaceholders();
            EnsureLayout();
            PrepareRewardList();
            CloseFantasyChoices();
            RebuildRewardList();
            Refresh();
        }

        private void OnDestroy()
        {
            UnbindButtons();
        }

        public void CompleteReward()
        {
            GameEventHub.RaiseRewardCompleted();
        }

        private void ResolveReferences()
        {
            if (bootstrap == null)
                bootstrap = FindFirstObjectByType<GameBootstrap>(FindObjectsInactive.Include);
        }

        private void HideScenePlaceholders()
        {
            for (int i = 0; i < transform.childCount; i++)
            {
                Transform child = transform.GetChild(i);
                if (layoutRoot != null && child == layoutRoot)
                    continue;
                if (child.name == "RewardRuntimeLayout")
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

            layoutRoot = CreateRect("RewardRuntimeLayout", transform, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
            layoutRoot.offsetMin = Vector2.zero;
            layoutRoot.offsetMax = Vector2.zero;

            CreateBackground();
            CreateStatusArea();
            CreateMoveCounter();
            CreateCurrencyPanel();
            CreateRewardList();
            CreateRewardCards();
            CreateBottomInventory();
            CreateRerollButton();
            CreateNextButton();
        }

        private void CreateBackground()
        {
            Image background = CreateImage("Overlay", layoutRoot, overlayColor);
            RectTransform rect = background.rectTransform;
            rect.anchorMin = Vector2.zero;
            rect.anchorMax = Vector2.one;
            rect.offsetMin = Vector2.zero;
            rect.offsetMax = Vector2.zero;
        }

        private void CreateStatusArea()
        {
            RectTransform statusPanel = CreatePanel("StatusPanel", layoutRoot, panelColor, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(300f, -105f), new Vector2(484f, 112f));

            Text nameText = CreateText("Name", statusPanel, "성냥팔이 소녀", 28, textColor, TextAnchor.MiddleLeft);
            SetRect(nameText.rectTransform, new Vector2(0f, 0f), new Vector2(0f, 1f), new Vector2(160f, 0f), new Vector2(260f, 112f));

            healthText = CreateText("Health", statusPanel, string.Empty, 34, healthColor, TextAnchor.MiddleRight);
            SetRect(healthText.rectTransform, new Vector2(1f, 0f), new Vector2(1f, 1f), new Vector2(-74f, 0f), new Vector2(90f, 112f));

            fantasySlotsRoot = CreatePanel("FantasySlots", layoutRoot, panelColor, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(299f, -228f), new Vector2(482f, 88f));
        }

        private void CreateMoveCounter()
        {
            RectTransform counter = CreatePanel("MoveCounter", layoutRoot, panelColor, new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(0f, -104f), new Vector2(404f, 122f));
            Text label = CreateText("MoveLabel", counter, "이동 횟수", 22, textColor, TextAnchor.MiddleCenter);
            SetRect(label.rectTransform, new Vector2(0f, 0.52f), new Vector2(1f, 1f), new Vector2(0f, -8f), new Vector2(0f, 42f));
            Text count = CreateText("MoveCount", counter, "2 / 2", 42, cyanColor, TextAnchor.MiddleCenter);
            SetRect(count.rectTransform, new Vector2(0f, 0f), new Vector2(1f, 0.65f), new Vector2(0f, -4f), new Vector2(0f, 70f));
        }

        private void CreateCurrencyPanel()
        {
            RectTransform currency = CreatePanel("CurrencyPanel", layoutRoot, panelColor, new Vector2(1f, 1f), new Vector2(1f, 1f), new Vector2(-300f, -105f), new Vector2(484f, 112f));
            Text label = CreateText("CurrencyLabel", currency, "요정", 28, textColor, TextAnchor.MiddleLeft);
            SetRect(label.rectTransform, new Vector2(0f, 0f), new Vector2(0f, 1f), new Vector2(108f, 0f), new Vector2(170f, 112f));
            Text value = CreateText("CurrencyValue", currency, "0", 34, greenColor, TextAnchor.MiddleRight);
            SetRect(value.rectTransform, new Vector2(1f, 0f), new Vector2(1f, 1f), new Vector2(-66f, 0f), new Vector2(90f, 112f));
        }

        private void CreateRewardCards()
        {
            rewardCardRoot = CreateRect("RewardCards", layoutRoot, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
            rewardCardRoot.gameObject.SetActive(false);
        }

        private void CreateRewardList()
        {
            rewardListRoot = CreatePanel("RewardList", layoutRoot, panelColor, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0f, -22f), new Vector2(500f, 608f));
        }

        private void CreateBottomInventory()
        {
            consumablePanel = CreatePanel("ConsumablePanel", layoutRoot, panelColor, new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(0f, 96f), new Vector2(364f, 116f));
            RefreshConsumables();
        }

        private void CreateSmallItem(RectTransform parent, Vector2 position, Color itemColor, string count)
        {
            RectTransform slot = CreatePanel("ItemSlot", parent, slotColor, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), position, new Vector2(88f, 88f));
            Text icon = CreateText("Icon", slot, "■", 31, itemColor, TextAnchor.MiddleCenter);
            SetRect(icon.rectTransform, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);

            RectTransform badge = CreatePanel("Badge", slot, panelColor, new Vector2(1f, 1f), new Vector2(1f, 1f), new Vector2(-12f, -12f), new Vector2(38f, 38f));
            Text badgeText = CreateText("Count", badge, count, 22, textColor, TextAnchor.MiddleCenter);
            SetRect(badgeText.rectTransform, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
        }

        private void CreateRerollButton()
        {
            RectTransform panel = CreatePanel("RerollButton", layoutRoot, panelColor, new Vector2(0f, 0f), new Vector2(0f, 0f), new Vector2(160f, 96f), new Vector2(112f, 112f));
            Text icon = CreateText("Icon", panel, "↻", 48, textColor, TextAnchor.MiddleCenter);
            SetRect(icon.rectTransform, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
        }

        private void CreateNextButton()
        {
            nextButton = CreateButton("NextButton", "다음 지역으로 이동 →", new Vector2(-281f, 96f), new Vector2(486f, 112f), 31, true);
        }

        private Button CreateButton(string name, string label, Vector2 anchoredPosition, Vector2 size, int fontSize, bool rightAnchor = false)
        {
            Vector2 anchor = rightAnchor ? new Vector2(1f, 0f) : new Vector2(0f, 0f);
            RectTransform panel = CreatePanel(name, layoutRoot, panelColor, anchor, anchor, anchoredPosition, size);
            Button button = panel.gameObject.AddComponent<Button>();
            Text buttonText = CreateText("Label", panel, label, fontSize, greenColor, TextAnchor.MiddleCenter);
            SetRect(buttonText.rectTransform, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
            return button;
        }

        private void PrepareRewardList()
        {
            hasFantasyReward = true;
            if (bootstrap != null && bootstrap.RunContext != null)
            {
                int itemChance = Mathf.Clamp(fantasyEffectRunner.ModifyValue(bootstrap.RunContext, 50, "Battle_Reward", "Item_Chance"), 0, 100);
                hasExtraMatchReward = bootstrap.RunContext.RollValue("reward.extra_match", 0, 99) < itemChance;
                hasEraserReward = bootstrap.RunContext.RollValue("reward.eraser", 0, 99) < itemChance;
                return;
            }

            hasExtraMatchReward = Random.value < 0.5f;
            hasEraserReward = Random.value < 0.5f;
        }

        private void RebuildRewardList()
        {
            if (rewardListRoot == null)
                return;

            ClearChildren(rewardListRoot);
            rewardListRoot.gameObject.SetActive(true);

            float rowY = -102f;
            if (hasFantasyReward)
            {
                CreateRewardListRow(
                    "FantasyReward",
                    "★",
                    GradeColor(FantasyGrade.White),
                    rowY,
                    OpenFantasyChoices);
                rowY -= 145f;
            }

            if (hasExtraMatchReward)
            {
                CreateRewardListRow(
                    "ExtraMatchReward",
                    "●",
                    new Color(1f, 0.30f, 0.30f, 1f),
                    rowY,
                    ClaimExtraMatch);
                rowY -= 145f;
            }

            if (hasEraserReward)
            {
                CreateRewardListRow(
                    "EraserReward",
                    "■",
                    textColor,
                    rowY,
                    ClaimEraser);
            }

            Button closeButton = CreatePanel("CloseButton", rewardListRoot, slotColor, new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(0f, 78f), new Vector2(232f, 96f)).gameObject.AddComponent<Button>();
            Text closeText = CreateText("Label", closeButton.transform, "Close", 31, textColor, TextAnchor.MiddleCenter);
            SetRect(closeText.rectTransform, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
            closeButton.onClick.AddListener(CloseRewardList);

            if (!HasPendingRewards())
                CloseRewardList();
        }

        private void CreateRewardListRow(string name, string iconText, Color iconColor, float y, UnityEngine.Events.UnityAction onClick)
        {
            RectTransform row = CreatePanel(name, rewardListRoot, slotColor, new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(0f, y), new Vector2(420f, 124f));
            Button button = row.gameObject.AddComponent<Button>();
            button.onClick.AddListener(onClick);

            RectTransform iconPanel = CreatePanel("IconPanel", row, panelColor, new Vector2(0f, 0.5f), new Vector2(0f, 0.5f), new Vector2(62f, 0f), new Vector2(90f, 90f));
            Text icon = CreateText("Icon", iconPanel, iconText, 48, iconColor, TextAnchor.MiddleCenter);
            SetRect(icon.rectTransform, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
        }

        private void OpenFantasyChoices()
        {
            if (!hasFantasyReward)
                return;

            if (rewardListRoot != null)
                rewardListRoot.gameObject.SetActive(false);

            PrepareFantasyChoices();
        }

        private void PrepareFantasyChoices()
        {
            currentRewards.Clear();
            if (bootstrap != null && bootstrap.RunContext != null)
                currentRewards.AddRange(rewardSelector.SelectRewards(fantasyDatabase, bootstrap.RunContext.fantasyInventory, RewardCount, bootstrap.RunContext));

            for (int i = currentRewards.Count; i < RewardCount; i++)
            {
                currentRewards.Add(new FantasyData
                {
                    id = $"prototype_reward_{i + 1}",
                    displayName = $"환상 {i + 1}",
                    grade = FantasyGrade.White,
                    description = "임시 환상 보상",
                    trigger = FantasyTrigger.None,
                    target = FantasyTarget.None
                });
            }

            RebuildRewardCards();
        }

        private void RebuildRewardCards()
        {
            ClearChildren(rewardCardRoot);
            rewardCardRoot.gameObject.SetActive(true);

            Vector2[] positions =
            {
                new Vector2(-440f, -50f),
                new Vector2(0f, -50f),
                new Vector2(440f, -50f)
            };

            for (int i = 0; i < RewardCount; i++)
                CreateRewardCard(currentRewards[i], positions[i]);
        }

        private void CreateRewardCard(FantasyData fantasy, Vector2 position)
        {
            RectTransform card = CreatePanel($"RewardCard_{fantasy.id}", rewardCardRoot, panelColor, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), position, new Vector2(354f, 592f));
            Button button = card.gameObject.AddComponent<Button>();
            button.onClick.AddListener(() => SelectReward(fantasy));

            RectTransform iconPanel = CreatePanel("IconPanel", card, slotColor, new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(0f, -166f), new Vector2(250f, 250f));
            Text icon = CreateText("Icon", iconPanel, "★", 92, GradeColor(fantasy.grade), TextAnchor.MiddleCenter);
            SetRect(icon.rectTransform, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);

            RectTransform descPanel = CreatePanel("DescriptionPanel", card, slotColor, new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(0f, 142f), new Vector2(264f, 210f));
            Text name = CreateText("Name", descPanel, DisplayName(fantasy), 24, textColor, TextAnchor.UpperCenter);
            SetRect(name.rectTransform, new Vector2(0f, 0.64f), Vector2.one, new Vector2(0f, -18f), new Vector2(-26f, -16f));

            Text description = CreateText("Description", descPanel, DescriptionText(fantasy), 18, textColor, TextAnchor.UpperLeft);
            SetRect(description.rectTransform, new Vector2(0f, 0.24f), new Vector2(1f, 0.70f), new Vector2(0f, -8f), new Vector2(-28f, -8f));

            Text effect = CreateText("Effect", descPanel, EffectSummary(fantasy), 15, cyanColor, TextAnchor.UpperLeft);
            SetRect(effect.rectTransform, Vector2.zero, new Vector2(1f, 0.28f), new Vector2(0f, 8f), new Vector2(-28f, -8f));
        }

        private void SelectReward(FantasyData fantasy)
        {
            if (!hasFantasyReward || fantasy == null || bootstrap == null || bootstrap.RunContext == null)
                return;

            bootstrap.RunContext.fantasyInventory.Add(fantasy);
            fantasyEffectRunner.Apply(fantasy, bootstrap.RunContext, "On_Acquire");
            fantasyEffectRunner.Apply(fantasy, bootstrap.RunContext, "Acquire");
            hasFantasyReward = false;
            CloseFantasyChoices();
            RefreshFantasySlots();
            Refresh();

            if (HasPendingRewards())
                RebuildRewardList();
            else
                CloseRewardList();
        }

        private void ClaimExtraMatch()
        {
            if (!hasExtraMatchReward || bootstrap == null || bootstrap.RunContext == null)
                return;

            fantasyEffectRunner.AddItemWithAcquireEffects(bootstrap.RunContext, ItemType.ExtraMatch, 1);
            hasExtraMatchReward = false;
            RefreshConsumables();
            RebuildRewardList();
        }

        private void ClaimEraser()
        {
            if (!hasEraserReward || bootstrap == null || bootstrap.RunContext == null)
                return;

            fantasyEffectRunner.AddItemWithAcquireEffects(bootstrap.RunContext, ItemType.Eraser, 1);
            hasEraserReward = false;
            RefreshConsumables();
            RebuildRewardList();
        }

        private void CloseFantasyChoices()
        {
            if (rewardCardRoot == null)
                return;

            ClearChildren(rewardCardRoot);
            rewardCardRoot.gameObject.SetActive(false);
        }

        private void CloseRewardList()
        {
            CloseFantasyChoices();
            if (rewardListRoot != null)
                rewardListRoot.gameObject.SetActive(false);
        }

        private bool HasPendingRewards()
        {
            return hasFantasyReward || hasExtraMatchReward || hasEraserReward;
        }

        private void BindButtons()
        {
            if (nextButton != null)
                nextButton.onClick.AddListener(CompleteReward);
        }

        private void UnbindButtons()
        {
            if (nextButton != null)
                nextButton.onClick.RemoveListener(CompleteReward);
        }

        private void Refresh()
        {
            if (healthText != null)
                healthText.text = bootstrap != null && bootstrap.RunContext != null ? bootstrap.RunContext.health.ToString() : "0";
            RefreshFantasySlots();
            RefreshConsumables();
        }

        private void RefreshFantasySlots()
        {
            if (fantasySlotsRoot == null)
                return;

            ClearChildren(fantasySlotsRoot);
            List<FantasyData> owned = bootstrap != null && bootstrap.RunContext != null
                ? bootstrap.RunContext.fantasyInventory.ownedFantasies
                : null;

            for (int i = 0; i < 6; i++)
            {
                RectTransform slot = CreatePanel($"FantasySlot{i + 1}", fantasySlotsRoot, slotColor, new Vector2(0f, 0.5f), new Vector2(0f, 0.5f), new Vector2(48f + i * 76f, 0f), new Vector2(60f, 60f));
                if (owned == null || i >= owned.Count || owned[i] == null)
                    continue;

                Text icon = CreateText("FantasyIcon", slot, "★", 29, GradeColor(owned[i].grade), TextAnchor.MiddleCenter);
                SetRect(icon.rectTransform, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
            }
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
            string value = !string.IsNullOrWhiteSpace(effect.valueExpression) ? effect.valueExpression : "0";
            return $"{trigger} / {target} / {calc} {value}";
        }

        private Color GradeColor(FantasyGrade grade)
        {
            switch (grade)
            {
                case FantasyGrade.Blue:
                    return cyanColor;
                case FantasyGrade.Red:
                    return healthColor;
                default:
                    return textColor;
            }
        }

        private void RefreshConsumables()
        {
            if (consumablePanel == null)
                return;

            ClearChildren(consumablePanel);

            int extraMatchCount = bootstrap != null && bootstrap.RunContext != null
                ? bootstrap.RunContext.itemInventory.GetCount(ItemType.ExtraMatch)
                : 0;
            int eraserCount = bootstrap != null && bootstrap.RunContext != null
                ? bootstrap.RunContext.itemInventory.GetCount(ItemType.Eraser)
                : 0;

            CreateSmallItem(consumablePanel, new Vector2(-58f, 0f), new Color(1f, 0.28f, 0.28f, 1f), extraMatchCount.ToString());
            CreateSmallItem(consumablePanel, new Vector2(58f, 0f), new Color(0.95f, 0.97f, 1f, 1f), eraserCount.ToString());
        }

        private static void ClearChildren(Transform root)
        {
            if (root == null)
                return;

            for (int i = root.childCount - 1; i >= 0; i--)
            {
                Transform child = root.GetChild(i);
                GameObject childObject = child.gameObject;
                childObject.SetActive(false);
                child.SetParent(null, false);
                Destroy(childObject);
            }
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
    }
}
