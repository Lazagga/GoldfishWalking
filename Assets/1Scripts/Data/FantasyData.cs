using System;
using UnityEngine;

namespace GoldfishWalking.Data
{
    public enum FantasyGrade
    {
        White,
        Blue,
        Red
    }

    public enum FantasyTrigger
    {
        None,
        Always,
        BattleStart,
        TurnEnd,
        OnHit,
        BattleReward,
        Rest,
        Shop,
        Special
    }

    public enum FantasyTarget
    {
        None,
        Health,
        Item,
        Damage,
        Multiplier,
        Strength,
        Formula,
        Rest,
        Shop,
        Special
    }

    [Serializable]
    public sealed class FantasyEffectData
    {
        public GameplayEffectTiming timingKind;
        public GameplayEffectTarget targetKind;
        public GameplayEffectOperation operationKind;
        public string trigger;
        public string target;
        public string operation;
        public string calc;
        public string valueExpression;
        public bool hasNumericValue;
        public float numericValue;
        public string option;
        public string condition;
        public float chance = 1f;
        public string lifetime;
        public string execution;
        public int duration;
        [TextArea] public string rawJson;
    }

    [Serializable]
    public sealed class FantasyData
    {
        public string id;
        public int sourceId;
        public string dataCode;
        public string devName;
        public string nameStringId;
        public string descStringId;
        public FantasyGrade grade;
        public string triggerType;
        public string displayName;
        [TextArea] public string description;
        public string sprite;
        [TextArea] public string rawEffects;
        public FantasyEffectData[] effects = Array.Empty<FantasyEffectData>();
        public bool isTemporary;

        // Legacy compatibility fields until fantasy effect execution is expanded.
        public FantasyTrigger trigger;
        public FantasyTarget target;
        public int value;
        public string specialHandler;
    }
}
