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
        [SerializeField] private int visibleSlots = 10;

        public void Bind(RectTransform root, FantasyTooltipView tooltip, int slotCount)
        {
            contentRoot = root != null ? root : transform as RectTransform;
            tooltipView = tooltip;
            visibleSlots = Mathf.Max(0, slotCount);
        }

        public void Refresh(IReadOnlyList<FantasyData> fantasies)
        {
            if (contentRoot == null)
                contentRoot = transform as RectTransform;
            if (contentRoot == null)
                return;

            int slotCount = Mathf.Min(visibleSlots, contentRoot.childCount);
            for (int i = 0; i < slotCount; i++)
                BindSlot(contentRoot.GetChild(i), fantasies != null && i < fantasies.Count ? fantasies[i] : null);

            for (int i = slotCount; i < contentRoot.childCount; i++)
                contentRoot.GetChild(i).gameObject.SetActive(false);

            if (visibleSlots > contentRoot.childCount)
                Debug.LogWarning($"[FantasyListView] Not enough prebuilt fantasy slots: requested {visibleSlots}, found {contentRoot.childCount}.");
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
            if (trigger != null)
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
