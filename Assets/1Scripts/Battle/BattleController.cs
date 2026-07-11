using GoldfishWalking.Core;
using GoldfishWalking.Data;
using GoldfishWalking.Fantasy;
using GoldfishWalking.Formula;
using GoldfishWalking.Map;
using System.Text;
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

        public bool MonsterSpecialBoxVisible => context != null && context.monster != null && context.monster.HasSpecialBox;

        public int MonsterSpecialBoxValue => context != null && context.monster != null && context.monster.HasSpecialBox
            ? context.monster.SpecialBoxValue
            : 0;

        public int MonsterSpecialBoxDigitCount => context != null && context.monster != null && context.monster.HasSpecialBox
            ? Mathf.Max(1, context.monster.SpecialBoxDigitCount)
            : 1;

        public string MonsterSpecialBoxLabel => context != null && context.monster != null && context.monster.HasSpecialBox
            ? context.monster.SpecialBoxLabel
            : string.Empty;

        public string MonsterSpecialBoxSegmentState => bootstrap != null && bootstrap.RunContext != null && bootstrap.RunContext.currentBattle != null
            ? bootstrap.RunContext.currentBattle.monsterSpecialBoxSegmentState
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

        public string MonsterStatusSummary
        {
            get
            {
                if (context == null || context.monster == null)
                    return "-";

                StringBuilder builder = new StringBuilder();
                AppendStatus(builder, "STR", context.monster.Strength);
                AppendStatus(builder, "STUN", context.monster.StunTurns);
                AppendStatus(builder, "SHIELD", context.monster.Shield);
                AppendStatus(builder, "FORTUNE", context.monster.FortuneStack);
                AppendStatus(builder, "PROPHECY", context.monster.ProphecyStack);

                return builder.Length > 0 ? builder.ToString() : "-";
            }
        }

        public string PlayerStatusSummary
        {
            get
            {
                if (context == null || context.run == null)
                    return "-";

                StringBuilder builder = new StringBuilder();
                AppendStatus(builder, "BLEED", context.run.playerBleed);
                AppendStatus(builder, "POISON", context.run.playerPoison);
                return builder.Length > 0 ? builder.ToString() : "-";
            }
        }

        public string DamageDebugSummary
        {
            get
            {
                if (context == null || context.run == null || context.run.battleDamageDebugLines == null || context.run.battleDamageDebugLines.Count == 0)
                    return "Damage log -";

                return string.Join("\n", context.run.battleDamageDebugLines);
            }
        }

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
            context.run.battleDamageDebugLines.Clear();
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

            context.run.ClearCommittedBattleEditItems();
            ApplyFormulaToMonster(playerResult);
            if (CompleteBattleResolution())
                return;

            ApplyTurnEndFantasyEffects();
            if (CompleteBattleResolution())
                return;

            if (monsterPatternRunner.IsAttackPattern(context.monsterPattern) && monsterPatternRunner.CanMonsterAct(context.monster))
            {
                int monsterDamageDealt = ApplyFormulaToPlayer(monsterResult);
                monsterPatternRunner.ApplyPatternEffects(
                    context.monster,
                    context.run,
                    context.monsterPattern,
                    context.playerFormula,
                    context.monsterFormula,
                    "Immediate",
                    monsterDamageDealt);
            }
            else
            {
                if (monsterPatternRunner.CanMonsterAct(context.monster))
                {
                    monsterPatternRunner.ApplyImmediateNonAttack(context.monster, context.monsterPattern);
                    monsterPatternRunner.ApplyPatternEffects(
                        context.monster,
                        context.run,
                        context.monsterPattern,
                        context.playerFormula,
                        context.monsterFormula,
                        "Immediate",
                        0);
                }

                monsterPatternRunner.AdvanceTurnDurations(context.monster);
            }

            ProcessMonsterSelfDestruct();
            if (CompleteBattleResolution())
                return;

            if (ProcessMonsterEscapeCountdown())
                return;

            ApplyPlayerEndTurnStatusDamage();
            ActivatePendingPlayerStatuses();
            if (CompleteBattleResolution())
                return;

            if (!CompleteBattleResolution())
            {
                AdvanceFantasyEffectDurations();
                context.state = BattleState.Editing;
                PrepareTurn(context.run.battleTurnNumber + 1, true);
            }
        }

        public void ResetBattle()
        {
            ResetCurrentBattleEdit();
        }

        public bool ForceSpawnMonster(string monsterId)
        {
            if (bootstrap == null || bootstrap.RunContext == null || string.IsNullOrWhiteSpace(monsterId))
                return false;

            string lookup = monsterId.Trim();
            if (!HasMonster(lookup))
                return false;

            bootstrap.RunContext.debugForcedMonsterId = lookup;
            StartBattle();
            return context != null && context.monster != null && context.monster.Data != null;
        }

        public bool DebugDamageMonster(int damage)
        {
            if (context == null || context.monster == null || damage <= 0)
                return false;

            context.monster.ApplyDamage(damage);
            if (context.run != null)
            {
                context.run.AddBattleDamageDebug("Debug", damage);
                context.run.lastDamageDealt = damage;
                context.run.battleDamageDealt += damage;
            }

            CompleteBattleResolution();
            return true;
        }

        public bool DebugKillMonster()
        {
            if (context == null || context.monster == null)
                return false;

            int damage = Mathf.Max(1, context.monster.CurrentHealth);
            return DebugDamageMonster(damage);
        }

        private bool HasMonster(string monsterId)
        {
            if (monsterDatabase == null || monsterDatabase.monsters == null)
                return false;

            for (int i = 0; i < monsterDatabase.monsters.Count; i++)
            {
                MonsterData monster = monsterDatabase.monsters[i];
                if (monster == null)
                    continue;
                if (MatchesDebugId(monster.id, monsterId)
                    || MatchesDebugId(monster.dataName, monsterId)
                    || MatchesDebugId(monster.devName, monsterId)
                    || MatchesDebugId(monster.displayName, monsterId))
                    return true;
            }

            return false;
        }

        private static bool MatchesDebugId(string value, string lookup)
        {
            return !string.IsNullOrWhiteSpace(value)
                && string.Equals(value.Trim(), lookup, System.StringComparison.OrdinalIgnoreCase);
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
                ApplyFantasyTrigger("Battle_Start");
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
                context.monsterFormula = formulaBuilder.BuildMonsterFormula(numbers.monsterBaseDamage, numbers.monsterHitCount, true, context.run);
        }

        private void PrepareTurn(int turnNumber, bool applyTurnStartEffects)
        {
            if (context == null || context.run == null)
                return;

            context.run.battleTurnNumber = Mathf.Max(1, turnNumber);
            if (applyTurnStartEffects)
            {
                ApplyFantasyTrigger("Turn_Start");
                ApplyFantasyTrigger($"Turn_{context.run.battleTurnNumber}");
                if (context.run.battleTurnNumber % 2 == 0)
                    ApplyFantasyTrigger("Turn_Even");
            }

            BattleNumberState numbers = context.run.EnsureBattleNumbers(MonsterHitCount);
            EnsurePlayerBaseDamageDigitCount(numbers);
            EnsurePlayerTurnDamage(numbers);
            context.playerFormula = formulaBuilder.BuildPlayerFormula(context.run, numbers.playerBaseDamage);
            PrepareMonsterPatternFormula(numbers);
            monsterPatternRunner.ApplyScheduledEffects(context.monster, context.run, context.playerFormula, context.monsterFormula);
            SyncSpecialBoxToNumbers(numbers);
            numbers.CaptureEditSnapshot(context.run.battleTurnNumber);
            context.run.ClearCommittedBattleEditItems();
            context.run.remainingMoveCount = CurrentMoveLimit;
        }

        private void ApplyFantasyTrigger(string trigger)
        {
            if (context == null || context.run == null)
                return;

            fantasyEffectRunner.ApplyTrigger(context.run, trigger);
            ApplyPendingEnemyStrengthModifiers();
        }

        private void ApplyPendingEnemyStrengthModifiers()
        {
            if (context == null || context.run == null || context.monster == null || context.run.pendingEnemyStrengthModifiers == null)
                return;

            for (int i = 0; i < context.run.pendingEnemyStrengthModifiers.Count; i++)
            {
                TimedStrengthModifier modifier = context.run.pendingEnemyStrengthModifiers[i];
                if (modifier == null || modifier.amount == 0)
                    continue;

                context.monster.ChangeStrength(modifier.amount);
                if (modifier.remainingTurns > 0)
                    context.monster.AddTimedStrengthModifier(modifier.amount, modifier.remainingTurns);
            }

            context.run.pendingEnemyStrengthModifiers.Clear();
        }

        private void AdvanceFantasyEffectDurations()
        {
            if (context == null || context.run == null)
                return;

            if (context.run.timedPlayerStrengthModifiers != null)
            {
                for (int i = context.run.timedPlayerStrengthModifiers.Count - 1; i >= 0; i--)
                {
                    TimedStrengthModifier modifier = context.run.timedPlayerStrengthModifiers[i];
                    if (modifier == null)
                    {
                        context.run.timedPlayerStrengthModifiers.RemoveAt(i);
                        continue;
                    }

                    modifier.remainingTurns--;
                    if (modifier.remainingTurns > 0)
                        continue;

                    context.run.strength -= modifier.amount;
                    context.run.timedPlayerStrengthModifiers.RemoveAt(i);
                }
            }

            context.monster?.AdvanceStrengthModifierDurations();
        }

        private void ResetCurrentBattleEdit()
        {
            if (context == null || context.run == null || context.run.currentBattle == null)
                return;

            BattleNumberState numbers = context.run.currentBattle;
            numbers.RestoreEditSnapshot();
            RestoreSpecialBoxFromNumbers(numbers);
            context.run.RefundCommittedBattleEditItems();
            context.run.temporaryMoveBonus = 0;
            context.run.remainingMoveCount = CurrentMoveLimit;

            context.playerFormula = formulaBuilder.BuildPlayerFormula(context.run, numbers.playerBaseDamage);
            bool hitCountEditable = context.monsterPattern != null && context.monsterPattern.patternType == MonsterPatternType.MultiHit;
            context.monsterFormula = formulaBuilder.BuildMonsterFormula(numbers.monsterBaseDamage, numbers.monsterHitCount, hitCountEditable, context.run);
            context.state = BattleState.Editing;
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

            if (context.monster != null && context.monster.IsStunned)
            {
                numbers.monsterBaseDamage = 0;
                numbers.monsterHitCount = 1;
                numbers.monsterBaseDamageSegmentState = string.Empty;
                numbers.monsterHitCountSegmentState = string.Empty;
                context.monsterFormula = formulaBuilder.BuildMonsterFormula(0, 1, false, context.run);
                EnsureMonsterIdentitySpecialBox(numbers);
                return;
            }

            if (!monsterPatternRunner.IsAttackPattern(pattern))
            {
                numbers.monsterBaseDamage = 0;
                numbers.monsterHitCount = 1;
                numbers.monsterBaseDamageSegmentState = string.Empty;
                numbers.monsterHitCountSegmentState = string.Empty;
                context.monsterFormula = formulaBuilder.BuildMonsterFormula(0, 1, false, context.run);
                EnsureMonsterIdentitySpecialBox(numbers);
                return;
            }

            int baseDamage;
            if (pattern.hasDynamicDamageValue)
            {
                baseDamage = Mathf.Max(0, monsterPatternRunner.EvaluateValueExpression(pattern.damageValueExpression, context.monster, context.run));
            }
            else
            {
                int monsterStrength = context.monster != null ? context.monster.Strength : 0;
                int damageDigits = Mathf.Max(1, pattern.damageDigitCount + monsterStrength);
                int damageMin = MonsterPatternKeyUtility.MinForDigits(damageDigits);
                int damageMax = MonsterPatternKeyUtility.MaxForDigits(damageDigits);
                baseDamage = numbers.EnsureMonsterPatternDamage(turnKey, () =>
                    context.run.RollValue($"battle.monster.base_damage.{patternId}.{context.run.battleTurnNumber}", damageMin, damageMax));
            }

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
            context.monsterFormula = formulaBuilder.BuildMonsterFormula(numbers.monsterBaseDamage, numbers.monsterHitCount, hitCountEditable, context.run);
            EnsureMonsterIdentitySpecialBox(numbers);
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
                context.monsterFormula = formulaBuilder.BuildMonsterFormula(numbers.monsterBaseDamage, numbers.monsterHitCount, true, context.run);
        }

        public void SetMonsterSpecialBoxValue(int value, string segmentState)
        {
            if (context == null || context.monster == null || bootstrap == null || bootstrap.RunContext == null)
                return;

            context.monster.SetSpecialBoxValue(value);
            BattleNumberState numbers = bootstrap.RunContext.EnsureBattleNumbers(monsterHitCount: MonsterHitCount);
            numbers.monsterSpecialBoxVisible = context.monster.HasSpecialBox;
            numbers.monsterSpecialBoxValue = context.monster.SpecialBoxValue;
            numbers.monsterSpecialBoxDigitCount = Mathf.Max(1, context.monster.SpecialBoxDigitCount);
            numbers.monsterSpecialBoxLabel = context.monster.SpecialBoxLabel;
            numbers.monsterSpecialBoxSegmentState = segmentState;
        }

        private void SyncSpecialBoxToNumbers(BattleNumberState numbers)
        {
            if (numbers == null || context == null || context.monster == null)
                return;

            bool changedSpecialBox =
                numbers.monsterSpecialBoxVisible != context.monster.HasSpecialBox
                || numbers.monsterSpecialBoxValue != context.monster.SpecialBoxValue
                || numbers.monsterSpecialBoxDigitCount != (context.monster.HasSpecialBox ? Mathf.Max(1, context.monster.SpecialBoxDigitCount) : 0)
                || numbers.monsterSpecialBoxLabel != context.monster.SpecialBoxLabel;

            numbers.monsterSpecialBoxVisible = context.monster.HasSpecialBox;
            numbers.monsterSpecialBoxValue = context.monster.SpecialBoxValue;
            numbers.monsterSpecialBoxDigitCount = context.monster.HasSpecialBox ? Mathf.Max(1, context.monster.SpecialBoxDigitCount) : 0;
            numbers.monsterSpecialBoxLabel = context.monster.SpecialBoxLabel;
            if (!context.monster.HasSpecialBox || changedSpecialBox)
                numbers.monsterSpecialBoxSegmentState = string.Empty;
        }

        private void RestoreSpecialBoxFromNumbers(BattleNumberState numbers)
        {
            if (numbers == null || context == null || context.monster == null)
                return;

            if (!numbers.monsterSpecialBoxVisible)
            {
                context.monster.ClearSpecialBox();
                return;
            }

            context.monster.SetSpecialBox(
                numbers.monsterSpecialBoxValue,
                Mathf.Max(1, numbers.monsterSpecialBoxDigitCount),
                numbers.monsterSpecialBoxLabel);
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
                    context.run.AddBattleDamageDebug("Direct", dealt);
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

        private int ApplyFormulaToPlayer(BattleFormulaResult result)
        {
            if (context == null || context.run == null || result.hitCount <= 0)
                return 0;

            int incomingDamage = 0;
            int damagePerHit = Mathf.Max(0, result.damagePerHit);
            int hitCount = Mathf.Max(0, result.hitCount);
            for (int hitIndex = 0; hitIndex < hitCount; hitIndex++)
                incomingDamage += Mathf.Max(0, fantasyEffectRunner.ModifyValue(context.run, damagePerHit, "Take_Damage", "Damage_Taken"));

            context.run.lastDamageTaken = incomingDamage;
            context.run.health -= incomingDamage;
            context.run.battleDamageTaken += incomingDamage;
            fantasyEffectRunner.ApplyTrigger(context.run, "Take_Damage");
            ApplyPendingMonsterDamage();
            return incomingDamage;
        }

        private void EnsureMonsterIdentitySpecialBox(BattleNumberState numbers)
        {
            if (context == null || context.monster == null || context.monster.Data == null || context.monster.HasSpecialBox || numbers == null)
                return;

            string dataName = context.monster.Data.dataName ?? string.Empty;
            string devName = context.monster.Data.devName ?? string.Empty;
            string label = string.Empty;
            int min = 0;
            int max = 9;

            if (dataName.Contains("WhiteRabbit") || devName.Contains("화이트 래빗"))
                label = "RABBIT";
            else if (dataName.Contains("HeartQueen") || devName.Contains("하트 여왕"))
                label = "HEART";
            else if ((dataName.Contains("Witch") && !dataName.Contains("LittleWitch")) || devName == "마녀")
            {
                label = "/";
                min = 1;
            }

            if (string.IsNullOrWhiteSpace(label))
                return;

            int value = context.run != null
                ? context.run.RollValue($"monster.identity_box.{dataName}.{context.run.battleTurnNumber}", min, max)
                : min;

            if (IsWhiteRabbit(context.monster.Data))
                value = 3;

            context.monster.SetSpecialBox(value, 1, label);
            SyncSpecialBoxToNumbers(numbers);
        }

        private bool ProcessMonsterEscapeCountdown()
        {
            if (context == null || context.monster == null || !IsWhiteRabbit(context.monster.Data) || !context.monster.HasSpecialBox)
                return false;

            context.monster.SetSpecialBoxValue(context.monster.SpecialBoxValue - 1);
            SyncSpecialBoxToNumbers(context.run?.currentBattle);
            if (context.monster.SpecialBoxValue > 0)
                return false;

            CleanupBattleTemporaryState();
            context.state = BattleState.Won;
            GameEventHub.RaiseBattleEscaped();
            return true;
        }

        private static bool IsWhiteRabbit(MonsterData data)
        {
            if (data == null)
                return false;

            string dataName = data.dataName ?? string.Empty;
            string devName = data.devName ?? string.Empty;
            return dataName.Contains("WhiteRabbit") || devName.Contains("화이트 래빗");
        }

        private void ProcessMonsterSelfDestruct()
        {
            if (context == null || context.monster == null || context.monsterPattern == null)
                return;
            if (context.monster.IsDead || !IsSelfDestructPattern(context.monsterPattern))
                return;

            int damage = Mathf.Max(1, context.monster.CurrentHealth);
            context.monster.ApplyDamage(damage);
            if (context.run != null)
                context.run.AddBattleDamageDebug("Self Destruct", damage);
        }

        private static bool IsSelfDestructPattern(MonsterPatternData pattern)
        {
            if (pattern == null)
                return false;

            string id = pattern.id ?? string.Empty;
            string dataCode = pattern.dataCode ?? string.Empty;
            string handler = pattern.specialHandler ?? string.Empty;
            return id.IndexOf("OrbSkill", System.StringComparison.OrdinalIgnoreCase) >= 0
                || dataCode.IndexOf("OrbSkill", System.StringComparison.OrdinalIgnoreCase) >= 0
                || handler.IndexOf("OrbSkill", System.StringComparison.OrdinalIgnoreCase) >= 0;
        }

        private void ApplyTurnEndFantasyEffects()
        {
            if (context == null || context.run == null)
                return;
            if (context.run.health <= 0)
                return;

            fantasyEffectRunner.ApplyTrigger(context.run, "Turn_End");
            ApplyPendingMonsterDamage();
        }

        private void ApplyPlayerEndTurnStatusDamage()
        {
            if (context == null || context.run == null)
                return;

            int damage = 0;
            if (context.run.playerBleed > 0)
            {
                damage += context.run.playerBleed;
                context.run.playerBleed = 0;
            }

            if (context.run.playerPoison > 0)
                damage += context.run.playerPoison;

            if (damage <= 0)
                return;

            context.run.health -= damage;
            context.run.lastDamageTaken = damage;
            context.run.battleDamageTaken += damage;
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
                if (context.run.battleDamageDebugLines.Count == 0)
                    context.run.AddBattleDamageDebug("Pending", damage);
                context.run.lastDamageDealt = damage;
                context.run.battleDamageDealt += damage;
            }
        }

        private static void AppendStatus(StringBuilder builder, string label, int value)
        {
            if (value == 0)
                return;

            if (builder.Length > 0)
                builder.Append("  ");
            builder.Append(label);
            builder.Append(' ');
            builder.Append(value);
        }

        private bool CompleteBattleResolution()
        {
            if (context == null)
                return true;

            if (context.run != null && context.run.health <= 0)
            {
                CleanupBattleTemporaryState();
                context.state = BattleState.Lost;
                GameEventHub.RaiseBattleLost();
                return true;
            }

            if (context.monster != null && context.monster.IsDead)
            {
                if (context.run != null)
                    fantasyEffectRunner.ApplyTrigger(context.run, "Battle_End");
                CleanupBattleTemporaryState();
                context.state = BattleState.Won;
                GameEventHub.RaiseBattleWon();
                return true;
            }

            context.state = BattleState.Editing;
            return false;
        }

        private void CleanupBattleTemporaryState()
        {
            if (context == null || context.run == null)
                return;

            context.run.strength = 0;
            context.run.playerBleed = 0;
            context.run.playerPoison = 0;
            context.run.timedPlayerStrengthModifiers.Clear();
            context.run.pendingEnemyStrengthModifiers.Clear();
            context.run.pendingPlayerBleed = 0;
            context.run.pendingPlayerPoison = 0;
            context.run.ClearCommittedBattleEditItems();
            context.run.itemInventory.ClearTemporary();
            context.run.fantasyInventory?.RemoveTemporary();
            GameEventHub.RaiseItemInventoryChanged();
        }

        private void ActivatePendingPlayerStatuses()
        {
            if (context == null || context.run == null)
                return;

            if (context.run.pendingPlayerBleed > 0)
            {
                context.run.playerBleed = Mathf.Max(0, context.run.playerBleed + context.run.pendingPlayerBleed);
                context.run.pendingPlayerBleed = 0;
            }

            if (context.run.pendingPlayerPoison > 0)
            {
                context.run.playerPoison = Mathf.Max(0, context.run.playerPoison + context.run.pendingPlayerPoison);
                context.run.pendingPlayerPoison = 0;
            }
        }
    }
}
