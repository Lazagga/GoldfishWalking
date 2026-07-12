using System.Collections.Generic;
using GoldfishWalking.Core;
using GoldfishWalking.Data;
using GoldfishWalking.Fantasy;
using UnityEngine;
using UnityEngine.UI;
#if UNITY_EDITOR
using UnityEditor;
#endif

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
        private RectTransform fantasyTooltipRoot;
        private Image overlayImage;
        private Text healthText;
        private Text fantasyTooltipName;
        private Text fantasyTooltipDescription;
        private Text fantasyTooltipEffect;
        private FantasyTooltipView fantasyTooltipView;
        private FantasyListView fantasyListView;
        private Image screenBackgroundImage;
        private Button nextButton;
        private Button rerollButton;
        private bool hasFantasyReward;
        private bool hasExtraMatchReward;
        private bool hasEraserReward;

        private void Awake()
        {
            ResolveReferences();
            HideScenePlaceholders();
            EnsureLayout();
            BindExistingLayout();
            HideScreenBackground();
            HideRewardChrome();
            BindButtons();
        }

        private void OnEnable()
        {
            transform.SetAsLastSibling();
            ResolveReferences();
            HideScenePlaceholders();
            EnsureLayout();
            BindExistingLayout();
            HideScreenBackground();
            HideRewardChrome();
            PrepareRewardList();
            SetRewardChromeVisible(true);
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

        private void RemoveExistingLayoutImmediate()
        {
            layoutRoot = null;

            for (int i = transform.childCount - 1; i >= 0; i--)
            {
                Transform child = transform.GetChild(i);
                if (child.name != "RewardRuntimeLayout")
                    continue;

                DestroyImmediate(child.gameObject);
            }
        }

#if UNITY_EDITOR
        [ContextMenu("Rebuild Scene UI Layout")]
        public void RebuildSceneUILayout()
        {
            ResolveReferences();
            RemoveExistingLayoutImmediate();
            EnsureLayout();
            BindExistingLayout();
            EditorUtility.SetDirty(gameObject);
            UnityEditor.SceneManagement.EditorSceneManager.MarkSceneDirty(gameObject.scene);
        }
#endif

        private void EnsureLayout()
        {
            if (layoutRoot != null)
                return;

            Transform existing = transform.Find("RewardRuntimeLayout");
            if (existing is RectTransform existingLayout)
            {
                layoutRoot = existingLayout;
                BindExistingLayout();
                return;
            }

            Debug.LogError("[RewardView] Missing prebuilt RewardRuntimeLayout. Build the UI in the scene instead of creating it from script.");
        }

        private void BindExistingLayout()
        {
            if (layoutRoot == null)
                return;

            rewardListRoot = FindRect("RewardList");
            rewardCardRoot = FindRect("RewardCards");
            fantasySlotsRoot = FindRect("FantasySlots");
            consumablePanel = FindRect("ConsumablePanel");
            overlayImage = FindComponent<Image>("Overlay");
            rerollButton = FindComponent<Button>("RerollButton");
            nextButton = FindComponent<Button>("NextButton");
            fantasyListView = FindComponent<FantasyListView>("FantasySlots/Viewport/Content");
            fantasyTooltipRoot = FindRect("FantasyTooltip");
            fantasyTooltipName = FindComponent<Text>("FantasyTooltip/Name");
            fantasyTooltipDescription = FindComponent<Text>("FantasyTooltip/Description");
            fantasyTooltipEffect = FindComponent<Text>("FantasyTooltip/Effect");
            fantasyTooltipView = fantasyTooltipRoot != null ? fantasyTooltipRoot.GetComponent<FantasyTooltipView>() : null;
            if (fantasyTooltipView != null)
                fantasyTooltipView.Bind(fantasyTooltipName, fantasyTooltipDescription, fantasyTooltipEffect);
            else if (fantasyTooltipRoot != null)
                Debug.LogWarning("[RewardView] Missing FantasyTooltipView on FantasyTooltip.");
            screenBackgroundImage = GetComponent<Image>();
            HideRewardChrome();
        }

        private RectTransform FindRect(string path)
        {
            Transform child = layoutRoot != null ? layoutRoot.Find(path) : null;
            return child as RectTransform;
        }

        private T FindComponent<T>(string path) where T : Component
        {
            Transform child = layoutRoot != null ? layoutRoot.Find(path) : null;
            return child != null ? child.GetComponent<T>() : null;
        }

        private void HideScreenBackground()
        {
            if (screenBackgroundImage == null)
                screenBackgroundImage = GetComponent<Image>();

            if (screenBackgroundImage != null)
            {
                screenBackgroundImage.enabled = false;
                screenBackgroundImage.raycastTarget = false;
            }
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

            SetRewardChromeVisible(true);
            ClearChildren(rewardListRoot);
            rewardListRoot.gameObject.SetActive(true);

            float rowY = -102f;
            const float rowStep = 145f;
            if (hasFantasyReward)
            {
                CreateRewardListRow("FantasyReward", "★", GradeColor(FantasyGrade.White), rowY, OpenFantasyChoices);
                rowY -= rowStep;
            }

            if (hasExtraMatchReward)
            {
                CreateRewardListRow("ExtraMatchReward", "+", new Color(1f, 0.30f, 0.30f, 1f), rowY, ClaimExtraMatch);
                rowY -= rowStep;
            }

            if (hasEraserReward)
            {
                CreateRewardListRow("EraserReward", "-", textColor, rowY, ClaimEraser);
                rowY -= rowStep;
            }

            CreateCloseButton();

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

            Text label = CreateText("Label", row, RewardRowLabel(name), 26, textColor, TextAnchor.MiddleLeft);
            SetRect(label.rectTransform, Vector2.zero, Vector2.one, new Vector2(52f, 0f), new Vector2(-144f, -20f));
        }

        private static string RewardRowLabel(string name)
        {
            switch (name)
            {
                case "FantasyReward":
                    return "Fantasy";
                case "ExtraMatchReward":
                    return "Extra Match";
                case "EraserReward":
                    return "Eraser";
                default:
                    return name;
            }
        }

        private void CreateCloseButton()
        {
            RectTransform panel = CreatePanel("CloseButton", rewardListRoot, slotColor, new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(0f, 78f), new Vector2(232f, 96f));
            Button closeButton = panel.gameObject.AddComponent<Button>();
            closeButton.onClick.AddListener(CloseRewardList);
            Text closeText = CreateText("Label", panel, "Close", 31, textColor, TextAnchor.MiddleCenter);
            SetRect(closeText.rectTransform, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
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
            if (rewardCardRoot == null)
                return;

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

            Refresh();
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
            Text name = CreateText("Name", descPanel, FantasyText.DisplayName(fantasy), 24, textColor, TextAnchor.UpperCenter);
            SetRect(name.rectTransform, new Vector2(0f, 0.64f), Vector2.one, new Vector2(0f, -18f), new Vector2(-26f, -16f));

            Text description = CreateText("Description", descPanel, FantasyText.Description(fantasy), 18, textColor, TextAnchor.UpperLeft);
            SetRect(description.rectTransform, new Vector2(0f, 0.24f), new Vector2(1f, 0.70f), new Vector2(0f, -8f), new Vector2(-28f, -8f));

            Text effect = CreateText("Effect", descPanel, FantasyText.EffectSummary(fantasy), 15, cyanColor, TextAnchor.UpperLeft);
            SetRect(effect.rectTransform, Vector2.zero, new Vector2(1f, 0.28f), new Vector2(0f, 8f), new Vector2(-28f, -8f));
        }

        private void SelectReward(FantasyData fantasy)
        {
            if (!hasFantasyReward || fantasy == null || bootstrap == null || bootstrap.RunContext == null)
                return;

            bootstrap.RunContext.fantasyInventory.Add(fantasy);
            fantasyEffectRunner.Apply(fantasy, bootstrap.RunContext, "On_Acquire");
            fantasyEffectRunner.Apply(fantasy, bootstrap.RunContext, "Acquire");
            FantasyCollectionRules.ApplyPostAcquireTransforms(bootstrap.RunContext.fantasyInventory, fantasyDatabase);
            hasFantasyReward = false;
            CloseFantasyChoices();
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
            RebuildRewardList();
        }

        private void ClaimEraser()
        {
            if (!hasEraserReward || bootstrap == null || bootstrap.RunContext == null)
                return;

            fantasyEffectRunner.AddItemWithAcquireEffects(bootstrap.RunContext, ItemType.Eraser, 1);
            hasEraserReward = false;
            RebuildRewardList();
        }

        private void CloseFantasyChoices()
        {
            HideFantasyTooltip();

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
            SetRewardChromeVisible(false);
        }

        private void SetRewardChromeVisible(bool visible)
        {
            if (overlayImage != null)
            {
                overlayImage.raycastTarget = false;
                overlayImage.gameObject.SetActive(false);
            }

            HideRewardChrome();
        }

        private bool HasPendingRewards()
        {
            return hasFantasyReward || hasExtraMatchReward || hasEraserReward;
        }

        private void BindButtons()
        {
            if (nextButton != null)
                nextButton.onClick.AddListener(CompleteReward);
            if (rerollButton != null)
                rerollButton.onClick.AddListener(RerollFantasyChoices);
        }

        private void UnbindButtons()
        {
            if (nextButton != null)
                nextButton.onClick.RemoveListener(CompleteReward);
            if (rerollButton != null)
                rerollButton.onClick.RemoveListener(RerollFantasyChoices);
        }

        private void Refresh()
        {
            if (rerollButton != null)
                rerollButton.interactable = bootstrap != null && bootstrap.RunContext != null && bootstrap.RunContext.rewardRerolls > 0 && rewardCardRoot != null && rewardCardRoot.gameObject.activeSelf;
        }

        private void HideRewardChrome()
        {
            if (layoutRoot == null)
                return;

            HideChild("StatusPanel");
            HideChild("MoveCounter");
            HideChild("CurrencyPanel");
            HideChild("FantasySlots");
            HideChild("ConsumablePanel");
            HideChild("FantasyTooltip");
            HideChild("Overlay");
        }

        private void HideChild(string childName)
        {
            Transform child = layoutRoot.Find(childName);
            if (child != null)
                child.gameObject.SetActive(false);
        }

        private void RerollFantasyChoices()
        {
            if (bootstrap == null || bootstrap.RunContext == null || bootstrap.RunContext.rewardRerolls <= 0)
                return;
            if (rewardCardRoot == null || !rewardCardRoot.gameObject.activeSelf)
                return;

            bootstrap.RunContext.rewardRerolls--;
            PrepareFantasyChoices();
            Refresh();
        }

        private void RefreshFantasySlots()
        {
            if (fantasyListView != null)
            {
                fantasyListView.Refresh(bootstrap != null && bootstrap.RunContext != null
                    ? bootstrap.RunContext.fantasyInventory.ownedFantasies
                    : null);
                if (fantasySlotsRoot != null)
                    fantasySlotsRoot.SetAsLastSibling();
                if (fantasyTooltipRoot != null)
                    fantasyTooltipRoot.SetAsLastSibling();
                return;
            }

            Debug.LogWarning("[RewardView] Missing FantasyListView on FantasySlots/Viewport/Content.");
        }
        private void ShowFantasyTooltip(FantasyData fantasy)
        {
            if (fantasyTooltipView != null)
                fantasyTooltipView.Show(fantasy);
        }

        private void HideFantasyTooltip()
        {
            if (fantasyTooltipView != null)
                fantasyTooltipView.Hide();
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

            int extraMatchCount = bootstrap != null && bootstrap.RunContext != null
                ? bootstrap.RunContext.itemInventory.GetCount(ItemType.ExtraMatch)
                : 0;
            int eraserCount = bootstrap != null && bootstrap.RunContext != null
                ? bootstrap.RunContext.itemInventory.GetCount(ItemType.Eraser)
                : 0;

            SetConsumableCount(0, extraMatchCount);
            SetConsumableCount(1, eraserCount);
        }

        private void SetConsumableCount(int slotIndex, int count)
        {
            if (consumablePanel == null || slotIndex < 0 || slotIndex >= consumablePanel.childCount)
                return;

            Text countText = consumablePanel.GetChild(slotIndex).Find("Badge/Count")?.GetComponent<Text>();
            if (countText != null)
                countText.text = count.ToString(System.Globalization.CultureInfo.InvariantCulture);
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

        private static void SetRect(RectTransform rect, Vector2 anchorMin, Vector2 anchorMax, Vector2 anchoredPosition, Vector2 sizeDelta)
        {
            rect.anchorMin = anchorMin;
            rect.anchorMax = anchorMax;
            rect.pivot = new Vector2(0.5f, 0.5f);
            rect.anchoredPosition = anchoredPosition;
            rect.sizeDelta = sizeDelta;
        }

        private static void ClearChildren(Transform root)
        {
            if (root == null)
                return;

            for (int i = root.childCount - 1; i >= 0; i--)
            {
                GameObject child = root.GetChild(i).gameObject;
                if (Application.isPlaying)
                    Destroy(child);
                else
                    DestroyImmediate(child);
            }
        }
    }
}
