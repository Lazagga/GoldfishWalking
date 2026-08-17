using System;
using System.Collections.Generic;
using GoldfishWalking.Data;
using GoldfishWalking.Item;

namespace GoldfishWalking.Core
{
    [Serializable]
    public sealed class BattleSessionState
    {
        public int lastDamageDealt;
        public int previousDamageDealt;
        public bool hasPreviousDamageDealt;
        public int lastDamageTaken;
        public int incomingDamageAmount;
        public int enemyStrengthGainAmount;
        public int consecutiveDigitRunCount;
        public bool enemyActsFirst;
        public bool battleRewindUsed;
        public int battleStartHealth;
        public List<RuntimeCounter> fantasyCounters = new List<RuntimeCounter>();
        public int totalDamageDealt;
        public int totalDamageTaken;
        public int pendingMonsterDamage;
        public List<string> damageDebugLines = new List<string>();
        public int playerBleed;
        public int playerPoison;
        public int pendingPlayerBleed;
        public int pendingPlayerPoison;
        public int prophecyStack;
        public int turnNumber;
        public int moveLimit;
        public int remainingMoves;
        public int temporaryMoveBonus;
        public int sagittariusWholeBoxEraseTurn;
        public int itemUseCount;
        public int committedExtraMatches;
        public int committedErasers;
        public int committedTemporaryExtraMatches;
        public int committedTemporaryErasers;
        public ItemType lastAcquiredItemType;
        public int lastAcquiredItemCount;
        public ItemType lastUsedItemType;
        public List<TimedStrengthModifier> timedPlayerStrengthModifiers = new List<TimedStrengthModifier>();
        public List<TimedStrengthModifier> pendingEnemyStrengthModifiers = new List<TimedStrengthModifier>();

        public void Clear(ItemInventory inventory)
        {
            lastDamageDealt = 0;
            previousDamageDealt = 0;
            hasPreviousDamageDealt = false;
            lastDamageTaken = 0;
            incomingDamageAmount = 0;
            enemyStrengthGainAmount = 0;
            consecutiveDigitRunCount = 0;
            enemyActsFirst = false;
            battleRewindUsed = false;
            battleStartHealth = 0;
            fantasyCounters.Clear();
            totalDamageDealt = 0;
            totalDamageTaken = 0;
            pendingMonsterDamage = 0;
            damageDebugLines.Clear();
            playerBleed = 0;
            playerPoison = 0;
            pendingPlayerBleed = 0;
            pendingPlayerPoison = 0;
            prophecyStack = 0;
            turnNumber = 0;
            moveLimit = 0;
            remainingMoves = 0;
            temporaryMoveBonus = 0;
            sagittariusWholeBoxEraseTurn = 0;
            itemUseCount = 0;
            committedExtraMatches = 0;
            committedErasers = 0;
            committedTemporaryExtraMatches = 0;
            committedTemporaryErasers = 0;
            lastAcquiredItemCount = 0;
            timedPlayerStrengthModifiers.Clear();
            pendingEnemyStrengthModifiers.Clear();
            inventory?.ClearTemporary();
        }

        public int GetCounter(string key)
        {
            RuntimeCounter counter = fantasyCounters.Find(item => item != null && string.Equals(item.key, key, StringComparison.OrdinalIgnoreCase));
            return counter != null ? counter.value : 0;
        }

        public void SetCounter(string key, int value)
        {
            RuntimeCounter counter = fantasyCounters.Find(item => item != null && string.Equals(item.key, key, StringComparison.OrdinalIgnoreCase));
            if (counter == null)
            {
                counter = new RuntimeCounter { key = key };
                fantasyCounters.Add(counter);
            }
            counter.value = value;
        }
    }

    [Serializable]
    public sealed class RuntimeCounter
    {
        public string key;
        public int value;
    }

    [Serializable]
    public sealed class RewardSessionState
    {
        public int rerolls;
        public int choiceRollIndex;

        public void Clear()
        {
            rerolls = 0;
            choiceRollIndex = 0;
        }
    }
}
