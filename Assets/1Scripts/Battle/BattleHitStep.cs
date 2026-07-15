using GoldfishWalking.Data;

namespace GoldfishWalking.Battle
{
    public sealed class BattleHitStep
    {
        public int hitIndex;
        public int damage;
        public FantasyData sourceFantasy;

        public bool IsFantasyHit => sourceFantasy != null;
    }
}
