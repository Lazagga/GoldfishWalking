using System;
using System.Collections.Generic;
using GoldfishWalking.Formula;

namespace GoldfishWalking.Match
{
    [Serializable]
    public sealed class MatchEditSession
    {
        public FormulaBox targetBox;
        public int originalValue;
        public int currentValue;
        public FormulaOperator originalOperator;
        public FormulaOperator currentOperator;
        public int movesUsed;
        public List<MatchSlot> slots = new List<MatchSlot>();
        public MatchPiece heldPiece;
        public int returnedAddedMatches;

        [NonSerialized] private bool splitDigits;
        [NonSerialized] private Func<int, bool> isDigitLocked;
        private int heldOriginDigit = -1;

        private readonly MatchPatternInterpreter interpreter = new MatchPatternInterpreter();

        public bool IsOpen => targetBox != null;
        public bool IsHoldingPiece => heldPiece != null;

        public void Open(FormulaBox box)
        {
            targetBox = box;
            originalValue = box != null ? box.numberValue : 0;
            currentValue = originalValue;
            originalOperator = box != null ? box.operatorValue : FormulaOperator.Add;
            currentOperator = originalOperator;
            movesUsed = 0;
            heldPiece = null;
            returnedAddedMatches = 0;
            heldOriginDigit = -1;
        }

        public void ConfigureStructuralRules(bool split, Func<int, bool> digitLocked)
        {
            splitDigits = split;
            isDigitLocked = digitLocked;
        }

        public void SetValue(int value)
        {
            currentValue = value;
            movesUsed++;
        }

        public void SetOperator(FormulaOperator formulaOperator)
        {
            currentOperator = formulaOperator;
            movesUsed++;
        }

        public MatchEditResult Commit()
        {
            MatchEditResult validation = ValidateClose();
            if (!validation.success)
                return validation;

            if (targetBox != null)
            {
                if (targetBox.boxType == FormulaBoxType.Number)
                    targetBox.numberValue = currentValue;
                else
                    targetBox.operatorValue = currentOperator;
            }

            Close();
            return MatchEditResult.Ok();
        }

        public MatchEditResult TryPickUp(int digitIndex, int segmentIndex)
        {
            if (!IsOpen)
                return MatchEditResult.Fail("No formula box is open.");

            if (IsHoldingPiece)
                return MatchEditResult.Fail("Already holding a match.");

            if (isDigitLocked?.Invoke(digitIndex) == true)
                return MatchEditResult.Fail("That digit is locked.");

            MatchSlot slot = FindSlot(digitIndex, segmentIndex);
            if (slot == null || slot.piece == null)
                return MatchEditResult.Fail("No match exists in that slot.");

            if (!slot.piece.CanMove)
                return MatchEditResult.Fail("Locked matches cannot move.");

            heldPiece = slot.piece;
            slot.piece = null;
            heldOriginDigit = digitIndex;
            return MatchEditResult.Ok();
        }

        public MatchEditResult TryPlace(int digitIndex, int segmentIndex)
        {
            if (!IsOpen)
                return MatchEditResult.Fail("No formula box is open.");

            if (!IsHoldingPiece)
                return MatchEditResult.Fail("No match is being held.");

            if (isDigitLocked?.Invoke(digitIndex) == true)
                return MatchEditResult.Fail("That digit is locked.");

            if (splitDigits && heldOriginDigit >= 0 && heldOriginDigit != digitIndex)
                return MatchEditResult.Fail("Matches cannot move between split digits.");

            MatchSlot slot = FindOrCreateSlot(digitIndex, segmentIndex);
            if (slot.piece != null)
                return MatchEditResult.Fail("That slot already has a match.");

            slot.piece = heldPiece;
            heldPiece = null;
            heldOriginDigit = -1;
            movesUsed++;
            return MatchEditResult.Ok();
        }

        public MatchEditResult TryErase(int digitIndex, int segmentIndex)
        {
            if (!IsOpen)
                return MatchEditResult.Fail("No formula box is open.");

            if (isDigitLocked?.Invoke(digitIndex) == true)
                return MatchEditResult.Fail("That digit is locked.");

            MatchSlot slot = FindSlot(digitIndex, segmentIndex);
            if (slot == null || slot.piece == null)
                return MatchEditResult.Fail("No match exists in that slot.");

            if (!slot.piece.CanErase)
                return MatchEditResult.Fail("Locked matches cannot be erased.");

            ReturnIfAdded(slot.piece);
            slot.piece = null;
            movesUsed++;
            return MatchEditResult.Ok();
        }

        public MatchEditResult AddExtraMatch(MatchPiece addedPiece)
        {
            if (!IsOpen)
                return MatchEditResult.Fail("No formula box is open.");

            if (IsHoldingPiece)
                return MatchEditResult.Fail("Already holding a match.");

            if (addedPiece == null)
                return MatchEditResult.Fail("Added match is missing.");

            addedPiece.kind = MatchPieceKind.Added;
            heldPiece = addedPiece;
            heldOriginDigit = -1;
            return MatchEditResult.Ok();
        }

        public MatchEditResult DropHeldPieceOutsideTable()
        {
            if (!IsHoldingPiece)
                return MatchEditResult.Fail("No match is being held.");

            ReturnIfAdded(heldPiece);
            heldPiece = null;
            heldOriginDigit = -1;
            movesUsed++;
            return MatchEditResult.Ok();
        }

        public void ResetBox()
        {
            currentValue = originalValue;
            currentOperator = originalOperator;
            movesUsed = 0;
            heldPiece = null;
            heldOriginDigit = -1;
            returnedAddedMatches = 0;
        }

        public void Close()
        {
            targetBox = null;
            heldPiece = null;
            heldOriginDigit = -1;
        }

        public MatchEditResult ValidateClose()
        {
            if (!IsOpen)
                return MatchEditResult.Fail("No formula box is open.");

            if (IsHoldingPiece)
                return MatchEditResult.Fail("Place or return the held match before closing.");

            MatchPatternParseResult parsed = targetBox.boxType == FormulaBoxType.Number
                ? interpreter.ParseNumber(slots)
                : interpreter.ParseOperator(slots);

            if (!parsed.success)
                return MatchEditResult.Fail(parsed.error);

            if (targetBox.boxType == FormulaBoxType.Number)
            {
                if (parsed.numberValue < 0)
                    return MatchEditResult.Fail("Negative number input is not allowed.");

                currentValue = parsed.numberValue;
            }
            else
            {
                currentOperator = parsed.operatorValue;
            }

            return MatchEditResult.Ok();
        }

        private MatchSlot FindSlot(int digitIndex, int segmentIndex)
        {
            return slots.Find(slot => slot.SameAddress(digitIndex, segmentIndex));
        }

        private MatchSlot FindOrCreateSlot(int digitIndex, int segmentIndex)
        {
            MatchSlot slot = FindSlot(digitIndex, segmentIndex);
            if (slot != null)
                return slot;

            slot = new MatchSlot
            {
                digitIndex = digitIndex,
                segmentIndex = segmentIndex
            };
            slots.Add(slot);
            return slot;
        }

        private void ReturnIfAdded(MatchPiece piece)
        {
            if (piece != null && piece.IsAdded)
                returnedAddedMatches++;
        }
    }
}
