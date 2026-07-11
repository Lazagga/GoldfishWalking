using UnityEngine;
using GoldfishWalking.Map;

namespace GoldfishWalking.Core
{
    public sealed class GameBootstrap : MonoBehaviour
    {
        private const int FinalAct = 3;

        [SerializeField] private int startingHealth = 150;
        [SerializeField] private int mapSeed;
        [SerializeField] private int mapRoomCount = 15;

        public RunContext RunContext { get; private set; }
        public GameStateMachine StateMachine { get; private set; }

        private void Awake()
        {
            RunContext = new RunContext();
            StateMachine = new GameStateMachine();
        }

        private void OnEnable()
        {
            GameEventHub.MapNodeSelected += OnMapNodeSelected;
            GameEventHub.BattleWon += OnBattleWon;
            GameEventHub.BattleLost += OnBattleLost;
            GameEventHub.BattleEscaped += OnBattleEscaped;
            GameEventHub.RewardCompleted += OnRewardCompleted;
            GameEventHub.RestCompleted += OnRestCompleted;
            GameEventHub.ShopClosed += OnShopClosed;
        }

        private void OnDisable()
        {
            GameEventHub.MapNodeSelected -= OnMapNodeSelected;
            GameEventHub.BattleWon -= OnBattleWon;
            GameEventHub.BattleLost -= OnBattleLost;
            GameEventHub.BattleEscaped -= OnBattleEscaped;
            GameEventHub.RewardCompleted -= OnRewardCompleted;
            GameEventHub.RestCompleted -= OnRestCompleted;
            GameEventHub.ShopClosed -= OnShopClosed;
        }

        private void Start()
        {
            StateMachine.ChangeState(GameState.Title);
        }

        public void StartNewRun()
        {
            int seed = mapSeed != 0 ? mapSeed : Random.Range(1, int.MaxValue);
            RunContext.StartNewRun(seed, startingHealth);
            RunContext.map = new MapGenerator().Generate(seed, RunContext.act, mapRoomCount);
            StateMachine.ChangeState(GameState.Map);
        }

        private void OnMapNodeSelected(MapNode node)
        {
            RunContext.AdvanceTo(node);

            switch (node.nodeType)
            {
                case MapNodeType.Rest:
                    StateMachine.ChangeState(GameState.Rest);
                    break;
                case MapNodeType.Shop:
                    StateMachine.ChangeState(GameState.Shop);
                    break;
                case MapNodeType.Boss:
                case MapNodeType.EliteBattle:
                case MapNodeType.NormalBattle:
                    StateMachine.ChangeState(GameState.Battle);
                    break;
                default:
                    StateMachine.ChangeState(GameState.Map);
                    break;
            }
        }

        private void OnBattleWon()
        {
            StateMachine.ChangeState(GameState.Reward);
        }

        private void OnBattleLost()
        {
            StateMachine.ChangeState(GameState.GameOver);
        }

        private void OnBattleEscaped()
        {
            StateMachine.ChangeState(GameState.Map);
        }

        private void OnRewardCompleted()
        {
            if (RunContext != null && RunContext.currentNode != null && RunContext.currentNode.nodeType == MapNodeType.Boss)
            {
                if (RunContext.act >= FinalAct)
                {
                    StateMachine.ChangeState(GameState.RunClear);
                    return;
                }

                int nextAct = RunContext.act + 1;
                RunMap nextMap = new MapGenerator().Generate(RunContext.seed, nextAct, mapRoomCount);
                RunContext.StartNextAct(nextMap);
                StateMachine.ChangeState(GameState.Map);
                return;
            }

            StateMachine.ChangeState(GameState.Map);
        }

        private void OnRestCompleted()
        {
            StateMachine.ChangeState(GameState.Map);
        }

        private void OnShopClosed()
        {
            StateMachine.ChangeState(GameState.Map);
        }
    }
}
