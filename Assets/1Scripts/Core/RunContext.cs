using System;
using System.Collections.Generic;
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
        public List<string> battleDamageDebugLines = new List<string>();
        public int playerBleed;
        public int playerPoison;
        public int pendingPlayerBleed;
        public int pendingPlayerPoison;
        public int prophecyStack;
        public int battleTurnNumber;
        public int currentTurnMoveLimit;
        public int remainingMoveCount;
        public int temporaryMoveBonus;
        public int passiveAttackCountBonus;

        public int sagittariusWholeBoxEraseTurn;
        public int itemUseCountThisBattle;
        public int committedBattleEditExtraMatches;
        public int committedBattleEditErasers;
        public int committedBattleEditTemporaryExtraMatches;
        public int committedBattleEditTemporaryErasers;
        public ItemType lastAcquiredItemType;
        public int lastAcquiredItemCount;
        public ItemType lastUsedItemType;
        public int lastShopPurchaseCost;
        public int stampCouponHealthSpent;
        public int rewardRerolls;
        public int rewardChoiceRollIndex;
        public string debugForcedMonsterId;
        public List<TimedStrengthModifier> timedPlayerStrengthModifiers = new List<TimedStrengthModifier>();
        public List<TimedStrengthModifier> pendingEnemyStrengthModifiers = new List<TimedStrengthModifier>();

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
            stampCouponHealthSpent = 0;
            debugForcedMonsterId = string.Empty;
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
            battleDamageDebugLines.Clear();
            playerBleed = 0;
            playerPoison = 0;
            pendingPlayerBleed = 0;
            pendingPlayerPoison = 0;
            prophecyStack = 0;
            battleTurnNumber = 0;
            currentTurnMoveLimit = 0;
            remainingMoveCount = 0;
            temporaryMoveBonus = 0;

            sagittariusWholeBoxEraseTurn = 0;
            itemUseCountThisBattle = 0;
            committedBattleEditExtraMatches = 0;
            committedBattleEditErasers = 0;
            committedBattleEditTemporaryExtraMatches = 0;
            committedBattleEditTemporaryErasers = 0;
            lastAcquiredItemCount = 0;
            lastShopPurchaseCost = 0;
            rewardRerolls = 0;
            rewardChoiceRollIndex = 0;
            timedPlayerStrengthModifiers.Clear();
            pendingEnemyStrengthModifiers.Clear();
            itemInventory.ClearTemporary();
        }

        public void AddTimedPlayerStrength(int amount, int duration)
        {
            if (amount == 0 || duration <= 0)
                return;

            timedPlayerStrengthModifiers.Add(new TimedStrengthModifier
            {
                amount = amount,
                remainingTurns = duration
            });
        }

        public void QueueEnemyStrengthModifier(int amount, int duration)
        {
            if (amount == 0)
                return;

            pendingEnemyStrengthModifiers.Add(new TimedStrengthModifier
            {
                amount = amount,
                remainingTurns = Math.Max(0, duration)
            });
        }

        public void AddBattleDamageDebug(string source, int amount)
        {
            if (amount == 0)
                return;

            battleDamageDebugLines.Add($"{source}: {amount}");
            if (battleDamageDebugLines.Count > 8)
                battleDamageDebugLines.RemoveAt(0);
        }

        public void AddPlayerDamageDebug(string source, int amount)
        {
            if (amount <= 0)
                return;

            AddBattleDamageDebug($"<color=#FF5555>{source}", amount);
            int lastIndex = battleDamageDebugLines.Count - 1;
            if (lastIndex >= 0)
                battleDamageDebugLines[lastIndex] += "</color>";
        }

        public void RegisterBattleEditItemSpend(ItemType itemType, int permanentCount, int temporaryCount)
        {
            if (itemType == ItemType.ExtraMatch)
            {
                committedBattleEditExtraMatches += Math.Max(0, permanentCount);
                committedBattleEditTemporaryExtraMatches += Math.Max(0, temporaryCount);
            }
            else if (itemType == ItemType.Eraser)
            {
                committedBattleEditErasers += Math.Max(0, permanentCount);
                committedBattleEditTemporaryErasers += Math.Max(0, temporaryCount);
            }
        }

        public void RefundCommittedBattleEditItems()
        {
            if (committedBattleEditExtraMatches > 0)
                itemInventory.Add(ItemType.ExtraMatch, committedBattleEditExtraMatches);
            if (committedBattleEditErasers > 0)
                itemInventory.Add(ItemType.Eraser, committedBattleEditErasers);
            if (committedBattleEditTemporaryExtraMatches > 0)
                itemInventory.AddTemporary(ItemType.ExtraMatch, committedBattleEditTemporaryExtraMatches);
            if (committedBattleEditTemporaryErasers > 0)
                itemInventory.AddTemporary(ItemType.Eraser, committedBattleEditTemporaryErasers);

            committedBattleEditExtraMatches = 0;
            committedBattleEditErasers = 0;
            committedBattleEditTemporaryExtraMatches = 0;
            committedBattleEditTemporaryErasers = 0;
        }

        public void ClearCommittedBattleEditItems()
        {
            committedBattleEditExtraMatches = 0;
            committedBattleEditErasers = 0;
            committedBattleEditTemporaryExtraMatches = 0;
            committedBattleEditTemporaryErasers = 0;
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

    [Serializable]
    public sealed class TimedStrengthModifier
    {
        public int amount;
        public int remainingTurns;
    }
}
