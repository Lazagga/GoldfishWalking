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
        public string playerBaseDamageSegmentState;
        public string monsterBaseDamageSegmentState;
        public string monsterHitCountSegmentState;
        public string monsterId;
        public string activeMonsterPatternId;
        public int activeMonsterPatternTurn;
        public int editSnapshotTurn;
        public int editSnapshotPlayerBaseDamage;
        public int editSnapshotMonsterBaseDamage;
        public int editSnapshotMonsterHitCount;
        public string editSnapshotPlayerBaseDamageSegmentState;
        public string editSnapshotMonsterBaseDamageSegmentState;
        public string editSnapshotMonsterHitCountSegmentState;
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
            editSnapshotPlayerBaseDamageSegmentState = playerBaseDamageSegmentState;
            editSnapshotMonsterBaseDamageSegmentState = monsterBaseDamageSegmentState;
            editSnapshotMonsterHitCountSegmentState = monsterHitCountSegmentState;
        }

        public void RestoreEditSnapshot()
        {
            playerBaseDamage = editSnapshotPlayerBaseDamage;
            monsterBaseDamage = editSnapshotMonsterBaseDamage;
            monsterHitCount = editSnapshotMonsterHitCount;
            playerBaseDamageSegmentState = editSnapshotPlayerBaseDamageSegmentState;
            monsterBaseDamageSegmentState = editSnapshotMonsterBaseDamageSegmentState;
            monsterHitCountSegmentState = editSnapshotMonsterHitCountSegmentState;
        }
    }

    [Serializable]
    public sealed class RestNumberState
    {
        public int healAmount;
    }

    [Serializable]
    public sealed class ShopNumberState
    {
        public Dictionary<string, int> prices = new Dictionary<string, int>();
        public Dictionary<string, string> fantasyIds = new Dictionary<string, string>();
        public List<string> purchasedFantasyIds = new List<string>();
        public List<string> freePurchasedItemIds = new List<string>();
        public bool shopEnterFantasyApplied;

        public void Clear()
        {
            prices.Clear();
            fantasyIds.Clear();
            purchasedFantasyIds.Clear();
            freePurchasedItemIds.Clear();
            shopEnterFantasyApplied = false;
        }
    }
}
