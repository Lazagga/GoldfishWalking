using GoldfishWalking.Core;
using GoldfishWalking.Data;
using GoldfishWalking.Fantasy;
using System.Collections.Generic;
using UnityEngine;

namespace GoldfishWalking.Rest
{
    public sealed class RestController : MonoBehaviour
    {
        [SerializeField] private GameBootstrap bootstrap;
        [SerializeField] private FantasyDatabase fantasyDatabase;
        private readonly FantasyEffectRunner fantasyEffectRunner = new FantasyEffectRunner();

        private void OnEnable()
        {
            GameEventHub.StateChanged += OnStateChanged;
        }

        private void OnDisable()
        {
            GameEventHub.StateChanged -= OnStateChanged;
        }

        public void CompleteRest()
        {
            if (bootstrap == null || bootstrap.RunContext == null)
                return;

            GameEventHub.RaiseRestCompleted();
        }

        public void Heal(int amount)
        {
            if (bootstrap == null || bootstrap.RunContext == null)
                return;

            bootstrap.RunContext.health += GetModifiedHealAmount(amount);
        }

        public int CurrentHealth => bootstrap != null && bootstrap.RunContext != null ? bootstrap.RunContext.health : 0;
        public int CurrentHealAmount => bootstrap != null && bootstrap.RunContext != null ? bootstrap.RunContext.EnsureRestNumbers().healAmount : 0;
        public int MaxRestCount => bootstrap != null && bootstrap.RunContext != null
            ? Mathf.Max(1, fantasyEffectRunner.ModifyValue(bootstrap.RunContext, 1, "Passive", "Rest_Count"))
            : 1;
        public IReadOnlyList<FantasyData> OwnedFantasies => bootstrap != null && bootstrap.RunContext != null && bootstrap.RunContext.fantasyInventory != null
            ? bootstrap.RunContext.fantasyInventory.ownedFantasies
            : null;
        public bool CanClaimCoffeeFantasy => bootstrap != null && bootstrap.RunContext != null && bootstrap.RunContext.fantasyInventory.Contains("fan_rest_coffee");

        public void SetHealAmount(int amount)
        {
            if (bootstrap == null || bootstrap.RunContext == null)
                return;

            bootstrap.RunContext.EnsureRestNumbers().healAmount = Mathf.Max(0, amount);
        }

        public bool TryClaimCoffeeFantasy()
        {
            if (!CanClaimCoffeeFantasy || fantasyDatabase == null)
                return false;

            FantasyData selected = null;
            int seen = 0;
            for (int i = 0; i < fantasyDatabase.fantasies.Count; i++)
            {
                FantasyData fantasy = fantasyDatabase.fantasies[i];
                if (fantasy == null || fantasy.grade != FantasyGrade.White)
                    continue;
                if (bootstrap.RunContext.fantasyInventory.Contains(fantasy.id))
                    continue;

                seen++;
                if (bootstrap.RunContext.RollValue($"rest.coffee.fantasy.{seen}", 0, seen - 1) == 0)
                    selected = fantasy;
            }

            if (selected == null)
                return false;

            bootstrap.RunContext.fantasyInventory.Add(selected);
            fantasyEffectRunner.Apply(selected, bootstrap.RunContext, "On_Acquire");
            fantasyEffectRunner.Apply(selected, bootstrap.RunContext, "Acquire");
            return true;
        }

        private void OnStateChanged(GameState previous, GameState next)
        {
            if (next != GameState.Rest)
                return;

            if (bootstrap != null && bootstrap.RunContext != null)
                bootstrap.RunContext.EnsureRestNumbers();
        }

        private int GetModifiedHealAmount(int amount)
        {
            if (bootstrap == null || bootstrap.RunContext == null)
                return Mathf.Max(0, amount);

            int modified = Mathf.Max(0, amount);
            modified = fantasyEffectRunner.ModifyValue(bootstrap.RunContext, modified, "Passive", "HP");
            modified = fantasyEffectRunner.ModifyValue(bootstrap.RunContext, modified, "Rest", "HP");
            return Mathf.Max(0, modified);
        }
    }
}
