using System.Collections.Generic;
using UnityEngine;

namespace GoldfishWalking.Data
{
    [CreateAssetMenu(menuName = "GoldfishWalking/Data/Monster Pattern Database")]
    public sealed class MonsterPatternDatabase : ScriptableObject
    {
        public List<MonsterPatternData> patterns = new List<MonsterPatternData>();
    }
}
