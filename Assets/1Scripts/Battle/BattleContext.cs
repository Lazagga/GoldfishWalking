using GoldfishWalking.Core;
using GoldfishWalking.Data;
using GoldfishWalking.Formula;
using GoldfishWalking.Map;

namespace GoldfishWalking.Battle
{
    public sealed class BattleContext
    {
        public RunContext run;
        public MapNode sourceNode;
        public MonsterRuntime monster;
        public MonsterPatternData monsterPattern;
        public BattleFormulaState playerFormula = new BattleFormulaState();
        public BattleFormulaState monsterFormula = new BattleFormulaState();
        public BattleState state = BattleState.NotStarted;
    }
}
