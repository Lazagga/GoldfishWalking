using GoldfishWalking.Core;
using GoldfishWalking.Data;
using GoldfishWalking.Fantasy;
using GoldfishWalking.Formula;
using GoldfishWalking.Map;
using UnityEngine;

namespace GoldfishWalking.Battle
{
    public sealed class BattleController : MonoBehaviour
    {
        [SerializeField] private GameBootstrap bootstrap;
        [SerializeField] private MonsterDatabase monsterDatabase;
        [SerializeField] private MonsterPatternDatabase monsterPatternDatabase;

        private readonly MonsterSelector monsterSelector = new MonsterSelector();
        private readonly MonsterPatternRunner monsterPatternRunner = new MonsterPatternRunner();
        private readonly FormulaEvaluator formulaEvaluator = new FormulaEvaluator();
        private readonly BattleFormulaBuilder formulaBuilder = new BattleFormulaBuilder();
        private readonly FantasyEffectRunner fantasyEffectRunner = new FantasyEffectRunner();
        private BattleContext context;

        public int PlayerBaseDamage => bootstrap != null && bootstrap.RunContext != null && bootstrap.RunContext.currentBattle != null
            ? bootstrap.RunContext.currentBattle.playerBaseDamage
            : 0;

        public int PlayerDamageDigitCount => bootstrap != null && bootstrap.RunContext != null
            ? GetPlayerDamageDigitCount(bootstrap.RunContext)
            : 2;

        public int MonsterBaseDamage => bootstrap != null && bootstrap.RunContext != null && bootstrap.RunContext.currentBattle != null
            ? bootstrap.RunContext.currentBattle.monsterBaseDamage
            : 0;

        public int MonsterHitCount => bootstrap != null && bootstrap.RunContext != null && bootstrap.RunContext.currentBattle != null
            ? bootstrap.RunContext.currentBattle.monsterHitCount
            : 1;

        public string PlayerBaseDamageSegmentState => bootstrap != null && bootstrap.RunContext != null && bootstrap.RunContext.currentBattle != null
            ? bootstrap.RunContext.currentBattle.playerBaseDamageSegmentState
            : string.Empty;

        public string MonsterBaseDamageSegmentState => bootstrap != null && bootstrap.RunContext != null && bootstrap.RunContext.currentBattle != null
            ? bootstrap.RunContext.currentBattle.monsterBaseDamageSegmentState
            : string.Empty;

        public string MonsterHitCountSegmentState => bootstrap != null && bootstrap.RunContext != null && bootstrap.RunContext.currentBattle != null
            ? bootstrap.RunContext.currentBattle.monsterHitCountSegmentState
            : string.Empty;

        public string MonsterDisplayName
        {
            get
            {
                MonsterData data = context != null && context.monster != null ? context.monster.Data : null;
                if (data == null)
                    return "Monster";
                if (!string.IsNullOrWhiteSpace(data.displayName))
                    return data.displayName;
                if (!string.IsNullOrWhiteSpace(data.dataName))
                    return data.dataName;
                if (!string.IsNullOrWhiteSpace(data.devName))
                    return data.devName;
                return !string.IsNullOrWhiteSpace(data.id) ? data.id : "Monster";
            }
        }

        public int MonsterCurrentHealth => context != null && context.monster != null
            ? Mathf.Max(0, context.monster.CurrentHealth)
            : 0;

        public int MonsterMaxHealth => context != null && context.monster != null && context.monster.Data != null
            ? Mathf.Max(1, context.monster.Data.baseHealth)
            : 1;

        public int CurrentMoveLimit => bootstrap != null && bootstrap.RunContext != null
            ? GetCurrentMoveLimit()
            : 2;

        public void SetUsedMoveCount(int usedMoveCount)
        {
            if (bootstrap == null || bootstrap.RunContext == null)
                return;

            bootstrap.RunContext.remainingMoveCount = Mathf.Max(0, CurrentMoveLimit - Mathf.Max(0, usedMoveCount));
            bootstrap.RunContext.temporaryMoveBonus = 0;
        }

        private int GetCurrentMoveLimit()
        {
            int limit = 2;
            limit = fantasyEffectRunner.ModifyValue(bootstrap.RunContext, limit, "Passive", "Movement");
            limit = fantasyEffectRunner.ModifyValue(bootstrap.RunContext, limit, "Battle_Start", "Movement");
            limit = fantasyEffectRunner.ModifyValue(bootstrap.RunContext, limit, "Turn_Start", "Movement");
            limit += bootstrap.RunContext.temporaryMoveBonus;
            return Mathf.Max(0, limit);
        }

        private void OnEnable()
        {
            GameEventHub.StateChanged += OnStateChanged;
        }

        private void OnDisable()
        {
            GameEventHub.StateChanged -= OnStateChanged;
        }

        public void ResolveBattle()
        {
            if (context == null || context.state != BattleState.Editing)
                return;

            context.state = BattleState.Resolving;
            BattleFormulaResult playerResult = formulaEvaluator.EvaluateBattleFormula(context.playerFormula);

            if (!playerResult.isValid)
            {
                Debug.LogWarning($"[BattleController] Invalid player formula: {playerResult.error}");
                context.state = BattleState.Editing;
                return;
            }

            BattleFormulaResult monsterResult = formulaEvaluator.EvaluateBattleFormula(context.monsterFormula);
            if (!monsterResult.isValid)
            {
                Debug.LogWarning($"[BattleController] Invalid monster formula: {monsterResult.error}");
                context.state = BattleState.Editing;
                return;
            }

            ApplyFormulaToMonster(playerResult);
            ApplyTurnEndFantasyEffects();
            if (CompleteBattleResolution())
                return;

            if (monsterPatternRunner.IsAttackPattern(context.monsterPattern))
                ApplyFormulaToPlayer(monsterResult);
            if (!CompleteBattleResolution())
            {
                context.state = BattleState.Editing;
                PrepareTurn(context.run.battleTurnNumber + 1, true);
            }
        }

        public void ResetBattle()
        {
            StartBattle();
        }

        private void OnStateChanged(GameState previous, GameState next)
        {
            if (next == GameState.Battle)
                StartBattle();
        }

        private void StartBattle()
        {
            if (bootstrap == null || bootstrap.RunContext == null)
            {
                Debug.LogWarning("[BattleController] Missing GameBootstrap reference.");
                return;
            }

            MonsterData selectedMonster = monsterSelector.Select(
                monsterDatabase,
                bootstrap.RunContext,
                bootstrap.RunContext.currentNode != null
                    ? bootstrap.RunContext.currentNode.nodeType
                    : MapNodeType.NormalBattle);

            bootstrap.RunContext.ClearBattleRuntimeValues();
            context = new BattleContext
            {
                run = bootstrap.RunContext,
                sourceNode = bootstrap.RunContext.currentNode,
                monster = new MonsterRuntime(selectedMonster),
                state = BattleState.Editing
            };

            BattleNumberState numbers = bootstrap.RunContext.EnsureBattleNumbers(monsterHitCount: 1);
            numbers.monsterId = selectedMonster != null ? selectedMonster.id : string.Empty;
            if (!numbers.battleStartFantasyApplied)
            {
                fantasyEffectRunner.ApplyTrigger(bootstrap.RunContext, "Battle_Start");
                EnsurePlayerBaseDamageDigitCount(numbers);
                numbers.playerBaseDamage = fantasyEffectRunner.ModifyValue(bootstrap.RunContext, numbers.playerBaseDamage, string.Empty, "Base_Damage");
                numbers.battleStartFantasyApplied = true;
            }

            PrepareTurn(1, true);
        }

        public void SetPlayerBaseDamage(int value)
        {
            SetPlayerBaseDamage(value, string.Empty);
        }

        public void SetPlayerBaseDamage(int value, string segmentState)
        {
            if (bootstrap == null || bootstrap.RunContext == null)
                return;

            BattleNumberState numbers = bootstrap.RunContext.EnsureBattleNumbers(monsterHitCount: MonsterHitCount);
            numbers.playerBaseDamage = Mathf.Max(0, value);
            numbers.playerBaseDamageSegmentState = segmentState;
            if (context != null)
                context.playerFormula = formulaBuilder.BuildPlayerFormula(bootstrap.RunContext, numbers.playerBaseDamage);
        }

        public void SetMonsterBaseDamage(int value)
        {
            SetMonsterBaseDamage(value, string.Empty);
        }

        public void SetMonsterBaseDamage(int value, string segmentState)
        {
            if (bootstrap == null || bootstrap.RunContext == null)
                return;

            BattleNumberState numbers = bootstrap.RunContext.EnsureBattleNumbers(monsterHitCount: MonsterHitCount);
            numbers.monsterBaseDamage = Mathf.Max(0, value);
            numbers.monsterBaseDamageSegmentState = segmentState;
            if (context != null)
                context.monsterFormula = formulaBuilder.BuildMonsterFormula(numbers.monsterBaseDamage, numbers.monsterHitCount, true);
        }

        private void PrepareTurn(int turnNumber, bool applyTurnStartEffects)
        {
            if (context == null || context.run == null)
                return;

            context.run.battleTurnNumber = Mathf.Max(1, turnNumber);
            if (applyTurnStartEffects)
            {
                fantasyEffectRunner.ApplyTrigger(context.run, "Turn_Start");
                fantasyEffectRunner.ApplyTrigger(context.run, $"Turn_{context.run.battleTurnNumber}");
                if (context.run.battleTurnNumber % 2 == 0)
                    fantasyEffectRunner.ApplyTrigger(context.run, "Turn_Even");
            }

            BattleNumberState numbers = context.run.EnsureBattleNumbers(MonsterHitCount);
            EnsurePlayerBaseDamageDigitCount(numbers);
            EnsurePlayerTurnDamage(numbers);
            context.playerFormula = formulaBuilder.BuildPlayerFormula(context.run, numbers.playerBaseDamage);
            PrepareMonsterPatternFormula(numbers);
            context.run.remainingMoveCount = CurrentMoveLimit;
        }

        private void EnsurePlayerBaseDamageDigitCount(BattleNumberState numbers)
        {
            if (context == null || context.run == null || numbers == null)
                return;

            int digitCount = GetPlayerDamageDigitCount(context.run);
            if (numbers.playerBaseDamageDigitCount == digitCount)
                return;

            int damageMin = MonsterPatternKeyUtility.MinForDigits(digitCount);
            int damageMax = MonsterPatternKeyUtility.MaxForDigits(digitCount);
            numbers.playerBaseDamage = context.run.RollValue($"battle.player.base_damage.{digitCount}digits", damageMin, damageMax);
            numbers.playerBaseDamageDigitCount = digitCount;
            numbers.playerBaseDamageTurn = 0;
            numbers.playerBaseDamageSegmentState = string.Empty;
        }

        private void EnsurePlayerTurnDamage(BattleNumberState numbers)
        {
            if (context == null || context.run == null || numbers == null)
                return;

            int turnNumber = Mathf.Max(1, context.run.battleTurnNumber);
            if (numbers.playerBaseDamageTurn == turnNumber)
                return;

            int digitCount = GetPlayerDamageDigitCount(context.run);
            int damageMin = MonsterPatternKeyUtility.MinForDigits(digitCount);
            int damageMax = MonsterPatternKeyUtility.MaxForDigits(digitCount);
            string turnKey = $"{turnNumber}.{digitCount}digits";
            numbers.playerBaseDamage = numbers.EnsurePlayerTurnDamage(turnKey, () =>
                context.run.RollValue($"battle.player.base_damage.{digitCount}digits.turn.{turnNumber}", damageMin, damageMax));
            numbers.playerBaseDamageTurn = turnNumber;
            numbers.playerBaseDamageSegmentState = string.Empty;
        }

        private static int GetPlayerDamageDigitCount(RunContext runContext)
        {
            int strength = runContext != null ? Mathf.Max(0, runContext.strength) : 0;
            return Mathf.Max(1, 2 + strength);
        }

        private void PrepareMonsterPatternFormula(BattleNumberState numbers)
        {
            if (context == null || context.run == null || numbers == null)
                return;

            MonsterPatternData pattern = monsterPatternRunner.SelectPattern(context.monster, monsterPatternDatabase, context.run);
            context.monsterPattern = pattern;
            string patternId = pattern != null && !string.IsNullOrWhiteSpace(pattern.id) ? pattern.id : "2_Single";
            string turnKey = $"{context.run.battleTurnNumber}.{patternId}";
            bool changedMonsterPattern = numbers.activeMonsterPatternTurn != context.run.battleTurnNumber || numbers.activeMonsterPatternId != patternId;
            numbers.activeMonsterPatternId = patternId;
            numbers.activeMonsterPatternTurn = context.run.battleTurnNumber;
            if (changedMonsterPattern)
            {
                numbers.monsterBaseDamageSegmentState = string.Empty;
                numbers.monsterHitCountSegmentState = string.Empty;
            }

            if (!monsterPatternRunner.IsAttackPattern(pattern))
            {
                monsterPatternRunner.ApplyImmediateNonAttack(context.monster, pattern);
                numbers.monsterBaseDamage = 0;
                numbers.monsterHitCount = 1;
                numbers.monsterBaseDamageSegmentState = string.Empty;
                numbers.monsterHitCountSegmentState = string.Empty;
                context.monsterFormula = formulaBuilder.BuildMonsterFormula(0, 1, false);
                return;
            }

            int monsterStrength = context.monster != null ? context.monster.Strength : 0;
            int damageDigits = Mathf.Max(1, pattern.damageDigitCount + monsterStrength);
            int damageMin = MonsterPatternKeyUtility.MinForDigits(damageDigits);
            int damageMax = MonsterPatternKeyUtility.MaxForDigits(damageDigits);
            int baseDamage = numbers.EnsureMonsterPatternDamage(turnKey, () =>
                context.run.RollValue($"battle.monster.base_damage.{patternId}.{context.run.battleTurnNumber}", damageMin, damageMax));

            int hitCount = 1;
            bool hitCountEditable = pattern.patternType == MonsterPatternType.MultiHit;
            if (hitCountEditable)
            {
                int hitDigits = Mathf.Max(1, pattern.hitDigitCount);
                int hitMin = MonsterPatternKeyUtility.MinForDigits(hitDigits);
                int hitMax = MonsterPatternKeyUtility.MaxForDigits(hitDigits);
                hitCount = numbers.EnsureMonsterPatternHitCount(turnKey, () =>
                    context.run.RollValue($"battle.monster.hit_count.{patternId}.{context.run.battleTurnNumber}", hitMin, hitMax));
            }

            numbers.monsterBaseDamage = Mathf.Max(0, baseDamage);
            numbers.monsterHitCount = Mathf.Max(0, hitCount);
            context.monsterFormula = formulaBuilder.BuildMonsterFormula(numbers.monsterBaseDamage, numbers.monsterHitCount, hitCountEditable);
        }

        public void SetMonsterHitCount(int value)
        {
            SetMonsterHitCount(value, string.Empty);
        }

        public void SetMonsterHitCount(int value, string segmentState)
        {
            if (bootstrap == null || bootstrap.RunContext == null)
                return;

            BattleNumberState numbers = bootstrap.RunContext.EnsureBattleNumbers(monsterHitCount: MonsterHitCount);
            numbers.monsterHitCount = Mathf.Max(0, value);
            numbers.monsterHitCountSegmentState = segmentState;
            if (context != null)
                context.monsterFormula = formulaBuilder.BuildMonsterFormula(numbers.monsterBaseDamage, numbers.monsterHitCount, true);
        }

        private void ApplyFormulaToMonster(BattleFormulaResult result)
        {
            if (context == null || context.monster == null || result.hitCount <= 0)
                return;

            int hitCount = GetModifiedPlayerHitCount(result.hitCount);
            for (int hitIndex = 0; hitIndex < hitCount; hitIndex++)
            {
                context.monster.ApplyDamage(result.damagePerHit);

                if (result.countsAsHit)
                {
                    int dealt = Mathf.Max(0, result.damagePerHit);
                    context.run.lastDamageDealt = dealt;
                    context.run.battleDamageDealt += dealt;
                    fantasyEffectRunner.ApplyTrigger(context.run, "Attack");
                    fantasyEffectRunner.ApplyTrigger(context.run, "Deal_Damage");
                    fantasyEffectRunner.ApplyTrigger(context.run, "On_Hit");
                    ApplyPendingMonsterDamage();
                }
            }
        }

        private int GetModifiedPlayerHitCount(int baseHitCount)
        {
            if (context == null || context.run == null)
                return baseHitCount;

            int hitCount = Mathf.Max(0, baseHitCount);
            hitCount += context.run.passiveAttackCountBonus;
            if (context.run.fantasyInventory != null && context.run.fantasyInventory.Contains("fan_attack_animalfriends"))
                hitCount += 4;
            hitCount = fantasyEffectRunner.ModifyValue(context.run, hitCount, "Passive", "Attack_Count");
            hitCount = fantasyEffectRunner.ModifyValue(context.run, hitCount, "Turn_Start", "Attack_Count");
            hitCount = fantasyEffectRunner.ModifyValue(context.run, hitCount, $"Turn_{context.run.battleTurnNumber}", "Attack_Count");
            if (context.run.battleTurnNumber % 2 == 0)
                hitCount = fantasyEffectRunner.ModifyValue(context.run, hitCount, "Turn_Even", "Attack_Count");
            hitCount = fantasyEffectRunner.ModifyValue(context.run, hitCount, "Turn_End", "Attack_Count");
            return Mathf.Max(0, hitCount);
        }

        private void ApplyFormulaToPlayer(BattleFormulaResult result)
        {
            if (context == null || context.run == null || result.hitCount <= 0)
                return;

            int incomingDamage = Mathf.Max(0, result.totalDamage);
            incomingDamage = Mathf.Max(0, fantasyEffectRunner.ModifyValue(context.run, incomingDamage, "Take_Damage", "Damage_Taken"));
            context.run.lastDamageTaken = incomingDamage;
            context.run.health -= incomingDamage;
            context.run.battleDamageTaken += incomingDamage;
            fantasyEffectRunner.ApplyTrigger(context.run, "Take_Damage");
            ApplyPendingMonsterDamage();
        }

        private void ApplyTurnEndFantasyEffects()
        {
            if (context == null || context.run == null)
                return;

            fantasyEffectRunner.ApplyTrigger(context.run, "Turn_End");
            ApplyPendingMonsterDamage();
        }

        private void ApplyPendingMonsterDamage()
        {
            if (context == null || context.run == null || context.monster == null)
                return;

            int damage = context.run.pendingMonsterDamage;
            if (damage == 0)
                return;

            context.run.pendingMonsterDamage = 0;
            context.monster.ApplyDamage(damage);
            if (damage > 0)
            {
                context.run.lastDamageDealt = damage;
                context.run.battleDamageDealt += damage;
            }
        }

        private bool CompleteBattleResolution()
        {
            if (context == null)
                return true;

            if (context.monster != null && context.monster.IsDead)
            {
                if (context.run != null)
                    fantasyEffectRunner.ApplyTrigger(context.run, "Battle_End");
                context.state = BattleState.Won;
                GameEventHub.RaiseBattleWon();
                return true;
            }

            if (context.run != null && context.run.health <= 0)
            {
                context.state = BattleState.Lost;
                GameEventHub.RaiseBattleLost();
                return true;
            }

            context.state = BattleState.Editing;
            return false;
        }
    }
}
