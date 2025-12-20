using System.Collections;
using System.Collections.Generic;
using UnityEditor.Experimental.GraphView;
using UnityEngine;
using UnityEngine.SceneManagement;

public class MapWorldController : MonoBehaviour
{
    public CameraMovement cameraController;

    [Header("Prefabs")]
    public NodeWorldView nodePrefab;
    public LineRenderer linePrefab;

    [Header("World Layout")]
    public Vector3 worldOrigin = Vector3.zero;

    private SimpleMap map;

    private readonly Dictionary<int, NodeWorldView> nodeViews = new();
    private readonly List<LineRenderer> lines = new();

    private int currentNodeId = -1;

    private Coroutine renderRoutine;

    private void OnEnable()
    {
        SceneManager.sceneLoaded += OnSceneLoaded;

        StartRenderRoutine();
    }

    private void OnDisable()
    {
        SceneManager.sceneLoaded -= OnSceneLoaded;

        if (renderRoutine != null)
        {
            StopCoroutine(renderRoutine);
            renderRoutine = null;
        }
    }

    private void OnSceneLoaded(Scene scene, LoadSceneMode mode)
    {
        StartRenderRoutine();
    }

    private void StartRenderRoutine()
    {
        if (!isActiveAndEnabled) return;

        if (renderRoutine != null)
            StopCoroutine(renderRoutine);

        renderRoutine = StartCoroutine(CoRenderWhenReady());
    }

    private IEnumerator CoRenderWhenReady()
    {
        while (true)
        {
            var run = MapRunManager.Instance;
            if (run != null && run.map != null && run.map.nodes != null && run.map.nodes.Count > 0)
                break;

            yield return null;
        }

        GenerateAndRender();
        renderRoutine = null;
    }

    [ContextMenu("Generate And Render (World)")]
    public void GenerateAndRender()
    {
        ClearWorld();

        var run = MapRunManager.Instance;
        if (run == null)
        {
            Debug.LogError("[MapWorldController] MapRunManager missing");
            return;
        }

        if (run.map == null || run.map.nodes == null || run.map.nodes.Count == 0)
        {
            Debug.LogError("[MapWorldController] run.map is null or empty");
            return;
        }

        map = run.map;
        currentNodeId = run.currentNodeId;

        RenderFromMap(map);
        UpdateSelectable();

        Debug.Log($"[MapWorldController] Render done. nodes={map.nodes.Count} nodeViews={nodeViews.Count} lines={lines.Count}");
    }

    public void TrySelectNode(int nodeId)
    {
        if (map == null) return;
        if (nodeId == currentNodeId) return;

        var cur = GetNodeById(currentNodeId);
        if (cur == null) return;

        if (!cur.next.Contains(nodeId)) return;

        currentNodeId = nodeId;

        var run = MapRunManager.Instance;
        if (run != null) run.currentNodeId = nodeId;

        UpdateSelectable();

        var selectedNode = GetNodeById(nodeId);
        var worldPos = ToWorld(selectedNode.pos);

        // 카메라 이동 완료 후 씬 이동
        cameraController.MoveTo(worldPos, () =>
        {
            string SceneName = selectedNode.type.ToString();
            SceneManager.LoadScene(SceneName);
        });
    }

    private void RenderFromMap(SimpleMap map)
    {
        var byId = new Dictionary<int, Node>(map.nodes.Count);
        foreach (var n in map.nodes)
            byId[n.id] = n;

        // 1) 노드 생성
        foreach (var n in map.nodes)
        {
            var worldPos = ToWorld(n.pos);

            var view = Instantiate(nodePrefab, worldPos, Quaternion.identity, transform);
            view.name = $"Node_{n.id}_{n.type}";
            view.Init(this, n.id);

            nodeViews[n.id] = view;
        }

        // 2) 라인 생성 (유향)
        foreach (var from in map.nodes)
        {
            var fromWorld = ToWorld(from.pos);

            for (int j = 0; j < from.next.Count; j++)
            {
                int toId = from.next[j];
                if (!byId.TryGetValue(toId, out var to))
                {
                    Debug.LogError($"[MapWorldController] Invalid edge: from {from.id} to {toId} (toId not found)");
                    continue;
                }

                var toWorld = ToWorld(to.pos);

                var lr = Instantiate(linePrefab, Vector3.zero, Quaternion.identity, transform);
                lr.name = $"Edge_{from.id}_to_{toId}";
                lr.positionCount = 2;
                lr.useWorldSpace = true;
                lr.SetPosition(0, fromWorld);
                lr.SetPosition(1, toWorld);

                lines.Add(lr);
            }
        }
    }

    private void UpdateSelectable()
    {
        if (map == null) return;

        var cur = GetNodeById(currentNodeId);
        if (cur == null) return;

        var selectable = new HashSet<int>(cur.next) { currentNodeId };

        foreach (var kv in nodeViews)
            kv.Value.SetSelectable(selectable.Contains(kv.Key));
    }

    private Node GetNodeById(int id)
    {
        if (map == null || map.nodes == null) return null;
        for (int i = 0; i < map.nodes.Count; i++)
        {
            if (map.nodes[i].id == id) return map.nodes[i];
        }
        return null;
    }

    private Vector3 ToWorld(Vector2 p)
    {
        return worldOrigin + new Vector3(p.x, p.y, 0f);
    }

    private void ClearWorld()
    {
        foreach (var kv in nodeViews)
        {
            if (kv.Value == null) continue;
            if (Application.isPlaying) Destroy(kv.Value.gameObject);
            else DestroyImmediate(kv.Value.gameObject);
        }
        nodeViews.Clear();

        foreach (var lr in lines)
        {
            if (lr == null) continue;
            if (Application.isPlaying) Destroy(lr.gameObject);
            else DestroyImmediate(lr.gameObject);
        }
        lines.Clear();
    }
}
