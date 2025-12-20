using UnityEngine;
using UnityEngine.UI;

public class RewardManager : MonoBehaviour
{
    public Button Count;
    public Button Oper;
    public Button Reward;

    private void Awake()
    {
        Count.GetComponent<Button>().onClick.AddListener(OnCount);
        Oper.GetComponent<Button>().onClick.AddListener(OnOper);
        OnClearBattle();
    }

    public void OnCount()
    {
        GameManager.instance.MaxMoveCount++;
        Count.GetComponent<Animator>().SetTrigger("Choose");
        Oper.GetComponent<Animator>().SetTrigger("Choose");
    }

    public void OnOper()
    {
        //연산기호 랜덤 하나 추가
        Count.GetComponent<Animator>().SetTrigger("Choose");
        Oper.GetComponent<Animator>().SetTrigger("Choose");
    }

    public void OnClearBattle()
    {
        Count.GetComponent<Animator>().SetTrigger("Clear");
        Oper.GetComponent<Animator>().SetTrigger("Clear");
    }
}
