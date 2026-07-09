using System;

namespace GoldfishWalking.Data
{
    public enum MonsterGrade
    {
        Normal,
        Elite,
        Boss
    }

    public enum MonsterDifficulty
    {
        None,
        Easy,
        Normal,
        Hard
    }

    public enum MonsterAiType
    {
        Static,
        Random
    }

    [Serializable]
    public sealed class MonsterData
    {
        public string id;
        public int sourceId;
        public int act = 1;
        public MonsterGrade grade;
        public MonsterDifficulty difficulty;
        public string devName;
        public string dataName;
        public string nameStringId;
        public string descStringId;
        public string displayName;
        public string description;
        public int baseHealth = 10;
        public int baseStrength;
        public MonsterAiType aiType;
        public string[] patternIds;
        public string rawPatternArray;
        public string sprite;
    }
}
