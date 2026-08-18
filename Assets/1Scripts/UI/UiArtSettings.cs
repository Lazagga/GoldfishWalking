using UnityEngine;
using UnityEngine.UI;

namespace GoldfishWalking.UI
{
    public sealed class UiArtSettings : MonoBehaviour
    {
        [SerializeField] private Sprite campfireIcon;
        [SerializeField] private Sprite battleIcon;
        [SerializeField] private Sprite bossIcon;
        [SerializeField] private Sprite eraserIcon;
        [SerializeField] private Sprite matchItemIcon;
        [SerializeField] private Sprite expandedPanel;
        [SerializeField] private Sprite textContainerLeft;
        [SerializeField] private Sprite textContainerMiddle;
        [SerializeField] private Sprite textContainerRight;

        public static UiArtSettings Instance { get; private set; }
        public Sprite CampfireIcon => campfireIcon;
        public Sprite BattleIcon => battleIcon;
        public Sprite BossIcon => bossIcon;
        public Sprite EraserIcon => eraserIcon;
        public Sprite MatchItemIcon => matchItemIcon;

        private void Awake() => Instance = this;

        private void OnDestroy()
        {
            if (Instance == this)
                Instance = null;
        }

        public void Configure(Sprite campfire, Sprite battle, Sprite boss, Sprite eraser, Sprite matchItem, Sprite panel,
            Sprite containerLeft, Sprite containerMiddle, Sprite containerRight)
        {
            campfireIcon = campfire;
            battleIcon = battle;
            bossIcon = boss;
            eraserIcon = eraser;
            matchItemIcon = matchItem;
            expandedPanel = panel;
            textContainerLeft = containerLeft;
            textContainerMiddle = containerMiddle;
            textContainerRight = containerRight;
            Instance = this;
        }

        public static UiArtSettings Resolve()
        {
            if (Instance == null)
                Instance = FindFirstObjectByType<UiArtSettings>(FindObjectsInactive.Include);
            return Instance;
        }

        public static Image ApplyIcon(Transform target, Sprite sprite, float size = 48f)
        {
            if (target == null || sprite == null)
                return null;
            Transform existing = target.Find("ArtIcon");
            GameObject iconObject = existing != null ? existing.gameObject
                : new GameObject("ArtIcon", typeof(RectTransform), typeof(CanvasRenderer), typeof(Image));
            if (existing == null)
                iconObject.transform.SetParent(target, false);
            Image image = iconObject.GetComponent<Image>();
            image.sprite = sprite;
            image.type = Image.Type.Simple;
            image.preserveAspect = true;
            image.color = Color.white;
            image.raycastTarget = false;
            RectTransform rect = image.rectTransform;
            rect.anchorMin = rect.anchorMax = rect.pivot = new Vector2(0.5f, 0.5f);
            rect.anchoredPosition = Vector2.zero;
            rect.sizeDelta = new Vector2(size, size);
            rect.SetAsLastSibling();
            Text oldIcon = target.Find("Icon")?.GetComponent<Text>();
            if (oldIcon != null)
                oldIcon.enabled = false;
            return image;
        }
    }
}
