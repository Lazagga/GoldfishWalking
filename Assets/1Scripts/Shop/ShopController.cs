using GoldfishWalking.Core;
using GoldfishWalking.Data;
using GoldfishWalking.Fantasy;
using System.Collections.Generic;
using UnityEngine;

namespace GoldfishWalking.Shop
{
    public sealed class ShopController : MonoBehaviour
    {
        [SerializeField] private GameBootstrap bootstrap;
        [SerializeField] private FantasyDatabase fantasyDatabase;
        private readonly FantasyEffectRunner fantasyEffectRunner = new FantasyEffectRunner();

        private void OnEnable()
        {
            GameEventHub.StateChanged += OnStateChanged;
        }

        private void OnDisable()
        {
            GameEventHub.StateChanged -= OnStateChanged;
        }

        public void CloseShop()
        {
            GameEventHub.RaiseShopClosed();
        }

        public bool TrySpendHealth(int amount)
        {
            if (bootstrap == null || bootstrap.RunContext == null)
                return false;

            if (amount <= 0 || bootstrap.RunContext.health <= amount)
                return false;

            bootstrap.RunContext.health -= amount;
            bootstrap.RunContext.lastShopPurchaseCost = amount;
            fantasyEffectRunner.ApplyTrigger(bootstrap.RunContext, "Shop_Purchase");
            bootstrap.RunContext.lastShopPurchaseCost = 0;
            return true;
        }

        public bool TryUseFreeConsumablePurchase(string itemId)
        {
            if (bootstrap == null || bootstrap.RunContext == null || bootstrap.RunContext.currentShop == null)
                return false;

            if (!HasStickyGlove() || bootstrap.RunContext.currentShop.freePurchasedItemIds.Contains(itemId))
                return false;

            bootstrap.RunContext.currentShop.freePurchasedItemIds.Add(itemId);
            return true;
        }

        public int CurrentHealth => bootstrap != null && bootstrap.RunContext != null ? bootstrap.RunContext.health : 0;
        public IReadOnlyList<FantasyData> OwnedFantasies => bootstrap != null && bootstrap.RunContext != null && bootstrap.RunContext.fantasyInventory != null
            ? bootstrap.RunContext.fantasyInventory.ownedFantasies
            : null;
        public int CurrentMoveLimit => bootstrap != null && bootstrap.RunContext != null
            ? Mathf.Max(0, fantasyEffectRunner.ModifyValue(bootstrap.RunContext, 2, "Passive", "Shop_Movement", "Movement"))
            : 2;

        public int GetPrice(string itemId, int minInclusive, int maxInclusive)
        {
            if (bootstrap == null || bootstrap.RunContext == null)
                return minInclusive;

            if (bootstrap.RunContext.currentShop == null)
                bootstrap.RunContext.currentShop = new ShopNumberState();

            if (bootstrap.RunContext.currentShop.prices.TryGetValue(itemId, out int price))
                return price;

            int rolledPrice = bootstrap.RunContext.RollValue($"shop.price.{itemId}", minInclusive, maxInclusive);
            price = Mathf.Max(0, fantasyEffectRunner.ModifyValue(bootstrap.RunContext, rolledPrice, "Passive", "Price"));
            bootstrap.RunContext.currentShop.prices[itemId] = price;
            return price;
        }

        public void SetPrice(string itemId, int price)
        {
            if (bootstrap == null || bootstrap.RunContext == null)
                return;

            bootstrap.RunContext.SetShopPrice(itemId, price);
        }

        public void AddItem(ItemType itemType, int count)
        {
            if (bootstrap == null || bootstrap.RunContext == null)
                return;

            fantasyEffectRunner.AddItemWithAcquireEffects(bootstrap.RunContext, itemType, Mathf.Max(0, count));
        }

        public FantasyData GetShopFantasy(string slotId, FantasyGrade grade)
        {
            if (bootstrap == null || bootstrap.RunContext == null || fantasyDatabase == null)
                return null;

            if (bootstrap.RunContext.currentShop == null)
                bootstrap.RunContext.currentShop = new ShopNumberState();

            if (bootstrap.RunContext.currentShop.fantasyIds.TryGetValue(slotId, out string existingId))
                return FindFantasy(existingId);

            FantasyData selected = SelectFantasyForShop(slotId, grade);
            if (selected != null)
                bootstrap.RunContext.currentShop.fantasyIds[slotId] = selected.id;

            return selected;
        }

        public bool IsFantasyPurchased(FantasyData fantasy)
        {
            if (fantasy == null || bootstrap == null || bootstrap.RunContext == null || bootstrap.RunContext.currentShop == null)
                return false;

            return bootstrap.RunContext.currentShop.purchasedFantasyIds.Contains(fantasy.id)
                || bootstrap.RunContext.fantasyInventory.Contains(fantasy.id);
        }

        public bool TryBuyFantasy(FantasyData fantasy, int price)
        {
            if (fantasy == null || bootstrap == null || bootstrap.RunContext == null)
                return false;

            if (IsFantasyPurchased(fantasy) || !TrySpendHealth(price))
                return false;

            bootstrap.RunContext.fantasyInventory.Add(fantasy);
            if (bootstrap.RunContext.currentShop == null)
                bootstrap.RunContext.currentShop = new ShopNumberState();
            if (!bootstrap.RunContext.currentShop.purchasedFantasyIds.Contains(fantasy.id))
                bootstrap.RunContext.currentShop.purchasedFantasyIds.Add(fantasy.id);

            fantasyEffectRunner.Apply(fantasy, bootstrap.RunContext, "On_Acquire");
            fantasyEffectRunner.Apply(fantasy, bootstrap.RunContext, "Acquire");
            return true;
        }

        private void OnStateChanged(GameState previous, GameState next)
        {
            if (next != GameState.Shop || bootstrap == null || bootstrap.RunContext == null)
                return;

            if (bootstrap.RunContext.currentShop == null)
                bootstrap.RunContext.currentShop = new ShopNumberState();

            if (bootstrap.RunContext.currentShop.shopEnterFantasyApplied)
                return;

            fantasyEffectRunner.ApplyTrigger(bootstrap.RunContext, "Shop_Enter");
            bootstrap.RunContext.currentShop.shopEnterFantasyApplied = true;
        }

        private FantasyData SelectFantasyForShop(string slotId, FantasyGrade grade)
        {
            FantasyData fallback = null;
            int seen = 0;

            for (int i = 0; i < fantasyDatabase.fantasies.Count; i++)
            {
                FantasyData fantasy = fantasyDatabase.fantasies[i];
                if (fantasy == null || fantasy.grade != grade)
                    continue;
                if (bootstrap.RunContext.fantasyInventory.Contains(fantasy.id))
                    continue;
                if (IsFantasyAlreadyOffered(fantasy.id))
                    continue;

                fallback ??= fantasy;
                seen++;
                int pick = bootstrap.RunContext.RollValue($"shop.fantasy.{slotId}.{seen}", 0, seen - 1);
                if (pick == 0)
                    fallback = fantasy;
            }

            return fallback;
        }

        private bool HasStickyGlove()
        {
            if (bootstrap == null || bootstrap.RunContext == null || bootstrap.RunContext.fantasyInventory == null)
                return false;

            return bootstrap.RunContext.fantasyInventory.Contains("fan_shop_stickyglove");
        }

        private bool IsFantasyAlreadyOffered(string fantasyId)
        {
            if (bootstrap == null || bootstrap.RunContext == null || bootstrap.RunContext.currentShop == null)
                return false;

            foreach (string offeredId in bootstrap.RunContext.currentShop.fantasyIds.Values)
            {
                if (offeredId == fantasyId)
                    return true;
            }

            return false;
        }

        private FantasyData FindFantasy(string fantasyId)
        {
            if (fantasyDatabase == null || string.IsNullOrWhiteSpace(fantasyId))
                return null;

            for (int i = 0; i < fantasyDatabase.fantasies.Count; i++)
            {
                FantasyData fantasy = fantasyDatabase.fantasies[i];
                if (fantasy != null && fantasy.id == fantasyId)
                    return fantasy;
            }

            return null;
        }
    }
}
