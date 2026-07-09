using System;

namespace GoldfishWalking.Match
{
    [Serializable]
    public sealed class MatchPattern
    {
        public int value;
        public int[] segments;

        public MatchPattern(int value, params int[] segments)
        {
            this.value = value;
            this.segments = segments;
        }
    }
}