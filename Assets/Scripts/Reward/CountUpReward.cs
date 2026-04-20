public class CountUpReward : IReward
{
    public string DisplayName => "Move +1";
    public void Apply(PlayerRunData data) => data.AddMaxMoveCount();
}
