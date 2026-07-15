using GoldfishWalking.Core;
using GoldfishWalking.Fantasy;

namespace GoldfishWalking.Formula
{
    public sealed class BattleFormulaBuilder
    {
        private const int BaseDamage = 10;
        private const int BaseDamageDigitCount = 2;
        private const int BaseMultiplier = 1;
        private readonly FantasyEffectRunner fantasyEffectRunner = new FantasyEffectRunner();

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
            int transformedBaseDamage = FantasyEffectRunner.TransformBattleNumber(runContext, baseDamage, true);
            transformedBaseDamage = fantasyEffectRunner.ModifyValue(runContext, transformedBaseDamage, string.Empty, "Base_Damage");
            bool split = ShouldSplitBoxes(runContext);

            BuildPlayerDamageExpression(formula.damageExpression, strength, transformedBaseDamage, split);
            BuildPlayerHitCountExpression(formula.hitCountExpression, split);

            return formula;
        }

        public BattleFormulaState BuildMonsterFormula(int damage, int hitCount = BaseMultiplier, bool hitCountEditable = false, RunContext runContext = null)
        {
            BattleFormulaState formula = new BattleFormulaState();
            int monsterDamage = damage > 0 ? FantasyEffectRunner.TransformBattleNumber(runContext, damage, false) : 0;
            int monsterHitCount = hitCount > 0 ? FantasyEffectRunner.TransformBattleNumber(runContext, hitCount, false) : 0;
            bool split = ShouldSplitBoxes(runContext);

            formula.damageExpression.Clear();
            FormulaBox damageBox = FormulaBox.Number("monster_damage", monsterDamage);
            damageBox.split = split;
            formula.damageExpression.boxes.Add(damageBox);

            formula.hitCountExpression.Clear();
            FormulaBox hitCountBox = FormulaBox.Number("monster_hit_count", monsterHitCount, locked: !hitCountEditable);
            hitCountBox.split = split;
            formula.hitCountExpression.boxes.Add(hitCountBox);

            return formula;
        }

        private static void BuildPlayerDamageExpression(FormulaState expression, int strength, int baseDamage, bool split)
        {
            expression.Clear();
            int digitCount = BaseDamageDigitCount + strength;
            FormulaBox box = FormulaBox.Number("damage_base", baseDamage, digitCount: digitCount);
            box.split = split;
            expression.boxes.Add(box);
        }

        private static void BuildPlayerHitCountExpression(FormulaState expression, bool split)
        {
            expression.Clear();
            FormulaBox box = FormulaBox.Number("hit_multiplier", BaseMultiplier, locked: true);
            box.split = split;
            expression.boxes.Add(box);
        }

        private static bool ShouldSplitBoxes(RunContext runContext)
        {
            return runContext != null
                && runContext.fantasyInventory != null
                && runContext.fantasyInventory.HasEffect("Player_Boxes", "Split");
        }
    }
}
