using GoldfishWalking.Data;

namespace GoldfishWalking.Battle
{
    public sealed class MonsterRuntime
    {
        public MonsterData Data { get; }
        public int CurrentHealth { get; private set; }
        public int Strength { get; private set; }

        public bool IsDead => CurrentHealth <= 0;

        public MonsterRuntime(MonsterData data)
        {
            Data = data;
            CurrentHealth = data != null ? data.baseHealth : 1;
            Strength = data != null ? data.baseStrength : 0;
        }

        public void ApplyDamage(int amount)
        {
            CurrentHealth -= amount;
        }

        public void Heal(int amount)
        {
            CurrentHealth += amount;
        }

        public void ChangeStrength(int amount)
        {
            Strength += amount;
        }

        public void SetStrength(int value)
        {
            Strength = value;
        }
    }
}
