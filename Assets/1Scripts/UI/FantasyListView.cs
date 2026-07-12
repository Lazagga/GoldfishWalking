using System.Collections.Generic;
using GoldfishWalking.Data;
using UnityEngine;
using UnityEngine.UI;

namespace GoldfishWalking.UI
{
    public sealed class FantasyListView : MonoBehaviour
    {
        [SerializeField] private RectTransform contentRoot;
        [SerializeField] private FantasyTooltipView tooltipView;
        private bool dynamicSlotsInitialized;
        private Vector2 slotSize = new Vector2(68f, 68f);
        private Vector2 initialContentSize;
        private Color slotColor = new Color(0.20f, 0.22f, 0.29f, 0.96f);
        private const float SlotSpacing = 8f;

        public void Bind(RectTransform root, FantasyTooltipView tooltip, int slotCount)
        {
            RectTransform nextRoot = root != null ? root : transform as RectTransform;
            if (contentRoot != nextRoot)
                dynamicSlotsInitialized = false;
            contentRoot = nextRoot;
            tooltipView = tooltip;
        }

        public void Refresh(IReadOnlyList<FantasyData> fantasies)
        {
            if (contentRoot == null)
                contentRoot = transform as RectTransform;
            if (contentRoot == null)
                return;

            int fantasyCount = fantasies != null ? fantasies.Count : 0;
            InitializeDynamicSlots();
            SetSlotCount(fantasyCount);
            for (int i = 0; i < fantasyCount; i++)
                BindSlot(contentRoot.GetChild(i), fantasies[i]);
            LayoutSlots();
        }

        private void InitializeDynamicSlots()
        {
            if (dynamicSlotsInitialized || contentRoot == null)
                return;

            initialContentSize = contentRoot.sizeDelta;

            if (contentRoot.childCount > 0)
            {
                RectTransform templateRect = contentRoot.GetChild(0) as RectTransform;
                if (templateRect != null)
                    slotSize = templateRect.sizeDelta;
                Image templateImage = contentRoot.GetChild(0).GetComponent<Image>();
                if (templateImage != null)
                    slotColor = templateImage.color;
            }

            for (int i = contentRoot.childCount - 1; i >= 0; i--)
            {
                GameObject child = contentRoot.GetChild(i).gameObject;
                child.transform.SetParent(null, false);
                if (Application.isPlaying)
                    Destroy(child);
                else
                    DestroyImmediate(child);
            }

            dynamicSlotsInitialized = true;
        }

        private void SetSlotCount(int requiredCount)
        {
            while (contentRoot.childCount > requiredCount)
            {
                GameObject child = contentRoot.GetChild(contentRoot.childCount - 1).gameObject;
                child.transform.SetParent(null, false);
                if (Application.isPlaying)
                    Destroy(child);
                else
                    DestroyImmediate(child);
            }

            while (contentRoot.childCount < requiredCount)
                CreateSlot(contentRoot.childCount + 1);
        }

        private void CreateSlot(int oneBasedIndex)
        {
            GameObject slotObject = new GameObject($"FantasySlot{oneBasedIndex}", typeof(RectTransform), typeof(CanvasRenderer), typeof(Image));
            RectTransform rect = slotObject.GetComponent<RectTransform>();
            rect.SetParent(contentRoot, false);
            rect.sizeDelta = slotSize;

            Image image = slotObject.GetComponent<Image>();
            image.color = slotColor;
            image.raycastTarget = true;
        }

        private void LayoutSlots()
        {
            if (contentRoot == null)
                return;

            float width = Mathf.Max(1f, slotSize.x);
            float height = Mathf.Max(1f, slotSize.y);
            for (int i = 0; i < contentRoot.childCount; i++)
            {
                RectTransform slot = contentRoot.GetChild(i) as RectTransform;
                if (slot == null)
                    continue;

                slot.anchorMin = new Vector2(0f, 0.5f);
                slot.anchorMax = new Vector2(0f, 0.5f);
                slot.pivot = new Vector2(0f, 0.5f);
                slot.sizeDelta = new Vector2(width, height);
                slot.anchoredPosition = new Vector2(i * (width + SlotSpacing), 0f);
            }

            float requiredWidth = contentRoot.childCount > 0
                ? contentRoot.childCount * width + (contentRoot.childCount - 1) * SlotSpacing
                : 0f;
            contentRoot.sizeDelta = new Vector2(requiredWidth, Mathf.Max(initialContentSize.y, height));
        }

        private void BindSlot(Transform slot, FantasyData fantasy)
        {
            if (slot == null)
                return;

            slot.gameObject.SetActive(true);
            Text icon = slot.GetComponentInChildren<Text>(true);
            if (icon == null)
                icon = CreateIcon(slot);
            if (icon != null)
            {
                icon.text = fantasy != null ? "★" : string.Empty;
                icon.color = fantasy != null
                    ? FantasyText.GradeColor(fantasy.grade, Color.white, new Color(0.24f, 0.74f, 0.90f, 1f), new Color(1f, 0.32f, 0.32f, 1f))
                    : Color.white;
            }

            FantasyTooltipTrigger trigger = slot.GetComponent<FantasyTooltipTrigger>();
            if (trigger == null)
                trigger = slot.gameObject.AddComponent<FantasyTooltipTrigger>();
            trigger.Initialize(tooltipView, fantasy);
        }

        private static Text CreateIcon(Transform slot)
        {
            GameObject iconObject = new GameObject("FantasyIcon", typeof(RectTransform), typeof(CanvasRenderer), typeof(Text));
            RectTransform rect = iconObject.GetComponent<RectTransform>();
            rect.SetParent(slot, false);
            rect.anchorMin = Vector2.zero;
            rect.anchorMax = Vector2.one;
            rect.offsetMin = Vector2.zero;
            rect.offsetMax = Vector2.zero;

            Text icon = iconObject.GetComponent<Text>();
            icon.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            icon.fontSize = 34;
            icon.fontStyle = FontStyle.Bold;
            icon.alignment = TextAnchor.MiddleCenter;
            icon.raycastTarget = false;
            return icon;
        }
    }
}
