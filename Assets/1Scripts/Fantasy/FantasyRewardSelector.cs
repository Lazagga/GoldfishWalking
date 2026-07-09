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
            List<FantasyData> rewards = new List<FantasyData>();
            if (database == null || database.fantasies == null || count <= 0)
                return rewards;

            FantasyGrade? preferredGrade = GetPreferredGrade(runContext);
            List<FantasyData> primaryCandidates = new List<FantasyData>();
            List<FantasyData> fallbackCandidates = new List<FantasyData>();

            foreach (FantasyData fantasy in database.fantasies)
            {
                if (fantasy == null)
                    continue;

                if (inventory != null && inventory.Contains(fantasy.id))
                    continue;

                if (preferredGrade.HasValue && fantasy.grade == preferredGrade.Value)
                    primaryCandidates.Add(fantasy);
                else
                    fallbackCandidates.Add(fantasy);
            }

            Random random = CreateRewardRandom(runContext);
            Shuffle(primaryCandidates, random);
            Shuffle(fallbackCandidates, random);

            AddUpTo(rewards, primaryCandidates, count);
            AddUpTo(rewards, fallbackCandidates, count);
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
                ? runContext.RollValue("reward.fantasy.choices", 0, int.MaxValue - 1)
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
