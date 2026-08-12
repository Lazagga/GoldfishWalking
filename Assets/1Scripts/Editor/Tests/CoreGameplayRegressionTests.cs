using System.Collections.Generic;
using GoldfishWalking.Core;
using GoldfishWalking.Battle;
using GoldfishWalking.Data;
using GoldfishWalking.Formula;
using GoldfishWalking.Match;
using NUnit.Framework;
using UnityEditor;

namespace GoldfishWalking.Editor.Tests
{
    public sealed class CoreGameplayRegressionTests
    {
        [Test]
        public void FormulaEvaluator_UsesLeftToRightOrder()
        {
            FormulaState formula = Formula(
                FormulaBox.Number("a", 10),
                FormulaBox.Operator("plus", FormulaOperator.Add),
                FormulaBox.Number("b", 5),
                FormulaBox.Operator("times", FormulaOperator.Multiply),
                FormulaBox.Number("c", 2));

            FormulaResult result = new FormulaEvaluator().EvaluateLeftToRight(formula);

            Assert.That(result.isValid, Is.True);
            Assert.That(result.value, Is.EqualTo(30));
        }

        [Test]
        public void FormulaEvaluator_FloorsNegativeDivisionResult()
        {
            FormulaState formula = Formula(
                FormulaBox.Number("a", 1),
                FormulaBox.Operator("minus", FormulaOperator.Subtract),
                FormulaBox.Number("b", 4),
                FormulaBox.Operator("divide", FormulaOperator.Divide),
                FormulaBox.Number("c", 2));

            FormulaResult result = new FormulaEvaluator().EvaluateLeftToRight(formula);

            Assert.That(result.isValid, Is.True);
            Assert.That(result.value, Is.EqualTo(-2));
        }

        [Test]
        public void FormulaEvaluator_RejectsDivisionByZeroAndNegativeInput()
        {
            FormulaResult division = new FormulaEvaluator().EvaluateLeftToRight(Formula(
                FormulaBox.Number("a", 10),
                FormulaBox.Operator("divide", FormulaOperator.Divide),
                FormulaBox.Number("b", 0)));
            FormulaResult negative = new FormulaEvaluator().EvaluateLeftToRight(Formula(FormulaBox.Number("a", -1)));

            Assert.That(division.isValid, Is.False);
            Assert.That(negative.isValid, Is.False);
        }

        [Test]
        public void DeterministicValue_IsStableAndPurposeIndependent()
        {
            int first = DeterministicValue.Range(1234, 2, 8, "node", "battle.damage", 10, 99);
            int repeated = DeterministicValue.Range(1234, 2, 8, "node", "battle.damage", 10, 99);
            int otherPurpose = DeterministicValue.Range(1234, 2, 8, "node", "shop.price", 10, 99);

            Assert.That(repeated, Is.EqualTo(first));
            Assert.That(otherPurpose, Is.Not.EqualTo(first));
        }

        [Test]
        public void MatchPatternInterpreter_PreservesLeadingZeroAsNumericValue()
        {
            List<MatchSlot> slots = new List<MatchSlot>();
            AddDigit(slots, 0, 0);
            AddDigit(slots, 1, 6);

            MatchPatternParseResult result = new MatchPatternInterpreter().ParseNumber(slots);

            Assert.That(result.success, Is.True);
            Assert.That(result.numberValue, Is.EqualTo(6));
        }

        [Test]
        public void MatchEditSession_RejectsLockedPieceAndRefundsErasedAddedPiece()
        {
            MatchEditSession session = new MatchEditSession();
            session.Open(FormulaBox.Number("number", 1));
            session.slots.Add(new MatchSlot { digitIndex = 0, segmentIndex = 0, piece = new MatchPiece { kind = MatchPieceKind.Locked } });
            session.slots.Add(new MatchSlot { digitIndex = 0, segmentIndex = 1, piece = new MatchPiece { kind = MatchPieceKind.Added } });

            Assert.That(session.TryPickUp(0, 0).success, Is.False);
            Assert.That(session.TryErase(0, 1).success, Is.True);
            Assert.That(session.returnedAddedMatches, Is.EqualTo(1));
        }

        [Test]
        public void MatchEditSession_PreventsCrossDigitMovesWhenSplit()
        {
            MatchEditSession session = new MatchEditSession();
            session.Open(FormulaBox.Number("number", 12));
            session.ConfigureStructuralRules(true, _ => false);
            session.slots.Add(new MatchSlot { digitIndex = 0, segmentIndex = 0, piece = new MatchPiece() });

            Assert.That(session.TryPickUp(0, 0).success, Is.True);
            Assert.That(session.TryPlace(1, 0).success, Is.False);
            Assert.That(session.TryPlace(0, 1).success, Is.True);
        }

        [Test]
        public void GeneratedDatabases_AreBackedByExpectedJsonCounts()
        {
            MonsterDatabase monsters = AssetDatabase.LoadAssetAtPath<MonsterDatabase>("Assets/Data/Generated/MonsterDatabase.asset");
            MonsterPatternDatabase patterns = AssetDatabase.LoadAssetAtPath<MonsterPatternDatabase>("Assets/Data/Generated/MonsterPatternDatabase.asset");
            FantasyDatabase fantasies = AssetDatabase.LoadAssetAtPath<FantasyDatabase>("Assets/Data/Generated/FantasyDatabase.asset");

            Assert.That(monsters, Is.Not.Null);
            Assert.That(patterns, Is.Not.Null);
            Assert.That(fantasies, Is.Not.Null);
            Assert.That(monsters.monsters, Has.Count.EqualTo(39));
            Assert.That(patterns.patterns, Has.Count.EqualTo(38));
            Assert.That(fantasies.fantasies, Has.Count.EqualTo(60));
        }

        [Test]
        public void BattleOutcomeService_PrioritizesPlayerLoss()
        {
            BattleContext context = new BattleContext { run = new RunContext { health = 0 } };
            Assert.That(new BattleOutcomeService().EvaluateCombatants(context), Is.EqualTo(BattleOutcome.PlayerLost));
        }

        [Test]
        public void MonsterEffectExpressionEvaluator_UsesScopedBattleState()
        {
            RunContext run = new RunContext();
            run.battleSession.totalDamageDealt = 40;
            run.battleSession.playerBleed = 3;
            MonsterEffectExpressionEvaluator evaluator = new MonsterEffectExpressionEvaluator();

            Assert.That(evaluator.EvaluateValue("DamageTaken * 50", null, run, 0), Is.EqualTo(20));
            Assert.That(evaluator.EvaluateCondition("PlayerBleed >= 3 && PlayerHP > 0", null, run), Is.True);
        }

        [Test]
        public void MonsterEffectExpressionEvaluator_FloorsDivisionAndProtectsZero()
        {
            MonsterEffectExpressionEvaluator evaluator = new MonsterEffectExpressionEvaluator();

            Assert.That(evaluator.EvaluateValue("5 / 2", null, null, 0), Is.EqualTo(2));
            Assert.That(evaluator.EvaluateValue("5 / 0", null, null, 0), Is.EqualTo(0));
        }

        private static FormulaState Formula(params FormulaBox[] boxes)
        {
            FormulaState state = new FormulaState();
            state.boxes.AddRange(boxes);
            return state;
        }

        private static void AddDigit(List<MatchSlot> slots, int digitIndex, int digit)
        {
            MatchPattern pattern = System.Array.Find(MatchPatternTable.DigitPatterns, item => item.value == digit);
            foreach (int segment in pattern.segments)
                slots.Add(new MatchSlot { digitIndex = digitIndex, segmentIndex = segment, piece = new MatchPiece() });
        }
    }
}
