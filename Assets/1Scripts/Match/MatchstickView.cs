using UnityEngine;

namespace GoldfishWalking.Match
{
    public sealed class MatchstickView : MonoBehaviour
    {
        [SerializeField] private bool locked;

        public bool Locked => locked;

        private void Awake()
        {
            MatchstickVisualSettings.Apply(GetComponent<UnityEngine.UI.Image>());
        }

        public void SetLocked(bool value)
        {
            locked = value;
        }
    }
}
