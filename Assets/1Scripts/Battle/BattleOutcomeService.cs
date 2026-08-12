using System;
using GoldfishWalking.Core;

namespace GoldfishWalking.Battle
{
    public enum BattleOutcome
    {
        None,
        PlayerLost,
        MonsterDefeated,
        MonsterEscaped,
        ExecuteCountdownPattern
    }

    public sealed class BattleOutcomeService
    {
        public BattleOutcome EvaluateCombatants(BattleContext context)
        {
            if (context?.run != null && context.run.health <= 0)
                return BattleOutcome.PlayerLost;
            if (context?.monster != null && context.monster.IsDead)
                return BattleOutcome.MonsterDefeated;
            return BattleOutcome.None;
        }

        public BattleOutcome TickCountdown(BattleContext context)
        {
            if (context?.monster?.Data == null || !context.monster.HasSpecialBox)
                return BattleOutcome.None;

            string action = context.monster.Data.countdownAction;
            if (!string.Equals(action, "Escape", StringComparison.OrdinalIgnoreCase)
                && !string.Equals(action, "Pattern", StringComparison.OrdinalIgnoreCase))
                return BattleOutcome.None;

            context.monster.SetSpecialBoxValue(context.monster.SpecialBoxValue - 1);
            if (context.monster.SpecialBoxValue > 0)
                return BattleOutcome.None;

            return string.Equals(action, "Escape", StringComparison.OrdinalIgnoreCase)
                ? BattleOutcome.MonsterEscaped
                : BattleOutcome.ExecuteCountdownPattern;
        }
    }
}
