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
        public int monsterBaseDamageDigitCount = 1;
        
        public int monsterHitCountDigitCount = 1;
public int monsterHitCount = 1;
        public bool monsterSpecialBoxVisible;
        public int monsterSpecialBoxValue;
        public int monsterSpecialBoxDigitCount;
        public string monsterSpecialBoxLabel;
        public bool monsterSpecialBoxEditable;
        public string playerBaseDamageSegmentState;
        public string monsterBaseDamageSegmentState;
        public string monsterHitCountSegmentState;
        public string playerDebuffOperator;
        public int playerDebuffValue = 1;
        public int playerDebuffDigitCount = 1;
        public int playerDebuffExpiresAfterTurn = -1;
        public int playerDebuffRollTurn;
        public string playerDebuffSegmentState;
        public string monsterSpecialBoxSegmentState;
        public string monsterId;
        public string activeMonsterPatternId;
        public int activeMonsterPatternTurn;
        public int editSnapshotTurn;
        public int editSnapshotPlayerBaseDamage;
        public int editSnapshotMonsterBaseDamage;
        public int editSnapshotMonsterBaseDamageDigitCount;
        public int editSnapshotMonsterHitCount;
        public int editSnapshotMonsterHitCountDigitCount;
        public bool editSnapshotMonsterSpecialBoxVisible;
        public int editSnapshotMonsterSpecialBoxValue;
        public int editSnapshotMonsterSpecialBoxDigitCount;
        public string editSnapshotMonsterSpecialBoxLabel;
        public bool editSnapshotMonsterSpecialBoxEditable;
        public string editSnapshotPlayerBaseDamageSegmentState;
        public string editSnapshotMonsterBaseDamageSegmentState;
        public string editSnapshotMonsterHitCountSegmentState;
        public int editSnapshotPlayerDebuffValue;
        public string editSnapshotPlayerDebuffSegmentState;
        
        public int editSnapshotPlayerAttackConditionCount;
        public string editSnapshotPlayerAttackConditionSegmentState;
public string editSnapshotMonsterSpecialBoxSegmentState;
        public Dictionary<string, int> playerTurnDamageValues = new Dictionary<string, int>();
        public Dictionary<string, int> monsterPatternDamageValues = new Dictionary<string, int>();
        public Dictionary<string, int> monsterPatternHitCountValues = new Dictionary<string, int>();
        public bool rewardItemsRolled;
        public bool rewardExtraMatch;
        public bool rewardEraser;
        public bool battleStartFantasyApplied;
        public int aimedShotValue;
        
        public int monsterDecoyTurn;
        public string monsterDecoyBox;
        public int monsterDecoyDigitIndex = -1;
        public int monsterActualDamageDigitCount;
        
        public int playerAttackConditionTurn;
        public string playerAttackConditionType;
        public string playerAttackConditionOperator;
        public int playerAttackConditionValue;
        public int playerAttackConditionCount;
        public string playerAttackConditionSegmentState;
public int monsterActualHitDigitCount;
public int aimedShotRollTurn;

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
            editSnapshotMonsterBaseDamageDigitCount = monsterBaseDamageDigitCount;
            editSnapshotMonsterHitCount = monsterHitCount;
            editSnapshotMonsterHitCountDigitCount = monsterHitCountDigitCount;
            editSnapshotMonsterSpecialBoxVisible = monsterSpecialBoxVisible;
            editSnapshotMonsterSpecialBoxValue = monsterSpecialBoxValue;
            editSnapshotMonsterSpecialBoxDigitCount = monsterSpecialBoxDigitCount;
            editSnapshotMonsterSpecialBoxLabel = monsterSpecialBoxLabel;
            editSnapshotMonsterSpecialBoxEditable = monsterSpecialBoxEditable;
            editSnapshotPlayerBaseDamageSegmentState = playerBaseDamageSegmentState;
            editSnapshotMonsterBaseDamageSegmentState = monsterBaseDamageSegmentState;
            editSnapshotMonsterHitCountSegmentState = monsterHitCountSegmentState;
            editSnapshotPlayerDebuffValue = playerDebuffValue;
            editSnapshotPlayerDebuffSegmentState = playerDebuffSegmentState;
            
            editSnapshotPlayerAttackConditionCount = playerAttackConditionCount;
            editSnapshotPlayerAttackConditionSegmentState = playerAttackConditionSegmentState;
editSnapshotMonsterSpecialBoxSegmentState = monsterSpecialBoxSegmentState;
        }

        public void RestoreEditSnapshot()
        {
            playerBaseDamage = editSnapshotPlayerBaseDamage;
            monsterBaseDamage = editSnapshotMonsterBaseDamage;
            monsterBaseDamageDigitCount = editSnapshotMonsterBaseDamageDigitCount;
            monsterHitCount = editSnapshotMonsterHitCount;
            monsterHitCountDigitCount = editSnapshotMonsterHitCountDigitCount;
            monsterSpecialBoxVisible = editSnapshotMonsterSpecialBoxVisible;
            monsterSpecialBoxValue = editSnapshotMonsterSpecialBoxValue;
            monsterSpecialBoxDigitCount = editSnapshotMonsterSpecialBoxDigitCount;
            monsterSpecialBoxLabel = editSnapshotMonsterSpecialBoxLabel;
            monsterSpecialBoxEditable = editSnapshotMonsterSpecialBoxEditable;
            playerBaseDamageSegmentState = editSnapshotPlayerBaseDamageSegmentState;
            monsterBaseDamageSegmentState = editSnapshotMonsterBaseDamageSegmentState;
            monsterHitCountSegmentState = editSnapshotMonsterHitCountSegmentState;
            playerDebuffValue = editSnapshotPlayerDebuffValue;
            playerDebuffSegmentState = editSnapshotPlayerDebuffSegmentState;
            
            playerAttackConditionCount = editSnapshotPlayerAttackConditionCount;
            playerAttackConditionSegmentState = editSnapshotPlayerAttackConditionSegmentState;
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
        public int priceMovesConsumed;
        public bool shopEnterFantasyApplied;

        public void Clear()
        {
            prices.Clear();
            priceRollCounts.Clear();
            fantasyIds.Clear();
            purchasedFantasyIds.Clear();
            freePurchasedItemIds.Clear();
            priceMovesConsumed = 0;
            shopEnterFantasyApplied = false;
        }
    }
}
