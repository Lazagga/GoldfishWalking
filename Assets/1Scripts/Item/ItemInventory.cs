using System;
using System.Collections.Generic;
using GoldfishWalking.Data;

namespace GoldfishWalking.Item
{
    [Serializable]
    public sealed class ItemInventory
    {
        public List<ItemStack> items = new List<ItemStack>();

        public int GetCount(ItemType itemType)
        {
            ItemStack stack = items.Find(item => item.itemType == itemType);
            return stack != null ? stack.count : 0;
        }

        public void Add(ItemType itemType, int count)
        {
            ItemStack stack = items.Find(item => item.itemType == itemType);
            if (stack == null)
            {
                stack = new ItemStack { itemType = itemType };
                items.Add(stack);
            }

            stack.count += count;
        }

        public bool TryConsume(ItemType itemType)
        {
            ItemStack stack = items.Find(item => item.itemType == itemType);
            if (stack == null || stack.count <= 0)
                return false;

            stack.count--;
            return true;
        }

        public void Clear()
        {
            items.Clear();
        }
    }

    [Serializable]
    public sealed class ItemStack
    {
        public ItemType itemType;
        public int count;
    }
}
