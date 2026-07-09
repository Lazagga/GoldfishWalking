using System;
using UnityEngine;

namespace GoldfishWalking.Data
{
    public enum ItemType
    {
        ExtraMatch,
        Eraser
    }

    [Serializable]
    public sealed class ItemData
    {
        public string id;
        public ItemType itemType;
        public string displayName;
        [TextArea] public string description;
    }
}
