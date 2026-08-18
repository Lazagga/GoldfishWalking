using UnityEngine;
using UnityEngine.UI;
using GoldfishWalking.Data;

namespace GoldfishWalking.Match
{
    public sealed class MatchstickVisualSettings : MonoBehaviour
    {
        [SerializeField] private Sprite matchSprite;
        [SerializeField] private UiSkinData uiSkin;

        public static MatchstickVisualSettings Instance { get; private set; }

        private void Awake()
        {
            Instance = this;
        }

        private void OnDestroy()
        {
            if (Instance == this)
                Instance = null;
        }

        public void Configure(Sprite sprite, UiSkinData skin)
        {
            matchSprite = sprite;
            uiSkin = skin;
            Instance = this;
        }

        public static void Apply(Image image)
        {
            MatchstickVisualSettings settings = Resolve();
            if (image == null || settings == null || settings.matchSprite == null)
                return;
            image.sprite = settings.matchSprite;
            image.type = Image.Type.Simple;
            image.preserveAspect = true;
        }

        public static void ApplySoloButton(Image image)
        {
            MatchstickVisualSettings settings = Resolve();
            if (image == null || settings == null || settings.uiSkin == null || settings.uiSkin.singleButton == null)
                return;
            image.sprite = settings.uiSkin.singleButton;
            image.type = Image.Type.Sliced;
            image.color = Color.white;
            image.raycastTarget = true;
        }

        private static MatchstickVisualSettings Resolve()
        {
            if (Instance == null)
                Instance = FindFirstObjectByType<MatchstickVisualSettings>(FindObjectsInactive.Include);
            return Instance;
        }
    }
}
