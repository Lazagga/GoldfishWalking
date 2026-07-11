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
            MonsterData forcedMonster = FindForcedMonster(database, runContext);
            if (forcedMonster != null)
                return forcedMonster;

            if (act == 1 && grade == MonsterGrade.Normal && runContext != null)
            {
                if (runContext.roomIndex == 0)
                {
                    MonsterData fairy = database.monsters.Find(monster =>
                        monster != null
                        && monster.act == 1
                        && monster.grade == MonsterGrade.Normal
                        && (monster.dataName == "Mob_10101_Fairy" || monster.devName == "요정"));
                    if (fairy != null)
                        return fairy;
                }

                if (runContext.roomIndex == 1 || runContext.roomIndex == 2)
                {
                    List<MonsterData> easyCandidates = database.monsters.FindAll(monster =>
                        monster != null
                        && monster.act == 1
                        && monster.grade == MonsterGrade.Normal
                        && monster.difficulty == MonsterDifficulty.Easy);
                    if (easyCandidates.Count > 0)
                    {
                        int easyIndex = runContext.RollValue($"monster.select.act1.easy.floor.{runContext.roomIndex}", 0, easyCandidates.Count - 1);
                        return easyCandidates[easyIndex];
                    }
                }
            }

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

        private static MonsterData FindForcedMonster(MonsterDatabase database, RunContext runContext)
        {
            if (database == null || database.monsters == null || runContext == null || string.IsNullOrWhiteSpace(runContext.debugForcedMonsterId))
                return null;

            string lookup = runContext.debugForcedMonsterId.Trim();
            MonsterData found = database.monsters.Find(monster =>
                monster != null
                && (Matches(monster.id, lookup)
                    || Matches(monster.dataName, lookup)
                    || Matches(monster.devName, lookup)
                    || Matches(monster.displayName, lookup)));

            if (found != null)
                runContext.debugForcedMonsterId = string.Empty;

            return found;
        }

        private static bool Matches(string value, string lookup)
        {
            return !string.IsNullOrWhiteSpace(value)
                && string.Equals(value.Trim(), lookup, System.StringComparison.OrdinalIgnoreCase);
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
