using GoldfishWalking.Formula;

namespace GoldfishWalking.Battle
{
    public sealed class FormulaStructuralEffectExecutor
    {
        public void SetSplit(string target, BattleFormulaState playerFormula, BattleFormulaState monsterFormula)
        {
            ApplyToNumberBoxes(SelectFormula(target, playerFormula, monsterFormula), box => box.split = true);
        }

        public void SetLocked(string target, BattleFormulaState playerFormula, BattleFormulaState monsterFormula)
        {
            ApplyToNumberBoxes(SelectFormula(target, playerFormula, monsterFormula), box => box.locked = true);
        }

        public void LockLeadingDigits(string target, BattleFormulaState playerFormula, BattleFormulaState monsterFormula, int digitCount)
        {
            BattleFormulaState formula = SelectFormula(target, playerFormula, monsterFormula);
            if (formula?.damageExpression?.boxes == null)
                return;

            foreach (FormulaBox box in formula.damageExpression.boxes)
            {
                if (box == null || box.boxType != FormulaBoxType.Number)
                    continue;
                box.split = true;
                box.lockedDigitCount = System.Math.Max(box.lockedDigitCount, System.Math.Max(1, digitCount));
                return;
            }
        }

        private static BattleFormulaState SelectFormula(string target, BattleFormulaState playerFormula, BattleFormulaState monsterFormula)
        {
            return string.Equals(target, "self", System.StringComparison.OrdinalIgnoreCase) ? monsterFormula : playerFormula;
        }

        private static void ApplyToNumberBoxes(BattleFormulaState formula, System.Action<FormulaBox> apply)
        {
            if (formula == null)
                return;
            Apply(formula.damageExpression, apply);
            Apply(formula.hitCountExpression, apply);
        }

        private static void Apply(FormulaState state, System.Action<FormulaBox> apply)
        {
            if (state?.boxes == null)
                return;
            foreach (FormulaBox box in state.boxes)
                if (box != null && box.boxType == FormulaBoxType.Number)
                    apply(box);
        }
    }
}
