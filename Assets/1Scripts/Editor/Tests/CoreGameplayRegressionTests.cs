using System.Collections.Generic;
using System.IO;
using System.Text.RegularExpressions;
using GoldfishWalking.Core;
using GoldfishWalking.Battle;
using GoldfishWalking.Data;
using GoldfishWalking.Formula;
using GoldfishWalking.Fantasy;
using GoldfishWalking.Item;
using GoldfishWalking.Match;
using NUnit.Framework;
using UnityEditor;
using UnityEngine;

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
        public void MatchEditSession_ImmobileMatchesCanStillBeErasedAndAdded()
        {
            MatchEditSession session = new MatchEditSession();
            session.Open(FormulaBox.Number("number", 1));
            session.ConfigureStructuralRules(false, _ => false, false);
            session.slots.Add(new MatchSlot { digitIndex = 0, segmentIndex = 0, piece = new MatchPiece() });

            Assert.That(session.TryPickUp(0, 0).success, Is.False);
            Assert.That(session.TryErase(0, 0).success, Is.True);
            Assert.That(session.AddExtraMatch(new MatchPiece()).success, Is.True);
            Assert.That(session.TryPlace(0, 1).success, Is.True);
        }

        [Test]
        public void MonsterRuntime_ReactiveEditBoxesTriggerOnlyOncePerSelectedBox()
        {
            MonsterData data = new MonsterData
            {
                reactiveEditBoxIds = new[] { "a", "b", "c", "d" },
                reactiveEditGroupSize = 2,
                reactiveEditSelectionCount = 1,
                reactiveEditStrength = 1
            };
            MonsterRuntime monster = new MonsterRuntime(data);
            monster.ConfigureReactiveEditBoxes(new RunContext { seed = 17, act = 3, roomIndex = 4 }, "node");

            int selectedCount = 0;
            foreach (string boxId in data.reactiveEditBoxIds)
            {
                if (!monster.IsReactiveEditBox(boxId))
                    continue;
                selectedCount++;
                Assert.That(monster.TryReactToBoxEdit(boxId), Is.True);
                Assert.That(monster.TryReactToBoxEdit(boxId), Is.False);
            }

            Assert.That(selectedCount, Is.EqualTo(2));
            Assert.That(monster.Strength, Is.EqualTo(2));
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
            Assert.That(monsters.monsters, Has.Count.EqualTo(CountEnabledJson("Assets/Data/Json/monsters")));
            Assert.That(patterns.patterns, Has.Count.EqualTo(CountEnabledJson("Assets/Data/Json/patterns")));
            Assert.That(fantasies.fantasies, Has.Count.EqualTo(CountEnabledJson("Assets/Data/Json/fantasies")));
            MonsterData golem = monsters.monsters.Find(monster => monster.id == "Mob_30105_Golem");
            Assert.That(golem, Is.Not.Null);
            Assert.That(golem.playerMatchesMovable, Is.False);
            Assert.That(golem.monsterMatchesMovable, Is.True);
            MonsterData anglerfish = monsters.monsters.Find(monster => monster.id == "Mob_30106_Anglerfish");
            Assert.That(anglerfish, Is.Not.Null);
            Assert.That(anglerfish.reactiveEditGroupSize, Is.EqualTo(2));
            Assert.That(anglerfish.reactiveEditSelectionCount, Is.EqualTo(1));
            Assert.That(anglerfish.reactiveEditStrength, Is.EqualTo(1));
        }

        [Test]
        public void MonsterArt_AllGeneratedMonstersUseDirectPresentationReferences()
        {
            MonsterDatabase database = AssetDatabase.LoadAssetAtPath<MonsterDatabase>("Assets/Data/Generated/MonsterDatabase.asset");
            Assert.That(database, Is.Not.Null);
            Assert.That(database.monsters, Has.Count.EqualTo(39));

            foreach (MonsterData monster in database.monsters)
            {
                Assert.That(monster.sprite, Is.Not.Empty, $"{monster.id} has no authored art key.");
                Assert.That(monster.portraitSprite, Is.Not.Null, $"{monster.id} has no generated Sprite reference.");
                Assert.That(AssetDatabase.GetAssetPath(monster.portraitSprite), Does.StartWith("Assets/Art/enemy/"));
                if (monster.spritePhaseCount > 0)
                {
                    Assert.That(monster.phasePortraitSprites, Has.Length.EqualTo(monster.spritePhaseCount));
                    Assert.That(monster.phasePortraitSprites, Has.All.Not.Null);
                    Assert.That(monster.portraitAnimatorController, Is.Null, $"{monster.id} phase sprites must not use an AnimatorController.");
                }
                else
                {
                    Assert.That(monster.portraitAnimatorController, Is.Not.Null, $"{monster.id} has no generated AnimatorController reference.");
                    Assert.That(AssetDatabase.GetAssetPath(monster.portraitAnimatorController), Does.StartWith("Assets/Art/Generated/Enemies/"));
                }
            }
        }

        [Test]
        public void FantasyArt_CosmeticsAreDataDrivenAndHaveDirectSprites()
        {
            FantasyDatabase database = AssetDatabase.LoadAssetAtPath<FantasyDatabase>("Assets/Data/Generated/FantasyDatabase.asset");
            Assert.That(database, Is.Not.Null);

            List<FantasyData> cosmetics = database.fantasies
                .FindAll(fantasy => FantasyInventory.DataHasEffect(fantasy, "cosmetic"));
            Assert.That(cosmetics, Has.Count.EqualTo(4));
            Assert.That(cosmetics, Has.All.Matches<FantasyData>(fantasy => fantasy.iconSprite != null));
        }

        [Test]
        public void UiArt_GeneratedSkinContainsAllEightAuthoredSprites()
        {
            UiSkinData skin = AssetDatabase.LoadAssetAtPath<UiSkinData>("Assets/Art/Generated/UI/UiSkinData.asset");
            Assert.That(skin, Is.Not.Null);
            Assert.That(skin.nextButton, Is.Not.Null);
            Assert.That(skin.resetButton, Is.Not.Null);
            Assert.That(skin.closeButton, Is.Not.Null);
            Assert.That(skin.textPanel, Is.Not.Null);
            Assert.That(skin.singleButton, Is.Not.Null);
            Assert.That(skin.connectedLeftButton, Is.Not.Null);
            Assert.That(skin.connectedMiddleButton, Is.Not.Null);
            Assert.That(skin.connectedRightButton, Is.Not.Null);
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

        [Test]
        public void MonsterEffectExpressionEvaluator_ResolvesSpecialMonsterExpressions()
        {
            RunContext run = new RunContext { seed = 9, act = 3, roomIndex = 2, health = 100 };
            run.battleTurnNumber = 4;
            MonsterRuntime monster = new MonsterRuntime(new MonsterData());
            monster.SetSpecialBox(123, 3, "STAR", false);
            MonsterEffectExpressionEvaluator evaluator = new MonsterEffectExpressionEvaluator();

            Assert.That(evaluator.EvaluateValue("Stargazing_Multi_3", monster, run, 0), Is.EqualTo(123));
            Assert.That(evaluator.EvaluateValue("CosmictreeHeal", monster, run, 0), Is.EqualTo(1));
            float hpDamage = evaluator.EvaluateValue("PlayerHP_Multi_2", monster, run, 0);
            Assert.That(hpDamage, Is.InRange(10, 99));
            Assert.That(monster.SpecialBoxEditable, Is.False);
        }

        [Test]
        public void FantasyEffectRunner_EvaluatesFloorParenthesesAndRuntimeVariables()
        {
            RunContext run = new RunContext { health = 100 };
            run.battleSession.incomingDamageAmount = 250;
            FantasyData fantasy = Fantasy("heal", new FantasyEffectData
            {
                trigger = "Take_Damage", target = "HP", calc = "Add",
                valueExpression = "floor(IncomingDamageAmount/100)*20"
            });

            new FantasyEffectRunner().Apply(fantasy, run, "Take_Damage");

            Assert.That(run.health, Is.EqualTo(140));
        }

        [Test]
        public void FantasyEffectRunner_UsesGenericCountersAndNegativeExpressions()
        {
            RunContext run = new RunContext { health = 100 };
            run.battleSession.incomingDamageAmount = 30;
            FantasyData fantasy = Fantasy("bleed",
                new FantasyEffectData { trigger = "Take_Damage", target = "scorpio_bleed_stack", calc = "Add", valueExpression = "IncomingDamageAmount*0.5" },
                new FantasyEffectData { trigger = "Turn_End", target = "HP", calc = "Add", valueExpression = "-scorpio_bleed_stack" });
            FantasyEffectRunner runner = new FantasyEffectRunner();

            runner.Apply(fantasy, run, "Take_Damage");
            runner.Apply(fantasy, run, "Turn_End");

            Assert.That(run.battleSession.GetCounter("scorpiobleedstack"), Is.EqualTo(15));
            Assert.That(run.health, Is.EqualTo(85));
        }

        [Test]
        public void FantasyEffectRunner_AcquireForkProducesDuplicateOrVoid()
        {
            RunContext run = new RunContext { seed = 17 };
            FantasyData leo = Fantasy("leo", new FantasyEffectData
            {
                trigger = "On_Acquire", target = "Fantasy", operation = "duplicate_or_void_acquire",
                calc = "Toggle", chance = 0.5f, execution = "capability"
            });
            FantasyData acquired = Fantasy("candidate");
            run.fantasyInventory.Add(leo);

            new FantasyEffectRunner().AddFantasyWithAcquireEffects(run, acquired);

            int count = run.fantasyInventory.ownedFantasies.FindAll(item => item == acquired).Count;
            Assert.That(count, Is.EqualTo(0).Or.EqualTo(2));
        }

        [Test]
        public void FantasyEffectRunner_LeoDoesNotDuplicateOrVoidItselfOnAcquire()
        {
            RunContext run = new RunContext { seed = 17 };
            FantasyData leo = Fantasy("leo", new FantasyEffectData
            {
                trigger = "On_Acquire", target = "Fantasy", operation = "duplicate_or_void_acquire",
                calc = "Toggle", chance = 0.5f, execution = "capability"
            });

            bool added = new FantasyEffectRunner().AddFantasyWithAcquireEffects(run, leo);

            Assert.That(added, Is.True);
            Assert.That(run.fantasyInventory.ownedFantasies.FindAll(item => item == leo).Count, Is.EqualTo(1));
        }

        [Test]
        public void Virgo_CountsOnlyIncreasingTransitionsAcrossBothFormulas()
        {
            BattleFormulaState player = new BattleFormulaState
            {
                damageExpression = Formula(FormulaBox.Number("p12", 12)),
                hitCountExpression = Formula(FormulaBox.Number("p3", 3))
            };
            BattleFormulaState monster = new BattleFormulaState
            {
                damageExpression = Formula(FormulaBox.Number("m45", 45)),
                hitCountExpression = Formula(FormulaBox.Number("m6", 6))
            };

            Assert.That(BattleController.CountIncreasingDigitTransitions(player, monster), Is.EqualTo(5));

            BattleFormulaState descending = new BattleFormulaState
            {
                damageExpression = Formula(FormulaBox.Number("descending", 654321)),
                hitCountExpression = Formula()
            };
            Assert.That(BattleController.CountIncreasingDigitTransitions(descending, null), Is.EqualTo(0));
        }

        [Test]
        public void BattleHitPresentation_AcceleratesButNeverPassesMinimumDelay()
        {
            Assert.That(BattleController.CalculateAcceleratedHitDelay(0.2f, 0.025f, 0.85f, 0), Is.EqualTo(0.2f).Within(0.0001f));
            Assert.That(BattleController.CalculateAcceleratedHitDelay(0.2f, 0.025f, 0.85f, 5), Is.LessThan(0.2f));
            Assert.That(BattleController.CalculateAcceleratedHitDelay(0.2f, 0.025f, 0.85f, 100), Is.EqualTo(0.025f).Within(0.0001f));
        }

        [Test]
        public void MonsterAttack_ZeroDamageSkipsEveryHitRegardlessOfHitCount()
        {
            Assert.That(BattleController.CalculateProcessedAttackHitCount(0, 999), Is.EqualTo(0));
            Assert.That(BattleController.CalculateProcessedAttackHitCount(-10, 999), Is.EqualTo(0));
            Assert.That(BattleController.CalculateProcessedAttackHitCount(1, 999), Is.EqualTo(999));
        }

        private static FantasyData Fantasy(string id, params FantasyEffectData[] effects)
        {
            return new FantasyData { id = id, effects = effects };
        }

        private static FormulaState Formula(params FormulaBox[] boxes)
        {
            FormulaState state = new FormulaState();
            state.boxes.AddRange(boxes);
            return state;
        }

        private static int CountEnabledJson(string directory)
        {
            int count = 0;
            foreach (string path in Directory.GetFiles(directory, "*.json"))
            {
                string json = File.ReadAllText(path);
                if (!Regex.IsMatch(json, "\\\"enabled\\\"\\s*:\\s*false", RegexOptions.IgnoreCase))
                    count++;
            }
            return count;
        }

        private static void AddDigit(List<MatchSlot> slots, int digitIndex, int digit)
        {
            MatchPattern pattern = System.Array.Find(MatchPatternTable.DigitPatterns, item => item.value == digit);
            foreach (int segment in pattern.segments)
                slots.Add(new MatchSlot { digitIndex = digitIndex, segmentIndex = segment, piece = new MatchPiece() });
        }
    }
}
