using GoldfishWalking.Data;
using GoldfishWalking.Formula;

namespace GoldfishWalking.Item
{
    public sealed class ItemUseController
    {
        public bool TryUseExtraMatch(ItemInventory inventory, FormulaBox targetBox)
        {
            return targetBox != null
                && !targetBox.locked
                && inventory != null
                && inventory.TryConsume(ItemType.ExtraMatch);
        }

        public bool TryUseEraser(ItemInventory inventory, FormulaBox targetBox)
        {
            return targetBox != null
                && !targetBox.locked
                && inventory != null
                && inventory.TryConsume(ItemType.Eraser);
        }
    }
}
