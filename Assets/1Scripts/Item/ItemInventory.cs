using System;
using System.Collections.Generic;
using GoldfishWalking.Data;

namespace GoldfishWalking.Item
{
    [Serializable]
    public sealed class ItemInventory
    {
        public List<ItemStack> items = new List<ItemStack>();
        public List<ItemStack> temporaryItems = new List<ItemStack>();

        public int GetCount(ItemType itemType)
        {
            ItemStack stack = items.Find(item => item.itemType == itemType);
            ItemStack temporaryStack = temporaryItems.Find(item => item.itemType == itemType);
            return (stack != null ? stack.count : 0) + (temporaryStack != null ? temporaryStack.count : 0);
        }

        public void Add(ItemType itemType, int count)
        {
            AddTo(items, itemType, count);
        }

        public void AddTemporary(ItemType itemType, int count)
        {
            AddTo(temporaryItems, itemType, count);
        }

        public bool TryConsume(ItemType itemType)
        {
            return TryConsume(itemType, out _);
        }

        public bool TryConsume(ItemType itemType, out bool consumedTemporary)
        {
            ItemStack temporaryStack = temporaryItems.Find(item => item.itemType == itemType);
            if (temporaryStack != null && temporaryStack.count > 0)
            {
                temporaryStack.count--;
                consumedTemporary = true;
                return true;
            }

            ItemStack stack = items.Find(item => item.itemType == itemType);
            if (stack == null || stack.count <= 0)
            {
                consumedTemporary = false;
                return false;
            }

            stack.count--;
            consumedTemporary = false;
            return true;
        }

        public void ClearTemporary()
        {
            temporaryItems.Clear();
        }

        public void Clear()
        {
            items.Clear();
            temporaryItems.Clear();
        }

        private static void AddTo(List<ItemStack> target, ItemType itemType, int count)
        {
            if (count <= 0)
                return;

            ItemStack stack = target.Find(item => item.itemType == itemType);
            if (stack == null)
            {
                stack = new ItemStack { itemType = itemType };
                target.Add(stack);
            }

            stack.count += count;
        }
    }

    [Serializable]
    public sealed class ItemStack
    {
        public ItemType itemType;
        public int count;
    }
}
