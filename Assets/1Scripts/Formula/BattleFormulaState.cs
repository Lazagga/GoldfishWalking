using System;

namespace GoldfishWalking.Formula
{
    [Serializable]
    public sealed class BattleFormulaState
    {
        public FormulaState damageExpression = new FormulaState();
        public FormulaState hitCountExpression = new FormulaState();
    }
}