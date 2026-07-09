using GoldfishWalking.Core;
using UnityEngine;

namespace GoldfishWalking.Map
{
    public sealed class MapController : MonoBehaviour
    {
        public void SelectNode(MapNode node)
        {
            if (node == null)
            {
                Debug.LogWarning("[MapController] Tried to select a null node.");
                return;
            }

            GameEventHub.RaiseMapNodeSelected(node);
        }

        public void SelectNode(RunMap map, MapNode currentNode, MapNode node)
        {
            if (map == null || !map.CanSelect(node, currentNode))
            {
                Debug.LogWarning("[MapController] Tried to select an unavailable map node.");
                return;
            }

            SelectNode(node);
        }
    }
}
