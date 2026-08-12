namespace GoldfishWalking.Data
{
    public enum GameplayEffectOperation
    {
        Unknown,
        ModifyValue,
        SetValue,
        TransformValue,
        DealDamage,
        Heal,
        AddStatus,
        SetStatus,
        RemoveStatus,
        MultiplyStat,
        AddStack,
        SplitBox,
        LockBox,
        CreateFormulaBox,
        SetFormulaValue,
        CombineFantasies,
        Capability
    }

    public enum GameplayEffectTiming
    {
        Unspecified,
        Immediate,
        NextTurn,
        Passive,
        BattleStart,
        TurnStart,
        TurnEnd,
        DealDamage,
        TakeDamage,
        BattleEnd,
        Other
    }

    public enum GameplayEffectTarget
    {
        Unknown,
        Self,
        Player,
        Monster,
        PlayerHealth,
        PlayerStrength,
        MonsterStrength,
        PlayerDamageFormula,
        PlayerHitFormula,
        MonsterDamageFormula,
        Shop,
        Rest,
        Reward,
        Item,
        Fantasy,
        ContextValue,
        Special
    }

    public static class GameplayEffectTypeParser
    {
        public static GameplayEffectOperation ParseOperation(string value)
        {
            switch (Normalize(value))
            {
                case "add": case "modifyvalue": return GameplayEffectOperation.ModifyValue;
                case "set": case "setvalue": return GameplayEffectOperation.SetValue;
                case "transform": case "transformvalue": return GameplayEffectOperation.TransformValue;
                case "damage": case "dealdamage": return GameplayEffectOperation.DealDamage;
                case "heal": return GameplayEffectOperation.Heal;
                case "addbuff": case "addstatus": return GameplayEffectOperation.AddStatus;
                case "setbuff": case "setstatus": return GameplayEffectOperation.SetStatus;
                case "removebuff": case "removestatus": return GameplayEffectOperation.RemoveStatus;
                case "multiply": case "multiplybuff": case "multiplystat": return GameplayEffectOperation.MultiplyStat;
                case "addstack": return GameplayEffectOperation.AddStack;
                case "split": case "splitbox": return GameplayEffectOperation.SplitBox;
                case "lock": case "lockbox": return GameplayEffectOperation.LockBox;
                case "addbox": case "createformulabox": return GameplayEffectOperation.CreateFormulaBox;
                case "setformulavalue": return GameplayEffectOperation.SetFormulaValue;
                case "combine": case "combinefantasies": return GameplayEffectOperation.CombineFantasies;
                case "execute": case "capability": return GameplayEffectOperation.Capability;
                default: return GameplayEffectOperation.Unknown;
            }
        }

        public static GameplayEffectTiming ParseTiming(string value)
        {
            switch (Normalize(value))
            {
                case "": return GameplayEffectTiming.Unspecified;
                case "immediate": return GameplayEffectTiming.Immediate;
                case "nextturn": return GameplayEffectTiming.NextTurn;
                case "passive": return GameplayEffectTiming.Passive;
                case "battlestart": return GameplayEffectTiming.BattleStart;
                case "turnstart": return GameplayEffectTiming.TurnStart;
                case "turnend": return GameplayEffectTiming.TurnEnd;
                case "dealdamage": return GameplayEffectTiming.DealDamage;
                case "takedamage": return GameplayEffectTiming.TakeDamage;
                case "battleend": return GameplayEffectTiming.BattleEnd;
                default: return GameplayEffectTiming.Other;
            }
        }

        public static GameplayEffectTarget ParseTarget(string value)
        {
            switch (Normalize(value))
            {
                case "self": return GameplayEffectTarget.Self;
                case "player": return GameplayEffectTarget.Player;
                case "monster": return GameplayEffectTarget.Monster;
                case "hp": return GameplayEffectTarget.PlayerHealth;
                case "strength": return GameplayEffectTarget.PlayerStrength;
                case "enemystrength": return GameplayEffectTarget.MonsterStrength;
                case "basedamage": case "playerbasedamage": case "playerdamage": return GameplayEffectTarget.PlayerDamageFormula;
                case "attackcount": case "playerhits": return GameplayEffectTarget.PlayerHitFormula;
                case "monsterbase damage": case "monsterdamage": return GameplayEffectTarget.MonsterDamageFormula;
                case "shopmovement": case "price": case "itemcost": return GameplayEffectTarget.Shop;
                case "restcount": case "restfantasyalternative": return GameplayEffectTarget.Rest;
                case "itemchance": case "fantasyreroll": return GameplayEffectTarget.Reward;
                case "item": case "extramatch": case "eraser": return GameplayEffectTarget.Item;
                case "fantasy": case "collection": return GameplayEffectTarget.Fantasy;
                case "current": case "currentvalue": return GameplayEffectTarget.ContextValue;
                case "": return GameplayEffectTarget.Unknown;
                default: return GameplayEffectTarget.Special;
            }
        }

        private static string Normalize(string value)
        {
            return (value ?? string.Empty).Trim().ToLowerInvariant().Replace("_", string.Empty).Replace("-", string.Empty).Replace(" ", string.Empty);
        }
    }
}
