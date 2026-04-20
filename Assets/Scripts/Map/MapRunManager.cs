using UnityEngine;

/// <summary>
/// 현재 맵 런 데이터를 보관한다.
/// 단일 Game 씬 내에서만 동작하므로 DontDestroyOnLoad 불필요.
/// </summary>
public class MapRunManager : MonoBehaviour
{
    public static MapRunManager Instance { get; private set; }

    public SimpleMap map;
    public int currentNodeId;

    private void Awake()
    {
        Instance = this;
    }

    public bool HasMap => map != null && map.nodes != null && map.nodes.Count > 0;
}
