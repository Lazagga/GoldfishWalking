using System.Collections.Generic;
using GoldfishWalking.Core;
using GoldfishWalking.Data;
using GoldfishWalking.Map;

namespace GoldfishWalking.Battle
{
    public sealed class MonsterSelector
    {
        public MonsterData Select(MonsterDatabase database, RunContext runContext, MapNodeType nodeType)
        {
            if (database == null || database.monsters == null || database.monsters.Count == 0)
                return null;

            MonsterGrade grade = ToMonsterGrade(nodeType);
            int act = runContext != null ? runContext.act : 1;
            List<MonsterData> candidates = database.monsters.FindAll(monster =>
                monster != null && monster.act == act && monster.grade == grade);

            if (candidates.Count == 0)
                candidates = database.monsters.FindAll(monster => monster != null && monster.act == act);

            if (candidates.Count == 0)
                return null;

            int index = runContext != null
                ? runContext.RollValue($"monster.select.{grade}", 0, candidates.Count - 1)
                : 0;
            return candidates[index];
        }

        private static MonsterGrade ToMonsterGrade(MapNodeType nodeType)
        {
            switch (nodeType)
            {
                case MapNodeType.EliteBattle:
                    return MonsterGrade.Elite;
                case MapNodeType.Boss:
                    return MonsterGrade.Boss;
                default:
                    return MonsterGrade.Normal;
            }
        }
    }
}
