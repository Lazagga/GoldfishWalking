using System;
using System.Collections.Generic;

namespace GoldfishWalking.Core
{
    [Serializable]
    public sealed class BattleNumberState
    {
        public int playerBaseDamage;
        public int playerBaseDamageDigitCount = 2;
        public int playerBaseDamageTurn;
        public int monsterBaseDamage;
        public int monsterHitCount = 1;
        public bool monsterSpecialBoxVisible;
        public int monsterSpecialBoxValue;
        public int monsterSpecialBoxDigitCount;
        public string monsterSpecialBoxLabel;
        public string playerBaseDamageSegmentState;
        public string monsterBaseDamageSegmentState;
        public string monsterHitCountSegmentState;
        public string monsterSpecialBoxSegmentState;
        public string monsterId;
        public string activeMonsterPatternId;
        public int activeMonsterPatternTurn;
        public int editSnapshotTurn;
        public int editSnapshotPlayerBaseDamage;
        public int editSnapshotMonsterBaseDamage;
        public int editSnapshotMonsterHitCount;
        public bool editSnapshotMonsterSpecialBoxVisible;
        public int editSnapshotMonsterSpecialBoxValue;
        public int editSnapshotMonsterSpecialBoxDigitCount;
        public string editSnapshotMonsterSpecialBoxLabel;
        public string editSnapshotPlayerBaseDamageSegmentState;
        public string editSnapshotMonsterBaseDamageSegmentState;
        public string editSnapshotMonsterHitCountSegmentState;
        public string editSnapshotMonsterSpecialBoxSegmentState;
        public Dictionary<string, int> playerTurnDamageValues = new Dictionary<string, int>();
        public Dictionary<string, int> monsterPatternDamageValues = new Dictionary<string, int>();
        public Dictionary<string, int> monsterPatternHitCountValues = new Dictionary<string, int>();
        public bool battleStartFantasyApplied;

        public int EnsurePlayerTurnDamage(string key, Func<int> roll)
        {
            if (playerTurnDamageValues.TryGetValue(key, out int value))
                return value;

            value = roll != null ? roll() : playerBaseDamage;
            playerTurnDamageValues[key] = value;
            return value;
        }

        public int EnsureMonsterPatternDamage(string key, Func<int> roll)
        {
            if (monsterPatternDamageValues.TryGetValue(key, out int value))
                return value;

            value = roll != null ? roll() : monsterBaseDamage;
            monsterPatternDamageValues[key] = value;
            return value;
        }

        public int EnsureMonsterPatternHitCount(string key, Func<int> roll)
        {
            if (monsterPatternHitCountValues.TryGetValue(key, out int value))
                return value;

            value = roll != null ? roll() : monsterHitCount;
            monsterPatternHitCountValues[key] = Math.Max(1, value);
            return monsterPatternHitCountValues[key];
        }

        public void CaptureEditSnapshot(int turnNumber)
        {
            editSnapshotTurn = Math.Max(1, turnNumber);
            editSnapshotPlayerBaseDamage = playerBaseDamage;
            editSnapshotMonsterBaseDamage = monsterBaseDamage;
            editSnapshotMonsterHitCount = monsterHitCount;
            editSnapshotMonsterSpecialBoxVisible = monsterSpecialBoxVisible;
            editSnapshotMonsterSpecialBoxValue = monsterSpecialBoxValue;
            editSnapshotMonsterSpecialBoxDigitCount = monsterSpecialBoxDigitCount;
            editSnapshotMonsterSpecialBoxLabel = monsterSpecialBoxLabel;
            editSnapshotPlayerBaseDamageSegmentState = playerBaseDamageSegmentState;
            editSnapshotMonsterBaseDamageSegmentState = monsterBaseDamageSegmentState;
            editSnapshotMonsterHitCountSegmentState = monsterHitCountSegmentState;
            editSnapshotMonsterSpecialBoxSegmentState = monsterSpecialBoxSegmentState;
        }

        public void RestoreEditSnapshot()
        {
            playerBaseDamage = editSnapshotPlayerBaseDamage;
            monsterBaseDamage = editSnapshotMonsterBaseDamage;
            monsterHitCount = editSnapshotMonsterHitCount;
            monsterSpecialBoxVisible = editSnapshotMonsterSpecialBoxVisible;
            monsterSpecialBoxValue = editSnapshotMonsterSpecialBoxValue;
            monsterSpecialBoxDigitCount = editSnapshotMonsterSpecialBoxDigitCount;
            monsterSpecialBoxLabel = editSnapshotMonsterSpecialBoxLabel;
            playerBaseDamageSegmentState = editSnapshotPlayerBaseDamageSegmentState;
            monsterBaseDamageSegmentState = editSnapshotMonsterBaseDamageSegmentState;
            monsterHitCountSegmentState = editSnapshotMonsterHitCountSegmentState;
            monsterSpecialBoxSegmentState = editSnapshotMonsterSpecialBoxSegmentState;
        }
    }

    [Serializable]
    public sealed class RestNumberState
    {
        public int healAmount;
        public int healDigitCount = 2;
    }

    [Serializable]
    public sealed class ShopNumberState
    {
        public Dictionary<string, int> prices = new Dictionary<string, int>();
        public Dictionary<string, int> priceRollCounts = new Dictionary<string, int>();
        public Dictionary<string, string> fantasyIds = new Dictionary<string, string>();
        public List<string> purchasedFantasyIds = new List<string>();
        public List<string> freePurchasedItemIds = new List<string>();
        public bool shopEnterFantasyApplied;

        public void Clear()
        {
            prices.Clear();
            priceRollCounts.Clear();
            fantasyIds.Clear();
            purchasedFantasyIds.Clear();
            freePurchasedItemIds.Clear();
            shopEnterFantasyApplied = false;
        }
    }
}
