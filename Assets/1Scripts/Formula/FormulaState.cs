using System;
using System.Collections.Generic;

namespace GoldfishWalking.Formula
{
    [Serializable]
    public sealed class FormulaState
    {
        public List<FormulaBox> boxes = new List<FormulaBox>();

        public void Clear()
        {
            boxes.Clear();
        }
    }
}
