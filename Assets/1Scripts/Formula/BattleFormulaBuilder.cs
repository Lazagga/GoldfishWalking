using GoldfishWalking.Core;

namespace GoldfishWalking.Formula
{
    public sealed class BattleFormulaBuilder
    {
        private const int BaseDamage = 10;
        private const int BaseDamageDigitCount = 2;
        private const int BaseMultiplier = 1;

        public BattleFormulaState BuildPlayerFormula(RunContext runContext)
        {
            int baseDamage = runContext != null && runContext.currentBattle != null
                ? runContext.currentBattle.playerBaseDamage
                : BaseDamage;
            return BuildPlayerFormula(runContext, baseDamage);
        }

        public BattleFormulaState BuildPlayerFormula(RunContext runContext, int baseDamage)
        {
            BattleFormulaState formula = new BattleFormulaState();
            int strength = runContext != null && runContext.strength > 0 ? runContext.strength : 0;

            BuildPlayerDamageExpression(formula.damageExpression, strength, baseDamage);
            BuildPlayerHitCountExpression(formula.hitCountExpression);

            return formula;
        }

        public BattleFormulaState BuildMonsterFormula(int damage, int hitCount = BaseMultiplier, bool hitCountEditable = false)
        {
            BattleFormulaState formula = new BattleFormulaState();
            int monsterDamage = damage > 0 ? damage : 0;
            int monsterHitCount = hitCount > 0 ? hitCount : 0;

            formula.damageExpression.Clear();
            formula.damageExpression.boxes.Add(FormulaBox.Number("monster_damage", monsterDamage));

            formula.hitCountExpression.Clear();
            formula.hitCountExpression.boxes.Add(FormulaBox.Number("monster_hit_count", monsterHitCount, locked: !hitCountEditable));

            return formula;
        }

        private static void BuildPlayerDamageExpression(FormulaState expression, int strength, int baseDamage)
        {
            expression.Clear();
            int digitCount = BaseDamageDigitCount + strength;
            expression.boxes.Add(FormulaBox.Number("damage_base", baseDamage, digitCount: digitCount));
        }

        private static void BuildPlayerHitCountExpression(FormulaState expression)
        {
            expression.Clear();
            expression.boxes.Add(FormulaBox.Number("hit_multiplier", BaseMultiplier, locked: true));
        }
    }
}
