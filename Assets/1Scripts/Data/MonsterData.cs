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
        public int damageCap;
        public int damageCapBreakThreshold;
        public float lifestealRate;
        public bool baseDamageLocked;
        public bool playerMatchesMovable = true;
        public bool monsterMatchesMovable = true;
        public string[] reactiveEditBoxIds = Array.Empty<string>();
        public int reactiveEditGroupSize;
        public int reactiveEditSelectionCount;
        public int reactiveEditStrength;
        public bool reactiveEditOncePerBox = true;
        public int randomPlayerMatchLocksAtBattleStart;
        public int randomPlayerMatchLocksPerTurn;
        public bool lockDebuffOnDamageDealt;
        public bool lockDebuffOnDamageTaken;
        public bool clearLockDebuffWithoutEdits;
        public int hiddenAssignedDigitCount;
        public float damagePerAssignedDigitRatio;
        public int requiredPlayerDamageSuffixDigits;
        public float phaseTwoHealthRate;
        public bool phaseTwoSplitAllBoxes;
        public int phaseTwoMoveLimit = -1;
        public bool reduceStrengthOnZeroDamageTaken;
        public bool oncePerBattleStrengthReset;
        public bool lockAllPlayerMatchesOnStrengthReset;
        public bool zeroPlayerDigitsFromSpecialBox;
        public bool alwaysSplitPlayerBoxes;
        public string specialBoxLabel;
        public int specialBoxMin;
        public int specialBoxMax = 9;
        public int specialBoxValue = -1;
        public string countdownAction;
        public string countdownPattern;
        public int aimedShotMultiplier = 1;
        public int formulaDecoyDigitCount;
        public string playerAttackConditionJson;
        public string playerAttackConditionType;
        public int conditionValueMin;
        public int conditionValueMax;
        public int conditionCountMin;
        public int conditionCountMax;
        public string[] conditionOperators;
        public bool conditionCountEditable;
    }
}
