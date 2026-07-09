namespace GoldfishWalking.Formula
{
    public readonly struct BattleFormulaResult
    {
        public readonly bool isValid;
        public readonly int damagePerHit;
        public readonly int hitCount;
        public readonly int totalDamage;
        public readonly bool countsAsHit;
        public readonly string error;

        public BattleFormulaResult(bool isValid, int damagePerHit, int hitCount, int totalDamage, bool countsAsHit, string error)
        {
            this.isValid = isValid;
            this.damagePerHit = damagePerHit;
            this.hitCount = hitCount;
            this.totalDamage = totalDamage;
            this.countsAsHit = countsAsHit;
            this.error = error;
        }

        public static BattleFormulaResult Success(int damagePerHit, int hitCount)
        {
            bool countsAsHit = damagePerHit > 0 && hitCount > 0;
            int totalDamage = hitCount > 0 ? damagePerHit * hitCount : 0;
            return new BattleFormulaResult(true, damagePerHit, hitCount, totalDamage, countsAsHit, string.Empty);
        }

        public static BattleFormulaResult Failure(string error)
        {
            return new BattleFormulaResult(false, 0, 0, 0, false, error);
        }
    }
}
