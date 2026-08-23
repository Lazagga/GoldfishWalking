using System.Collections;
using System.Collections.Generic;
using GoldfishWalking.Data;
using GoldfishWalking.Match;
using GoldfishWalking.Rest;
using UnityEngine;
using UnityEngine.UI;
#if UNITY_EDITOR
using UnityEditor;
#endif

namespace GoldfishWalking.UI
{
    public sealed class RestView : MonoBehaviour
    {
        private const int DefaultHealAmount = 91;

        [SerializeField] private RestController restController;
        [SerializeField] private int healAmount = DefaultHealAmount;
        [SerializeField] private Sprite restBackground;
        [SerializeField] private Sprite restBackgroundLessBright;
        [SerializeField] private Sprite[] campfireFrames;
        [SerializeField] private float campfireFrameDuration = 0.16f;

        private readonly Color backgroundColor = new Color(0.58f, 0.66f, 0.72f, 1f);
        private readonly Color panelColor = new Color(0.14f, 0.16f, 0.20f, 0.92f);
        private readonly Color fantasySlotColor = new Color(0.20f, 0.22f, 0.29f, 0.96f);
        private readonly Color matchColor = new Color(1.0f, 0.74f, 0.33f, 1f);
        private readonly Color textColor = new Color(0.95f, 0.97f, 1f, 1f);
        private readonly Color healColor = new Color(0.16f, 0.90f, 0.48f, 1f);

        private RectTransform layoutRoot;
        private RectTransform statusPanel;
        private RectTransform fantasyContentRoot;
        private RectTransform matchNumberRoot;
        private RectTransform fantasyTooltipRoot;
        private Image restBackgroundImage;
        private Image campfireImage;
        private Text healthText;
        private Text moveCountText;
        private Text healFloatText;
        private Text fantasyTooltipName;
        private Text fantasyTooltipDescription;
        private Text fantasyTooltipEffect;
        private FantasyTooltipView fantasyTooltipView;
        private FantasyListView fantasyListView;
        private Button restButton;
        private Button coffeeButton;
        private Button nextButton;
        private Coroutine healFloatRoutine;
        private Coroutine campfireRoutine;
        private int restUseCount;
        private int healMoveDifference;

        private void Awake()
        {
            ResolveReferences();
            HideScenePlaceholders();
            EnsureLayout();
            BindExistingLayout();
            BindButtons();
        }

        private void OnEnable()
        {
            restUseCount = 0;
            ResolveReferences();
            HideScenePlaceholders();
            EnsureLayout();
            BindExistingLayout();
            Refresh();
            RestartCampfireAnimation();
        }

        private void OnDisable()
        {
            if (campfireRoutine != null)
            {
                StopCoroutine(campfireRoutine);
                campfireRoutine = null;
            }
        }

        private void OnDestroy()
        {
            UnbindButtons();
        }

        private void ResolveReferences()
        {
            if (restController == null)
                Debug.LogError("[RestView] RestController must be assigned in GumBwing_Er.unity.", this);
        }

        private void HideScenePlaceholders()
        {
            for (int i = 0; i < transform.childCount; i++)
            {
                Transform child = transform.GetChild(i);
                if (layoutRoot != null && child == layoutRoot)
                    continue;
                if (child.name == "RestRuntimeLayout")
                {
                    layoutRoot = child as RectTransform;
                    continue;
                }

                child.gameObject.SetActive(false);
            }
        }

        private void RemoveExistingLayoutImmediate()
        {
            layoutRoot = null;

            for (int i = transform.childCount - 1; i >= 0; i--)
            {
                Transform child = transform.GetChild(i);
                if (child.name != "RestRuntimeLayout")
                    continue;

                DestroyImmediate(child.gameObject);
            }
        }

#if UNITY_EDITOR
        [ContextMenu("Rebuild Scene UI Layout")]
        public void RebuildSceneUILayout()
        {
            ResolveReferences();
            RemoveExistingLayoutImmediate();
            EnsureLayout();
            BindExistingLayout();
            EditorUtility.SetDirty(gameObject);
            UnityEditor.SceneManagement.EditorSceneManager.MarkSceneDirty(gameObject.scene);
        }
#endif

        private void EnsureLayout()
        {
            if (layoutRoot != null)
                return;

            Transform existing = transform.Find("RestRuntimeLayout");
            if (existing is RectTransform existingLayout)
            {
                layoutRoot = existingLayout;
                BindExistingLayout();
                return;
            }

            Debug.LogError("[RestView] Missing prebuilt RestRuntimeLayout. Build the UI in the scene instead of creating it from script.");
        }

        private void BindExistingLayout()
        {
            if (layoutRoot == null)
                return;

            statusPanel = FindRect("StatusPanel");
            fantasyContentRoot = FindRect("FantasySlots/Viewport/Content");
            matchNumberRoot = FindRect("MatchNumber");
            fantasyTooltipRoot = FindRect("FantasyTooltip");
            restBackgroundImage = FindComponent<Image>("RestSceneArt/Background");
            campfireImage = FindComponent<Image>("RestSceneArt/Campfire");
            healthText = FindComponent<Text>("StatusPanel/Health");
            moveCountText = FindComponent<Text>("MoveCounter/MoveCount");
            healFloatText = FindComponent<Text>("StatusPanel/HealFloat");
            fantasyTooltipName = FindComponent<Text>("FantasyTooltip/Name");
            fantasyTooltipDescription = FindComponent<Text>("FantasyTooltip/Description");
            fantasyTooltipEffect = FindComponent<Text>("FantasyTooltip/Effect");
            fantasyTooltipView = fantasyTooltipRoot != null ? fantasyTooltipRoot.GetComponent<FantasyTooltipView>() : null;
            if (fantasyTooltipView != null)
                fantasyTooltipView.Bind(fantasyTooltipName, fantasyTooltipDescription, fantasyTooltipEffect);
            else if (fantasyTooltipRoot != null)
                Debug.LogWarning("[RestView] Missing FantasyTooltipView on FantasyTooltip.");
            fantasyListView = fantasyContentRoot != null ? fantasyContentRoot.GetComponent<FantasyListView>() : null;
            if (fantasyListView != null)
                fantasyListView.Bind(fantasyContentRoot, fantasyTooltipView, 10);
            else if (fantasyContentRoot != null)
                Debug.LogWarning("[RestView] Missing FantasyListView on FantasySlots/Viewport/Content.");
            restButton = FindComponent<Button>("RestButton");
            Transform restIcon = restButton != null ? restButton.transform.Find("ArtIcon") : null;
            if (restIcon != null)
                restIcon.gameObject.SetActive(false);
            coffeeButton = FindComponent<Button>("CoffeeButton");
            nextButton = FindComponent<Button>("NextButton");
            ApplyRestSceneFrame(0);
        }

        public void ConfigureSceneArt(Sprite background, Sprite lessBrightBackground, Sprite[] fireFrames)
        {
            restBackground = background;
            restBackgroundLessBright = lessBrightBackground;
            campfireFrames = fireFrames;
            ApplyRestSceneFrame(0);
        }

        private void RestartCampfireAnimation()
        {
            if (campfireRoutine != null)
                StopCoroutine(campfireRoutine);
            if (campfireFrames == null || campfireFrames.Length == 0)
                return;
            campfireRoutine = StartCoroutine(CampfireAnimationRoutine());
        }

        private IEnumerator CampfireAnimationRoutine()
        {
            int[] sequence = { 0, 1, 2, 1 };
            int sequenceIndex = 0;
            while (true)
            {
                int frame = Mathf.Min(sequence[sequenceIndex], campfireFrames.Length - 1);
                ApplyRestSceneFrame(frame);
                yield return new WaitForSeconds(Mathf.Max(0.02f, campfireFrameDuration));
                sequenceIndex = (sequenceIndex + 1) % sequence.Length;
            }
        }

        private void ApplyRestSceneFrame(int frame)
        {
            if (restBackgroundImage != null)
            {
                restBackgroundImage.sprite = frame == 0 && restBackgroundLessBright != null
                    ? restBackgroundLessBright
                    : restBackground;
                restBackgroundImage.enabled = restBackgroundImage.sprite != null;
            }

            if (campfireImage != null)
            {
                Sprite fire = campfireFrames != null && campfireFrames.Length > 0
                    ? campfireFrames[Mathf.Clamp(frame, 0, campfireFrames.Length - 1)]
                    : null;
                campfireImage.sprite = fire;
                campfireImage.enabled = fire != null;
            }
        }

        private RectTransform FindRect(string path)
        {
            Transform child = layoutRoot != null ? layoutRoot.Find(path) : null;
            return child as RectTransform;
        }

        private T FindComponent<T>(string path) where T : Component
        {
            Transform child = layoutRoot != null ? layoutRoot.Find(path) : null;
            return child != null ? child.GetComponent<T>() : null;
        }

        private void BindButtons()
        {
            if (restButton != null)
                restButton.onClick.AddListener(ApplyRest);
            if (coffeeButton != null)
                coffeeButton.onClick.AddListener(ClaimCoffeeFantasy);
            if (nextButton != null)
                nextButton.onClick.AddListener(CompleteRest);
        }

        private void UnbindButtons()
        {
            if (restButton != null)
                restButton.onClick.RemoveListener(ApplyRest);
            if (coffeeButton != null)
                coffeeButton.onClick.RemoveListener(ClaimCoffeeFantasy);
            if (nextButton != null)
                nextButton.onClick.RemoveListener(CompleteRest);
        }

        private void ApplyRest()
        {
            if (restController == null || restUseCount >= restController.MaxRestCount)
                return;

            int amount = Mathf.Max(0, restController.CurrentHealAmount);
            restController.Heal(amount);
            restUseCount++;
            Refresh();
            PlayHealFloat(amount);
        }

        private void CompleteRest()
        {
            if (restController != null)
                restController.CompleteRest();
        }

        private void ClaimCoffeeFantasy()
        {
            if (restController == null || restUseCount > 0 || !restController.TryClaimCoffeeFantasy())
                return;

            restUseCount = restController.MaxRestCount;
            Refresh();
        }

        private void Refresh()
        {
            if (healthText != null)
                healthText.text = restController != null ? restController.CurrentHealth.ToString() : "0";
            if (restButton != null)
                restButton.interactable = restController != null && restUseCount < restController.MaxRestCount;
            if (coffeeButton != null)
                coffeeButton.interactable = restController != null && restUseCount == 0 && restController.CanClaimCoffeeFantasy;
            if (healFloatText != null && restUseCount == 0)
                healFloatText.gameObject.SetActive(false);

            RefreshFantasySlots();
            HideFantasyTooltip();
            healAmount = restController != null ? restController.CurrentHealAmount : healAmount;
            DrawMatchNumber(healAmount);
            RefreshMoveCounter();
        }

        private void RefreshFantasySlots()
        {
            if (fantasyListView != null)
            {
                fantasyListView.Bind(fantasyContentRoot, fantasyTooltipView, 10);
                fantasyListView.Refresh(restController != null ? restController.OwnedFantasies : null);
                return;
            }

            Debug.LogWarning("[RestView] Missing FantasyListView on FantasySlots/Viewport/Content.");
        }

        private void PlayHealFloat(int amount)
        {
            if (healFloatText == null)
                return;

            if (healFloatRoutine != null)
                StopCoroutine(healFloatRoutine);
            healFloatRoutine = StartCoroutine(HealFloatRoutine(amount));
        }

        private IEnumerator HealFloatRoutine(int amount)
        {
            RectTransform rect = healFloatText.rectTransform;
            Vector2 start = new Vector2(-78f, 26f);
            Vector2 end = start + new Vector2(0f, 76f);
            float duration = 0.85f;
            float elapsed = 0f;

            healFloatText.text = $"+{amount}";
            healFloatText.color = healColor;
            rect.anchoredPosition = start;
            healFloatText.gameObject.SetActive(true);

            while (elapsed < duration)
            {
                elapsed += Time.deltaTime;
                float t = Mathf.Clamp01(elapsed / duration);
                rect.anchoredPosition = Vector2.Lerp(start, end, t);
                Color color = healColor;
                color.a = 1f - t;
                healFloatText.color = color;
                yield return null;
            }

            healFloatText.gameObject.SetActive(false);
            healFloatRoutine = null;
        }

        private void DrawMatchNumber(int value)
        {
            if (matchNumberRoot == null)
                return;

            EditableSevenSegmentBox box = matchNumberRoot.GetComponent<EditableSevenSegmentBox>();
            if (box == null)
            {
                Debug.LogWarning("[RestView] Missing EditableSevenSegmentBox on MatchNumber.");
                return;
            }

            box.Configure(value, 0, matchColor, OnHealAmountEdited, false, OnHealMoveDifferenceChanged, null, CanCommitHealMoveDifference);
        }

        private void OnHealMoveDifferenceChanged(int difference)
        {
            healMoveDifference = Mathf.Max(0, difference);
            RefreshMoveCounter();
        }

        private bool CanCommitHealMoveDifference(int proposedDifference)
        {
            return restController == null || proposedDifference <= restController.CurrentMoveLimit;
        }

        private void RefreshMoveCounter()
        {
            if (moveCountText == null)
                return;

            int limit = restController != null ? restController.CurrentMoveLimit : 2;
            moveCountText.text = $"{Mathf.Max(0, limit - healMoveDifference)} / {limit}";
        }

        private void OnHealAmountEdited(int newValue)
        {
            healAmount = Mathf.Max(0, newValue);
            if (restController != null)
                restController.SetHealAmount(healAmount);
        }

        private void ShowFantasyTooltip(FantasyData fantasy)
        {
            if (fantasyTooltipView != null)
                fantasyTooltipView.Show(fantasy);
        }

        private void HideFantasyTooltip()
        {
            if (fantasyTooltipView != null)
                fantasyTooltipView.Hide();
        }

    }
}
