using System.Collections.Generic;
using GoldfishWalking.Core;
using GoldfishWalking.Data;
using GoldfishWalking.Fantasy;
using GoldfishWalking.Map;
using System.Collections;
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
        private readonly List<RectTransform> currentRewardCards = new List<RectTransform>();
        private readonly List<RectTransform> transitioningEmbers = new List<RectTransform>();
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
        private RectTransform consumablePanel;
        private Image overlayImage;
        private Text healthText;
        private Image screenBackgroundImage;
        private Button nextButton;
        private Button rerollButton;
        private bool hasFantasyReward;
        private bool hasExtraMatchReward;
        private bool hasEraserReward;
        private bool isRevealingEmberChoices;

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
            isRevealingEmberChoices = false;
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
            if (IsEmberFantasyReward())
                OpenFantasyChoices();
            PositionNextButtonOverTurnButton();
            Refresh();
        }

        private void OnDestroy()
        {
            UnbindButtons();
        }

        public void CompleteReward()
        {
            if (bootstrap?.RunContext != null)
                bootstrap.RunContext.ForfeitPendingFantasyReward();
            GameEventHub.RaiseRewardCompleted();
        }

        private void PositionNextButtonOverTurnButton()
        {
            if (nextButton == null)
                return;
            RectTransform[] rects = FindObjectsByType<RectTransform>(FindObjectsInactive.Include, FindObjectsSortMode.None);
            for (int i = 0; i < rects.Length; i++)
            {
                if (rects[i].name != "ResolveBattleButton")
                    continue;
                nextButton.transform.position = rects[i].position;
                nextButton.transform.rotation = rects[i].rotation;
                nextButton.gameObject.SetActive(true);
                return;
            }
        }

        private void ResolveReferences()
        {
            if (bootstrap == null)
                Debug.LogError("[RewardView] GameBootstrap must be assigned in GumBwing_Er.unity.", this);
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
            ApplyExpandedPanel(rewardListRoot != null ? rewardListRoot.GetComponent<Image>() : null);
            ConfigureRewardPanelLayout();
            consumablePanel = FindRect("ConsumablePanel");
            overlayImage = FindComponent<Image>("Overlay");
            rerollButton = FindComponent<Button>("RerollButton");
            nextButton = FindComponent<Button>("NextButton");
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
            hasFantasyReward = ShouldOfferFantasyReward();
            if (bootstrap != null && bootstrap.RunContext != null)
            {
                BattleNumberState numbers = bootstrap.RunContext.currentBattle;
                int itemChance = Mathf.Clamp(fantasyEffectRunner.ModifyValue(bootstrap.RunContext, 50, "Battle_Reward", "Item_Chance"), 0, 100);
                if (numbers == null)
                {
                    hasExtraMatchReward = bootstrap.RunContext.RollValue("reward.extra_match", 0, 99) < itemChance;
                    hasEraserReward = bootstrap.RunContext.RollValue("reward.eraser", 0, 99) < itemChance;
                    return;
                }

                if (!numbers.rewardItemsRolled)
                {
                    numbers.rewardExtraMatch = bootstrap.RunContext.RollValue("reward.extra_match", 0, 99) < itemChance;
                    numbers.rewardEraser = bootstrap.RunContext.RollValue("reward.eraser", 0, 99) < itemChance;
                    numbers.rewardItemsRolled = true;
                }

                hasExtraMatchReward = numbers.rewardExtraMatch;
                hasEraserReward = numbers.rewardEraser;
                return;
            }

            hasExtraMatchReward = false;
            hasEraserReward = false;
        }

        private bool ShouldOfferFantasyReward()
        {
            if (bootstrap?.RunContext?.currentNode == null)
                return true;
            if (bootstrap.RunContext.currentNode.nodeType != MapNodeType.NormalBattle)
                return true;
            return bootstrap.RunContext.pendingFantasyRewardGrades != null
                && bootstrap.RunContext.pendingFantasyRewardGrades.Count == RewardCount;
        }

        private void RebuildRewardList()
        {
            if (rewardListRoot == null)
                return;

            SetRewardChromeVisible(true);
            ClearChildren(rewardListRoot);
            rewardListRoot.gameObject.SetActive(true);

            float rowY = -122f;
            const float rowStep = 162f;
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
            RectTransform row = CreatePanel(name, rewardListRoot, slotColor, new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(0f, y), new Vector2(590f, 138f));
            GoldfishWalking.Match.MatchstickVisualSettings.ApplySoloButton(row.GetComponent<Image>());
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
            RectTransform panel = CreatePanel("CloseButton", rewardListRoot, slotColor, new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(0f, 94f), new Vector2(300f, 108f));
            GoldfishWalking.Match.MatchstickVisualSettings.ApplySoloButton(panel.GetComponent<Image>());
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

        private void PrepareFantasyChoices(ISet<string> excludedFantasyIds = null)
        {
            currentRewards.Clear();
            if (bootstrap != null && bootstrap.RunContext != null)
            {
                if (bootstrap.RunContext.currentNode?.nodeType == MapNodeType.NormalBattle
                    && bootstrap.RunContext.pendingFantasyRewardGrades.Count == RewardCount)
                {
                    currentRewards.AddRange(rewardSelector.SelectRewardsForGrades(
                        fantasyDatabase,
                        bootstrap.RunContext.fantasyInventory,
                        bootstrap.RunContext.pendingFantasyRewardGrades,
                        bootstrap.RunContext,
                        excludedFantasyIds));
                }
                else
                {
                    currentRewards.AddRange(rewardSelector.SelectRewards(
                        fantasyDatabase,
                        bootstrap.RunContext.fantasyInventory,
                        RewardCount,
                        bootstrap.RunContext,
                        excludedFantasyIds));
                }
            }

            for (int i = 0; i < RewardCount; i++)
            {
                if (i < currentRewards.Count && currentRewards[i] != null)
                    continue;
                FantasyGrade fallbackGrade = IsEmberFantasyReward()
                    ? bootstrap.RunContext.pendingFantasyRewardGrades[i]
                    : FantasyGrade.White;
                FantasyData fallback = new FantasyData
                {
                    id = $"prototype_reward_{i + 1}",
                    displayName = $"환상 {i + 1}",
                    grade = fallbackGrade,
                    description = "임시 환상 보상",
                    trigger = FantasyTrigger.None,
                    target = FantasyTarget.None
                };
                if (i < currentRewards.Count)
                    currentRewards[i] = fallback;
                else
                    currentRewards.Add(fallback);
            }

            RebuildRewardCards();
        }

        private void RebuildRewardCards()
        {
            if (rewardCardRoot == null)
                return;

            ClearChildren(rewardCardRoot);
            currentRewardCards.Clear();
            rewardCardRoot.gameObject.SetActive(true);

            Vector2[] positions =
            {
                new Vector2(-600f, -20f),
                new Vector2(0f, -20f),
                new Vector2(600f, -20f)
            };

            for (int i = 0; i < RewardCount; i++)
                currentRewardCards.Add(CreateRewardCard(currentRewards[i], positions[i]));

            if (IsEmberFantasyReward())
                StartCoroutine(RevealEmberRewardCards(positions));

            Refresh();
        }

        private RectTransform CreateRewardCard(FantasyData fantasy, Vector2 position)
        {
            RectTransform card = CreatePanel($"RewardCard_{fantasy.id}", rewardCardRoot, panelColor, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), position, new Vector2(560f, 760f));
            ApplyExpandedPanel(card.GetComponent<Image>());
            Button button = card.gameObject.AddComponent<Button>();
            button.onClick.AddListener(() => SelectReward(fantasy));

            RectTransform iconPanel = CreatePanel("IconPanel", card, slotColor, new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(0f, -184f), new Vector2(292f, 292f));
            GameObject iconObject = new GameObject("FantasyIcon", typeof(RectTransform), typeof(CanvasRenderer), typeof(Image));
            RectTransform iconRect = iconObject.GetComponent<RectTransform>();
            iconRect.SetParent(iconPanel, false);
            SetRect(iconRect, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
            Image icon = iconObject.GetComponent<Image>();
            icon.sprite = fantasy.iconSprite;
            icon.preserveAspect = true;
            icon.raycastTarget = false;

            RectTransform descPanel = CreatePanel("DescriptionPanel", card, slotColor, new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(0f, 154f), new Vector2(440f, 226f));
            Text name = CreateText("Name", descPanel, FantasyText.DisplayName(fantasy), 24, textColor, TextAnchor.UpperCenter);
            name.color = FantasyText.GradeColor(fantasy.grade);
            SetRect(name.rectTransform, new Vector2(0f, 0.64f), Vector2.one, new Vector2(0f, -18f), new Vector2(-26f, -16f));

            Text description = CreateText("Description", descPanel, FantasyText.Description(fantasy), 18, textColor, TextAnchor.UpperLeft);
            SetRect(description.rectTransform, new Vector2(0f, 0.06f), new Vector2(1f, 0.70f), new Vector2(0f, 8f), new Vector2(-28f, -8f));
            return card;
        }

        private bool IsEmberFantasyReward()
        {
            return bootstrap?.RunContext?.currentNode?.nodeType == MapNodeType.NormalBattle
                && bootstrap.RunContext.pendingFantasyRewardGrades != null
                && bootstrap.RunContext.pendingFantasyRewardGrades.Count == RewardCount;
        }

        private IEnumerator RevealEmberRewardCards(IReadOnlyList<Vector2> destinations)
        {
            isRevealingEmberChoices = true;
            Refresh();
            CanvasGroup[] cardGroups = new CanvasGroup[currentRewardCards.Count];
            for (int i = 0; i < currentRewardCards.Count; i++)
            {
                currentRewardCards[i].gameObject.SetActive(true);
                cardGroups[i] = currentRewardCards[i].gameObject.AddComponent<CanvasGroup>();
                cardGroups[i].alpha = 0f;
                cardGroups[i].blocksRaycasts = false;
                currentRewardCards[i].localScale = Vector3.one * 0.78f;
            }

            RectTransform player = FindRectInScene("PlayerPortrait");
            Vector2 playerCenter = player != null
                ? WorldToLocal(rewardCardRoot, player.TransformPoint(player.rect.center))
                : new Vector2(-600f, -180f);
            transitioningEmbers.Clear();
            EmberRewardView emberView = FindFirstObjectByType<EmberRewardView>(FindObjectsInactive.Include);
            bool handedOff = emberView != null
                && emberView.TryHandoffOrbitingEmbers(rewardCardRoot, transitioningEmbers);
            if (!handedOff)
            {
                for (int i = 0; i < currentRewardCards.Count; i++)
                {
                    FantasyEmberType type = bootstrap.RunContext.pendingFantasyRewardGrades[i] == FantasyGrade.Blue
                        ? FantasyEmberType.Blue
                        : FantasyEmberType.White;
                    RectTransform fallback = EmberRewardView.CreateEmberVisual(rewardCardRoot, $"ChoiceEmber_{i + 1}", type);
                    float phase = i * Mathf.PI * 2f / RewardCount;
                    fallback.anchoredPosition = playerCenter + new Vector2(Mathf.Cos(phase) * 118f, Mathf.Sin(phase) * 58f + 12f);
                    transitioningEmbers.Add(fallback);
                }
            }
            bootstrap.RunContext.ConsumeCompletedEmbers();

            Vector2[] starts = new Vector2[transitioningEmbers.Count];
            for (int i = 0; i < transitioningEmbers.Count; i++)
                starts[i] = transitioningEmbers[i].anchoredPosition;

            const float stagger = 0.09f;
            const float travelDuration = 0.72f;
            float totalDuration = travelDuration + stagger * (transitioningEmbers.Count - 1);
            float elapsed = 0f;
            while (elapsed < totalDuration)
            {
                elapsed += Time.unscaledDeltaTime;
                for (int i = 0; i < transitioningEmbers.Count; i++)
                {
                    float t = Mathf.Clamp01((elapsed - stagger * i) / travelDuration);
                    if (t <= 0f)
                        continue;
                    float eased = 1f - Mathf.Pow(1f - t, 3f);
                    RectTransform ember = transitioningEmbers[i];
                    Vector2 point = Vector2.Lerp(starts[i], destinations[i], eased);
                    point.y += Mathf.Sin(t * Mathf.PI) * 110f;
                    ember.anchoredPosition = point;

                    float transformT = Mathf.Clamp01((t - 0.68f) / 0.32f);
                    float pulse = Mathf.Sin(transformT * Mathf.PI);
                    ember.localScale = Vector3.one * (1f + pulse * 2.2f);
                    CanvasGroup emberGroup = ember.GetComponent<CanvasGroup>();
                    if (emberGroup != null)
                        emberGroup.alpha = 1f - transformT;

                    float cardT = Mathf.SmoothStep(0f, 1f, transformT);
                    cardGroups[i].alpha = cardT;
                    currentRewardCards[i].localScale = Vector3.one * Mathf.Lerp(0.78f, 1f, cardT);
                }
                yield return null;
            }

            for (int i = 0; i < transitioningEmbers.Count; i++)
            {
                Destroy(transitioningEmbers[i].gameObject);
                cardGroups[i].alpha = 1f;
                cardGroups[i].blocksRaycasts = true;
                currentRewardCards[i].localScale = Vector3.one;
            }
            transitioningEmbers.Clear();
            isRevealingEmberChoices = false;
            Refresh();
        }

        private static RectTransform FindRectInScene(string objectName)
        {
            RectTransform[] rects = FindObjectsByType<RectTransform>(FindObjectsInactive.Include, FindObjectsSortMode.None);
            for (int i = 0; i < rects.Length; i++)
                if (rects[i].name == objectName) return rects[i];
            return null;
        }

        private static Vector2 WorldToLocal(RectTransform parent, Vector3 world)
        {
            Vector3 local = parent.InverseTransformPoint(world);
            return new Vector2(local.x, local.y);
        }

        private static void ApplyExpandedPanel(Image image)
        {
            UiArtSettings art = UiArtSettings.Resolve();
            if (image == null || art == null || art.ExpandedPanel == null)
                return;
            image.sprite = art.ExpandedPanel;
            image.type = Image.Type.Simple;
            image.preserveAspect = false;
            image.color = Color.white;
        }

        private void ConfigureRewardPanelLayout()
        {
            if (rewardListRoot == null)
                return;
            rewardListRoot.anchoredPosition = new Vector2(0f, -8f);
            rewardListRoot.sizeDelta = new Vector2(720f, 920f);
        }

        private void SelectReward(FantasyData fantasy)
        {
            if (!hasFantasyReward || fantasy == null || bootstrap == null || bootstrap.RunContext == null)
                return;

            fantasyEffectRunner.AddFantasyWithAcquireEffects(bootstrap.RunContext, fantasy);
            FantasyCollectionRules.ApplyPostAcquireTransforms(bootstrap.RunContext.fantasyInventory, fantasyDatabase);
            GameEventHub.RaiseFantasyInventoryChanged();
            hasFantasyReward = false;
            bootstrap.RunContext.pendingFantasyRewardGrades.Clear();
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
                rerollButton.interactable = !isRevealingEmberChoices && bootstrap != null && bootstrap.RunContext != null && bootstrap.RunContext.rewardSession.rerolls > 0 && rewardCardRoot != null && rewardCardRoot.gameObject.activeSelf;
        }

        private void HideRewardChrome()
        {
            if (layoutRoot == null)
                return;

            HideChild("StatusPanel");
            HideChild("MoveCounter");
            HideChild("CurrencyPanel");
            HideChild("ConsumablePanel");
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
            if (bootstrap == null || bootstrap.RunContext == null || bootstrap.RunContext.rewardSession.rerolls <= 0)
                return;
            if (rewardCardRoot == null || !rewardCardRoot.gameObject.activeSelf)
                return;

            HashSet<string> previousRewardIds = new HashSet<string>();
            for (int i = 0; i < currentRewards.Count; i++)
            {
                FantasyData fantasy = currentRewards[i];
                if (fantasy != null && !string.IsNullOrWhiteSpace(fantasy.id))
                    previousRewardIds.Add(fantasy.id);
            }

            bootstrap.RunContext.rewardSession.rerolls--;
            bootstrap.RunContext.rewardSession.choiceRollIndex++;
            PrepareFantasyChoices(previousRewardIds);
            Refresh();
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
            text.font = GameFontSettings.ResolveFont();
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
