using UnityEngine;
using UnityEngine.EventSystems;

public class Matchstick : MonoBehaviour, IPointerClickHandler
{
    public MatchManager matchManager;

    private int remainingMoves;

    private void OnEnable()
    {
        GameEvents.OnMoveCountChanged += OnMoveCountChanged;
    }

    private void OnDisable()
    {
        GameEvents.OnMoveCountChanged -= OnMoveCountChanged;
    }

    private void OnMoveCountChanged(int remaining)
    {
        remainingMoves = remaining;
    }

    public void OnPointerClick(PointerEventData eventData)
    {
        if (remainingMoves == 0) return;

        // 성냥 선택
        if (matchManager.selectedMatch == null)
        {
            matchManager.selectedMatch = transform;
            return;
        }

        // 성냥 놓기
        if (matchManager.selectedMatch == transform)
        {
            matchManager.selectedMatch = null;

            Transform bestSlot = matchManager.GetNearestSlot(transform.position);

            if (bestSlot == null)
            {
                transform.position = transform.parent.position;
                return;
            }

            transform.SetPositionAndRotation(bestSlot.position, bestSlot.rotation);
            transform.SetParent(bestSlot);

            matchManager.UpdateState();
        }
    }

    private void Update()
    {
        transform.localScale = Vector3.one;
        if (matchManager.selectedMatch == transform)
            transform.position = Input.mousePosition;
    }
}
