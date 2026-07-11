using GoldfishWalking.Data;
using GoldfishWalking.Core;
using System.Collections.Generic;

namespace GoldfishWalking.Battle
{
    public sealed class MonsterRuntime
    {
        public MonsterData Data { get; }
        public int CurrentHealth { get; private set; }
        public int Strength { get; private set; }
        public int StunTurns { get; private set; }
        public int Shield { get; private set; }
        public int DamageCapPerHit { get; private set; }
        public int FortuneStack { get; private set; }
        public int ProphecyStack { get; private set; }
        public int Phase { get; private set; } = 1;
        public bool HasSpecialBox { get; private set; }
        public int SpecialBoxValue { get; private set; }
        public int SpecialBoxDigitCount { get; private set; }
        public string SpecialBoxLabel { get; private set; } = string.Empty;
        public List<ScheduledMonsterPatternEffect> ScheduledEffects { get; } = new List<ScheduledMonsterPatternEffect>();
        public List<TimedStrengthModifier> TimedStrengthModifiers { get; } = new List<TimedStrengthModifier>();

        public bool IsDead => CurrentHealth <= 0;
        public bool IsStunned => StunTurns > 0;

        public MonsterRuntime(MonsterData data)
        {
            Data = data;
            CurrentHealth = data != null ? data.baseHealth : 1;
            Strength = data != null ? data.baseStrength : 0;
            DamageCapPerHit = InitialDamageCap(data);
        }

        public int ApplyDamage(int amount)
        {
            if (amount > 0 && DamageCapPerHit > 0)
                amount = System.Math.Min(amount, DamageCapPerHit);

            if (amount > 0 && Shield > 0)
            {
                int blocked = amount < Shield ? amount : Shield;
                Shield -= blocked;
                amount -= blocked;
            }

            CurrentHealth -= amount;
            return amount > 0 ? amount : 0;
        }

        public void Kill()
        {
            CurrentHealth = 0;
        }

        public void Heal(int amount)
        {
            CurrentHealth += amount;
        }

        public void ChangeStrength(int amount)
        {
            Strength += amount;
        }

        public void AddTimedStrengthModifier(int amount, int duration)
        {
            if (amount == 0 || duration <= 0)
                return;

            TimedStrengthModifiers.Add(new TimedStrengthModifier
            {
                amount = amount,
                remainingTurns = duration
            });
        }

        public void AdvanceStrengthModifierDurations()
        {
            for (int i = TimedStrengthModifiers.Count - 1; i >= 0; i--)
            {
                TimedStrengthModifier modifier = TimedStrengthModifiers[i];
                if (modifier == null)
                {
                    TimedStrengthModifiers.RemoveAt(i);
                    continue;
                }

                modifier.remainingTurns--;
                if (modifier.remainingTurns > 0)
                    continue;

                Strength -= modifier.amount;
                TimedStrengthModifiers.RemoveAt(i);
            }
        }

        public void SetStrength(int value)
        {
            Strength = value;
        }

        public void ChangeStun(int amount)
        {
            StunTurns = System.Math.Max(0, StunTurns + amount);
        }

        public void SetStun(int value)
        {
            StunTurns = System.Math.Max(0, value);
        }

        public void ChangeShield(int amount)
        {
            Shield = System.Math.Max(0, Shield + amount);
        }

        public void SetShield(int value)
        {
            Shield = System.Math.Max(0, value);
        }

        public void ClearDamageCap()
        {
            DamageCapPerHit = 0;
        }

        public void ChangeFortuneStack(int amount)
        {
            FortuneStack = System.Math.Max(0, FortuneStack + amount);
        }

        public void SetFortuneStack(int value)
        {
            FortuneStack = System.Math.Max(0, value);
        }

        public void ChangeProphecyStack(int amount)
        {
            ProphecyStack = System.Math.Max(0, ProphecyStack + amount);
        }

        public void SetProphecyStack(int value)
        {
            ProphecyStack = System.Math.Max(0, value);
        }

        public void SetPhase(int value)
        {
            Phase = System.Math.Max(1, value);
        }

        public void SetSpecialBox(int value, int digitCount, string label)
        {
            HasSpecialBox = true;
            SpecialBoxValue = System.Math.Max(0, value);
            SpecialBoxDigitCount = System.Math.Max(1, digitCount);
            SpecialBoxLabel = label ?? string.Empty;
        }

        public void SetSpecialBoxValue(int value)
        {
            if (!HasSpecialBox)
                SetSpecialBox(value, 1, "SPECIAL");

            SpecialBoxValue = System.Math.Max(0, value);
        }

        public void ClearSpecialBox()
        {
            HasSpecialBox = false;
            SpecialBoxValue = 0;
            SpecialBoxDigitCount = 0;
            SpecialBoxLabel = string.Empty;
        }

        public void AdvanceTurnDurations()
        {
            if (StunTurns > 0)
                StunTurns--;
        }

        private static int InitialDamageCap(MonsterData data)
        {
            if (data == null)
                return 0;

            string dataName = data.dataName ?? string.Empty;
            string devName = data.devName ?? string.Empty;
            if (dataName.Contains("Guard") || devName.Contains("경비병"))
                return 45;
            if (dataName.Contains("Knight") || devName.Contains("기사"))
                return 20;
            return 0;
        }
    }

    public sealed class ScheduledMonsterPatternEffect
    {
        public MonsterPatternEffectData effect;
        public int triggerTurn;
    }
}
