using System;
using System.Collections.Generic;

namespace GoldfishWalking.Map
{
    [Serializable]
    public sealed class RunMap
    {
        public int seed;
        public int act = 1;
        public List<MapNode> nodes = new List<MapNode>();
        public List<string> completedNodeIds = new List<string>();

        public MapNode FindNode(string id)
        {
            return nodes.Find(node => node.id == id);
        }

        public bool IsCompleted(MapNode node)
        {
            return node != null && completedNodeIds.Contains(node.id);
        }

        public void MarkCompleted(MapNode node)
        {
            if (node == null || completedNodeIds.Contains(node.id))
                return;

            completedNodeIds.Add(node.id);
        }

        public bool CanSelect(MapNode node, MapNode currentNode)
        {
            if (node == null || IsCompleted(node))
                return false;

            if (node.nodeType == MapNodeType.Start)
                return currentNode == null;

            if (currentNode == null)
                return node.roomIndex == 0;

            return currentNode.nextNodeIds.Contains(node.id);
        }
    }
}
