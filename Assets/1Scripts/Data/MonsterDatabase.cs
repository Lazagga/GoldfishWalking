using System.Collections.Generic;
using UnityEngine;

namespace GoldfishWalking.Data
{
    [CreateAssetMenu(menuName = "GoldfishWalking/Data/Monster Database")]
    public sealed class MonsterDatabase : ScriptableObject
    {
        public List<MonsterData> monsters = new List<MonsterData>();
    }
}
