using System.Collections.Generic;
using System.Linq;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// Reward 패널 전담 컨트롤러.
/// Strategy 패턴: IReward 목록에서 랜덤 2개를 선택해 제시한다.
/// 새 보상 추가 = rewardPool에 항목 추가만으로 완결.
/// </summary>
public class RewardManager : MonoBehaviour
{
    [Header("Player Data")]
    public PlayerRunData playerData;

    [Header("UI")]
    public Button Left, Right;

    private IReward leftReward;
    private IReward rightReward;

    private readonly List<IReward> rewardPool = new()
    {
        new CountUpReward(),
        // new OperatorReward(),
        // new RemoverReward(),
    };

    private void OnEnable()
    {
        ShowRewards();
    }

    private void ShowRewards()
    {
        var shuffled = rewardPool.OrderBy(_ => Random.value).ToList();

        leftReward  = shuffled[0];
        rightReward = shuffled.Count > 1 ? shuffled[1] : shuffled[0];

        Left.GetComponentInChildren<TMP_Text>().text  = leftReward.DisplayName;
        Right.GetComponentInChildren<TMP_Text>().text = rightReward.DisplayName;

        Left.GetComponent<Animator>().SetTrigger("Up");
        Right.GetComponent<Animator>().SetTrigger("Up");
    }

    public void OnLeft()
    {
        leftReward.Apply(playerData);
        Complete();
    }

    public void OnRight()
    {
        rightReward.Apply(playerData); // 수정: 기존 코드는 rightReward에서도 LeftNum을 체크하는 버그 있었음
        Complete();
    }

    private void Complete()
    {
        Left.GetComponent<Animator>().SetTrigger("Down");
        Right.GetComponent<Animator>().SetTrigger("Down");
        GameEvents.RewardCompleted();
    }
}
