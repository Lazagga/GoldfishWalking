using UnityEngine;
using UnityEngine.EventSystems;

public class Matchstick : MonoBehaviour, IPointerClickHandler
{

    public void OnPointerClick(PointerEventData eventData)
    {
        // 성냥 선택
        if(MatchManager.Instance.selectedMatch == null)
        {
            MatchManager.Instance.selectedMatch = transform;
            transform.SetParent(MatchManager.Instance.transform);
        }

        // 성냥 놓기
        else if(MatchManager.Instance.selectedMatch == transform)
        {
            MatchManager.Instance.selectedMatch = null;

            Transform bestSlot = MatchManager.Instance.getNearestSlot(transform.position);

            if(bestSlot == null) return;

            transform.SetPositionAndRotation(bestSlot.position, bestSlot.rotation);
            transform.SetParent(bestSlot);
        }
    }

    void Update()
    {
        // 선택된 성냥이면 마우스 따라가기
        if(MatchManager.Instance.selectedMatch == transform)
        {
            transform.position = Input.mousePosition;
        }
    }
}
