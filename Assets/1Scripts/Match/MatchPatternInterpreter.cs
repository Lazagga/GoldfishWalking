using System.Collections.Generic;
using GoldfishWalking.Formula;

namespace GoldfishWalking.Match
{
    public sealed class MatchPatternInterpreter
    {
        public MatchPatternParseResult ParseNumber(IReadOnlyList<MatchSlot> slots)
        {
            SortedDictionary<int, List<int>> digitSegments = CollectDigitSegments(slots);
            if (digitSegments.Count == 0)
                return MatchPatternParseResult.Fail("A number box cannot be empty.");

            int value = 0;
            bool hasParsedDigit = false;

            foreach (KeyValuePair<int, List<int>> entry in digitSegments)
            {
                if (entry.Value.Count == 0)
                    continue;

                if (!TryParseDigit(entry.Value, out int digit))
                    return MatchPatternParseResult.Fail("Invalid number match pattern.");

                value = value * 10 + digit;
                hasParsedDigit = true;
            }

            return hasParsedDigit
                ? MatchPatternParseResult.Number(value)
                : MatchPatternParseResult.Fail("A number box cannot be empty.");
        }

        public MatchPatternParseResult ParseOperator(IReadOnlyList<MatchSlot> slots)
        {
            List<int> segments = CollectSingleOperatorSegments(slots);
            if (segments.Count == 0)
                return MatchPatternParseResult.Fail("An operator box cannot be empty.");

            foreach (KeyValuePair<FormulaOperator, int[]> pattern in MatchPatternTable.OperatorPatterns)
            {
                if (MatchPatternTable.SameSegments(segments, pattern.Value))
                    return MatchPatternParseResult.Operator(pattern.Key);
            }

            return MatchPatternParseResult.Fail("Invalid operator match pattern.");
        }

        private static bool TryParseDigit(IReadOnlyList<int> segments, out int digit)
        {
            foreach (MatchPattern pattern in MatchPatternTable.DigitPatterns)
            {
                if (MatchPatternTable.SameSegments(segments, pattern.segments))
                {
                    digit = pattern.value;
                    return true;
                }
            }

            digit = 0;
            return false;
        }

        private static SortedDictionary<int, List<int>> CollectDigitSegments(IReadOnlyList<MatchSlot> slots)
        {
            SortedDictionary<int, List<int>> digitSegments = new SortedDictionary<int, List<int>>();
            if (slots == null)
                return digitSegments;

            foreach (MatchSlot slot in slots)
            {
                if (slot == null || !slot.HasPiece)
                    continue;

                if (!digitSegments.TryGetValue(slot.digitIndex, out List<int> segments))
                {
                    segments = new List<int>();
                    digitSegments.Add(slot.digitIndex, segments);
                }

                segments.Add(slot.segmentIndex);
            }

            return digitSegments;
        }

        private static List<int> CollectSingleOperatorSegments(IReadOnlyList<MatchSlot> slots)
        {
            List<int> segments = new List<int>();
            if (slots == null)
                return segments;

            foreach (MatchSlot slot in slots)
            {
                if (slot == null || !slot.HasPiece)
                    continue;

                segments.Add(slot.segmentIndex);
            }

            return segments;
        }
    }
}
