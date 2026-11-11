using System;
using System.Collections.Generic;
using System.IO;
using GoldfishWalking.Core;
using GoldfishWalking.Data;
using GoldfishWalking.Fantasy;
using GoldfishWalking.Item;
using GoldfishWalking.Map;
using UnityEngine;

namespace GoldfishWalking.Save
{
    public static class RunSaveSystem
    {
        private const int CurrentVersion = 1;
        private const string FileName = "run_save.json";

        public static string SavePath => Path.Combine(Application.persistentDataPath, FileName);
        public static bool HasSave => File.Exists(SavePath);

        public static bool Save(RunContext run, GameState state)
        {
            if (run == null || run.seed == 0 || run.map == null)
                return false;

            try
            {
                RunSaveData data = RunSaveData.Capture(run, state);
                string json = JsonUtility.ToJson(data, true);
                Directory.CreateDirectory(Application.persistentDataPath);
                string temporaryPath = SavePath + ".tmp";
                File.WriteAllText(temporaryPath, json);
                if (File.Exists(SavePath))
                    File.Delete(SavePath);
                File.Move(temporaryPath, SavePath);
                return true;
            }
            catch (Exception exception)
            {
                Debug.LogError($"[RunSaveSystem] Save failed: {exception.Message}");
                return false;
            }
        }

        public static bool TryLoad(FantasyDatabase database, out RunContext run, out GameState state)
        {
            run = null;
            state = GameState.Map;
            if (!HasSave || database == null)
                return false;

            try
            {
                RunSaveData data = JsonUtility.FromJson<RunSaveData>(File.ReadAllText(SavePath));
                if (data == null || data.version != CurrentVersion || data.seed == 0 || data.map == null)
                    return false;

                run = data.Restore(database);
                state = IsPlayableState(data.state) ? data.state : GameState.Map;
                return run != null;
            }
            catch (Exception exception)
            {
                Debug.LogError($"[RunSaveSystem] Load failed: {exception.Message}");
                return false;
            }
        }

        private static bool IsPlayableState(GameState state)
        {
            return state == GameState.Map || state == GameState.Battle || state == GameState.Reward
                || state == GameState.EmberReward || state == GameState.Rest || state == GameState.Shop;
        }

        [Serializable]
        private sealed class RunSaveData
        {
            public int version = CurrentVersion;
            public GameState state;
            public int seed;
            public int act;
            public int roomIndex;
            public int health;
            public int strength;
            public RunMap map;
            public string currentNodeId;
            public ItemInventory itemInventory;
            public List<FantasySaveEntry> fantasies = new List<FantasySaveEntry>();
            public BattleNumberState currentBattle;
            public RestNumberState currentRest;
            public ShopNumberState currentShop;
            public BattleSessionState battleSession;
            public RewardSessionState rewardSession;
            public int passiveAttackCountBonus;
            public int lastShopPurchaseCost;
            public int stampCouponHealthSpent;
            public string debugForcedMonsterId;
            public List<FantasyEmberType> fantasyEmbers;
            public bool hasPendingEmber;
            public FantasyEmberType pendingEmber;
            public List<FantasyGrade> pendingFantasyRewardGrades;
            public List<StringIntEntry> playerTurnDamageValues;
            public List<StringIntEntry> monsterPatternDamageValues;
            public List<StringIntEntry> monsterPatternHitCountValues;
            public List<StringIntEntry> shopPrices;
            public List<StringIntEntry> shopPriceRollCounts;
            public List<StringStringEntry> shopFantasyIds;

            public static RunSaveData Capture(RunContext run, GameState state)
            {
                RunSaveData data = new RunSaveData
                {
                    state = state,
                    seed = run.seed,
                    act = run.act,
                    roomIndex = run.roomIndex,
                    health = run.health,
                    strength = run.strength,
                    map = run.map,
                    currentNodeId = run.currentNode != null ? run.currentNode.id : string.Empty,
                    itemInventory = run.itemInventory,
                    currentBattle = run.currentBattle,
                    currentRest = run.currentRest,
                    currentShop = run.currentShop,
                    battleSession = run.battleSession,
                    rewardSession = run.rewardSession,
                    passiveAttackCountBonus = run.passiveAttackCountBonus,
                    lastShopPurchaseCost = run.lastShopPurchaseCost,
                    stampCouponHealthSpent = run.stampCouponHealthSpent,
                    debugForcedMonsterId = run.debugForcedMonsterId,
                    fantasyEmbers = run.fantasyEmbers,
                    hasPendingEmber = run.hasPendingEmber,
                    pendingEmber = run.pendingEmber,
                    pendingFantasyRewardGrades = run.pendingFantasyRewardGrades
                };

                if (run.fantasyInventory?.ownedFantasies != null)
                {
                    foreach (FantasyData fantasy in run.fantasyInventory.ownedFantasies)
                    {
                        if (fantasy != null && !string.IsNullOrWhiteSpace(fantasy.id))
                            data.fantasies.Add(new FantasySaveEntry { id = fantasy.id, isTemporary = fantasy.isTemporary });
                    }
                }

                if (run.currentBattle != null)
                {
                    data.playerTurnDamageValues = Capture(run.currentBattle.playerTurnDamageValues);
                    data.monsterPatternDamageValues = Capture(run.currentBattle.monsterPatternDamageValues);
                    data.monsterPatternHitCountValues = Capture(run.currentBattle.monsterPatternHitCountValues);
                }
                if (run.currentShop != null)
                {
                    data.shopPrices = Capture(run.currentShop.prices);
                    data.shopPriceRollCounts = Capture(run.currentShop.priceRollCounts);
                    data.shopFantasyIds = Capture(run.currentShop.fantasyIds);
                }
                return data;
            }

            public RunContext Restore(FantasyDatabase database)
            {
                RunContext run = new RunContext
                {
                    seed = seed,
                    act = Mathf.Max(1, act),
                    roomIndex = Mathf.Max(0, roomIndex),
                    health = health,
                    strength = strength,
                    map = map,
                    itemInventory = itemInventory ?? new ItemInventory(),
                    currentBattle = currentBattle,
                    currentRest = currentRest,
                    currentShop = currentShop ?? new ShopNumberState(),
                    battleSession = battleSession ?? new BattleSessionState(),
                    rewardSession = rewardSession ?? new RewardSessionState(),
                    passiveAttackCountBonus = passiveAttackCountBonus,
                    lastShopPurchaseCost = lastShopPurchaseCost,
                    stampCouponHealthSpent = stampCouponHealthSpent,
                    debugForcedMonsterId = debugForcedMonsterId ?? string.Empty,
                    fantasyEmbers = fantasyEmbers ?? new List<FantasyEmberType>(),
                    hasPendingEmber = hasPendingEmber,
                    pendingEmber = pendingEmber,
                    pendingFantasyRewardGrades = pendingFantasyRewardGrades ?? new List<FantasyGrade>()
                };
                run.currentNode = run.map != null ? run.map.FindNode(currentNodeId) : null;
                run.fantasyInventory = new FantasyInventory();
                RestoreFantasies(run.fantasyInventory, database, fantasies);

                if (run.currentBattle != null)
                {
                    run.currentBattle.playerTurnDamageValues ??= new Dictionary<string, int>();
                    run.currentBattle.monsterPatternDamageValues ??= new Dictionary<string, int>();
                    run.currentBattle.monsterPatternHitCountValues ??= new Dictionary<string, int>();
                    Restore(run.currentBattle.playerTurnDamageValues, playerTurnDamageValues);
                    Restore(run.currentBattle.monsterPatternDamageValues, monsterPatternDamageValues);
                    Restore(run.currentBattle.monsterPatternHitCountValues, monsterPatternHitCountValues);
                }
                run.currentShop.prices ??= new Dictionary<string, int>();
                run.currentShop.priceRollCounts ??= new Dictionary<string, int>();
                run.currentShop.fantasyIds ??= new Dictionary<string, string>();
                Restore(run.currentShop.prices, shopPrices);
                Restore(run.currentShop.priceRollCounts, shopPriceRollCounts);
                Restore(run.currentShop.fantasyIds, shopFantasyIds);
                return run;
            }

            private static void RestoreFantasies(FantasyInventory inventory, FantasyDatabase database, List<FantasySaveEntry> entries)
            {
                if (entries == null || database?.fantasies == null)
                    return;
                foreach (FantasySaveEntry entry in entries)
                {
                    FantasyData source = database.fantasies.Find(value => value != null && value.id == entry.id);
                    if (source == null)
                    {
                        Debug.LogWarning($"[RunSaveSystem] Missing fantasy '{entry.id}' while loading save.");
                        continue;
                    }
                    inventory.AddDuplicate(entry.isTemporary ? CloneTemporary(source) : source);
                }
            }

            private static FantasyData CloneTemporary(FantasyData source)
            {
                return new FantasyData
                {
                    id = source.id, sourceId = source.sourceId, dataCode = source.dataCode,
                    devName = source.devName, nameStringId = source.nameStringId, descStringId = source.descStringId,
                    grade = source.grade, triggerType = source.triggerType, displayName = source.displayName,
                    description = source.description, sprite = source.sprite, iconSprite = source.iconSprite,
                    rawEffects = source.rawEffects, effects = source.effects, isTemporary = true,
                    trigger = source.trigger, target = source.target, value = source.value,
                    specialHandler = source.specialHandler
                };
            }

            private static List<StringIntEntry> Capture(Dictionary<string, int> source)
            {
                List<StringIntEntry> entries = new List<StringIntEntry>();
                if (source != null)
                    foreach (KeyValuePair<string, int> pair in source)
                        entries.Add(new StringIntEntry { key = pair.Key, value = pair.Value });
                return entries;
            }

            private static List<StringStringEntry> Capture(Dictionary<string, string> source)
            {
                List<StringStringEntry> entries = new List<StringStringEntry>();
                if (source != null)
                    foreach (KeyValuePair<string, string> pair in source)
                        entries.Add(new StringStringEntry { key = pair.Key, value = pair.Value });
                return entries;
            }

            private static void Restore(Dictionary<string, int> target, List<StringIntEntry> entries)
            {
                target.Clear();
                if (entries != null)
                    foreach (StringIntEntry entry in entries)
                        if (!string.IsNullOrEmpty(entry.key)) target[entry.key] = entry.value;
            }

            private static void Restore(Dictionary<string, string> target, List<StringStringEntry> entries)
            {
                target.Clear();
                if (entries != null)
                    foreach (StringStringEntry entry in entries)
                        if (!string.IsNullOrEmpty(entry.key)) target[entry.key] = entry.value;
            }
        }

        [Serializable] private sealed class FantasySaveEntry { public string id; public bool isTemporary; }
        [Serializable] private sealed class StringIntEntry { public string key; public int value; }
        [Serializable] private sealed class StringStringEntry { public string key; public string value; }
    }
}
