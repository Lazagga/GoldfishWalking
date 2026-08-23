using UnityEngine;
using GoldfishWalking.Map;
using System.Globalization;

namespace GoldfishWalking.Core
{
    public sealed class GameBootstrap : MonoBehaviour
    {
        private const int FinalAct = 3;

        [SerializeField] private int startingHealth = 150;
        [SerializeField] private int mapSeed;
        [SerializeField] private bool useFixedSeed;
        [SerializeField] private int mapRoomCount = 15;

        public RunContext RunContext { get; private set; }
        public GameStateMachine StateMachine { get; private set; }
        public int CurrentSeed => RunContext != null && RunContext.seed != 0 ? RunContext.seed : mapSeed;
        public bool HasActiveSeed => RunContext != null && RunContext.seed != 0;
        public string SeedInputText => useFixedSeed || mapSeed != 0 ? mapSeed.ToString(CultureInfo.InvariantCulture) : string.Empty;

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
            int seed = useFixedSeed || mapSeed != 0 ? mapSeed : Random.Range(1, int.MaxValue);
            StartRun(seed);
        }

        public void RestartWithNewSeed()
        {
            int previousSeed = RunContext != null ? RunContext.seed : 0;
            int seed;
            do
            {
                seed = Random.Range(1, int.MaxValue);
            }
            while (seed == previousSeed);

            StartRun(seed);
        }

        public void RestartWithCurrentSeed()
        {
            int seed = RunContext != null && RunContext.seed != 0
                ? RunContext.seed
                : (useFixedSeed || mapSeed != 0 ? mapSeed : Random.Range(1, int.MaxValue));
            StartRun(seed);
        }

        public void ReturnToTitle()
        {
            StateMachine.ChangeState(GameState.Title);
        }

        private void StartRun(int seed)
        {
            RunContext.StartNewRun(seed, startingHealth);
            RunContext.map = new MapGenerator().Generate(seed, RunContext.act, mapRoomCount);
            StateMachine.ChangeState(GameState.Map);
        }

        public void SetSeedFromText(string seedText)
        {
            if (string.IsNullOrWhiteSpace(seedText))
            {
                useFixedSeed = false;
                mapSeed = 0;
                return;
            }

            if (!int.TryParse(seedText, NumberStyles.Integer, CultureInfo.InvariantCulture, out int parsedSeed))
                return;

            useFixedSeed = true;
            mapSeed = parsedSeed;
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
