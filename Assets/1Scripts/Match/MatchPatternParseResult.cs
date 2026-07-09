using GoldfishWalking.Formula;

namespace GoldfishWalking.Match
{
    public readonly struct MatchPatternParseResult
    {
        public readonly bool success;
        public readonly int numberValue;
        public readonly FormulaOperator operatorValue;
        public readonly string error;

        public MatchPatternParseResult(bool success, int numberValue, FormulaOperator operatorValue, string error)
        {
            this.success = success;
            this.numberValue = numberValue;
            this.operatorValue = operatorValue;
            this.error = error;
        }

        public static MatchPatternParseResult Number(int value)
        {
            return new MatchPatternParseResult(true, value, FormulaOperator.Add, string.Empty);
        }

        public static MatchPatternParseResult Operator(FormulaOperator value)
        {
            return new MatchPatternParseResult(true, 0, value, string.Empty);
        }

        public static MatchPatternParseResult Fail(string error)
        {
            return new MatchPatternParseResult(false, 0, FormulaOperator.Add, error);
        }
    }
}
