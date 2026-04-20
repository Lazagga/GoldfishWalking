using TMPro;
using UnityEngine;

/// <summary>
/// PlayerRunData 이벤트를 구독하여 HUD를 갱신한다.
/// PlayerData(구 싱글톤)의 UI 책임을 분리한 컴포넌트.
/// </summary>
public class PlayerHUD : MonoBehaviour
{
    [Header("Data")]
    public PlayerRunData playerData;

    [Header("UI")]
    public TMP_Text healthText;
    public TMP_Text moveCountText;

    private void OnEnable()
    {
        playerData.OnHealthChanged       += UpdateHealth;
        playerData.OnMaxMoveCountChanged += _ => RefreshMoveCountMax();
        GameEvents.OnMoveCountChanged    += UpdateMoveCountRemaining;

        // 초기값 표시
        UpdateHealth(playerData.health);
        RefreshMoveCountMax();
    }

    private void OnDisable()
    {
        playerData.OnHealthChanged       -= UpdateHealth;
        playerData.OnMaxMoveCountChanged -= _ => RefreshMoveCountMax();
        GameEvents.OnMoveCountChanged    -= UpdateMoveCountRemaining;
    }

    private void UpdateHealth(int hp)
        => healthText.text = $"HP = {hp}";

    private void RefreshMoveCountMax()
        => moveCountText.text = $"? / {playerData.maxMoveCount}";

    private void UpdateMoveCountRemaining(int remaining)
        => moveCountText.text = $"{remaining} / {playerData.maxMoveCount}";
}
