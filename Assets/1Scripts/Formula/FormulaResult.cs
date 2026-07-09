namespace GoldfishWalking.Formula
{
    public readonly struct FormulaResult
    {
        public readonly bool isValid;
        public readonly int value;
        public readonly string error;

        public FormulaResult(bool isValid, int value, string error)
        {
            this.isValid = isValid;
            this.value = value;
            this.error = error;
        }

        public static FormulaResult Success(int value)
        {
            return new FormulaResult(true, value, string.Empty);
        }

        public static FormulaResult Failure(string error)
        {
            return new FormulaResult(false, 0, error);
        }
    }
}
