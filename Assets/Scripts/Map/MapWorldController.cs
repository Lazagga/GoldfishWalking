using System.Collections;
using System.Collections.Generic;
using UnityEngine;

/// <summary>
/// Map 패널 전담 컨트롤러.
/// OnEnable 시 MapRunManager에서 맵 데이터를 읽어 렌더링한다.
/// 노드 선택 시 SceneManager 대신 GameEvents.NodeSelected를 발행한다.
/// </summary>
public class MapWorldController : MonoBehaviour
{
    public CameraMovement cameraController;
    public Sprite Battle, Rest, Boss;

    [Header("Prefabs")]
    public NodeWorldView nodePrefab;
    public LineRenderer linePrefab;

    [Header("World Layout")]
    public Vector3 worldOrigin = Vector3.zero;

    private SimpleMap map;
    private readonly Dictionary<int, NodeWorldView> nodeViews = new();
    private readonly List<LineRenderer> lines = new();

    private void OnEnable()
    {
        var run = MapRunManager.Instance;
        if (run == null || !run.HasMap)
        {
            Debug.LogError("[MapWorldController] MapRunManager에 맵 데이터가 없음");
            return;
        }

        map = run.map;
        cameraController.MoveTo(ToWorld(map.nodes[run.currentNodeId].pos));

        RenderFromMap(map);
        UpdateSelectable(run.currentNodeId);
    }

    private void OnDisable()
    {
        ClearWorld();
    }

    public void TrySelectNode(int nodeId)
    {
        if (map == null) return;

        var run = MapRunManager.Instance;
        int currentId = run.currentNodeId;

        if (nodeId == currentId) return;

        var cur = GetNodeById(currentId);
        if (cur == null || !cur.next.Contains(nodeId)) return;

        UpdateSelectable(nodeId);

        var selected = GetNodeById(nodeId);
        var worldPos = ToWorld(selected.pos);

        // 카메라 이동 완료 후 GameEvents로 전환 요청
        cameraController.MoveTo(worldPos, onArrived: () =>
        {
            GameEvents.NodeSelected(nodeId, selected.type);
        });
    }

    private void RenderFromMap(SimpleMap map)
    {
        var byId = new Dictionary<int, Node>(map.nodes.Count);
        foreach (var n in map.nodes) byId[n.id] = n;

        foreach (var n in map.nodes)
        {
            var worldPos = ToWorld(n.pos);
            var view = Instantiate(nodePrefab, worldPos, Quaternion.identity, transform);
            view.transform.localScale = Vector3.one * 8;
            view.GetComponent<SpriteRenderer>().sprite = n.type switch
            {
                NodeType.Start   => Battle,
                NodeType.Battle  => Battle,
                NodeType.Battle2 => Battle,
                NodeType.Rest    => Rest,
                NodeType.End     => Boss,
                _                => null
            };
            view.name = $"Node_{n.id}_{n.type}";
            view.Init(this, n.id);
            nodeViews[n.id] = view;
        }

        foreach (var from in map.nodes)
        {
            var fromWorld = ToWorld(from.pos);
            foreach (int toId in from.next)
            {
                if (!byId.TryGetValue(toId, out var to)) continue;

                var lr = Instantiate(linePrefab, Vector3.zero, Quaternion.identity, transform);
                lr.name = $"Edge_{from.id}_to_{toId}";
                lr.positionCount = 2;
                lr.useWorldSpace = true;
                lr.SetPosition(0, fromWorld);
                lr.SetPosition(1, ToWorld(to.pos));
                lines.Add(lr);
            }
        }
    }

    private void UpdateSelectable(int currentId)
    {
        var cur = GetNodeById(currentId);
        if (cur == null) return;

        var selectable = new HashSet<int>(cur.next) { currentId };
        foreach (var kv in nodeViews)
            kv.Value.SetSelectable(selectable.Contains(kv.Key));
    }

    private Node GetNodeById(int id)
    {
        if (map?.nodes == null) return null;
        foreach (var n in map.nodes)
            if (n.id == id) return n;
        return null;
    }

    private Vector3 ToWorld(Vector2 p) => worldOrigin + new Vector3(p.x, p.y, 0f);

    private void ClearWorld()
    {
        foreach (var kv in nodeViews)
            if (kv.Value != null) Destroy(kv.Value.gameObject);
        nodeViews.Clear();

        foreach (var lr in lines)
            if (lr != null) Destroy(lr.gameObject);
        lines.Clear();

        map = null;
    }
}
