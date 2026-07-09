namespace GoldfishWalking.Match
{
    public readonly struct MatchEditResult
    {
        public readonly bool success;
        public readonly string message;

        public MatchEditResult(bool success, string message)
        {
            this.success = success;
            this.message = message;
        }

        public static MatchEditResult Ok()
        {
            return new MatchEditResult(true, string.Empty);
        }

        public static MatchEditResult Fail(string message)
        {
            return new MatchEditResult(false, message);
        }
    }
}