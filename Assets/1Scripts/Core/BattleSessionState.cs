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
        public int lastDamageTaken;
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
            lastDamageTaken = 0;
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
