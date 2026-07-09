using GoldfishWalking.Formula;
using UnityEngine;
using UnityEngine.Events;

namespace GoldfishWalking.Match
{
    public sealed class MatchBoxController : MonoBehaviour
    {
        [SerializeField] private UnityEvent<string> validationFailed;

        public MatchEditSession CurrentSession { get; } = new MatchEditSession();

        public void Open(FormulaBox box)
        {
            if (box == null)
            {
                Warn("Formula box is missing.");
                return;
            }

            if (box.locked)
            {
                Warn("Locked boxes cannot be edited.");
                return;
            }

            CurrentSession.Open(box);
        }

        public void Commit()
        {
            MatchEditResult result = CurrentSession.Commit();
            WarnIfFailed(result);
        }

        public void ResetCurrentBox()
        {
            CurrentSession.ResetBox();
        }

        public void PickUp(int digitIndex, int segmentIndex)
        {
            WarnIfFailed(CurrentSession.TryPickUp(digitIndex, segmentIndex));
        }

        public void Place(int digitIndex, int segmentIndex)
        {
            WarnIfFailed(CurrentSession.TryPlace(digitIndex, segmentIndex));
        }

        public void Erase(int digitIndex, int segmentIndex)
        {
            WarnIfFailed(CurrentSession.TryErase(digitIndex, segmentIndex));
        }

        public void DropOutsideTable()
        {
            WarnIfFailed(CurrentSession.DropHeldPieceOutsideTable());
        }

        public void AddExtraMatch(string id)
        {
            MatchPiece piece = new MatchPiece
            {
                id = id,
                kind = MatchPieceKind.Added
            };

            WarnIfFailed(CurrentSession.AddExtraMatch(piece));
        }

        private void WarnIfFailed(MatchEditResult result)
        {
            if (!result.success)
                Warn(result.message);
        }

        private void Warn(string message)
        {
            Debug.LogWarning($"[MatchBoxController] {message}");
            validationFailed?.Invoke(message);
        }
    }
}