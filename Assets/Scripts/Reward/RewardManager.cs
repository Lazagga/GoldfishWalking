using UnityEngine;
using UnityEngine.UI;
using TMPro;

public class RewardManager : MonoBehaviour
{
    public Button Left, Right;

    public enum RewardType
    {
        CountUp,
        Operator,
        Additional,
        Remover
    }

    public int LeftNum, RightNum;
    public RewardType leftReward, rightReward;

    private void Update()
    {
        if(Input.GetMouseButtonDown(0))
        {
            ShowRewards();
        }
    }

    public void ShowRewards()
    {
        LeftNum = Random.Range(0, 3);
        RightNum = Random.Range(0, 3);
        while(RightNum == LeftNum) RightNum = Random.Range(0, 3);
        if (LeftNum > RightNum)
        {
            int temp = LeftNum;
            LeftNum = RightNum;
            RightNum = temp;
        }

        leftReward = (RewardType)LeftNum;
        rightReward = (RewardType)RightNum;

        Left.GetComponentInChildren<TMP_Text>().text = leftReward.ToString();
        Right.GetComponentInChildren<TMP_Text>().text = rightReward.ToString();

        Left.GetComponent<Animator>().SetTrigger("Up");
        Right.GetComponent<Animator>().SetTrigger("Up");
    }

    public void OnLeft()
    {
        if(LeftNum == 0) PlayerData.Instance.AddMaxCount();
        //else if (LeftNum == 1) PlayerData.Instance.GetComponent<OperatorManager>().ShowOperators();
        //else if (LeftNum == 2) PlayerData.Instance.GetComponent<ItemManager>().ShowAdditionalItems();
        //else if (LeftNum == 3) PlayerData.Instance.GetComponent<ItemManager>().ShowRemoverItems();
        Left.GetComponent<Animator>().SetTrigger("Down");
        Right.GetComponent<Animator>().SetTrigger("Down");
    }

    public void OnRight()
    {
        if (LeftNum == 0) PlayerData.Instance.AddMaxCount();
        //else if (LeftNum == 1) PlayerData.Instance.GetComponent<OperatorManager>().ShowOperators();
        //else if (LeftNum == 2) PlayerData.Instance.GetComponent<ItemManager>().ShowAdditionalItems();
        //else if (LeftNum == 3) PlayerData.Instance.GetComponent<ItemManager>().ShowRemoverItems();
        Left.GetComponent<Animator>().SetTrigger("Down");
        Right.GetComponent<Animator>().SetTrigger("Down");
    }
}
