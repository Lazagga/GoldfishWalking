using System;
using System.Text;

namespace GoldfishWalking.Core
{
    public static class DeterministicValue
    {
        public static int Range(int runSeed, int act, int roomIndex, string nodeId, string purposeKey, int minInclusive, int maxInclusive)
        {
            if (maxInclusive < minInclusive)
                return minInclusive;

            int seed = BuildSeed(runSeed, act, roomIndex, nodeId, purposeKey);
            Random random = new Random(seed);
            return random.Next(minInclusive, maxInclusive + 1);
        }

        private static int BuildSeed(int runSeed, int act, int roomIndex, string nodeId, string purposeKey)
        {
            string input = $"{runSeed}|{act}|{roomIndex}|{nodeId ?? string.Empty}|{purposeKey ?? string.Empty}";
            unchecked
            {
                const uint offset = 2166136261u;
                const uint prime = 16777619u;
                uint hash = offset;
                byte[] bytes = Encoding.UTF8.GetBytes(input);
                for (int i = 0; i < bytes.Length; i++)
                {
                    hash ^= bytes[i];
                    hash *= prime;
                }

                return (int)(hash & 0x7fffffff);
            }
        }
    }
}
