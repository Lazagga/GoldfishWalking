using GoldfishWalking.Data;
using UnityEngine;
using UnityEngine.UI;

namespace GoldfishWalking.UI
{
    public sealed class FantasyTooltipView : MonoBehaviour
    {
        [SerializeField] private Text titleText;
        [SerializeField] private Text descriptionText;
        [SerializeField] private Text effectText;
        [SerializeField] private Vector2 cursorOffset = Vector2.zero;

        private RectTransform rectTransform;
        private RectTransform canvasRect;
        private Canvas canvas;
        private bool visible;

        private void Awake()
        {
            ResolveReferences();
            Hide();
        }

        private void Update()
        {
            if (!visible)
                return;

            FollowMouse();
        }

        public void Bind(Text title, Text description, Text effect)
        {
            titleText = title;
            descriptionText = description;
            effectText = effect;
            ResolveReferences();
        }

        public void Show(FantasyData fantasy)
        {
            if (fantasy == null)
                return;

            Show(FantasyText.DisplayName(fantasy), FantasyText.Description(fantasy), FantasyText.EffectSummary(fantasy));
        }

        public void Show(string title, string description, string effect)
        {
            ResolveReferences();

            if (titleText != null)
                titleText.text = title ?? string.Empty;
            if (descriptionText != null)
                descriptionText.text = description ?? string.Empty;
            if (effectText != null)
                effectText.text = effect ?? string.Empty;

            visible = true;
            gameObject.SetActive(true);
            transform.SetAsLastSibling();
            FollowMouse();
        }

        public void Hide()
        {
            visible = false;
            gameObject.SetActive(false);
        }

        private void ResolveReferences()
        {
            if (rectTransform == null)
                rectTransform = transform as RectTransform;
            if (rectTransform != null)
                rectTransform.pivot = new Vector2(0f, 1f);
            if (canvas == null)
                canvas = GetComponentInParent<Canvas>(true);
            if (canvasRect == null && canvas != null)
                canvasRect = canvas.transform as RectTransform;

            DisableRaycasts();
        }

        private void DisableRaycasts()
        {
            Graphic[] graphics = GetComponentsInChildren<Graphic>(true);
            for (int i = 0; i < graphics.Length; i++)
            {
                if (graphics[i] != null)
                    graphics[i].raycastTarget = false;
            }

            CanvasGroup canvasGroup = GetComponent<CanvasGroup>();
            if (canvasGroup == null)
                canvasGroup = gameObject.AddComponent<CanvasGroup>();

            canvasGroup.blocksRaycasts = false;
            canvasGroup.interactable = false;
        }

        private void FollowMouse()
        {
            if (rectTransform == null || canvasRect == null)
                return;

            Camera eventCamera = canvas != null && canvas.renderMode != RenderMode.ScreenSpaceOverlay ? canvas.worldCamera : null;
            if (!RectTransformUtility.ScreenPointToLocalPointInRectangle(canvasRect, Input.mousePosition, eventCamera, out Vector2 localPoint))
                return;

            Vector2 target = localPoint + cursorOffset;
            Vector2 halfCanvas = canvasRect.rect.size * 0.5f;
            Vector2 tooltipSize = rectTransform.rect.size;

            target.x = Mathf.Clamp(target.x, -halfCanvas.x, halfCanvas.x - tooltipSize.x);
            target.y = Mathf.Clamp(target.y, -halfCanvas.y + tooltipSize.y, halfCanvas.y);
            rectTransform.anchoredPosition = target;
        }
    }
}
