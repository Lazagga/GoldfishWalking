using UnityEngine;

namespace GoldfishWalking.Data
{
    [CreateAssetMenu(menuName = "GoldfishWalking/UI/UI Skin")]
    public sealed class UiSkinData : ScriptableObject
    {
        public Sprite nextButton;
        public Sprite resetButton;
        public Sprite closeButton;
        public Sprite textPanel;
        public Sprite singleButton;
        public Sprite connectedLeftButton;
        public Sprite connectedMiddleButton;
        public Sprite connectedRightButton;
    }
}
