using UnityEngine;

namespace GoldfishWalking.Core
{
    public sealed class GameStateMachine
    {
        public GameState CurrentState { get; private set; } = GameState.Boot;

        public void ChangeState(GameState next)
        {
            if (CurrentState == next)
                return;

            GameState previous = CurrentState;
            CurrentState = next;
            Debug.Log($"[GameStateMachine] {previous} -> {next}");
            GameEventHub.RaiseStateChanged(previous, next);
        }
    }
}
