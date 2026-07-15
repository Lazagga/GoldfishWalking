namespace GoldfishWalking.Battle
{
    public enum BattleState
    {
        NotStarted,
        Editing,
        Validating,
        PlayerAttack,
        PlayerEffects,
        MonsterAction,
        MonsterEffects,
        StatusEffects,
        DurationCleanup,
        OutcomeCheck,
        Won,
        Lost
    }
}
