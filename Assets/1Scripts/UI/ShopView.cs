using System.Collections;
using System.Collections.Generic;
using GoldfishWalking.Data;
using GoldfishWalking.Match;
using GoldfishWalking.Shop;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;
#if UNITY_EDITOR
using UnityEditor;
#endif

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
        private RectTransform tooltipRoot;
        private Text healthText;
        private Text moveCountText;
        private Text spendFloatText;
        private Text tooltipName;
        private Text tooltipDescription;
        private Text tooltipEffect;
        private FantasyTooltipView tooltipView;
        private FantasyListView fantasyListView;
        private Button closeButton;
        private Coroutine spendFloatRoutine;
        private readonly Dictionary<string, EditableSevenSegmentBox> priceBoxes = new Dictionary<string, EditableSevenSegmentBox>();
        private readonly Dictionary<string, Button> itemButtons = new Dictionary<string, Button>();
        private readonly Dictionary<string, RectTransform> itemRoots = new Dictionary<string, RectTransform>();
        private readonly Dictionary<string, Text> itemTitleTexts = new Dictionary<string, Text>();

        private void Awake()
        {
            ResolveReferences();
            HideScenePlaceholders();
            EnsureLayout();
            BindExistingLayout();
            BindButtons();
        }

        private void OnEnable()
        {
            ResolveReferences();
            HideScenePlaceholders();
            EnsureLayout();
            BindExistingLayout();
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

        private void RemoveExistingLayoutImmediate()
        {
            layoutRoot = null;

            for (int i = transform.childCount - 1; i >= 0; i--)
            {
                Transform child = transform.GetChild(i);
                if (child.name != "ShopRuntimeLayout")
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

            Transform existing = transform.Find("ShopRuntimeLayout");
            if (existing is RectTransform existingLayout)
            {
                layoutRoot = existingLayout;
                BindExistingLayout();
                return;
            }

            Debug.LogError("[ShopView] Missing prebuilt ShopRuntimeLayout. Build the UI in the scene instead of creating it from script.");
        }

        private void BindExistingLayout()
        {
            if (layoutRoot == null)
                return;

            statusPanel = FindRect("StatusPanel");
            fantasySlotsRoot = FindRect("FantasySlots");
            fantasyContentRoot = FindRect("FantasySlots/Viewport/Content");
            tooltipRoot = FindRect("ShopTooltip");
            healthText = FindComponent<Text>("StatusPanel/Health");
            spendFloatText = FindComponent<Text>("StatusPanel/SpendFloat");
            moveCountText = FindComponent<Text>("MoveCounter/MoveCount");
            tooltipName = FindComponent<Text>("ShopTooltip/Name");
            tooltipDescription = FindComponent<Text>("ShopTooltip/Description");
            tooltipEffect = FindComponent<Text>("ShopTooltip/Effect");
            tooltipView = tooltipRoot != null ? tooltipRoot.GetComponent<FantasyTooltipView>() : null;
            if (tooltipView != null)
                tooltipView.Bind(tooltipName, tooltipDescription, tooltipEffect);
            else if (tooltipRoot != null)
                Debug.LogWarning("[ShopView] Missing FantasyTooltipView on ShopTooltip.");
            fantasyListView = fantasyContentRoot != null ? fantasyContentRoot.GetComponent<FantasyListView>() : null;
            if (fantasyListView != null)
                fantasyListView.Bind(fantasyContentRoot, tooltipView, 10);
            closeButton = FindComponent<Button>("CloseButton");

            priceBoxes.Clear();
            itemButtons.Clear();
            itemRoots.Clear();
            itemTitleTexts.Clear();
            for (int i = 0; i < shopItems.Length; i++)
                BindShopItem(shopItems[i]);
        }

        private void BindShopItem(ShopItem item)
        {
            RectTransform itemRoot = FindRect(item.id);
            if (itemRoot == null)
                return;

            itemRoots[item.id] = itemRoot;

            Transform iconPanel = itemRoot.Find("IconPanel");
            Button button = iconPanel != null ? iconPanel.GetComponent<Button>() : null;
            if (button != null)
            {
                button.onClick.RemoveAllListeners();
                button.onClick.AddListener(() => OnItemClicked(item, button));
                itemButtons[item.id] = button;
            }

            if (iconPanel != null)
            {
                ShopTooltipTrigger trigger = iconPanel.GetComponent<ShopTooltipTrigger>();
                if (trigger != null)
                    trigger.Initialize(this, item);
                else
                    Debug.LogWarning($"[ShopView] Missing ShopTooltipTrigger on {item.id}/IconPanel.");
            }

            Transform title = itemRoot.Find("Title");
            Text titleText = title != null ? title.GetComponent<Text>() : null;
            if (titleText != null)
                itemTitleTexts[item.id] = titleText;

            Transform price = itemRoot.Find("Price");
            EditableSevenSegmentBox priceBox = price != null ? price.GetComponent<EditableSevenSegmentBox>() : null;
            if (priceBox != null)
                priceBoxes[item.id] = priceBox;
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

            bool boughtFantasy = false;
            if (TryGetShopFantasy(item, out FantasyData fantasy))
            {
                if (!shopController.TryBuyFantasy(item.id, fantasy, price))
                    return;
                boughtFantasy = true;
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

            if (boughtFantasy)
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
            RefreshItemTitles();
            RefreshItemButtons();
            HideTooltip();
        }

        private void RefreshFantasySlots()
        {
            if (fantasyListView != null)
            {
                fantasyListView.Bind(fantasyContentRoot, tooltipView, 10);
                fantasyListView.Refresh(shopController != null ? shopController.OwnedFantasies : null);
                return;
            }

            Debug.LogWarning("[ShopView] Missing FantasyListView on FantasySlots/Viewport/Content.");
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

        private void RefreshPrices()
        {
            for (int i = 0; i < shopItems.Length; i++)
            {
                ShopItem item = shopItems[i];
                if (!priceBoxes.TryGetValue(item.id, out EditableSevenSegmentBox box) || box == null)
                    continue;

                box.Configure(GetCurrentPrice(item), GetMinDigits(item.id), priceMatchColor, newValue => OnPriceEdited(item.id, newValue));
            }
        }

        private void RefreshItemTitles()
        {
            for (int i = 0; i < shopItems.Length; i++)
            {
                ShopItem item = shopItems[i];
                if (!itemTitleTexts.TryGetValue(item.id, out Text titleText) || titleText == null)
                    continue;

                titleText.text = GetItemTitle(item);
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
                case "ShopItemPlaceholder":
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
                return FantasyText.DisplayName(fantasy);

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

        private void ShowFantasyTooltip(FantasyData fantasy)
        {
            if (fantasy == null)
                return;

            ShowTooltip(FantasyText.DisplayName(fantasy), FantasyText.Description(fantasy), FantasyText.EffectSummary(fantasy));
        }

        private void ShowShopItemTooltip(ShopItem item)
        {
            if (TryGetShopFantasy(item, out FantasyData fantasy))
            {
                ShowFantasyTooltip(fantasy);
                return;
            }

            switch (item.id)
            {
                case "ShopItemExtraMatch":
                    ShowTooltip("Extra Match", "소모품", "구매 시 추가 성냥 +1");
                    break;
                case "ShopItemEraser":
                    ShowTooltip("Eraser", "소모품", "구매 시 지우개 +1");
                    break;
                default:
                    HideTooltip();
                    break;
            }
        }

        private void ShowTooltip(string title, string description, string effect)
        {
            if (tooltipView != null)
                tooltipView.Show(title, description, effect);
        }

        private void HideTooltip()
        {
            if (tooltipView != null)
                tooltipView.Hide();
        }

        private void RefreshItemButtons()
        {
            for (int i = 0; i < shopItems.Length; i++)
            {
                ShopItem item = shopItems[i];
                if (!itemButtons.TryGetValue(item.id, out Button button) || button == null)
                    continue;

                if (itemRoots.TryGetValue(item.id, out RectTransform root) && root != null)
                    root.gameObject.SetActive(ShouldShowItem(item.id));

                if (!ShouldShowItem(item.id))
                    continue;

                if (TryGetShopFantasy(item, out FantasyData fantasy))
                    button.interactable = !shopController.IsShopSlotFantasyPurchased(item.id, fantasy);
                else
                    button.interactable = true;
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
            string value = effect.hasNumericValue ? effect.numericValue.ToString(System.Globalization.CultureInfo.InvariantCulture) : (!string.IsNullOrWhiteSpace(effect.valueExpression) ? effect.valueExpression : "0");
            return $"{trigger} / {target} / {calc} {value}";
        }

        private static int GetMinPrice(ShopItem item)
        {
            if (item.id == "ShopFantasyRed")
                return 1000;
            return item.price < 100 ? 10 : 100;
        }

        private static int GetMaxPrice(ShopItem item)
        {
            if (item.id == "ShopFantasyRed")
                return 9999;
            return item.price < 100 ? 99 : 999;
        }

        private static int GetMinDigits(string itemId)
        {
            return itemId == "ShopFantasyRed" ? 4 : 0;
        }

        private bool ShouldShowItem(string itemId)
        {
            if (itemId != "ShopItemPlaceholder")
                return true;

            return shopController != null
                && shopController.OwnedFantasies != null
                && ContainsFantasy(shopController.OwnedFantasies, "fan_shop_stencil");
        }

        private static bool ContainsFantasy(IReadOnlyList<FantasyData> fantasies, string fantasyId)
        {
            if (fantasies == null)
                return false;

            for (int i = 0; i < fantasies.Count; i++)
            {
                FantasyData fantasy = fantasies[i];
                if (fantasy != null && fantasy.id == fantasyId)
                    return true;
            }

            return false;
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

        private sealed class ShopTooltipTrigger : MonoBehaviour, IPointerEnterHandler, IPointerExitHandler
        {
            private ShopView owner;
            private FantasyData fantasy;
            private ShopItem item;
            private bool hasItem;

            public void Initialize(ShopView tooltipOwner, FantasyData tooltipFantasy)
            {
                owner = tooltipOwner;
                fantasy = tooltipFantasy;
                hasItem = false;
            }

            public void Initialize(ShopView tooltipOwner, ShopItem tooltipItem)
            {
                owner = tooltipOwner;
                item = tooltipItem;
                hasItem = true;
            }

            public void OnPointerEnter(PointerEventData eventData)
            {
                if (hasItem)
                    owner?.ShowShopItemTooltip(item);
                else
                    owner?.ShowFantasyTooltip(fantasy);
            }

            public void OnPointerExit(PointerEventData eventData)
            {
                owner?.HideTooltip();
            }
        }
    }
}
