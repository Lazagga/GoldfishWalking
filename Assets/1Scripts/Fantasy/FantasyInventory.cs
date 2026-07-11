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

        public void Clear()
        {
            ownedFantasies.Clear();
        }
    }

    public static class FantasyCollectionRules
    {
        public const string AnimalFriendsId = "fan_attack_animalfriends";
        public const string StencilId = "fan_shop_stencil";
        public const string CoffeeId = "fan_rest_coffee";

        private static readonly string[] CosmeticAnimalFriendIds =
        {
            "fan_rabbit_head",
            "fan_turtle_head",
            "fan_cat_head",
            "fan_parrot_head"
        };

        public static bool CanAppearInRewardOrShop(FantasyData fantasy)
        {
            return fantasy != null && fantasy.id != AnimalFriendsId;
        }

        public static void ApplyPostAcquireTransforms(FantasyInventory inventory, FantasyDatabase database)
        {
            if (inventory == null || database == null || database.fantasies == null)
                return;
            if (inventory.Contains(AnimalFriendsId))
                return;

            for (int i = 0; i < CosmeticAnimalFriendIds.Length; i++)
            {
                if (!inventory.Contains(CosmeticAnimalFriendIds[i]))
                    return;
            }

            FantasyData animalFriends = FindFantasy(database, AnimalFriendsId);
            if (animalFriends != null)
                inventory.Add(animalFriends);
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
    }
}
