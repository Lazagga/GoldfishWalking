using System;
using System.Collections.Generic;
using GoldfishWalking.Core;
using GoldfishWalking.Data;
using GoldfishWalking.Map;

namespace GoldfishWalking.Fantasy
{
    public sealed class FantasyRewardSelector
    {
        public List<FantasyData> SelectRewards(FantasyDatabase database, FantasyInventory inventory, int count)
        {
            return SelectRewards(database, inventory, count, null);
        }

        public List<FantasyData> SelectRewards(FantasyDatabase database, FantasyInventory inventory, int count, RunContext runContext)
        {
            return SelectRewards(database, inventory, count, runContext, null);
        }

        public List<FantasyData> SelectRewards(
            FantasyDatabase database,
            FantasyInventory inventory,
            int count,
            RunContext runContext,
            ISet<string> excludedFantasyIds)
        {
            List<FantasyData> rewards = new List<FantasyData>();
            if (database == null || database.fantasies == null || count <= 0)
                return rewards;

            FantasyGrade? preferredGrade = GetPreferredGrade(runContext);
            List<FantasyData> primaryCandidates = new List<FantasyData>();
            List<FantasyData> fallbackCandidates = new List<FantasyData>();
            List<FantasyData> excludedPrimaryCandidates = new List<FantasyData>();
            List<FantasyData> excludedFallbackCandidates = new List<FantasyData>();

            foreach (FantasyData fantasy in database.fantasies)
            {
                if (fantasy == null)
                    continue;
                if (!FantasyCollectionRules.CanAppearInRewardOrShop(fantasy))
                    continue;

                if (inventory != null && inventory.Contains(fantasy.id))
                    continue;

                bool preferred = preferredGrade.HasValue && fantasy.grade == preferredGrade.Value;
                bool excluded = excludedFantasyIds != null && excludedFantasyIds.Contains(fantasy.id);
                if (excluded && preferred)
                    excludedPrimaryCandidates.Add(fantasy);
                else if (excluded)
                    excludedFallbackCandidates.Add(fantasy);
                else if (preferred)
                    primaryCandidates.Add(fantasy);
                else
                    fallbackCandidates.Add(fantasy);
            }

            Random random = CreateRewardRandom(runContext);
            Shuffle(primaryCandidates, random);
            Shuffle(fallbackCandidates, random);
            Shuffle(excludedPrimaryCandidates, random);
            Shuffle(excludedFallbackCandidates, random);

            AddUpTo(rewards, primaryCandidates, count);
            AddUpTo(rewards, fallbackCandidates, count);
            AddUpTo(rewards, excludedPrimaryCandidates, count);
            AddUpTo(rewards, excludedFallbackCandidates, count);
            return rewards;
        }

        private static FantasyGrade? GetPreferredGrade(RunContext runContext)
        {
            if (runContext == null || runContext.currentNode == null)
                return null;

            switch (runContext.currentNode.nodeType)
            {
                case MapNodeType.EliteBattle:
                    return FantasyGrade.Blue;
                case MapNodeType.Boss:
                    return FantasyGrade.Red;
                case MapNodeType.NormalBattle:
                    return FantasyGrade.White;
                default:
                    return null;
            }
        }

        private static Random CreateRewardRandom(RunContext runContext)
        {
            int seed = runContext != null
                ? runContext.RollValue($"reward.fantasy.choices.{runContext.rewardChoiceRollIndex}", 0, int.MaxValue - 1)
                : Environment.TickCount;

            return new Random(seed);
        }

        private static void Shuffle(List<FantasyData> fantasies, Random random)
        {
            for (int i = fantasies.Count - 1; i > 0; i--)
            {
                int swapIndex = random.Next(i + 1);
                FantasyData temp = fantasies[i];
                fantasies[i] = fantasies[swapIndex];
                fantasies[swapIndex] = temp;
            }
        }

        private static void AddUpTo(List<FantasyData> rewards, List<FantasyData> candidates, int count)
        {
            for (int i = 0; i < candidates.Count && rewards.Count < count; i++)
                rewards.Add(candidates[i]);
        }
    }
}
