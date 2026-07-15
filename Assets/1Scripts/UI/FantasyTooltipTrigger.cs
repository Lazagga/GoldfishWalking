using GoldfishWalking.Data;
using UnityEngine;
using UnityEngine.EventSystems;

namespace GoldfishWalking.UI
{
    public sealed class FantasyTooltipTrigger : MonoBehaviour, IPointerEnterHandler, IPointerExitHandler, IPointerMoveHandler
    {
        private FantasyTooltipView tooltip;
        private FantasyData fantasy;
        private string title;
        private string description;
        private string effect;
        private bool usesText;

        public void Initialize(FantasyTooltipView tooltipView, FantasyData tooltipFantasy)
        {
            tooltip = tooltipView;
            fantasy = tooltipFantasy;
            usesText = false;
        }

public bool Matches(FantasyData candidate)
        {
            return fantasy != null && candidate != null && ReferenceEquals(fantasy, candidate);
        }


        public void Initialize(FantasyTooltipView tooltipView, string tooltipTitle, string tooltipDescription, string tooltipEffect)
        {
            tooltip = tooltipView;
            title = tooltipTitle;
            description = tooltipDescription;
            effect = tooltipEffect;
            usesText = true;
        }

        public void OnPointerEnter(PointerEventData eventData)
        {
            if (tooltip == null)
                return;

            if (usesText)
                tooltip.Show(title, description, effect);
            else
                tooltip.Show(fantasy);
        }

        public void OnPointerExit(PointerEventData eventData)
        {
            if (tooltip != null)
                tooltip.Hide();
        }

        public void OnPointerMove(PointerEventData eventData)
        {
            OnPointerEnter(eventData);
        }
    }
}
