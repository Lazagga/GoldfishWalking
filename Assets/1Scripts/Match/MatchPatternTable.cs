using System.Collections.Generic;
using GoldfishWalking.Formula;

namespace GoldfishWalking.Match
{
    public static class MatchPatternTable
    {
        public static readonly MatchPattern[] DigitPatterns =
        {
            new MatchPattern(0, Seg(MatchSegment.Top), Seg(MatchSegment.UpperRight), Seg(MatchSegment.LowerRight), Seg(MatchSegment.Bottom), Seg(MatchSegment.LowerLeft), Seg(MatchSegment.UpperLeft)),
            new MatchPattern(1, Seg(MatchSegment.UpperRight), Seg(MatchSegment.LowerRight)),
            new MatchPattern(2, Seg(MatchSegment.Top), Seg(MatchSegment.UpperRight), Seg(MatchSegment.Middle), Seg(MatchSegment.LowerLeft), Seg(MatchSegment.Bottom)),
            new MatchPattern(3, Seg(MatchSegment.Top), Seg(MatchSegment.UpperRight), Seg(MatchSegment.Middle), Seg(MatchSegment.LowerRight), Seg(MatchSegment.Bottom)),
            new MatchPattern(4, Seg(MatchSegment.UpperLeft), Seg(MatchSegment.Middle), Seg(MatchSegment.UpperRight), Seg(MatchSegment.LowerRight)),
            new MatchPattern(5, Seg(MatchSegment.Top), Seg(MatchSegment.UpperLeft), Seg(MatchSegment.Middle), Seg(MatchSegment.LowerRight), Seg(MatchSegment.Bottom)),
            new MatchPattern(6, Seg(MatchSegment.Top), Seg(MatchSegment.UpperLeft), Seg(MatchSegment.Middle), Seg(MatchSegment.LowerLeft), Seg(MatchSegment.LowerRight), Seg(MatchSegment.Bottom)),
            new MatchPattern(7, Seg(MatchSegment.Top), Seg(MatchSegment.UpperRight), Seg(MatchSegment.LowerRight)),
            new MatchPattern(8, Seg(MatchSegment.Top), Seg(MatchSegment.UpperRight), Seg(MatchSegment.LowerRight), Seg(MatchSegment.Bottom), Seg(MatchSegment.LowerLeft), Seg(MatchSegment.UpperLeft), Seg(MatchSegment.Middle)),
            new MatchPattern(9, Seg(MatchSegment.Top), Seg(MatchSegment.UpperRight), Seg(MatchSegment.LowerRight), Seg(MatchSegment.Bottom), Seg(MatchSegment.UpperLeft), Seg(MatchSegment.Middle))
        };

        public static readonly Dictionary<FormulaOperator, int[]> OperatorPatterns = new Dictionary<FormulaOperator, int[]>
        {
            { FormulaOperator.Add, new[] { Seg(MatchSegment.Middle), Seg(MatchSegment.VerticalCenter) } },
            { FormulaOperator.Subtract, new[] { Seg(MatchSegment.Middle) } },
            { FormulaOperator.Multiply, new[] { Seg(MatchSegment.SlashForward), Seg(MatchSegment.SlashBack) } },
            { FormulaOperator.Divide, new[] { Seg(MatchSegment.SlashForward) } }
        };

        public static bool SameSegments(IReadOnlyList<int> left, IReadOnlyList<int> right)
        {
            if (left == null || right == null || left.Count != right.Count)
                return false;

            HashSet<int> set = new HashSet<int>(left);
            foreach (int value in right)
            {
                if (!set.Contains(value))
                    return false;
            }

            return true;
        }

        private static int Seg(MatchSegment segment)
        {
            return (int)segment;
        }
    }
}
