using System;
using System.Collections.Generic;

namespace GoldfishWalking.Map
{
    [Serializable]
    public sealed class MapNode
    {
        public string id;
        public int roomIndex;
        public int laneIndex;
        public MapNodeType nodeType;
        public List<string> nextNodeIds = new List<string>();
    }
}
