using GoldfishWalking.Core;
using UnityEngine;
using UnityEngine.UI;

namespace GoldfishWalking.UI
{
    public sealed class PlayerHudView : MonoBehaviour
    {
        [SerializeField] private GameBootstrap bootstrap;
        [SerializeField] private Text healthText;
        [SerializeField] private Text roomText;

        private void Update()
        {
            if (bootstrap == null || bootstrap.RunContext == null)
                return;

            if (healthText != null)
                healthText.text = bootstrap.RunContext.health.ToString();

            if (roomText != null)
                roomText.text = bootstrap.RunContext.roomIndex.ToString();
        }
    }
}
