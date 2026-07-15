using System;
using System.Collections.Generic;
using GoldfishWalking.Data;

namespace GoldfishWalking.Fantasy
{
    [Serializable]
    public sealed class FantasyInventory
    {
        public List<FantasyData> ownedFantasies = new List<FantasyData>();

        public void Add(FantasyData fantasy)
        {
            if (fantasy == null || Contains(fantasy.id))
                return;

            ownedFantasies.Add(fantasy);
        }

        public void AddDuplicate(FantasyData fantasy)
        {
            if (fantasy == null)
                return;

            ownedFantasies.Add(fantasy);
        }

        public void Remove(FantasyData fantasy)
        {
            if (fantasy == null)
                return;

            ownedFantasies.Remove(fantasy);
        }

        public void RemoveTemporary()
        {
            for (int i = ownedFantasies.Count - 1; i >= 0; i--)
            {
                FantasyData fantasy = ownedFantasies[i];
                if (fantasy != null && fantasy.isTemporary)
                    ownedFantasies.RemoveAt(i);
            }
        }

        public bool Contains(string id)
        {
            return ownedFantasies.Exists(fantasy => fantasy != null && fantasy.id == id);
        }

        public bool HasEffect(string target, string calc = null)
        {
            string normalizedTarget = Normalize(target);
            string normalizedCalc = Normalize(calc);
            for (int i = 0; i < ownedFantasies.Count; i++)
            {
                FantasyEffectData[] effects = ownedFantasies[i]?.effects;
                if (effects == null)
                    continue;
                for (int j = 0; j < effects.Length; j++)
                {
                    FantasyEffectData effect = effects[j];
                    if (effect != null && Normalize(effect.target) == normalizedTarget
                        && (string.IsNullOrEmpty(normalizedCalc) || Normalize(effect.calc) == normalizedCalc))
                        return true;
                }
            }
            return false;
        }

        public static bool DataHasEffect(FantasyData fantasy, string target, string calc = null)
        {
            string normalizedTarget = Normalize(target);
            string normalizedCalc = Normalize(calc);
            FantasyEffectData[] effects = fantasy?.effects;
            if (effects == null)
                return false;
            for (int i = 0; i < effects.Length; i++)
            {
                FantasyEffectData effect = effects[i];
                if (effect != null && Normalize(effect.target) == normalizedTarget
                    && (string.IsNullOrEmpty(normalizedCalc) || Normalize(effect.calc) == normalizedCalc))
                    return true;
            }
            return false;
        }

        private static string Normalize(string value)
        {
            return (value ?? string.Empty).Trim().Replace("_", string.Empty).Replace("-", string.Empty).Replace(" ", string.Empty).ToLowerInvariant();
        }

        public void Clear()
        {
            ownedFantasies.Clear();
        }
    }

    public static class FantasyCollectionRules
    {
public static bool CanAppearInRewardOrShop(FantasyData fantasy)
        {
            return fantasy != null && !FantasyInventory.DataHasEffect(fantasy, "Availability", "Exclude");
        }

public static int ApplyShopPurchaseTransforms(FantasyInventory inventory, FantasyDatabase database, int accumulatedHealthSpent, int purchaseCost)
        {
            if (inventory == null || database == null || purchaseCost <= 0)
                return accumulatedHealthSpent;

            FantasyEffectData transform = null;
            for (int i = 0; i < inventory.ownedFantasies.Count && transform == null; i++)
                transform = FindEffect(inventory.ownedFantasies[i], "Health_Spent", "Transform");

            if (transform == null)
                return accumulatedHealthSpent;

            accumulatedHealthSpent = purchaseCost > int.MaxValue - accumulatedHealthSpent
                ? int.MaxValue : accumulatedHealthSpent + purchaseCost;
            int threshold = transform.hasNumericValue ? UnityEngine.Mathf.Max(1, UnityEngine.Mathf.FloorToInt(transform.numericValue)) : 1;
            if (accumulatedHealthSpent < threshold || string.IsNullOrWhiteSpace(transform.option))
                return accumulatedHealthSpent;

            FantasyData reward = FindFantasy(database, transform.option);
            if (reward != null && !inventory.Contains(reward.id))
                inventory.Add(reward);
            return accumulatedHealthSpent;
        }

public static void ApplyPostAcquireTransforms(FantasyInventory inventory, FantasyDatabase database)
        {
            if (inventory == null || database?.fantasies == null)
                return;

            for (int i = 0; i < database.fantasies.Count; i++)
            {
                FantasyData result = database.fantasies[i];
                FantasyEffectData recipe = FindEffect(result, "Collection", "Combine");
                if (recipe == null || inventory.Contains(result.id) || string.IsNullOrWhiteSpace(recipe.option))
                    continue;

                string[] requiredIds = recipe.option.Split(',');
                bool complete = true;
                for (int j = 0; j < requiredIds.Length; j++)
                {
                    if (!inventory.Contains(requiredIds[j].Trim()))
                    {
                        complete = false;
                        break;
                    }
                }
                if (complete)
                    inventory.Add(result);
            }
        }

        private static FantasyData FindFantasy(FantasyDatabase database, string fantasyId)
        {
            for (int i = 0; i < database.fantasies.Count; i++)
            {
                FantasyData fantasy = database.fantasies[i];
                if (fantasy != null && fantasy.id == fantasyId)
                    return fantasy;
            }

            return null;
        }


private static FantasyEffectData FindEffect(FantasyData fantasy, string target, string calc)
        {
            if (fantasy?.effects == null)
                return null;
            string normalizedTarget = Normalize(target);
            string normalizedCalc = Normalize(calc);
            for (int i = 0; i < fantasy.effects.Length; i++)
            {
                FantasyEffectData effect = fantasy.effects[i];
                if (effect != null && Normalize(effect.target) == normalizedTarget && Normalize(effect.calc) == normalizedCalc)
                    return effect;
            }
            return null;
        }

        private static string Normalize(string value)
        {
            return (value ?? string.Empty).Trim().Replace("_", string.Empty).Replace("-", string.Empty).Replace(" ", string.Empty).ToLowerInvariant();
        }
}
}
