using System;
using GoldfishWalking.Map;

namespace GoldfishWalking.Core
{
    public static class GameEventHub
    {
        public static event Action<GameState, GameState> StateChanged;
        public static event Action<MapNode> MapNodeSelected;
        public static event Action BattleWon;
        public static event Action BattleLost;
        public static event Action RewardCompleted;
        public static event Action RestCompleted;
        public static event Action ShopClosed;
        public static event Action ItemInventoryChanged;

        public static void RaiseStateChanged(GameState previous, GameState next)
        {
            StateChanged?.Invoke(previous, next);
        }

        public static void RaiseMapNodeSelected(MapNode node)
        {
            MapNodeSelected?.Invoke(node);
        }

        public static void RaiseBattleWon()
        {
            BattleWon?.Invoke();
        }

        public static void RaiseBattleLost()
        {
            BattleLost?.Invoke();
        }

        public static void RaiseRewardCompleted()
        {
            RewardCompleted?.Invoke();
        }

        public static void RaiseRestCompleted()
        {
            RestCompleted?.Invoke();
        }

        public static void RaiseShopClosed()
        {
            ShopClosed?.Invoke();
        }

        public static void RaiseItemInventoryChanged()
        {
            ItemInventoryChanged?.Invoke();
        }
    }
}
