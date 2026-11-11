using GoldfishWalking.Core;
using GoldfishWalking.Data;
using UnityEngine;
using UnityEngine.UI;

namespace GoldfishWalking.UI
{
    public sealed class SharedFantasyInventoryView : MonoBehaviour
    {
        [SerializeField] private GameBootstrap bootstrap;
        [SerializeField] private RectTransform fantasySlotsRoot;
        [SerializeField] private RectTransform contentRoot;
        [SerializeField] private FantasyListView fantasyListView;
        [SerializeField] private RectTransform tooltipRoot;
        [SerializeField] private FantasyTooltipView tooltipView;

        public static SharedFantasyInventoryView Instance { get; private set; }

        private void Awake()
        {
            Instance = this;
            ResolveReferences();
        }

        private void OnEnable()
        {
            Instance = this;
            GameEventHub.FantasyInventoryChanged += Refresh;
            GameEventHub.StateChanged += OnStateChanged;
            ResolveReferences();
            RefreshVisibility(CurrentState());
            Refresh();
        }

        private void OnDisable()
        {
            GameEventHub.FantasyInventoryChanged -= Refresh;
            GameEventHub.StateChanged -= OnStateChanged;
            if (Instance == this)
                Instance = null;
        }

        public void Emphasize(FantasyData fantasy)
        {
            fantasyListView?.Emphasize(fantasy);
        }

        private void ResolveReferences()
        {
            if (bootstrap == null)
                bootstrap = FindFirstObjectByType<GameBootstrap>(FindObjectsInactive.Include);
            if (fantasySlotsRoot == null)
                fantasySlotsRoot = transform.Find("FantasySlots") as RectTransform;
            if (contentRoot == null && fantasySlotsRoot != null)
                contentRoot = fantasySlotsRoot.Find("Viewport/Content") as RectTransform;
            if (fantasyListView == null && contentRoot != null)
                fantasyListView = contentRoot.GetComponent<FantasyListView>();
            if (tooltipRoot == null)
                tooltipRoot = transform.Find("FantasyTooltip") as RectTransform;
            if (tooltipView == null && tooltipRoot != null)
                tooltipView = tooltipRoot.GetComponent<FantasyTooltipView>();

            if (tooltipView != null && tooltipRoot != null)
            {
                tooltipView.Bind(
                    tooltipRoot.Find("Name")?.GetComponent<Text>(),
                    tooltipRoot.Find("Description")?.GetComponent<Text>(),
                    tooltipRoot.Find("Effect")?.GetComponent<Text>());
            }

            if (fantasyListView != null)
                fantasyListView.Bind(contentRoot, tooltipView, 10);
        }

        private void Refresh()
        {
            fantasyListView?.Refresh(
                bootstrap != null && bootstrap.RunContext != null && bootstrap.RunContext.fantasyInventory != null
                    ? bootstrap.RunContext.fantasyInventory.ownedFantasies
                    : null);
        }

        private void OnStateChanged(GameState previous, GameState next)
        {
            RefreshVisibility(next);
            if (IsVisibleIn(next))
                Refresh();
        }

        private void RefreshVisibility(GameState state)
        {
            bool visible = IsVisibleIn(state);
            if (fantasySlotsRoot != null)
                fantasySlotsRoot.gameObject.SetActive(visible);
            if (!visible && tooltipView != null)
                tooltipView.Hide();
        }

        private GameState CurrentState()
        {
            return bootstrap != null && bootstrap.StateMachine != null
                ? bootstrap.StateMachine.CurrentState
                : GameState.Boot;
        }

        private static bool IsVisibleIn(GameState state)
        {
            return state == GameState.Battle
                || state == GameState.EmberReward
                || state == GameState.Reward
                || state == GameState.Rest
                || state == GameState.Shop;
        }
    }
}
