using GoldfishWalking.Battle;
using GoldfishWalking.Core;
using GoldfishWalking.Data;
using GoldfishWalking.Match;
using UnityEngine;
using UnityEngine.Serialization;
using UnityEngine.UI;

namespace GoldfishWalking.UI
{
    public sealed class BattleView : MonoBehaviour
    {
        [SerializeField] private BattleController battleController;
        [SerializeField] private GameBootstrap bootstrap;
        [FormerlySerializedAs("endTurnButton")]
        [SerializeField] private Button resolveBattleButton;
        [SerializeField] private Button resetButton;

        private readonly Color backgroundColor = new Color(0.07f, 0.08f, 0.11f, 1f);
        private readonly Color panelColor = new Color(0.14f, 0.16f, 0.20f, 0.94f);
        private readonly Color slotColor = new Color(0.20f, 0.22f, 0.29f, 0.96f);
        private readonly Color textColor = new Color(0.95f, 0.97f, 1f, 1f);
        private readonly Color healthColor = new Color(1f, 0.32f, 0.32f, 1f);
        private readonly Color greenColor = new Color(0.13f, 0.86f, 0.43f, 1f);
        private readonly Color cyanColor = new Color(0.24f, 0.74f, 0.90f, 1f);

        private RectTransform layoutRoot;
        private RectTransform fantasyContent;
        private RectTransform consumablePanel;
        private Text healthText;
        private Text monsterNameText;
        private Text monsterHealthText;
        private Text moveCountText;
        private EditableSevenSegmentBox playerDamageBox;
        private EditableSevenSegmentBox monsterDamageBox;
        private EditableSevenSegmentBox monsterHitCountBox;
        private int playerDamageDifference;
        private int monsterDamageDifference;
        private int monsterHitDifference;

        private void Awake()
        {
            ResolveReferences();
            RemoveRuntimeLayouts();
            HideScenePlaceholders();
            EnsureLayout();
            BindButtons();
        }

        private void OnEnable()
        {
            GameEventHub.ItemInventoryChanged += RefreshConsumables;
            ResolveReferences();
            HideScenePlaceholders();
            EnsureLayout();
            Refresh();
        }

        private void OnDisable()
        {
            GameEventHub.ItemInventoryChanged -= RefreshConsumables;
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
        }

        private void HideScenePlaceholders()
        {
            for (int i = transform.childCount - 1; i >= 0; i--)
            {
                Transform child = transform.GetChild(i);
                if (child.name == "BattleRuntimeLayout")
                    continue;

                child.gameObject.SetActive(false);
            }
        }

        private void RemoveRuntimeLayouts()
        {
            layoutRoot = null;

            for (int i = transform.childCount - 1; i >= 0; i--)
            {
                Transform child = transform.GetChild(i);
                if (child.name != "BattleRuntimeLayout")
                    continue;

                GameObject childObject = child.gameObject;
                if (Application.isPlaying)
                {
                    child.SetParent(null, false);
                    Destroy(childObject);
                }
                else
                {
                    DestroyImmediate(childObject);
                }
            }
        }

        private void EnsureLayout()
        {
            if (layoutRoot != null)
                return;

            layoutRoot = CreateRect("BattleRuntimeLayout", transform, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
            layoutRoot.offsetMin = Vector2.zero;
            layoutRoot.offsetMax = Vector2.zero;

            CreateBackground();
            CreateStatusArea();
            CreateMoveCounter();
            CreateMonsterStatusPanel();
            CreateCombatArea();
            CreateBottomInventory();
            CreateResetButton();
            CreateResolveButton();
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
            RectTransform statusPanel = CreatePanel("StatusPanel", layoutRoot, panelColor, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(300f, -105f), new Vector2(484f, 112f));

            Text nameText = CreateText("Name", statusPanel, "성냥팔이 소녀", 28, textColor, TextAnchor.MiddleLeft);
            SetRect(nameText.rectTransform, new Vector2(0f, 0f), new Vector2(0f, 1f), new Vector2(160f, 0f), new Vector2(260f, 112f));

            healthText = CreateText("Health", statusPanel, string.Empty, 34, healthColor, TextAnchor.MiddleRight);
            SetRect(healthText.rectTransform, new Vector2(1f, 0f), new Vector2(1f, 1f), new Vector2(-74f, 0f), new Vector2(90f, 112f));

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

            RectTransform content = CreateRect("Content", viewport, new Vector2(0f, 0.5f), new Vector2(0f, 0.5f), Vector2.zero, Vector2.zero);
            content.pivot = new Vector2(0f, 0.5f);
            content.anchoredPosition = Vector2.zero;
            content.sizeDelta = new Vector2(746f, 68f);
            fantasyContent = content;
            RefreshFantasySlots();

            scrollRect.viewport = viewport;
            scrollRect.content = content;
        }

        private void CreateMoveCounter()
        {
            RectTransform counter = CreatePanel("MoveCounter", layoutRoot, panelColor, new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(0f, -104f), new Vector2(404f, 122f));
            Text label = CreateText("MoveLabel", counter, "이동 횟수", 22, textColor, TextAnchor.MiddleCenter);
            SetRect(label.rectTransform, new Vector2(0f, 0.52f), new Vector2(1f, 1f), new Vector2(0f, -8f), new Vector2(0f, 42f));
            moveCountText = CreateText("MoveCount", counter, "0 / 2", 42, cyanColor, TextAnchor.MiddleCenter);
            SetRect(moveCountText.rectTransform, new Vector2(0f, 0f), new Vector2(1f, 0.65f), new Vector2(0f, -4f), new Vector2(0f, 70f));
        }

        private void CreateMonsterStatusPanel()
        {
            RectTransform monsterStatus = CreatePanel("MonsterStatusPanel", layoutRoot, panelColor, new Vector2(1f, 1f), new Vector2(1f, 1f), new Vector2(-300f, -105f), new Vector2(484f, 112f));
            monsterNameText = CreateText("MonsterName", monsterStatus, string.Empty, 28, textColor, TextAnchor.MiddleLeft);
            SetRect(monsterNameText.rectTransform, new Vector2(0f, 0f), new Vector2(0f, 1f), new Vector2(108f, 0f), new Vector2(220f, 112f));
            monsterHealthText = CreateText("MonsterHealth", monsterStatus, string.Empty, 34, healthColor, TextAnchor.MiddleRight);
            SetRect(monsterHealthText.rectTransform, new Vector2(1f, 0f), new Vector2(1f, 1f), new Vector2(-88f, 0f), new Vector2(144f, 112f));
        }

        private void CreateCombatArea()
        {
            CreatePlayerFormula();
            CreateMonsterFormula();

            Text arrow = CreateText("Arrow", layoutRoot, "←", 106, textColor, TextAnchor.MiddleCenter);
            SetRect(arrow.rectTransform, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(220f, 112f), new Vector2(168f, 92f));

            Text player = CreateText("PlayerSpritePlaceholder", layoutRoot, "성냥\n소녀", 28, textColor, TextAnchor.MiddleCenter);
            SetRect(player.rectTransform, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(-560f, -182f), new Vector2(180f, 180f));

            Text monster = CreateText("MonsterSpritePlaceholder", layoutRoot, "요정", 30, textColor, TextAnchor.MiddleCenter);
            SetRect(monster.rectTransform, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(560f, -142f), new Vector2(180f, 180f));
        }

        private void CreatePlayerFormula()
        {
            RectTransform panel = CreatePanel("PlayerFormulaPanel", layoutRoot, panelColor, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(-560f, 92f), new Vector2(304f, 126f));
            playerDamageBox = CreateFormulaNumberBox(panel, "PlayerDamage", GetPlayerBaseDamage(), Vector2.zero, new Vector2(196f, 98f), healthColor, OnPlayerDamageDifferenceChanged, OnPlayerDamageEdited, false, GetPlayerDamageDigitCount());
        }

        private void CreateMonsterFormula()
        {
            RectTransform panel = CreatePanel("MonsterFormulaPanel", layoutRoot, panelColor, new Vector2(1f, 0.5f), new Vector2(1f, 0.5f), new Vector2(-374f, 92f), new Vector2(504f, 126f));
            Image panelImage = panel.GetComponent<Image>();
            if (panelImage != null)
                panelImage.color = new Color(0.07f, 0.20f, 0.15f, 0.95f);

            RectTransform formulaContent = CreateRect("FormulaContent", panel, new Vector2(1f, 0.5f), new Vector2(1f, 0.5f), Vector2.zero, Vector2.zero);
            formulaContent.pivot = new Vector2(1f, 0.5f);
            formulaContent.anchoredPosition = new Vector2(-16f, 0f);
            formulaContent.sizeDelta = new Vector2(470f, 104f);

            monsterDamageBox = CreateFormulaNumberBox(formulaContent, "MonsterDamage", GetMonsterBaseDamage(), new Vector2(-330f, 0f), new Vector2(188f, 98f), healthColor, OnMonsterDamageDifferenceChanged, OnMonsterDamageEdited, true);
            CreateFormulaOperator(formulaContent, "x", new Vector2(-192f, 0f), new Vector2(92f, 98f), healthColor, true);
            monsterHitCountBox = CreateFormulaNumberBox(formulaContent, "MonsterHitCount", GetMonsterHitCount(), new Vector2(-54f, 0f), new Vector2(172f, 98f), healthColor, OnMonsterHitDifferenceChanged, OnMonsterHitCountEdited, true);
        }

        private EditableSevenSegmentBox CreateFormulaNumberBox(RectTransform parent, string name, int value, Vector2 position, Vector2 size, Color color, UnityEngine.Events.UnityAction<int> onDifferenceChanged, UnityEngine.Events.UnityAction<int> onValueChanged, bool rightAnchor = false, int minimumDigits = 0)
        {
            Vector2 anchor = rightAnchor ? new Vector2(1f, 0.5f) : new Vector2(0.5f, 0.5f);
            RectTransform box = CreatePanel(name, parent, slotColor, anchor, anchor, position, size);
            EditableSevenSegmentBox sevenSegment = box.gameObject.AddComponent<EditableSevenSegmentBox>();
            sevenSegment.Configure(value, minimumDigits, color, onValueChanged, false, diff =>
            {
                onDifferenceChanged?.Invoke(diff);
                RefreshMoveCounter();
            });
            return sevenSegment;
        }

        private void CreateFormulaOperator(RectTransform parent, string value, Vector2 position, Vector2 size, Color color, bool rightAnchor = false)
        {
            Vector2 anchor = rightAnchor ? new Vector2(1f, 0.5f) : new Vector2(0.5f, 0.5f);
            RectTransform box = CreatePanel($"FormulaOperator_{value}", parent, slotColor, anchor, anchor, position, size);
            Text text = CreateText("Text", box, value, 44, color, TextAnchor.MiddleCenter);
            SetRect(text.rectTransform, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
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

        private void CreateResetButton()
        {
            resetButton = CreateCircleButton("ResetButton", "↻", new Vector2(160f, 96f), false);
        }

        private void CreateResolveButton()
        {
            resolveBattleButton = CreateCircleButton("ResolveBattleButton", "E", new Vector2(-136f, 96f), true);
        }

        private Button CreateCircleButton(string name, string label, Vector2 position, bool rightAnchor)
        {
            Vector2 anchor = rightAnchor ? new Vector2(1f, 0f) : new Vector2(0f, 0f);
            RectTransform panel = CreatePanel(name, layoutRoot, panelColor, anchor, anchor, position, new Vector2(108f, 108f));
            Button button = panel.gameObject.AddComponent<Button>();
            Text text = CreateText("Label", panel, label, 46, textColor, TextAnchor.MiddleCenter);
            SetRect(text.rectTransform, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
            return button;
        }

        private void BindButtons()
        {
            if (resolveBattleButton != null)
                resolveBattleButton.onClick.AddListener(OnResolveBattleClicked);
            if (resetButton != null)
                resetButton.onClick.AddListener(OnResetClicked);
        }

        private void UnbindButtons()
        {
            if (resolveBattleButton != null)
                resolveBattleButton.onClick.RemoveListener(OnResolveBattleClicked);
            if (resetButton != null)
                resetButton.onClick.RemoveListener(OnResetClicked);
        }

        private void Refresh()
        {
            if (healthText != null)
                healthText.text = bootstrap != null && bootstrap.RunContext != null ? bootstrap.RunContext.health.ToString() : "0";
            RefreshMonsterStatus();
            RefreshFormulaValues();
            RefreshFantasySlots();
            RefreshConsumables();
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
        }

        private void RefreshFantasySlots()
        {
            if (fantasyContent == null)
                return;

            ClearChildren(fantasyContent);
            int ownedCount = bootstrap != null && bootstrap.RunContext != null && bootstrap.RunContext.fantasyInventory != null
                ? bootstrap.RunContext.fantasyInventory.ownedFantasies.Count
                : 0;
            int slotCount = Mathf.Max(10, ownedCount);
            fantasyContent.sizeDelta = new Vector2(Mathf.Max(746f, slotCount * 74f + 6f), 68f);

            for (int i = 0; i < slotCount; i++)
            {
                RectTransform slot = CreatePanel($"FantasySlot{i + 1}", fantasyContent, slotColor, new Vector2(0f, 0.5f), new Vector2(0f, 0.5f), new Vector2(34f + i * 74f, 0f), new Vector2(60f, 60f));
                if (i >= ownedCount)
                    continue;

                FantasyData fantasy = bootstrap.RunContext.fantasyInventory.ownedFantasies[i];
                if (fantasy == null)
                    continue;

                Text icon = CreateText("FantasyIcon", slot, "★", 29, GradeColor(fantasy.grade), TextAnchor.MiddleCenter);
                SetRect(icon.rectTransform, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
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

        private void RefreshFormulaValues()
        {
            if (playerDamageBox != null)
                playerDamageBox.Configure(GetPlayerBaseDamage(), GetPlayerDamageDigitCount(), healthColor, OnPlayerDamageEdited, false, OnPlayerDamageDifferenceChanged, battleController != null ? battleController.PlayerBaseDamageSegmentState : string.Empty);
            if (monsterDamageBox != null)
                monsterDamageBox.Configure(GetMonsterBaseDamage(), 0, healthColor, OnMonsterDamageEdited, false, OnMonsterDamageDifferenceChanged, battleController != null ? battleController.MonsterBaseDamageSegmentState : string.Empty);
            if (monsterHitCountBox != null)
                monsterHitCountBox.Configure(GetMonsterHitCount(), 0, healthColor, OnMonsterHitCountEdited, false, OnMonsterHitDifferenceChanged, battleController != null ? battleController.MonsterHitCountSegmentState : string.Empty);
        }

        private void RefreshMoveCounter()
        {
            if (moveCountText == null)
                return;

            int totalDifference = playerDamageDifference + monsterDamageDifference + monsterHitDifference;
            int limit = battleController != null ? battleController.CurrentMoveLimit : 2;
            moveCountText.text = $"{totalDifference} / {limit}";
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

        private void OnPlayerDamageDifferenceChanged(int difference)
        {
            playerDamageDifference = difference;
        }

        private void OnMonsterDamageDifferenceChanged(int difference)
        {
            monsterDamageDifference = difference;
        }

        private void OnMonsterHitDifferenceChanged(int difference)
        {
            monsterHitDifference = difference;
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

        private void OnResolveBattleClicked()
        {
            if (battleController != null)
            {
                battleController.SetUsedMoveCount(playerDamageDifference + monsterDamageDifference + monsterHitDifference);
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

        private static void ClearChildren(Transform root)
        {
            if (root == null)
                return;

            for (int i = root.childCount - 1; i >= 0; i--)
                Destroy(root.GetChild(i).gameObject);
        }
    }
}
