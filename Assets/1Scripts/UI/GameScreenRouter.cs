using GoldfishWalking.Core;
using UnityEngine;

namespace GoldfishWalking.UI
{
    public sealed class GameScreenRouter : MonoBehaviour
    {
        [SerializeField] private GameObject titleScreen;
        [SerializeField] private GameObject mapScreen;
        [SerializeField] private GameObject battleScreen;
        [SerializeField] private GameObject rewardScreen;
        [SerializeField] private GameObject restScreen;
        [SerializeField] private GameObject shopScreen;
        [SerializeField] private GameObject gameOverScreen;

        private void OnEnable()
        {
            GameEventHub.StateChanged += OnStateChanged;
        }

        private void OnDisable()
        {
            GameEventHub.StateChanged -= OnStateChanged;
        }

        private void OnStateChanged(GameState previous, GameState next)
        {
            SetActive(titleScreen, next == GameState.Title);
            SetActive(mapScreen, next == GameState.Map);
            SetActive(battleScreen, next == GameState.Battle || next == GameState.Reward);
            SetActive(rewardScreen, next == GameState.Reward);
            SetActive(restScreen, next == GameState.Rest);
            SetActive(shopScreen, next == GameState.Shop);
            SetActive(gameOverScreen, next == GameState.GameOver || next == GameState.RunClear);
        }

        private static void SetActive(GameObject target, bool active)
        {
            if (target != null)
                target.SetActive(active);
        }
    }
}
