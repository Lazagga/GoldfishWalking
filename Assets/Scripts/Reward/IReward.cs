/// <summary>
/// Strategy 패턴: 모든 보상 타입이 구현하는 인터페이스.
/// 새 보상 추가 = 이 인터페이스를 구현한 클래스 추가만으로 완결.
/// </summary>
public interface IReward
{
    string DisplayName { get; }
    void Apply(PlayerRunData data);
}
