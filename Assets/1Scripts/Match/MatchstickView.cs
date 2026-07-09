using UnityEngine;

namespace GoldfishWalking.Match
{
    public sealed class MatchstickView : MonoBehaviour
    {
        [SerializeField] private bool locked;

        public bool Locked => locked;

        public void SetLocked(bool value)
        {
            locked = value;
        }
    }
}
