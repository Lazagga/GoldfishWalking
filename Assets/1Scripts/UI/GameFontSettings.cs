using UnityEngine;
using UnityEngine.UI;

namespace GoldfishWalking.UI
{
    public sealed class GameFontSettings : MonoBehaviour
    {
        [SerializeField] private Font gameFont;

        public static GameFontSettings Instance { get; private set; }

        private void Awake()
        {
            Instance = this;
        }

        private void OnDestroy()
        {
            if (Instance == this)
                Instance = null;
        }

        public void Configure(Font font)
        {
            gameFont = font;
            Instance = this;
        }

        public static Font ResolveFont()
        {
            if (Instance == null)
                Instance = FindFirstObjectByType<GameFontSettings>(FindObjectsInactive.Include);
            return Instance != null && Instance.gameFont != null
                ? Instance.gameFont
                : Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
        }

        public static void Apply(Text text)
        {
            if (text != null)
                text.font = ResolveFont();
        }
    }
}
