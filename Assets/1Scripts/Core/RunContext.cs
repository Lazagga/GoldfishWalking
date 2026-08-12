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
        public BattleSessionState battleSession = new BattleSessionState();
        public RewardSessionState rewardSession = new RewardSessionState();
        public int passiveAttackCountBonus;
        public int lastShopPurchaseCost;
        public int stampCouponHealthSpent;
        public string debugForcedMonsterId;

        // Compatibility surface while callers migrate to battleSession/rewardSession.
        public int lastDamageDealt { get => battleSession.lastDamageDealt; set => battleSession.lastDamageDealt = value; }
        public int lastDamageTaken { get => battleSession.lastDamageTaken; set => battleSession.lastDamageTaken = value; }
        public int battleDamageDealt { get => battleSession.totalDamageDealt; set => battleSession.totalDamageDealt = value; }
        public int battleDamageTaken { get => battleSession.totalDamageTaken; set => battleSession.totalDamageTaken = value; }
        public int pendingMonsterDamage { get => battleSession.pendingMonsterDamage; set => battleSession.pendingMonsterDamage = value; }
        public List<string> battleDamageDebugLines => battleSession.damageDebugLines;
        public int playerBleed { get => battleSession.playerBleed; set => battleSession.playerBleed = value; }
        public int playerPoison { get => battleSession.playerPoison; set => battleSession.playerPoison = value; }
        public int pendingPlayerBleed { get => battleSession.pendingPlayerBleed; set => battleSession.pendingPlayerBleed = value; }
        public int pendingPlayerPoison { get => battleSession.pendingPlayerPoison; set => battleSession.pendingPlayerPoison = value; }
        public int prophecyStack { get => battleSession.prophecyStack; set => battleSession.prophecyStack = value; }
        public int battleTurnNumber { get => battleSession.turnNumber; set => battleSession.turnNumber = value; }
        public int currentTurnMoveLimit { get => battleSession.moveLimit; set => battleSession.moveLimit = value; }
        public int remainingMoveCount { get => battleSession.remainingMoves; set => battleSession.remainingMoves = value; }
        public int temporaryMoveBonus { get => battleSession.temporaryMoveBonus; set => battleSession.temporaryMoveBonus = value; }
        public int sagittariusWholeBoxEraseTurn { get => battleSession.sagittariusWholeBoxEraseTurn; set => battleSession.sagittariusWholeBoxEraseTurn = value; }
        public int itemUseCountThisBattle { get => battleSession.itemUseCount; set => battleSession.itemUseCount = value; }
        public int committedBattleEditExtraMatches { get => battleSession.committedExtraMatches; set => battleSession.committedExtraMatches = value; }
        public int committedBattleEditErasers { get => battleSession.committedErasers; set => battleSession.committedErasers = value; }
        public int committedBattleEditTemporaryExtraMatches { get => battleSession.committedTemporaryExtraMatches; set => battleSession.committedTemporaryExtraMatches = value; }
        public int committedBattleEditTemporaryErasers { get => battleSession.committedTemporaryErasers; set => battleSession.committedTemporaryErasers = value; }
        public List<TimedStrengthModifier> timedPlayerStrengthModifiers => battleSession.timedPlayerStrengthModifiers;
        public List<TimedStrengthModifier> pendingEnemyStrengthModifiers => battleSession.pendingEnemyStrengthModifiers;

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
            battleSession.Clear(itemInventory);
            lastShopPurchaseCost = 0;
            rewardSession.Clear();
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
