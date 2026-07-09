using System;

namespace GoldfishWalking.Formula
{
    public sealed class FormulaEvaluator
    {
        public FormulaResult EvaluateLeftToRight(FormulaState state)
        {
            if (state == null || state.boxes == null || state.boxes.Count == 0)
                return FormulaResult.Failure("Formula is empty.");

            if (state.boxes[0].boxType != FormulaBoxType.Number)
                return FormulaResult.Failure("Formula must start with a number.");

            FormulaResult validation = ValidateNumberInputs(state);
            if (!validation.isValid)
                return validation;

            int value = state.boxes[0].numberValue;
            int index = 1;

            while (index < state.boxes.Count)
            {
                if (index + 1 >= state.boxes.Count)
                    return FormulaResult.Failure("Formula ends with an operator.");

                FormulaBox operatorBox = state.boxes[index];
                FormulaBox numberBox = state.boxes[index + 1];

                if (operatorBox.boxType != FormulaBoxType.Operator || numberBox.boxType != FormulaBoxType.Number)
                    return FormulaResult.Failure("Formula must alternate operators and numbers.");

                if (operatorBox.operatorValue == FormulaOperator.Divide && numberBox.numberValue == 0)
                    return FormulaResult.Failure("Division by zero is not allowed.");

                value = Apply(value, operatorBox.operatorValue, numberBox.numberValue);
                index += 2;
            }

            return FormulaResult.Success(value);
        }

        public BattleFormulaResult EvaluateBattleFormula(BattleFormulaState state)
        {
            if (state == null)
                return BattleFormulaResult.Failure("Battle formula is empty.");

            FormulaResult damageResult = EvaluateLeftToRight(state.damageExpression);
            if (!damageResult.isValid)
                return BattleFormulaResult.Failure(damageResult.error);

            FormulaResult hitCountResult = EvaluateLeftToRight(state.hitCountExpression);
            if (!hitCountResult.isValid)
                return BattleFormulaResult.Failure(hitCountResult.error);

            return BattleFormulaResult.Success(damageResult.value, hitCountResult.value);
        }

        private static FormulaResult ValidateNumberInputs(FormulaState state)
        {
            foreach (FormulaBox box in state.boxes)
            {
                if (box.boxType == FormulaBoxType.Number && box.numberValue < 0)
                    return FormulaResult.Failure("Negative number input is not allowed.");
            }

            return FormulaResult.Success(0);
        }

        private static int Apply(int left, FormulaOperator formulaOperator, int right)
        {
            switch (formulaOperator)
            {
                case FormulaOperator.Add:
                    return left + right;
                case FormulaOperator.Subtract:
                    return left - right;
                case FormulaOperator.Multiply:
                    return left * right;
                case FormulaOperator.Divide:
                    return (int)Math.Floor((double)left / right);
                default:
                    return left;
            }
        }
    }
}