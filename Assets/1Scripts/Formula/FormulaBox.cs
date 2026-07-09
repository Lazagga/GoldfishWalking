using System;

namespace GoldfishWalking.Formula
{
    [Serializable]
    public sealed class FormulaBox
    {
        public string id;
        public FormulaBoxType boxType;
        public bool locked;
        public bool split;
        public int numberValue;
        public int digitCount;
        public FormulaOperator operatorValue;

        public static FormulaBox Number(string id, int value, bool locked = false, int digitCount = 0)
        {
            return new FormulaBox
            {
                id = id,
                boxType = FormulaBoxType.Number,
                numberValue = value,
                locked = locked,
                digitCount = digitCount
            };
        }

        public static FormulaBox Operator(string id, FormulaOperator value, bool locked = false)
        {
            return new FormulaBox
            {
                id = id,
                boxType = FormulaBoxType.Operator,
                operatorValue = value,
                locked = locked
            };
        }
    }
}
