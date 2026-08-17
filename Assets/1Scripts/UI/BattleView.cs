using GoldfishWalking.Battle;
using GoldfishWalking.Core;
using GoldfishWalking.Data;
using GoldfishWalking.Fantasy;
using GoldfishWalking.Match;
using System.Globalization;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Serialization;
using UnityEngine.UI;
#if UNITY_EDITOR
using UnityEditor;
#endif

namespace GoldfishWalking.UI
{
    public sealed class BattleView : MonoBehaviour
    {
        [SerializeField] private BattleController battleController;
        [SerializeField] private GameBootstrap bootstrap;
        [SerializeField] private FantasyDatabase fantasyDatabase;
        [FormerlySerializedAs("endTurnButton")]
        [SerializeField] private Button resolveBattleButton;
        [SerializeField] private Button resetButton;
        [SerializeField] private Button debugConsoleButton;

        private readonly Color backgroundColor = new Color(0.07f, 0.08f, 0.11f, 1f);
        private readonly Color panelColor = new Color(0.14f, 0.16f, 0.20f, 0.94f);
        private readonly Color slotColor = new Color(0.20f, 0.22f, 0.29f, 0.96f);
        private readonly Color textColor = new Color(0.95f, 0.97f, 1f, 1f);
        private readonly Color healthColor = new Color(1f, 0.32f, 0.32f, 1f);
        private readonly Color greenColor = new Color(0.13f, 0.86f, 0.43f, 1f);
        private readonly Color cyanColor = new Color(0.24f, 0.74f, 0.90f, 1f);
        private readonly FantasyEffectRunner fantasyEffectRunner = new FantasyEffectRunner();

        private RectTransform layoutRoot;
        private RectTransform fantasyContent;
        private RectTransform consumablePanel;
        private Text healthText;
        private Text monsterNameText;
        private Text monsterHealthText;
        private Text monsterBuffText;
        private Text playerBuffText;
        
        private RectTransform playerConditionPanel;
        private Text playerConditionLabel;
        private EditableSevenSegmentBox playerConditionBox;
private RectTransform playerDebuffPanel;
        private RectTransform monsterSpecialBoxPanel;
        private Text monsterSpecialBoxLabel;
        private Text moveCountText;
        private Text damageDebugText;
        private InputField debugFantasyInput;
        private RectTransform fantasyTooltipRoot;
        private Text fantasyTooltipName;
        private Text fantasyTooltipDescription;
        private Text fantasyTooltipEffect;
        private FantasyTooltipView fantasyTooltipView;
        private FantasyListView fantasyListView;
        private EditableSevenSegmentBox playerDebuffBox;
        private Text playerDebuffOperatorText;
        private EditableSevenSegmentBox playerDamageBox;
        private EditableSevenSegmentBox monsterDamageBox;
        private EditableSevenSegmentBox monsterHitCountBox;
        private EditableSevenSegmentBox monsterSpecialBox;
        private int playerDebuffDifference;
        private int playerDamageDifference;
        private int monsterDamageDifference;
        private int monsterHitDifference;
        private int monsterSpecialBoxDifference;

        private void Awake()
        {
            ResolveReferences();
            EnsureLayout();
            BindButtons();
        }

private void OnEnable()
        {
            GameEventHub.ItemInventoryChanged += RefreshConsumables;
            GameEventHub.FantasyInventoryChanged += RefreshFantasySlots;
            ResolveReferences();
            SubscribeBattlePresentation();
            EnsureLayout();
            if (battleController != null)
                OnResolutionPhaseChanged(battleController.State);
            else
                Refresh();
        }

private void OnDisable()
        {
            GameEventHub.ItemInventoryChanged -= RefreshConsumables;
            GameEventHub.FantasyInventoryChanged -= RefreshFantasySlots;
            UnsubscribeBattlePresentation();
        }

private void SubscribeBattlePresentation()
        {
            if (battleController == null)
                return;
            battleController.PlayerHitPresented -= OnPlayerHitPresented;
            battleController.ResolutionPhaseChanged -= OnResolutionPhaseChanged;
            battleController.BattlePresentationChanged -= OnBattlePresentationChanged;
            battleController.PlayerHitPresented += OnPlayerHitPresented;
            battleController.ResolutionPhaseChanged += OnResolutionPhaseChanged;
            battleController.BattlePresentationChanged += OnBattlePresentationChanged;
        }

private void UnsubscribeBattlePresentation()
        {
            if (battleController == null)
                return;
            battleController.PlayerHitPresented -= OnPlayerHitPresented;
            battleController.ResolutionPhaseChanged -= OnResolutionPhaseChanged;
            battleController.BattlePresentationChanged -= OnBattlePresentationChanged;
        }

private void OnPlayerHitPresented(BattleHitStep hit)
        {
            if (hit != null && hit.sourceFantasy != null)
                fantasyListView?.Emphasize(hit.sourceFantasy);
        }

private void OnBattlePresentationChanged()
        {
            Refresh();
        }




        private void OnResolutionPhaseChanged(BattleState phase)
        {
            bool editing = phase == BattleState.Editing;
            if (resolveBattleButton != null)
                resolveBattleButton.interactable = editing;
            if (resetButton != null)
                resetButton.interactable = editing;
            Refresh();
        }




        private void LateUpdate()
        {
            if (healthText != null && bootstrap != null && bootstrap.RunContext != null)
                healthText.text = bootstrap.RunContext.health.ToString();
        }

        private void OnDestroy()
        {
            UnbindButtons();
        }

        private void ResolveReferences()
        {
            if (battleController == null)
                Debug.LogError("[BattleView] BattleController must be assigned in GumBwing_Er.unity.", this);
            if (bootstrap == null)
                Debug.LogError("[BattleView] GameBootstrap must be assigned in GumBwing_Er.unity.", this);
            if (fantasyDatabase == null)
                fantasyDatabase = FindFirstFantasyDatabase();
        }

        private void RemoveExistingLayoutImmediate()
        {
            layoutRoot = null;

            for (int i = transform.childCount - 1; i >= 0; i--)
            {
                Transform child = transform.GetChild(i);
                if (child.name != "BattleRuntimeLayout")
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

            Transform existing = transform.Find("BattleRuntimeLayout");
            if (existing is RectTransform existingLayout)
            {
                layoutRoot = existingLayout;
                BindExistingLayout();
                return;
            }

            Debug.LogError("[BattleView] Missing prebuilt BattleRuntimeLayout. Build the UI in the scene instead of creating it from script.");
        }

        private void BindExistingLayout()
        {
            if (layoutRoot == null)
                return;

            EnsureDevelopmentDebugUI();

            fantasyContent = FindRect("FantasySlots/Viewport/Content");
            consumablePanel = FindRect("ConsumablePanel");
            healthText = FindComponent<Text>("StatusPanel/Health");
            monsterNameText = FindComponent<Text>("MonsterStatusPanel/MonsterName");
            monsterHealthText = FindComponent<Text>("MonsterStatusPanel/MonsterHealth");
            monsterBuffText = FindComponent<Text>("MonsterFormulaPanel/MonsterBuffs");
            playerBuffText = FindComponent<Text>("PlayerFormulaPanel/PlayerBuffs");
            monsterSpecialBoxPanel = FindRect("MonsterSpecialBoxPanel");
            monsterSpecialBoxLabel = FindComponent<Text>("MonsterSpecialBoxPanel/Label");
            moveCountText = FindComponent<Text>("MoveCounter/MoveCount");
            damageDebugText = FindComponent<Text>("DamageDebugPanel/DamageDebugText");
            if (damageDebugText != null)
                damageDebugText.supportRichText = true;
            debugFantasyInput = FindComponent<InputField>("DebugFantasyConsole/Input");
            fantasyTooltipRoot = FindRect("FantasyTooltip");
            fantasyTooltipName = FindComponent<Text>("FantasyTooltip/Name");
            fantasyTooltipDescription = FindComponent<Text>("FantasyTooltip/Description");
            fantasyTooltipEffect = FindComponent<Text>("FantasyTooltip/Effect");
            fantasyTooltipView = fantasyTooltipRoot != null ? fantasyTooltipRoot.GetComponent<FantasyTooltipView>() : null;
            if (fantasyTooltipView != null)
                fantasyTooltipView.Bind(fantasyTooltipName, fantasyTooltipDescription, fantasyTooltipEffect);
            else if (fantasyTooltipRoot != null)
                Debug.LogWarning("[BattleView] Missing FantasyTooltipView on FantasyTooltip.");
            fantasyListView = fantasyContent != null ? fantasyContent.GetComponent<FantasyListView>() : null;
            if (fantasyListView != null)
                fantasyListView.Bind(fantasyContent, fantasyTooltipView, 10);
            EnsurePlayerDebuffUI();
            playerDamageBox = FindComponent<EditableSevenSegmentBox>("PlayerFormulaPanel/PlayerDamage");
            monsterDamageBox = FindComponent<EditableSevenSegmentBox>("MonsterFormulaPanel/FormulaContent/MonsterDamage");
            monsterHitCountBox = FindComponent<EditableSevenSegmentBox>("MonsterFormulaPanel/FormulaContent/MonsterHitCount");
            monsterSpecialBox = FindComponent<EditableSevenSegmentBox>("MonsterSpecialBoxPanel/MonsterSpecialBox");
            resetButton = FindComponent<Button>("ResetButton");
            resolveBattleButton = FindComponent<Button>("ResolveBattleButton");
            debugConsoleButton = FindComponent<Button>("DebugFantasyConsole/AddButton");
            SetButtonLabel(resolveBattleButton, "턴\n종료", 26);
        }

private void EnsurePlayerDebuffUI()
        {
            
            playerConditionPanel = FindRect("PlayerConditionPanel");
            playerConditionLabel = FindComponent<Text>("PlayerConditionPanel/PlayerDebuffOperator");
            playerConditionBox = FindComponent<EditableSevenSegmentBox>("PlayerConditionPanel/PlayerDebuff");
playerDebuffPanel = FindRect("PlayerDebuffPanel");
            playerDebuffBox = FindComponent<EditableSevenSegmentBox>("PlayerDebuffPanel/PlayerDebuff");
            playerDebuffOperatorText = FindComponent<Text>("PlayerDebuffPanel/PlayerDebuffOperator");

            if (playerDebuffPanel == null || playerDebuffBox == null || playerDebuffOperatorText == null)
                Debug.LogError("[BattleView] Missing prebuilt PlayerDebuffPanel UI.");
        }


        private void EnsureDevelopmentDebugUI()
        {
            if (layoutRoot.Find("DamageDebugPanel") == null)
                CreateDamageDebugPanel();
            if (layoutRoot.Find("DebugFantasyConsole") == null)
                CreateDebugConsole();
        }

        private void CreateDamageDebugPanel()
        {
            RectTransform panel = CreateDebugRect("DamageDebugPanel", layoutRoot, new Vector2(430f, 150f));
            panel.anchorMin = panel.anchorMax = new Vector2(1f, 0f);
            panel.anchoredPosition = new Vector2(-300f, 250f);
            panel.gameObject.AddComponent<Image>().color = new Color(0.1f, 0.11f, 0.15f, 0.88f);

            Text text = CreateDebugText("DamageDebugText", panel, 18, TextAnchor.UpperLeft);
            RectTransform rect = (RectTransform)text.transform;
            rect.anchorMin = Vector2.zero;
            rect.anchorMax = Vector2.one;
            rect.offsetMin = new Vector2(14f, 10f);
            rect.offsetMax = new Vector2(-14f, -10f);
            text.text = "Damage log -";
        }

        private void CreateDebugConsole()
        {
            RectTransform panel = CreateDebugRect("DebugFantasyConsole", layoutRoot, new Vector2(484f, 120f));
            panel.anchorMin = panel.anchorMax = Vector2.zero;
            panel.anchoredPosition = new Vector2(300f, 250f);
            panel.gameObject.AddComponent<Image>().color = new Color(0.1f, 0.11f, 0.15f, 0.88f);

            RectTransform inputRect = CreateDebugRect("Input", panel, new Vector2(350f, 54f));
            inputRect.anchoredPosition = new Vector2(-52f, 0f);
            Image inputImage = inputRect.gameObject.AddComponent<Image>();
            inputImage.color = slotColor;
            InputField input = inputRect.gameObject.AddComponent<InputField>();

            Text placeholder = CreateDebugText("Placeholder", inputRect, 17, TextAnchor.MiddleLeft);
            placeholder.text = "fantasy / damage / kill / spawn";
            placeholder.color = new Color(0.65f, 0.68f, 0.75f, 1f);
            StretchDebugText(placeholder, 10f);

            Text value = CreateDebugText("Text", inputRect, 17, TextAnchor.MiddleLeft);
            StretchDebugText(value, 10f);
            input.textComponent = value;
            input.placeholder = placeholder;

            RectTransform buttonRect = CreateDebugRect("AddButton", panel, new Vector2(96f, 54f));
            buttonRect.anchoredPosition = new Vector2(180f, 0f);
            Image buttonImage = buttonRect.gameObject.AddComponent<Image>();
            buttonImage.color = cyanColor;
            Button button = buttonRect.gameObject.AddComponent<Button>();
            button.targetGraphic = buttonImage;
            Text label = CreateDebugText("Text", buttonRect, 18, TextAnchor.MiddleCenter);
            StretchDebugText(label, 0f);
            label.text = "Run";
        }

        private RectTransform CreateDebugRect(string objectName, Transform parent, Vector2 size)
        {
            GameObject child = new GameObject(objectName, typeof(RectTransform), typeof(CanvasRenderer));
            RectTransform rect = child.GetComponent<RectTransform>();
            rect.SetParent(parent, false);
            rect.sizeDelta = size;
            return rect;
        }

        private Text CreateDebugText(string objectName, Transform parent, int fontSize, TextAnchor alignment)
        {
            RectTransform rect = CreateDebugRect(objectName, parent, Vector2.zero);
            Text text = rect.gameObject.AddComponent<Text>();
            text.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            text.fontSize = fontSize;
            text.alignment = alignment;
            text.color = textColor;
            return text;
        }

        private static void StretchDebugText(Text text, float horizontalPadding)
        {
            RectTransform rect = (RectTransform)text.transform;
            rect.anchorMin = Vector2.zero;
            rect.anchorMax = Vector2.one;
            rect.offsetMin = new Vector2(horizontalPadding, 0f);
            rect.offsetMax = new Vector2(-horizontalPadding, 0f);
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

        private void BindButtons()
        {
            if (resolveBattleButton != null)
            {
                resolveBattleButton.onClick.RemoveListener(OnResolveBattleClicked);
                resolveBattleButton.onClick.AddListener(OnResolveBattleClicked);
            }
            if (resetButton != null)
            {
                resetButton.onClick.RemoveListener(OnResetClicked);
                resetButton.onClick.AddListener(OnResetClicked);
            }
            if (debugConsoleButton != null)
            {
                debugConsoleButton.onClick.RemoveListener(ExecuteDebugCommand);
                debugConsoleButton.onClick.AddListener(ExecuteDebugCommand);
            }
            if (debugFantasyInput != null)
            {
                debugFantasyInput.onEndEdit.RemoveListener(OnDebugInputEndEdit);
                debugFantasyInput.onEndEdit.AddListener(OnDebugInputEndEdit);
            }
        }

        private void UnbindButtons()
        {
            if (resolveBattleButton != null)
                resolveBattleButton.onClick.RemoveListener(OnResolveBattleClicked);
            if (resetButton != null)
                resetButton.onClick.RemoveListener(OnResetClicked);
            if (debugConsoleButton != null)
                debugConsoleButton.onClick.RemoveListener(ExecuteDebugCommand);
            if (debugFantasyInput != null)
                debugFantasyInput.onEndEdit.RemoveListener(OnDebugInputEndEdit);
        }

        private void SetButtonLabel(Button button, string label, int fontSize)
        {
            if (button == null)
                return;

            Text text = button.GetComponentInChildren<Text>(true);
            if (text == null)
                return;

            text.text = label;
            text.fontSize = fontSize;
            text.alignment = TextAnchor.MiddleCenter;
            text.horizontalOverflow = HorizontalWrapMode.Wrap;
            text.verticalOverflow = VerticalWrapMode.Truncate;
        }

        private void Refresh()
        {
            if (healthText != null)
                healthText.text = bootstrap != null && bootstrap.RunContext != null ? bootstrap.RunContext.health.ToString() : "0";
            RefreshMonsterStatus();
            RefreshFormulaValues();
            RefreshFantasySlots();
            RefreshConsumables();
            RefreshDamageDebug();
            RefreshMoveCounter();
        }

        private void RefreshMonsterStatus()
        {
            if (monsterNameText != null)
                monsterNameText.text = battleController != null ? battleController.MonsterDisplayName : "Monster";
            if (monsterHealthText != null)
                monsterHealthText.text = battleController != null
                    ? $"{battleController.MonsterCurrentHealth} / {battleController.MonsterMaxHealth}"
                    : "0 / 1";
            if (monsterBuffText != null)
                monsterBuffText.text = battleController != null ? battleController.MonsterStatusSummary : "-";
            if (playerBuffText != null)
                playerBuffText.text = battleController != null ? battleController.PlayerStatusSummary : "-";
        }

private string BuildPlayerConditionStatus()
        {
            if (battleController == null)
                return "-";
            string status = battleController.PlayerStatusSummary;
            string condition = battleController.PlayerAttackConditionSummary;
            if (string.IsNullOrWhiteSpace(condition))
                return status;
            return status == "-" ? $"RULE {condition}" : $"{status}  RULE {condition}";
        }


        private void RefreshFantasySlots()
        {
            if (fantasyListView != null)
            {
                fantasyListView.Bind(fantasyContent, fantasyTooltipView, 10);
                fantasyListView.Refresh(bootstrap != null && bootstrap.RunContext != null && bootstrap.RunContext.fantasyInventory != null
                    ? bootstrap.RunContext.fantasyInventory.ownedFantasies
                    : null);
                return;
            }

            Debug.LogWarning("[BattleView] Missing FantasyListView on FantasySlots/Viewport/Content.");
        }

        private void RefreshDamageDebug()
        {
            if (damageDebugText != null)
                damageDebugText.text = battleController != null ? battleController.DamageDebugSummary : "Damage log -";
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

            BindConsumableCount(0, extraMatchCount);
            BindConsumableCount(1, eraserCount);
        }

        private void BindConsumableCount(int slotIndex, int count)
        {
            if (consumablePanel == null || slotIndex < 0 || slotIndex >= consumablePanel.childCount)
            {
                Debug.LogWarning($"[BattleView] Missing prebuilt consumable slot {slotIndex}.");
                return;
            }

            Text countText = consumablePanel.GetChild(slotIndex).Find("Badge/Count")?.GetComponent<Text>();
            if (countText != null)
                countText.text = count.ToString(CultureInfo.InvariantCulture);
        }

        private void RefreshFormulaValues()
        {
            if (playerDamageBox != null)
                playerDamageBox.Configure(GetPlayerBaseDamage(), GetPlayerDamageDigitCount(), healthColor, OnPlayerDamageEdited,
                    battleController != null && battleController.PlayerBaseDamageLocked, OnPlayerDamageDifferenceChanged,
                    battleController != null ? battleController.PlayerBaseDamageSegmentState : string.Empty,
                    CanCommitPlayerDamageDifference, null,
                    battleController != null && battleController.PlayerBaseDamageSplit,
                    battleController != null ? battleController.PlayerBaseDamageLockedDigitCount : 0,
                    matchesMovable: battleController == null || battleController.PlayerBaseDamageMatchesMovable,
                    highlighted: battleController != null && battleController.PlayerBaseDamageReactive);
RefreshPlayerDebuffBox();
            if (monsterDamageBox != null)
                monsterDamageBox.Configure(GetMonsterBaseDamage(), battleController != null ? battleController.MonsterBaseDamageDigitCount : 1,
                    healthColor, OnMonsterDamageEdited, battleController != null && battleController.MonsterBaseDamageLocked,
                    OnMonsterDamageDifferenceChanged, battleController != null ? battleController.MonsterBaseDamageSegmentState : string.Empty,
                    CanCommitMonsterDamageDifference, null,
                    battleController != null && battleController.MonsterBaseDamageSplit,
                    battleController != null ? battleController.MonsterBaseDamageLockedDigitCount : 0,
                    matchesMovable: battleController == null || battleController.MonsterBaseDamageMatchesMovable,
                    highlighted: battleController != null && battleController.MonsterBaseDamageReactive);
            if (monsterHitCountBox != null)
                monsterHitCountBox.Configure(GetMonsterHitCount(), battleController != null ? battleController.MonsterHitCountDigitCount : 1, healthColor, OnMonsterHitCountEdited,
                    battleController != null && battleController.MonsterHitCountLocked, OnMonsterHitDifferenceChanged,
                    battleController != null ? battleController.MonsterHitCountSegmentState : string.Empty,
                    CanCommitMonsterHitDifference, null,
                    battleController != null && battleController.MonsterHitCountSplit,
                    battleController != null ? battleController.MonsterHitCountLockedDigitCount : 0,
                    matchesMovable: battleController == null || battleController.MonsterHitCountMatchesMovable,
                    highlighted: battleController != null && battleController.MonsterHitCountReactive);
            RefreshMonsterSpecialBox();
        }

private void RefreshPlayerDebuffBox()
        {
            bool visible = battleController != null && battleController.PlayerDebuffVisible;
            if (playerDebuffPanel != null)
                playerDebuffPanel.gameObject.SetActive(visible);
            if (playerDebuffBox != null)
                playerDebuffBox.gameObject.SetActive(visible);
            if (playerDebuffOperatorText != null)
            {
                playerDebuffOperatorText.gameObject.SetActive(visible);
                playerDebuffOperatorText.text = battleController != null && battleController.PlayerDebuffOperator == "Divide" ? "/" : "-";
            }

            if (!visible)
            {
                playerDebuffDifference = 0;
                return;
            }

            playerDebuffBox.Configure(battleController.PlayerDebuffValue, battleController.PlayerDebuffDigitCount,
                healthColor, OnPlayerDebuffEdited, false, OnPlayerDebuffDifferenceChanged,
                battleController.PlayerDebuffSegmentState, CanCommitPlayerDebuffDifference,
                null, false, 0, IsValidPlayerDebuffValue, "Division by zero is not allowed.");
        }

private void RefreshPlayerConditionBox()
        {
            bool visible = battleController != null && battleController.PlayerAttackConditionVisible;
            if (playerConditionPanel != null)
                playerConditionPanel.gameObject.SetActive(visible);
            if (!visible)
                return;

            if (playerConditionLabel != null)
                playerConditionLabel.text = battleController.PlayerAttackConditionLabel;
            if (playerConditionBox != null)
                playerConditionBox.Configure(battleController.PlayerAttackConditionBoxValue, 1, healthColor,
                    OnPlayerConditionEdited, !battleController.PlayerAttackConditionEditable);
        }

        private void OnPlayerConditionEdited(int value)
        {
            battleController?.SetPlayerAttackConditionBoxValue(value);
        }



        private void RefreshMonsterSpecialBox()
        {
            bool visible = battleController != null && battleController.MonsterSpecialBoxVisible;
            if (monsterSpecialBoxPanel != null)
                monsterSpecialBoxPanel.gameObject.SetActive(visible);

            if (!visible)
            {
                monsterSpecialBoxDifference = 0;
                return;
            }

            if (monsterSpecialBoxLabel != null)
                monsterSpecialBoxLabel.text = string.IsNullOrWhiteSpace(battleController.MonsterSpecialBoxLabel)
                    ? "SPECIAL"
                    : battleController.MonsterSpecialBoxLabel;

            if (monsterSpecialBox != null)
            {
                monsterSpecialBox.Configure(
                    battleController.MonsterSpecialBoxValue,
                    battleController.MonsterSpecialBoxDigitCount,
                    healthColor,
                    OnMonsterSpecialBoxEdited,
                    battleController.MonsterSpecialBoxLocked,
                    OnMonsterSpecialBoxDifferenceChanged,
                    battleController.MonsterSpecialBoxSegmentState,
                    CanCommitMonsterSpecialBoxDifference,
                    null,
                    battleController.AllFormulaBoxesSplit);
                Button actionButton = monsterSpecialBox.GetComponent<Button>();
                if (battleController.CosmicResetAvailable)
                {
                    if (actionButton == null)
                        actionButton = monsterSpecialBox.gameObject.AddComponent<Button>();
                    actionButton.enabled = true;
                    actionButton.onClick.RemoveAllListeners();
                    actionButton.onClick.AddListener(() => battleController.ActivateOncePerBattleMonsterAction());
                }
                else if (actionButton != null)
                {
                    actionButton.onClick.RemoveAllListeners();
                    actionButton.enabled = false;
                }
            }
        }

        private void RefreshMoveCounter()
        {
            if (moveCountText == null)
                return;

            int totalDifference = CurrentTotalMoveDifference();
            int remaining = battleController != null ? Mathf.Max(0, battleController.RemainingMoveCount - totalDifference) : Mathf.Max(0, 2 - totalDifference);
            int limit = battleController != null ? battleController.CurrentMoveLimit : 2;
            moveCountText.text = $"{remaining} / {limit}";
        }

        private int GetPlayerBaseDamage()
        {
            return battleController != null ? battleController.PlayerBaseDamage : 25;
        }

        private int GetPlayerDamageDigitCount()
        {
            return battleController != null ? battleController.PlayerDamageDigitCount : 2;
        }

        private int GetMonsterBaseDamage()
        {
            return battleController != null ? battleController.MonsterBaseDamage : 72;
        }

        private int GetMonsterHitCount()
        {
            return battleController != null ? battleController.MonsterHitCount : 4;
        }

        private void OnPlayerDamageEdited(int value)
        {
            if (battleController != null)
            {
                battleController.SetPlayerBaseDamage(value, playerDamageBox != null ? playerDamageBox.SegmentState : string.Empty);
                ReactToCommittedBoxEdit("damage_base", playerDamageBox);
            }
        }

private void OnPlayerDebuffEdited(int value)
        {
            if (battleController != null)
                battleController.SetPlayerDebuffValue(value, playerDebuffBox != null ? playerDebuffBox.SegmentState : string.Empty);
        }

        private void OnPlayerDebuffDifferenceChanged(int difference)
        {
            playerDebuffDifference = difference;
            RefreshMoveCounter();
        }

        private bool CanCommitPlayerDebuffDifference(int proposedDifference)
        {
            return CanCommitMoveDifference(playerDamageDifference, proposedDifference, monsterDamageDifference, monsterHitDifference, monsterSpecialBoxDifference);
        }

private bool IsValidPlayerDebuffValue(int value)
        {
            return battleController == null || battleController.PlayerDebuffOperator != "Divide" || value != 0;
        }



        private void OnMonsterDamageEdited(int value)
        {
            if (battleController != null)
            {
                battleController.SetMonsterBaseDamage(value, monsterDamageBox != null ? monsterDamageBox.SegmentState : string.Empty);
                ReactToCommittedBoxEdit("monster_damage", monsterDamageBox);
            }
        }

        private void OnMonsterHitCountEdited(int value)
        {
            if (battleController != null)
            {
                battleController.SetMonsterHitCount(value, monsterHitCountBox != null ? monsterHitCountBox.SegmentState : string.Empty);
                ReactToCommittedBoxEdit("monster_hit_count", monsterHitCountBox);
            }
        }

        private void ReactToCommittedBoxEdit(string boxId, EditableSevenSegmentBox box)
        {
            if (battleController != null && battleController.NotifyFormulaBoxEdited(boxId, box != null ? box.DifferenceFromOriginal : 0))
                RefreshMonsterStatus();
        }

        private void OnMonsterSpecialBoxEdited(int value)
        {
            if (battleController != null)
                battleController.SetMonsterSpecialBoxValue(value, monsterSpecialBox != null ? monsterSpecialBox.SegmentState : string.Empty);
        }

        private void OnPlayerDamageDifferenceChanged(int difference)
        {
            playerDamageDifference = difference;
            RefreshMoveCounter();
        }

        private void OnMonsterDamageDifferenceChanged(int difference)
        {
            monsterDamageDifference = difference;
            RefreshMoveCounter();
        }

        private void OnMonsterHitDifferenceChanged(int difference)
        {
            monsterHitDifference = difference;
            RefreshMoveCounter();
        }

        private void OnMonsterSpecialBoxDifferenceChanged(int difference)
        {
            monsterSpecialBoxDifference = difference;
            RefreshMoveCounter();
        }

        private bool CanCommitPlayerDamageDifference(int proposedDifference)
        {
            return CanCommitMoveDifference(proposedDifference, playerDebuffDifference, monsterDamageDifference, monsterHitDifference, monsterSpecialBoxDifference);
        }

        private bool CanCommitMonsterDamageDifference(int proposedDifference)
        {
            return CanCommitMoveDifference(playerDamageDifference, playerDebuffDifference, proposedDifference, monsterHitDifference, monsterSpecialBoxDifference);
        }

        private bool CanCommitMonsterHitDifference(int proposedDifference)
        {
            return CanCommitMoveDifference(playerDamageDifference, playerDebuffDifference, monsterDamageDifference, proposedDifference, monsterSpecialBoxDifference);
        }

        private bool CanCommitMonsterSpecialBoxDifference(int proposedDifference)
        {
            return CanCommitMoveDifference(playerDamageDifference, playerDebuffDifference, monsterDamageDifference, monsterHitDifference, proposedDifference);
        }

        private bool CanCommitMoveDifference(int playerDifference, int playerDebuffDifferenceValue, int monsterDamageDifferenceValue, int monsterHitDifferenceValue, int monsterSpecialDifferenceValue)
        {
            int totalDifference = Mathf.Max(0, playerDifference)
                + Mathf.Max(0, playerDebuffDifferenceValue)
                + Mathf.Max(0, monsterDamageDifferenceValue)
                + Mathf.Max(0, monsterHitDifferenceValue)
                + Mathf.Max(0, monsterSpecialDifferenceValue);
            int remaining = battleController != null ? battleController.RemainingMoveCount : 2;
            return totalDifference <= remaining;
        }

        private int CurrentTotalMoveDifference()
        {
            return Mathf.Max(0, playerDamageDifference)
                + Mathf.Max(0, playerDebuffDifference)
                + Mathf.Max(0, monsterDamageDifference)
                + Mathf.Max(0, monsterHitDifference)
                + Mathf.Max(0, monsterSpecialBoxDifference);
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

        private void ExecuteDebugCommand()
        {
            if (bootstrap == null || bootstrap.RunContext == null || debugFantasyInput == null)
                return;

            string command = (debugFantasyInput.text ?? string.Empty).Trim();
            if (string.IsNullOrWhiteSpace(command))
                return;

            string[] parts = command.Split(new[] { ' ' }, 2, System.StringSplitOptions.RemoveEmptyEntries);
            string verb = parts.Length > 0 ? parts[0].Trim().ToUpperInvariant() : string.Empty;
            string argument = parts.Length > 1 ? parts[1].Trim() : string.Empty;

            if (verb == "ADD")
            {
                ExecuteAddCommand(argument);
                return;
            }

            if (verb == "SPAWN")
            {
                ExecuteSpawnCommand(argument);
                return;
            }

            if (verb == "DAMAGE")
            {
                ExecuteDamageCommand(argument);
                return;
            }

            if (verb == "KILL")
            {
                ExecuteKillCommand();
                return;
            }

            Debug.LogWarning($"[BattleView] Unknown debug command: {command}");
        }

        private void OnDebugInputEndEdit(string value)
        {
            if (Input.GetKeyDown(KeyCode.Return) || Input.GetKeyDown(KeyCode.KeypadEnter))
                ExecuteDebugCommand();
        }

        private void ExecuteAddCommand(string argument)
        {
            if (string.IsNullOrWhiteSpace(argument))
                return;

            if (TryGetDebugItem(argument, out ItemType itemType, out int itemCount))
            {
                fantasyEffectRunner.AddItemWithAcquireEffects(bootstrap.RunContext, itemType, itemCount);
                debugFantasyInput.text = string.Empty;
                Refresh();
                Debug.Log($"[BattleView] Added debug item: {itemType} x{itemCount}");
                return;
            }

            FantasyData fantasy = FindFantasy(argument);
            if (fantasy == null)
            {
                Debug.LogWarning($"[BattleView] Debug ADD target not found: {argument}");
                return;
            }

            bootstrap.RunContext.fantasyInventory.AddDuplicate(fantasy);
            fantasyEffectRunner.Apply(fantasy, bootstrap.RunContext, "On_Acquire");
            fantasyEffectRunner.Apply(fantasy, bootstrap.RunContext, "Acquire");
            FantasyDatabase database = fantasyDatabase != null ? fantasyDatabase : FindFirstFantasyDatabase();
            FantasyCollectionRules.ApplyPostAcquireTransforms(bootstrap.RunContext.fantasyInventory, database);

            debugFantasyInput.text = string.Empty;
            Refresh();
            Debug.Log($"[BattleView] Added debug fantasy: {fantasy.id}");
        }

        private void ExecuteSpawnCommand(string argument)
        {
            if (string.IsNullOrWhiteSpace(argument) || battleController == null)
                return;

            bool spawned = battleController.ForceSpawnMonster(argument);
            debugFantasyInput.text = string.Empty;
            Refresh();
            if (spawned)
                Debug.Log($"[BattleView] Spawned debug monster: {argument}");
            else
                Debug.LogWarning($"[BattleView] Monster not found: {argument}");
        }

        private void ExecuteDamageCommand(string argument)
        {
            if (string.IsNullOrWhiteSpace(argument) || battleController == null)
                return;

            if (!int.TryParse(argument, NumberStyles.Integer, CultureInfo.InvariantCulture, out int damage) || damage <= 0)
            {
                Debug.LogWarning($"[BattleView] Invalid debug damage: {argument}");
                return;
            }

            bool applied = battleController.DebugDamageMonster(damage);
            debugFantasyInput.text = string.Empty;
            Refresh();
            if (applied)
                Debug.Log($"[BattleView] Applied debug damage: {damage}");
            else
                Debug.LogWarning("[BattleView] Debug damage failed.");
        }

        private void ExecuteKillCommand()
        {
            if (battleController == null)
                return;

            bool killed = battleController.DebugKillMonster();
            debugFantasyInput.text = string.Empty;
            Refresh();
            if (killed)
                Debug.Log("[BattleView] Killed debug monster.");
            else
                Debug.LogWarning("[BattleView] Debug kill failed.");
        }

        private static bool TryGetDebugItem(string value, out ItemType itemType, out int count)
        {
            count = 1;
            string text = (value ?? string.Empty).Trim();
            string[] parts = text.Split(new[] { ' ' }, System.StringSplitOptions.RemoveEmptyEntries);
            string itemCode = parts.Length > 0 ? parts[0] : string.Empty;
            if (parts.Length > 1 && (!int.TryParse(parts[1], NumberStyles.Integer, CultureInfo.InvariantCulture, out count) || count <= 0))
                count = 1;

            string lookup = itemCode.Replace("_", string.Empty).Replace("-", string.Empty).ToLowerInvariant();
            switch (lookup)
            {
                case "match":
                case "extramatch":
                case "addmatch":
                    itemType = ItemType.ExtraMatch;
                    return true;
                case "eraser":
                    itemType = ItemType.Eraser;
                    return true;
                default:
                    itemType = ItemType.ExtraMatch;
                    return false;
            }
        }

        private FantasyData FindFantasy(string id)
        {
            string lookup = (id ?? string.Empty).Trim();
            if (string.IsNullOrWhiteSpace(lookup))
                return null;

            FantasyDatabase database = fantasyDatabase != null ? fantasyDatabase : FindFirstFantasyDatabase();
            if (database == null || database.fantasies == null)
                return null;

            for (int i = 0; i < database.fantasies.Count; i++)
            {
                FantasyData fantasy = database.fantasies[i];
                if (fantasy == null)
                    continue;
                if (fantasy.id == lookup || fantasy.dataCode == lookup || fantasy.devName == lookup || fantasy.displayName == lookup)
                    return fantasy;
            }

            return null;
        }

        private static FantasyDatabase FindFirstFantasyDatabase()
        {
            FantasyDatabase[] databases = Resources.FindObjectsOfTypeAll<FantasyDatabase>();
            if (databases != null && databases.Length > 0)
                return databases[0];

#if UNITY_EDITOR
            return AssetDatabase.LoadAssetAtPath<FantasyDatabase>("Assets/Data/Generated/FantasyDatabase.asset");
#else
            return null;
#endif
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

        private void OnResolveBattleClicked()
        {
            if (battleController != null)
            {
                int usedMoveCount = CurrentTotalMoveDifference();
                if (usedMoveCount > battleController.RemainingMoveCount)
                {
                    Debug.LogWarning($"[BattleView] Not enough moves: used {usedMoveCount}, remaining {battleController.RemainingMoveCount}");
                    RefreshMoveCounter();
                    return;
                }

                battleController.SetUsedMoveCount(usedMoveCount);
                battleController.ResolveBattle();
            }

            Refresh();
        }

        private void OnResetClicked()
        {
            if (battleController != null)
                battleController.ResetBattle();
            Refresh();
        }

    }
}
