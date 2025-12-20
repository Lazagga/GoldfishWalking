using UnityEngine;

[RequireComponent(typeof(Collider2D))]
public class NodeWorldView : MonoBehaviour
{
    public int nodeId;

    private MapWorldController controller;

    public void Init(MapWorldController controller, int nodeId)
    {
        this.controller = controller;
        this.nodeId = nodeId;
    }

    private void OnMouseDown()
    {
        if (controller == null) return;
        controller.TrySelectNode(nodeId);
    }

    public void SetSelectable(bool selectable)
    {
        var sr = GetComponent<SpriteRenderer>();
        if (sr != null)
        {
            var c = sr.color;
            c.a = selectable ? 1f : 0.25f;
            sr.color = c;
        }
    }
}
