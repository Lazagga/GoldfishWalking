using GoldfishWalking.Data;
using GoldfishWalking.Core;
using System.Collections.Generic;

namespace GoldfishWalking.Battle
{
    public sealed class MonsterRuntime
    {
        public event System.Action<int> StrengthIncreased;
        public MonsterData Data { get; }
        public int CurrentHealth { get; private set; }
        public int Strength { get; private set; }
        public int StunTurns { get; private set; }
        public int Shield { get; private set; }
        public int DamageCapPerHit { get; private set; }
        public int DamageCapAccumulatedDamage { get; private set; }
        public int FortuneStack { get; private set; }
        public int ProphecyStack { get; private set; }
        public int Phase { get; private set; } = 1;
        public int LockDebuffStacks { get; private set; }
        public int LastTurnMoveCount { get; set; } = -1;
        public bool OncePerBattleActionUsed { get; private set; }
        public int HiddenDigitA { get; private set; } = -1;
        public int HiddenDigitB { get; private set; } = -1;
        public bool HiddenDigitADiscovered { get; private set; }
        public bool HiddenDigitBDiscovered { get; private set; }
        public bool HasSpecialBox { get; private set; }
        public int SpecialBoxValue { get; private set; }
        public int SpecialBoxDigitCount { get; private set; }
        public string SpecialBoxLabel { get; private set; } = string.Empty;
        public bool SpecialBoxEditable { get; private set; }
        public List<ScheduledMonsterPatternEffect> ScheduledEffects { get; } = new List<ScheduledMonsterPatternEffect>();
        public List<TimedStrengthModifier> TimedStrengthModifiers { get; } = new List<TimedStrengthModifier>();
        private readonly Dictionary<string, int> remainingPatternUses = new Dictionary<string, int>();
        private readonly HashSet<string> reactiveEditBoxes = new HashSet<string>();
        private readonly HashSet<string> reactedEditBoxes = new HashSet<string>();
        public int SelectedPatternTurn { get; private set; }
        public MonsterPatternData SelectedPattern { get; private set; }

        public bool IsDead => CurrentHealth <= 0;
        public bool IsStunned => StunTurns > 0;

        public bool CanUsePattern(MonsterPatternData pattern)
        {
            if (pattern == null || pattern.maxUses < 0)
                return true;
            return !remainingPatternUses.TryGetValue(pattern.id ?? string.Empty, out int remaining)
                ? pattern.maxUses > 0
                : remaining > 0;
        }

        public void SelectPatternForTurn(MonsterPatternData pattern, int turn)
        {
            SelectedPattern = pattern;
            SelectedPatternTurn = turn;
            if (pattern == null || pattern.maxUses < 0)
                return;
            string key = pattern.id ?? string.Empty;
            int remaining = remainingPatternUses.TryGetValue(key, out int stored) ? stored : pattern.maxUses;
            remainingPatternUses[key] = System.Math.Max(0, remaining - 1);
        }

        public MonsterRuntime(MonsterData data)
        {
            Data = data;
            CurrentHealth = data != null ? data.baseHealth : 1;
            Strength = data != null ? data.baseStrength : 0;
            DamageCapPerHit = data != null ? System.Math.Max(0, data.damageCap) : 0;
        }

        public void ConfigureReactiveEditBoxes(RunContext runContext, string nodeId)
        {
            reactiveEditBoxes.Clear();
            reactedEditBoxes.Clear();
            string[] candidates = Data?.reactiveEditBoxIds;
            int groupSize = Data != null ? Data.reactiveEditGroupSize : 0;
            int countPerGroup = Data != null ? Data.reactiveEditSelectionCount : 0;
            if (candidates == null || candidates.Length == 0 || groupSize <= 0 || countPerGroup <= 0)
                return;

            for (int groupStart = 0; groupStart < candidates.Length; groupStart += groupSize)
            {
                int groupCount = System.Math.Min(groupSize, candidates.Length - groupStart);
                int selections = System.Math.Min(countPerGroup, groupCount);
                List<int> available = new List<int>();
                for (int i = 0; i < groupCount; i++)
                    available.Add(i);

                for (int selection = 0; selection < selections; selection++)
                {
                    int picked = DeterministicValue.Range(
                        runContext?.seed ?? 0,
                        runContext?.act ?? 1,
                        runContext?.roomIndex ?? 0,
                        nodeId,
                        $"battle.monster.reactive_box.group.{groupStart / groupSize}.selection.{selection}",
                        0,
                        available.Count - 1);
                    reactiveEditBoxes.Add(candidates[groupStart + available[picked]]);
                    available.RemoveAt(picked);
                }
            }
        }

        public bool IsReactiveEditBox(string boxId)
        {
            return !string.IsNullOrWhiteSpace(boxId) && reactiveEditBoxes.Contains(boxId);
        }

        public bool TryReactToBoxEdit(string boxId)
        {
            if (!IsReactiveEditBox(boxId))
                return false;
            if (Data?.reactiveEditOncePerBox != false && !reactedEditBoxes.Add(boxId))
                return false;

            ChangeStrength(Data != null ? Data.reactiveEditStrength : 0);
            return true;
        }

        public void ConfigureHiddenDigits(RunContext runContext, string nodeId)
        {
            if (Data == null || Data.hiddenAssignedDigitCount <= 0)
                return;
            HiddenDigitA = DeterministicValue.Range(runContext?.seed ?? 0, runContext?.act ?? 1,
                runContext?.roomIndex ?? 0, nodeId, "battle.monster.hidden_digit.0", 0, 9);
            HiddenDigitB = DeterministicValue.Range(runContext?.seed ?? 0, runContext?.act ?? 1,
                runContext?.roomIndex ?? 0, nodeId, "battle.monster.hidden_digit.1", 0, 8);
            if (HiddenDigitB >= HiddenDigitA)
                HiddenDigitB++;
        }

        public float EvaluateHiddenDigitDamageRatio(int playerDamage)
        {
            if (Data == null || Data.hiddenAssignedDigitCount <= 0)
                return 1f;
            string digits = System.Math.Abs(playerDamage).ToString();
            bool foundA = HiddenDigitA >= 0 && digits.IndexOf((char)('0' + HiddenDigitA)) >= 0;
            bool foundB = HiddenDigitB >= 0 && digits.IndexOf((char)('0' + HiddenDigitB)) >= 0;
            HiddenDigitADiscovered |= foundA;
            HiddenDigitBDiscovered |= foundB;
            int found = (foundA ? 1 : 0) + (foundB ? 1 : 0);
            return System.Math.Min(1f, found * Data.damagePerAssignedDigitRatio);
        }

        public void AddLockDebuffStack()
        {
            LockDebuffStacks++;
        }

        public void ClearLockDebuffStacks()
        {
            LockDebuffStacks = 0;
        }

        public bool TryUseOncePerBattleAction()
        {
            if (OncePerBattleActionUsed)
                return false;
            OncePerBattleActionUsed = true;
            return true;
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
            int actualDamage = amount > 0 ? amount : 0;
            ApplyDamageCapBreakProgress(actualDamage);
            return actualDamage;
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
            if (amount > 0)
                StrengthIncreased?.Invoke(amount);
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
            int increase = value - Strength;
            Strength = value;
            if (increase > 0)
                StrengthIncreased?.Invoke(increase);
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

        private void ApplyDamageCapBreakProgress(int damage)
        {
            if (damage <= 0 || DamageCapPerHit <= 0 || Data == null || Data.damageCapBreakThreshold <= 0)
                return;

            DamageCapAccumulatedDamage += damage;
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

        public void SetSpecialBox(int value, int digitCount, string label, bool editable = true)
        {
            HasSpecialBox = true;
            SpecialBoxValue = System.Math.Max(0, value);
            SpecialBoxDigitCount = System.Math.Max(1, digitCount);
            SpecialBoxLabel = label ?? string.Empty;
            SpecialBoxEditable = editable;
        }

        public void AppendSpecialBoxDigit(int digit, string label, bool editable = false)
        {
            int clampedDigit = System.Math.Max(0, System.Math.Min(9, digit));
            if (!HasSpecialBox)
            {
                SetSpecialBox(clampedDigit, 1, label, editable);
                return;
            }

            SpecialBoxValue = SpecialBoxValue * 10 + clampedDigit;
            SpecialBoxDigitCount = System.Math.Max(1, SpecialBoxDigitCount + 1);
            if (!string.IsNullOrWhiteSpace(label))
                SpecialBoxLabel = label;
            SpecialBoxEditable = editable;
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
            SpecialBoxEditable = false;
        }

        public void AdvanceTurnDurations()
        {
            if (StunTurns > 0)
                StunTurns--;
        }

    }

    public sealed class ScheduledMonsterPatternEffect
    {
        public MonsterPatternEffectData effect;
        public int triggerTurn;
    }
}
