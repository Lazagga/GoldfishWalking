using System;

namespace GoldfishWalking.Match
{
    [Serializable]
    public sealed class MatchSlot
    {
        public int digitIndex;
        public int segmentIndex;
        public MatchPiece piece;

        public bool HasPiece => piece != null;

        public bool SameAddress(int otherDigitIndex, int otherSegmentIndex)
        {
            return digitIndex == otherDigitIndex && segmentIndex == otherSegmentIndex;
        }
    }
}