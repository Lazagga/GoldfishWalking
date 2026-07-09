using System;
using GoldfishWalking.Data;
using GoldfishWalking.Fantasy;
using GoldfishWalking.Item;
using GoldfishWalking.Map;

namespace GoldfishWalking.Core
{
    [Serializable]
    public sealed class RunContext
    {
        public int seed;
        public int act = 1;
        public int roomIndex;
        public int health = 150;
        public int strength;
        public RunMap map;
        public MapNode currentNode;
        public ItemInventory itemInventory = new ItemInventory();
        public FantasyInventory fantasyInventory = new FantasyInventory();
        public BattleNumberState currentBattle;
        public RestNumberState currentRest;
        public ShopNumberState currentShop = new ShopNumberState();
        public int lastDamageDealt;
        public int lastDamageTaken;
        public int battleDamageDealt;
        public int battleDamageTaken;
        public int pendingMonsterDamage;
        public int battleTurnNumber;
        public int remainingMoveCount;
        public int temporaryMoveBonus;
        public int passiveAttackCountBonus;
        public int itemUseCountThisBattle;
        public ItemType lastAcquiredItemType;
        public int lastAcquiredItemCount;
        public ItemType lastUsedItemType;
        public int lastShopPurchaseCost;

        public void StartNewRun(int newSeed, int startingHealth)
        {
            seed = newSeed;
            act = 1;
            roomIndex = 0;
            health = startingHealth;
            strength = 0;
            map = null;
            currentNode = null;
            currentBattle = null;
            currentRest = null;
            currentShop.Clear();
            itemInventory.Clear();
            fantasyInventory.Clear();
            passiveAttackCountBonus = 0;
            ClearBattleRuntimeValues();
        }

        public void StartNextAct(RunMap nextMap)
        {
            act += 1;
            roomIndex = 0;
            map = nextMap;
            currentNode = null;
            currentBattle = null;
            currentRest = null;
            currentShop.Clear();
            ClearBattleRuntimeValues();
        }

        public void AdvanceTo(MapNode node)
        {
            if (map != null && currentNode != null)
                map.MarkCompleted(currentNode);

            currentNode = node;
            roomIndex = node != null ? node.roomIndex : roomIndex;
            currentBattle = null;
            currentRest = null;
            currentShop.Clear();
            ClearBattleRuntimeValues();
        }

        public void ClearBattleRuntimeValues()
        {
            lastDamageDealt = 0;
            lastDamageTaken = 0;
            battleDamageDealt = 0;
            battleDamageTaken = 0;
            pendingMonsterDamage = 0;
            battleTurnNumber = 0;
            remainingMoveCount = 0;
            temporaryMoveBonus = 0;
            itemUseCountThisBattle = 0;
            lastAcquiredItemCount = 0;
            lastShopPurchaseCost = 0;
        }

        public BattleNumberState EnsureBattleNumbers(int monsterHitCount)
        {
            if (currentBattle != null)
                return currentBattle;

            currentBattle = new BattleNumberState
            {
                playerBaseDamage = Roll("battle.player.base_damage", 10, 99),
                playerBaseDamageDigitCount = 2,
                monsterBaseDamage = Roll("battle.monster.base_damage", 10, 99),
                monsterHitCount = Math.Max(1, monsterHitCount)
            };

            return currentBattle;
        }

        public RestNumberState EnsureRestNumbers()
        {
            if (currentRest != null)
                return currentRest;

            currentRest = new RestNumberState
            {
                healAmount = Roll("rest.heal_amount", 20, 99)
            };

            return currentRest;
        }

        public int EnsureShopPrice(string itemId, int minInclusive, int maxInclusive)
        {
            if (currentShop == null)
                currentShop = new ShopNumberState();

            if (currentShop.prices.TryGetValue(itemId, out int price))
                return price;

            price = Roll($"shop.price.{itemId}", minInclusive, maxInclusive);
            currentShop.prices[itemId] = price;
            return price;
        }

        public void SetShopPrice(string itemId, int price)
        {
            if (currentShop == null)
                currentShop = new ShopNumberState();

            currentShop.prices[itemId] = Math.Max(0, price);
        }

        public int RollValue(string purposeKey, int minInclusive, int maxInclusive)
        {
            return DeterministicValue.Range(
                seed,
                act,
                roomIndex,
                currentNode != null ? currentNode.id : string.Empty,
                purposeKey,
                minInclusive,
                maxInclusive);
        }

        private int Roll(string purposeKey, int minInclusive, int maxInclusive)
        {
            return RollValue(purposeKey, minInclusive, maxInclusive);
        }
    }
}
