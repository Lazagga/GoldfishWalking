using UnityEngine;

namespace GoldfishWalking.Match
{
    public sealed class MatchDigitView : MonoBehaviour
    {
        [SerializeField] private int value;

        public int Value => value;

        public void SetValue(int newValue)
        {
            value = Mathf.Clamp(newValue, 0, 9);
        }
    }
}
