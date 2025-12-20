using System;
using System.Collections.Generic;
using UnityEngine;

public enum NodeType { Start, Battle, Rest, End }

[Serializable]
public class Node
{
    public int id;
    public int layer;
    public int indexInLayer;
    public NodeType type;
    public Vector2 pos;
    public List<int> next = new();
}

[Serializable]
public class SimpleMap
{
    public List<Node> nodes = new();
    public int startId;
    public int endId;
}

public class MapGenerator : MonoBehaviour
{
    [Header("Shape")]
    public int middleLayers = 6;

    [Header("Layout (optional)")]
    public float xStep = 5;
    public float yOffset = 2;

    public SimpleMap Generate()
    {
        var rng = new System.Random();
        var map = new SimpleMap();
        var layerIds = new List<List<int>>();

        int idCounter = 0;

        layerIds.Add(new List<int>());
        {
            var n = new Node
            {
                id = idCounter++,
                layer = 0,
                indexInLayer = 0,
                type = NodeType.Start
            };
            map.nodes.Add(n);
            map.startId = n.id;
            layerIds[0].Add(n.id);
        }

        for (int layer = 1; layer <= middleLayers; layer++)
        {
            int count = rng.Next(0, 2) == 0 ? 1 : 2;

            layerIds.Add(new List<int>());
            for (int i = 0; i < count; i++)
            {
                var n = new Node
                {
                    id = idCounter++,
                    layer = layer,
                    indexInLayer = i,
                    type = NodeType.Battle
                };
                if(i == 1) n.type = NodeType.Rest;
                map.nodes.Add(n);
                layerIds[layer].Add(n.id);
            }
        }

        int endLayer = middleLayers + 1;
        layerIds.Add(new List<int>());
        {
            var n = new Node
            {
                id = idCounter++,
                layer = endLayer,
                indexInLayer = 0,
                type = NodeType.End
            };
            map.nodes.Add(n);
            map.endId = n.id;
            layerIds[endLayer].Add(n.id);
        }

        for (int layer = 0; layer < endLayer; layer++)
        {
            var cur = layerIds[layer];
            var nxt = layerIds[layer + 1];

            if (cur.Count == 1 && nxt.Count == 1)
            {
                AddEdge(map, cur[0], nxt[0]);
            }
            else if (cur.Count == 1 && nxt.Count == 2)
            {
                AddEdge(map, cur[0], nxt[0]);
                AddEdge(map, cur[0], nxt[1]);
            }
            else if (cur.Count == 2 && nxt.Count == 1)
            {
                AddEdge(map, cur[0], nxt[0]);
                AddEdge(map, cur[1], nxt[0]);
            }
            else
            {
                AddEdge(map, cur[0], nxt[0]);
                AddEdge(map, cur[1], nxt[1]);
            }
        }

        ApplyLayout(map, layerIds);

        return map;
    }

    private static void AddEdge(SimpleMap map, int from, int to)
    {
        var n = map.nodes[from];
        if (!n.next.Contains(to)) n.next.Add(to);
    }

    private void ApplyLayout(SimpleMap map, List<List<int>> layerIds)
    {
        for (int layer = 0; layer < layerIds.Count; layer++)
        {
            var ids = layerIds[layer];
            if (ids.Count == 1)
            {
                map.nodes[ids[0]].pos = new Vector2(layer * xStep, 0f);
            }
            else
            {
                map.nodes[ids[0]].pos = new Vector2(layer * xStep, +yOffset);
                map.nodes[ids[1]].pos = new Vector2(layer * xStep, -yOffset);
            }
        }
    }
}
