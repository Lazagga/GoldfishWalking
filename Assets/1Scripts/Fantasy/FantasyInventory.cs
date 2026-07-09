using System;
using System.Collections.Generic;
using GoldfishWalking.Data;

namespace GoldfishWalking.Fantasy
{
    [Serializable]
    public sealed class FantasyInventory
    {
        public List<FantasyData> ownedFantasies = new List<FantasyData>();

        public void Add(FantasyData fantasy)
        {
            if (fantasy == null || Contains(fantasy.id))
                return;

            ownedFantasies.Add(fantasy);
        }

        public bool Contains(string id)
        {
            return ownedFantasies.Exists(fantasy => fantasy != null && fantasy.id == id);
        }

        public void Clear()
        {
            ownedFantasies.Clear();
        }
    }
}
