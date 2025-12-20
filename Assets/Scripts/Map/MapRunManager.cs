using UnityEngine;

public class MapRunManager : MonoBehaviour
{
    public static MapRunManager Instance { get; private set; }

    public SimpleMap map = null;
    public int currentNodeId;

    private void Awake()
    {
        if (Instance != null)
        {
            Destroy(gameObject);
            return;
        }

        Instance = this;
        DontDestroyOnLoad(gameObject);
    }

    public bool HasMap => map != null && map.nodes != null && map.nodes.Count > 0;
}
