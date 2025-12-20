using UnityEngine;
using UnityEngine.EventSystems;

public class Matchstick : MonoBehaviour, IPointerClickHandler
{
    public MatchManager matchManager;
    private Transform originalParent;

    private void OnEnable()
    {
        originalParent = transform.parent;
    }

    public void OnPointerClick(PointerEventData eventData)
    {
        // 남은 이동이 없다면 무시
        if(GameManager.instance.MoveCount == 0) return;

        // 성냥 선택
        if(matchManager.selectedMatch == null)
        {
            matchManager.selectedMatch = transform;
            // transform.SetParent(MatchManager.Instance.transform);
        }

        // 성냥 놓기
        else if(matchManager.selectedMatch == transform)
        {
            matchManager.selectedMatch = null;

            Transform bestSlot = matchManager.GetNearestSlot(transform.position);

            if(bestSlot == null)
            {
                transform.position = transform.parent.position;
                return;
            }

            transform.SetPositionAndRotation(bestSlot.position, bestSlot.rotation);
            transform.SetParent(bestSlot);
        }
    }

    void Update()
    {
        // 선택된 성냥이면 마우스 따라가기
        if(matchManager.selectedMatch == transform)
        {
            transform.position = Input.mousePosition;
        }
    }
}
