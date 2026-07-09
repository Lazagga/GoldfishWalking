using System.Collections;
using System.Collections.Generic;
using GoldfishWalking.Data;
using GoldfishWalking.Match;
using GoldfishWalking.Shop;
using UnityEngine;
using UnityEngine.UI;

namespace GoldfishWalking.UI
{
    public sealed class ShopView : MonoBehaviour
    {
        private readonly ShopItem[] shopItems =
        {
            new ShopItem("ShopFantasyWhite", "★", 24, new Color(0.95f, 0.97f, 1f, 1f)),
            new ShopItem("ShopFantasyBlue", "★", 251, new Color(0.24f, 0.74f, 0.90f, 1f)),
            new ShopItem("ShopFantasyRed", "★", 1024, new Color(1.00f, 0.30f, 0.30f, 1f)),
            new ShopItem("ShopItemExtraMatch", "●", 18, new Color(1.00f, 0.30f, 0.30f, 1f)),
            new ShopItem("ShopItemEraser", "■", 43, new Color(0.95f, 0.97f, 1f, 1f)),
            new ShopItem("ShopItemPlaceholder", "▰", 87, new Color(0.90f, 0.92f, 0.95f, 1f))
        };

        [SerializeField] private ShopController shopController;

        private readonly Color backgroundColor = new Color(0.07f, 0.08f, 0.11f, 1f);
        private readonly Color panelColor = new Color(0.14f, 0.16f, 0.20f, 0.94f);
        private readonly Color slotColor = new Color(0.20f, 0.22f, 0.29f, 0.96f);
        private readonly Color textColor = new Color(0.95f, 0.97f, 1f, 1f);
        private readonly Color healthColor = new Color(1f, 0.32f, 0.32f, 1f);
        private readonly Color priceMatchColor = new Color(1f, 0.38f, 0.38f, 1f);

        private RectTransform layoutRoot;
        private RectTransform statusPanel;
        private RectTransform fantasySlotsRoot;
        private RectTransform fantasyContentRoot;
        private Text healthText;
        private Text moveCountText;
        private Text spendFloatText;
        private Button closeButton;
        private Coroutine spendFloatRoutine;
        private readonly Dictionary<string, EditableSevenSegmentBox> priceBoxes = new Dictionary<string, EditableSevenSegmentBox>();
        private readonly Dictionary<string, Button> itemButtons = new Dictionary<string, Button>();

        private void Awake()
        {
            ResolveReferences();
            HideScenePlaceholders();
            EnsureLayout();
            BindButtons();
        }

        private void OnEnable()
        {
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
            if (shopController == null)
                shopController = FindFirstObjectByType<ShopController>(FindObjectsInactive.Include);
        }

        private void HideScenePlaceholders()
        {
            for (int i = 0; i < transform.childCount; i++)
            {
                Transform child = transform.GetChild(i);
                if (layoutRoot != null && child == layoutRoot)
                    continue;
                if (child.name == "ShopRuntimeLayout")
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

            layoutRoot = CreateRect("ShopRuntimeLayout", transform, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
            layoutRoot.offsetMin = Vector2.zero;
            layoutRoot.offsetMax = Vector2.zero;

            CreateBackground();
            CreateStatusArea();
            CreateMerchantPanel();
            CreateMoveCounter();
            CreateShopGrid();
            CreateCloseButton();
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

            healthText = CreateText("Health", statusPanel, string.Empty, 34, healthColor, TextAnchor.MiddleRight);
            SetRect(healthText.rectTransform, new Vector2(1f, 0f), new Vector2(1f, 1f), new Vector2(-74f, 0f), new Vector2(90f, 112f));

            spendFloatText = CreateText("SpendFloat", statusPanel, string.Empty, 34, healthColor, TextAnchor.MiddleCenter);
            SetRect(spendFloatText.rectTransform, new Vector2(1f, 1f), new Vector2(1f, 1f), new Vector2(-78f, 26f), new Vector2(130f, 46f));
            spendFloatText.gameObject.SetActive(false);

            fantasySlotsRoot = CreatePanel("FantasySlots", layoutRoot, panelColor, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(299f, -228f), new Vector2(482f, 88f));
            ScrollRect scrollRect = fantasySlotsRoot.gameObject.AddComponent<ScrollRect>();
            scrollRect.horizontal = true;
            scrollRect.vertical = false;
            scrollRect.inertia = true;
            scrollRect.movementType = ScrollRect.MovementType.Clamped;

            RectTransform viewport = CreateRect("Viewport", fantasySlotsRoot, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
            viewport.offsetMin = new Vector2(10f, 10f);
            viewport.offsetMax = new Vector2(-10f, -10f);
            viewport.gameObject.AddComponent<RectMask2D>();

            fantasyContentRoot = CreateRect("Content", viewport, new Vector2(0f, 0.5f), new Vector2(0f, 0.5f), Vector2.zero, Vector2.zero);
            fantasyContentRoot.pivot = new Vector2(0f, 0.5f);
            fantasyContentRoot.anchoredPosition = Vector2.zero;
            fantasyContentRoot.sizeDelta = new Vector2(462f, 68f);

            scrollRect.viewport = viewport;
            scrollRect.content = fantasyContentRoot;
            RefreshFantasySlots();
        }

        private void CreateMerchantPanel()
        {
            RectTransform merchant = CreatePanel("MerchantPanel", layoutRoot, panelColor, new Vector2(0f, 0f), new Vector2(0f, 0f), new Vector2(299f, 458f), new Vector2(452f, 524f));
            Text face = CreateText("MerchantFace", merchant, "상점", 52, textColor, TextAnchor.MiddleCenter);
            SetRect(face.rectTransform, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
        }

        private void CreateMoveCounter()
        {
            RectTransform counter = CreatePanel("MoveCounter", layoutRoot, panelColor, new Vector2(0f, 0f), new Vector2(0f, 0f), new Vector2(299f, 96f), new Vector2(404f, 104f));
            Text label = CreateText("MoveLabel", counter, "이동 횟수", 22, textColor, TextAnchor.MiddleCenter);
            SetRect(label.rectTransform, new Vector2(0f, 0.5f), new Vector2(1f, 1f), new Vector2(0f, -8f), new Vector2(0f, 42f));
            moveCountText = CreateText("MoveCount", counter, "2 / 2", 36, new Color(0.24f, 0.74f, 0.90f, 1f), TextAnchor.MiddleCenter);
            SetRect(moveCountText.rectTransform, new Vector2(0f, 0f), new Vector2(1f, 0.6f), new Vector2(0f, -4f), new Vector2(0f, 58f));
        }

        private void CreateShopGrid()
        {
            Vector2[] positions =
            {
                new Vector2(850f, 760f),
                new Vector2(1230f, 760f),
                new Vector2(1610f, 760f),
                new Vector2(850f, 360f),
                new Vector2(1230f, 360f),
                new Vector2(1610f, 360f)
            };

            for (int i = 0; i < shopItems.Length; i++)
                CreateShopItem(shopItems[i], positions[i]);
        }

        private void CreateShopItem(ShopItem item, Vector2 centerPosition)
        {
            RectTransform itemRoot = CreateRect(item.id, layoutRoot, Vector2.zero, Vector2.zero, Vector2.zero, Vector2.zero);
            itemRoot.anchoredPosition = centerPosition;
            itemRoot.sizeDelta = new Vector2(260f, 330f);

            RectTransform iconPanel = CreatePanel("IconPanel", itemRoot, panelColor, new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(0f, -92f), new Vector2(216f, 216f));
            Text icon = CreateText("Icon", iconPanel, item.icon, 92, item.iconColor, TextAnchor.MiddleCenter);
            SetRect(icon.rectTransform, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);

            Button button = iconPanel.gameObject.AddComponent<Button>();
            button.onClick.AddListener(() => OnItemClicked(item, button));
            itemButtons[item.id] = button;

            string title = GetItemTitle(item);
            if (!string.IsNullOrWhiteSpace(title))
            {
                Text titleText = CreateText("Title", itemRoot, title, 16, textColor, TextAnchor.MiddleCenter);
                SetRect(titleText.rectTransform, new Vector2(0f, 0f), new Vector2(1f, 0f), new Vector2(0f, 106f), new Vector2(0f, 36f));
            }

            RectTransform priceRoot = CreateRect("Price", itemRoot, new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), Vector2.zero, Vector2.zero);
            priceRoot.anchoredPosition = new Vector2(0f, 35f);
            priceRoot.sizeDelta = new Vector2(230f, 88f);
            priceBoxes[item.id] = DrawMatchNumber(priceRoot, GetCurrentPrice(item), 0.45f, item.id);
        }

        private void CreateCloseButton()
        {
            closeButton = CreateButton("CloseButton", "다음 지역으로 이동 →", new Vector2(-281f, 96f), new Vector2(486f, 96f), 28, true);
        }

        private Button CreateButton(string name, string label, Vector2 anchoredPosition, Vector2 size, int fontSize, bool rightAnchor = false)
        {
            Vector2 anchor = rightAnchor ? new Vector2(1f, 0f) : new Vector2(0f, 0f);
            RectTransform panel = CreatePanel(name, layoutRoot, panelColor, anchor, anchor, anchoredPosition, size);
            Button button = panel.gameObject.AddComponent<Button>();
            Text buttonText = CreateText("Label", panel, label, fontSize, textColor, TextAnchor.MiddleCenter);
            SetRect(buttonText.rectTransform, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
            return button;
        }

        private void BindButtons()
        {
            if (closeButton != null)
                closeButton.onClick.AddListener(OnCloseClicked);
        }

        private void UnbindButtons()
        {
            if (closeButton != null)
                closeButton.onClick.RemoveListener(OnCloseClicked);
        }

        private void OnItemClicked(ShopItem item, Button button)
        {
            int price = GetCurrentPrice(item);
            if (shopController == null)
                return;

            if (TryGetShopFantasy(item, out FantasyData fantasy))
            {
                if (!shopController.TryBuyFantasy(fantasy, price))
                    return;
            }
            else if (TryGetPurchasedItemType(item.id, out ItemType itemType))
            {
                bool freePurchase = shopController.TryUseFreeConsumablePurchase(item.id);
                if (!freePurchase && !shopController.TrySpendHealth(price))
                    return;

                shopController.AddItem(itemType, 1);
                price = freePurchase ? 0 : price;
            }
            else
            {
                return;
            }

            button.interactable = false;
            Refresh();
            PlaySpendFloat(price);
        }

        private void OnCloseClicked()
        {
            if (shopController != null)
                shopController.CloseShop();
        }

        private void Refresh()
        {
            if (healthText != null)
                healthText.text = shopController != null ? shopController.CurrentHealth.ToString() : "0";
            if (moveCountText != null)
                moveCountText.text = $"2 / {(shopController != null ? shopController.CurrentMoveLimit : 2)}";
            RefreshFantasySlots();
            RefreshPrices();
            RefreshItemButtons();
        }

        private void RefreshFantasySlots()
        {
            if (fantasyContentRoot == null)
                return;

            ClearChildren(fantasyContentRoot);
            IReadOnlyList<FantasyData> owned = shopController != null ? shopController.OwnedFantasies : null;
            int ownedCount = owned != null ? owned.Count : 0;
            int slotCount = Mathf.Max(6, ownedCount);
            fantasyContentRoot.sizeDelta = new Vector2(Mathf.Max(462f, slotCount * 76f + 12f), 68f);

            for (int i = 0; i < slotCount; i++)
            {
                RectTransform slot = CreatePanel($"FantasySlot{i + 1}", fantasyContentRoot, slotColor, new Vector2(0f, 0.5f), new Vector2(0f, 0.5f), new Vector2(32f + i * 76f, 0f), new Vector2(60f, 60f));
                if (owned == null || i >= owned.Count || owned[i] == null)
                    continue;

                Text icon = CreateText("FantasyIcon", slot, "★", 29, GradeColor(owned[i].grade), TextAnchor.MiddleCenter);
                SetRect(icon.rectTransform, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
            }
        }

        private void PlaySpendFloat(int amount)
        {
            if (spendFloatText == null)
                return;

            if (spendFloatRoutine != null)
                StopCoroutine(spendFloatRoutine);
            spendFloatRoutine = StartCoroutine(SpendFloatRoutine(amount));
        }

        private IEnumerator SpendFloatRoutine(int amount)
        {
            RectTransform rect = spendFloatText.rectTransform;
            Vector2 start = new Vector2(-78f, 26f);
            Vector2 end = start + new Vector2(0f, 76f);
            float duration = 0.85f;
            float elapsed = 0f;

            spendFloatText.text = $"-{amount}";
            spendFloatText.color = healthColor;
            rect.anchoredPosition = start;
            spendFloatText.gameObject.SetActive(true);

            while (elapsed < duration)
            {
                elapsed += Time.deltaTime;
                float t = Mathf.Clamp01(elapsed / duration);
                rect.anchoredPosition = Vector2.Lerp(start, end, t);
                Color color = healthColor;
                color.a = 1f - t;
                spendFloatText.color = color;
                yield return null;
            }

            spendFloatText.gameObject.SetActive(false);
            spendFloatRoutine = null;
        }

        private EditableSevenSegmentBox DrawMatchNumber(RectTransform root, int value, float scale, string itemId)
        {
            EditableSevenSegmentBox box = root.GetComponent<EditableSevenSegmentBox>();
            if (box == null)
                box = root.gameObject.AddComponent<EditableSevenSegmentBox>();

            box.Configure(value, 0, priceMatchColor, newValue => OnPriceEdited(itemId, newValue));
            return box;
        }

        private void RefreshPrices()
        {
            for (int i = 0; i < shopItems.Length; i++)
            {
                ShopItem item = shopItems[i];
                if (!priceBoxes.TryGetValue(item.id, out EditableSevenSegmentBox box) || box == null)
                    continue;

                box.Configure(GetCurrentPrice(item), 0, priceMatchColor, newValue => OnPriceEdited(item.id, newValue));
            }
        }

        private int GetCurrentPrice(ShopItem item)
        {
            return shopController != null
                ? shopController.GetPrice(item.id, GetMinPrice(item), GetMaxPrice(item))
                : item.price;
        }

        private void OnPriceEdited(string itemId, int newValue)
        {
            if (shopController != null)
                shopController.SetPrice(itemId, Mathf.Max(0, newValue));
        }

        private static bool TryGetPurchasedItemType(string itemId, out ItemType itemType)
        {
            if (itemId == "ShopItemExtraMatch")
            {
                itemType = ItemType.ExtraMatch;
                return true;
            }

            if (itemId == "ShopItemEraser")
            {
                itemType = ItemType.Eraser;
                return true;
            }

            itemType = ItemType.ExtraMatch;
            return false;
        }

        private bool TryGetShopFantasy(ShopItem item, out FantasyData fantasy)
        {
            fantasy = null;
            if (shopController == null)
                return false;

            if (!TryGetFantasyGrade(item.id, out FantasyGrade grade))
                return false;

            fantasy = shopController.GetShopFantasy(item.id, grade);
            return fantasy != null;
        }

        private static bool TryGetFantasyGrade(string itemId, out FantasyGrade grade)
        {
            switch (itemId)
            {
                case "ShopFantasyWhite":
                    grade = FantasyGrade.White;
                    return true;
                case "ShopFantasyBlue":
                    grade = FantasyGrade.Blue;
                    return true;
                case "ShopFantasyRed":
                    grade = FantasyGrade.Red;
                    return true;
                default:
                    grade = FantasyGrade.White;
                    return false;
            }
        }

        private string GetItemTitle(ShopItem item)
        {
            if (TryGetShopFantasy(item, out FantasyData fantasy))
                return DisplayName(fantasy);

            switch (item.id)
            {
                case "ShopItemExtraMatch":
                    return "Extra Match";
                case "ShopItemEraser":
                    return "Eraser";
                default:
                    return string.Empty;
            }
        }

        private void RefreshItemButtons()
        {
            for (int i = 0; i < shopItems.Length; i++)
            {
                ShopItem item = shopItems[i];
                if (!itemButtons.TryGetValue(item.id, out Button button) || button == null)
                    continue;

                if (TryGetShopFantasy(item, out FantasyData fantasy))
                    button.interactable = !shopController.IsFantasyPurchased(fantasy);
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

        private Color GradeColor(FantasyGrade grade)
        {
            switch (grade)
            {
                case FantasyGrade.Blue:
                    return new Color(0.24f, 0.74f, 0.90f, 1f);
                case FantasyGrade.Red:
                    return healthColor;
                default:
                    return textColor;
            }
        }

        private static int GetMinPrice(ShopItem item)
        {
            return item.price < 100 ? 10 : 100;
        }

        private static int GetMaxPrice(ShopItem item)
        {
            return item.price < 100 ? 99 : 999;
        }

        private void DrawDigit(RectTransform digitRoot, int digit, float scale)
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
                CreateMatchSegment(digitRoot, (MatchSegment)pattern.segments[i], scale);
        }

        private void CreateMatchSegment(RectTransform digitRoot, MatchSegment segment, float scale)
        {
            RectTransform match = CreatePanel($"Segment{segment}", digitRoot, priceMatchColor, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), SegmentPosition(segment) * scale, SegmentSize(segment) * scale);
            match.gameObject.AddComponent<MatchstickView>();
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

        private readonly struct ShopItem
        {
            public readonly string id;
            public readonly string icon;
            public readonly int price;
            public readonly Color iconColor;

            public ShopItem(string id, string icon, int price, Color iconColor)
            {
                this.id = id;
                this.icon = icon;
                this.price = price;
                this.iconColor = iconColor;
            }
        }
    }
}
