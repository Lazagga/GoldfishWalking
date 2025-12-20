using UnityEngine;

public class MapBootstrap : MonoBehaviour
{
    public MapGenerator generator;

    private void Start()
    {
        var run = MapRunManager.Instance;

        if (run.map != null && run.map.nodes != null && run.map.nodes.Count > 0) return;

        run.map = generator.Generate();
        run.currentNodeId = run.map.startId;
    }
}
