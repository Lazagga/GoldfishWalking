using System;

namespace GoldfishWalking.Match
{
    [Serializable]
    public sealed class MatchPiece
    {
        public string id;
        public MatchPieceKind kind;

        public bool CanMove => kind != MatchPieceKind.Locked;
        public bool CanErase => kind != MatchPieceKind.Locked;
        public bool IsAdded => kind == MatchPieceKind.Added;
    }
}