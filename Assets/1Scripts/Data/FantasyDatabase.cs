using System.Collections.Generic;
using UnityEngine;

namespace GoldfishWalking.Data
{
    [CreateAssetMenu(menuName = "GoldfishWalking/Data/Fantasy Database")]
    public sealed class FantasyDatabase : ScriptableObject
    {
        public List<FantasyData> fantasies = new List<FantasyData>();
    }
}
