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
        private EditableSevenSegmentBox playerDamageBox;
        private EditableSevenSegmentBox monsterDamageBox;
        private EditableSevenSegmentBox monsterHitCountBox;
        private EditableSevenSegmentBox monsterSpecialBox;
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
            ResolveReferences();
            EnsureLayout();
            Refresh();
        }

        private void OnDisable()
        {
            GameEventHub.ItemInventoryChanged -= RefreshConsumables;
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
                battleController = FindFirstObjectByType<BattleController>(FindObjectsInactive.Include);
            if (bootstrap == null)
                bootstrap = FindFirstObjectByType<GameBootstrap>(FindObjectsInactive.Include);
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
            playerDamageBox = FindComponent<EditableSevenSegmentBox>("PlayerFormulaPanel/PlayerDamage");
            monsterDamageBox = FindComponent<EditableSevenSegmentBox>("MonsterFormulaPanel/FormulaContent/MonsterDamage");
            monsterHitCountBox = FindComponent<EditableSevenSegmentBox>("MonsterFormulaPanel/FormulaContent/MonsterHitCount");
            monsterSpecialBox = FindComponent<EditableSevenSegmentBox>("MonsterSpecialBoxPanel/MonsterSpecialBox");
            resetButton = FindComponent<Button>("ResetButton");
            resolveBattleButton = FindComponent<Button>("ResolveBattleButton");
            debugConsoleButton = FindComponent<Button>("DebugFantasyConsole/AddButton");
            SetButtonLabel(resolveBattleButton, "턴\n종료", 26);
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
                playerDamageBox.Configure(GetPlayerBaseDamage(), GetPlayerDamageDigitCount(), healthColor, OnPlayerDamageEdited, false, OnPlayerDamageDifferenceChanged, battleController != null ? battleController.PlayerBaseDamageSegmentState : string.Empty, CanCommitPlayerDamageDifference);
            if (monsterDamageBox != null)
                monsterDamageBox.Configure(GetMonsterBaseDamage(), 0, healthColor, OnMonsterDamageEdited, battleController != null && battleController.MonsterBaseDamageLocked, OnMonsterDamageDifferenceChanged, battleController != null ? battleController.MonsterBaseDamageSegmentState : string.Empty, CanCommitMonsterDamageDifference);
            if (monsterHitCountBox != null)
                monsterHitCountBox.Configure(GetMonsterHitCount(), 0, healthColor, OnMonsterHitCountEdited, false, OnMonsterHitDifferenceChanged, battleController != null ? battleController.MonsterHitCountSegmentState : string.Empty, CanCommitMonsterHitDifference);
            RefreshMonsterSpecialBox();
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
                monsterSpecialBox.Configure(
                    battleController.MonsterSpecialBoxValue,
                    battleController.MonsterSpecialBoxDigitCount,
                    healthColor,
                    OnMonsterSpecialBoxEdited,
                    false,
                    OnMonsterSpecialBoxDifferenceChanged,
                    battleController.MonsterSpecialBoxSegmentState,
                    CanCommitMonsterSpecialBoxDifference);
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
            return battleController != null && battleController.PlayerBaseDamage > 0 ? battleController.PlayerBaseDamage : 25;
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
                battleController.SetPlayerBaseDamage(value, playerDamageBox != null ? playerDamageBox.SegmentState : string.Empty);
        }

        private void OnMonsterDamageEdited(int value)
        {
            if (battleController != null)
                battleController.SetMonsterBaseDamage(value, monsterDamageBox != null ? monsterDamageBox.SegmentState : string.Empty);
        }

        private void OnMonsterHitCountEdited(int value)
        {
            if (battleController != null)
                battleController.SetMonsterHitCount(value, monsterHitCountBox != null ? monsterHitCountBox.SegmentState : string.Empty);
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
            return CanCommitMoveDifference(proposedDifference, monsterDamageDifference, monsterHitDifference, monsterSpecialBoxDifference);
        }

        private bool CanCommitMonsterDamageDifference(int proposedDifference)
        {
            return CanCommitMoveDifference(playerDamageDifference, proposedDifference, monsterHitDifference, monsterSpecialBoxDifference);
        }

        private bool CanCommitMonsterHitDifference(int proposedDifference)
        {
            return CanCommitMoveDifference(playerDamageDifference, monsterDamageDifference, proposedDifference, monsterSpecialBoxDifference);
        }

        private bool CanCommitMonsterSpecialBoxDifference(int proposedDifference)
        {
            return CanCommitMoveDifference(playerDamageDifference, monsterDamageDifference, monsterHitDifference, proposedDifference);
        }

        private bool CanCommitMoveDifference(int playerDifference, int monsterDamageDifferenceValue, int monsterHitDifferenceValue, int monsterSpecialDifferenceValue)
        {
            int totalDifference = Mathf.Max(0, playerDifference)
                + Mathf.Max(0, monsterDamageDifferenceValue)
                + Mathf.Max(0, monsterHitDifferenceValue)
                + Mathf.Max(0, monsterSpecialDifferenceValue);
            int remaining = battleController != null ? battleController.RemainingMoveCount : 2;
            return totalDifference <= remaining;
        }

        private int CurrentTotalMoveDifference()
        {
            return Mathf.Max(0, playerDamageDifference)
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
