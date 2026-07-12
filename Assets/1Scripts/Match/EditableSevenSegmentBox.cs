using System;
using System.Collections.Generic;
using GoldfishWalking.Core;
using GoldfishWalking.Data;
using GoldfishWalking.Fantasy;
using GoldfishWalking.Formula;
using GoldfishWalking.Item;
using UnityEngine;
using UnityEngine.Events;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace GoldfishWalking.Match
{
    [RequireComponent(typeof(RectTransform))]
    public sealed class EditableSevenSegmentBox : MonoBehaviour, IPointerClickHandler
    {
        [SerializeField] private int value;
        [SerializeField] private int minDigitCount;
        [SerializeField] private bool locked;
        [SerializeField] private Color matchColor = new Color(1f, 0.74f, 0.33f, 1f);
        [SerializeField] private Color addedMatchColor = new Color(0.38f, 0.82f, 1f, 1f);
        [SerializeField] private Color lockedMatchColor = new Color(0.05f, 0.05f, 0.055f, 1f);
        [SerializeField] private UnityEvent<int> valueChanged = new UnityEvent<int>();
        [SerializeField] private UnityEvent<int> differenceChanged = new UnityEvent<int>();

        private readonly List<MatchSlot> displaySlots = new List<MatchSlot>();
        private readonly List<MatchSlot> originalDisplaySlots = new List<MatchSlot>();
        private readonly List<RectTransform> renderedDigits = new List<RectTransform>();
        private RectTransform rectTransform;
        private int originalValue;
        private int displayDigitCount;
        private string segmentState;
        private Func<int, bool> moveCommitValidator;
        private Func<bool> interactionValidator;

        public int Value => value;
        public int OriginalValue => originalValue;
        public int MinDigitCount => minDigitCount;
        public int DifferenceFromOriginal => CountMoveDifference(originalDisplaySlots, displaySlots);
        public bool Locked => locked;
        public Color MatchColor => matchColor;
        public Color AddedMatchColor => addedMatchColor;
        public Color LockedMatchColor => lockedMatchColor;
        public string SegmentState => segmentState;
        internal int DisplayDigitCount => displayDigitCount;

        private void Awake()
        {
            rectTransform = GetComponent<RectTransform>();
            EnsureRaycastTarget();
            Redraw();
        }

        public void Configure(int initialValue, int minimumDigits, Color segmentColor, UnityAction<int> onValueChanged = null, bool isLocked = false, UnityAction<int> onDifferenceChanged = null, string savedSegmentState = null, Func<int, bool> onMoveCommitValidated = null, Func<bool> canInteract = null)
        {
            value = Mathf.Max(0, initialValue);
            originalValue = value;
            minDigitCount = Mathf.Max(0, minimumDigits);
            matchColor = segmentColor;
            locked = isLocked;
            moveCommitValidator = onMoveCommitValidated;
            interactionValidator = canInteract;
            if (!TryApplySegmentState(savedSegmentState))
                SetDisplayFromValue(value);
            StoreOriginalDisplaySlots();

            if (valueChanged == null)
                valueChanged = new UnityEvent<int>();
            if (differenceChanged == null)
                differenceChanged = new UnityEvent<int>();

            valueChanged.RemoveAllListeners();
            if (onValueChanged != null)
                valueChanged.AddListener(onValueChanged);
            differenceChanged.RemoveAllListeners();
            if (onDifferenceChanged != null)
                differenceChanged.AddListener(onDifferenceChanged);

            rectTransform = GetComponent<RectTransform>();
            EnsureRaycastTarget();
            Redraw();
            differenceChanged.Invoke(DifferenceFromOriginal);
        }

        public void SetValueFromPopup(int newValue)
        {
            SetValueFromPopup(newValue, null, 0);
        }

        internal void SetValueFromPopup(int newValue, IReadOnlyList<MatchSlot> slots, int digitCount, int moveDifference = -1)
        {
            value = Mathf.Max(0, newValue);
            if (slots != null)
                SetDisplayFromSlots(slots, digitCount);
            else
                SetDisplayFromValue(value);

            Redraw();
            valueChanged.Invoke(value);
            differenceChanged.Invoke(moveDifference >= 0 ? moveDifference : DifferenceFromOriginal);
        }

        private void StoreOriginalDisplaySlots()
        {
            originalDisplaySlots.Clear();
            for (int i = 0; i < displaySlots.Count; i++)
            {
                MatchSlot source = displaySlots[i];
                if (source == null)
                    continue;

                originalDisplaySlots.Add(new MatchSlot
                {
                    digitIndex = source.digitIndex,
                    segmentIndex = source.segmentIndex,
                    piece = CopyPiece(source.piece)
                });
            }
        }

        internal List<MatchSlot> CopyDisplaySlots()
        {
            List<MatchSlot> copy = new List<MatchSlot>();
            for (int i = 0; i < displaySlots.Count; i++)
            {
                MatchSlot source = displaySlots[i];
                if (source == null)
                    continue;

                copy.Add(new MatchSlot
                {
                    digitIndex = source.digitIndex,
                    segmentIndex = source.segmentIndex,
                    piece = CopyPiece(source.piece)
                });
            }

            return copy;
        }

        public static int CountMoveDifference(int originalNumber, int currentNumber)
        {
            return CountMoveDifference(originalNumber, currentNumber, 0);
        }

        public static int CountMoveDifference(int originalNumber, int currentNumber, int minimumDigits)
        {
            HashSet<string> original = BuildShapeSet(Mathf.Max(0, originalNumber), minimumDigits);
            HashSet<string> current = BuildShapeSet(Mathf.Max(0, currentNumber), minimumDigits);
            return CountMoveDifference(original, current);
        }

        private static int CountMoveDifference(IReadOnlyList<MatchSlot> originalSlots, IReadOnlyList<MatchSlot> currentSlots)
        {
            HashSet<string> original = BuildShapeSet(originalSlots);
            HashSet<string> current = BuildShapeSet(currentSlots);
            return CountMoveDifference(original, current);
        }

        private static int CountMoveDifference(HashSet<string> original, HashSet<string> current)
        {
            int difference = 0;

            foreach (string address in original)
            {
                if (!current.Contains(address))
                    difference++;
            }

            foreach (string address in current)
            {
                if (!original.Contains(address))
                    difference++;
            }

            return difference / 2;
        }

        public void OnPointerClick(PointerEventData eventData)
        {
            if (locked || (interactionValidator != null && !interactionValidator()))
                return;

            GameBootstrap bootstrap = FindFirstObjectByType<GameBootstrap>(FindObjectsInactive.Include);
            if (bootstrap != null && bootstrap.StateMachine != null && bootstrap.StateMachine.CurrentState == GameState.Reward)
                return;

            SevenSegmentEditPopup.Open(this);
        }

        internal bool CanCommitMoveDifference(int proposedDifference)
        {
            return moveCommitValidator == null || moveCommitValidator(Mathf.Max(0, proposedDifference));
        }

        private void Redraw()
        {
            if (rectTransform == null)
                rectTransform = GetComponent<RectTransform>();

            ClearChildren(rectTransform);
            renderedDigits.Clear();

            string valueText = Mathf.Max(0, value).ToString();
            if (minDigitCount > valueText.Length)
                valueText = valueText.PadLeft(minDigitCount, '0');

            float height = Mathf.Max(1f, rectTransform.rect.height);
            float digitWidth = Mathf.Max(34f, height * 0.62f);
            float gap = Mathf.Max(8f, height * 0.12f);
            float totalWidth = valueText.Length * digitWidth + Mathf.Max(0, valueText.Length - 1) * gap;
            float startX = -totalWidth * 0.5f + digitWidth * 0.5f;

            for (int i = 0; i < valueText.Length; i++)
            {
                int digit = valueText[i] - '0';
                RectTransform digitRoot = SevenSegmentUI.CreateRect($"Digit{i}_{digit}", rectTransform);
                digitRoot.anchoredPosition = new Vector2(startX + i * (digitWidth + gap), 0f);
                digitRoot.sizeDelta = new Vector2(digitWidth, height);
                SevenSegmentUI.DrawDigit(digitRoot, digit, matchColor);
                renderedDigits.Add(digitRoot);
            }
        }

        private void DrawDisplayDigit(RectTransform digitRoot, int digitIndex)
        {
            for (int i = 0; i < displaySlots.Count; i++)
            {
                MatchSlot slot = displaySlots[i];
                if (slot == null || slot.piece == null || slot.digitIndex != digitIndex)
                    continue;

                Color color = matchColor;
                if (slot.piece.kind == MatchPieceKind.Added)
                    color = addedMatchColor;
                else if (slot.piece.kind == MatchPieceKind.Locked)
                    color = lockedMatchColor;

                SevenSegmentUI.CreateDisplaySegment(digitRoot, slot.segmentIndex, color);
            }
        }

        private void EnsureRaycastTarget()
        {
            Image image = GetComponent<Image>();
            if (image == null)
                image = gameObject.AddComponent<Image>();

            Color color = image.color;
            color.a = Mathf.Min(color.a, 0.01f);
            image.color = color;
            image.raycastTarget = true;
        }

        private void SetDisplayFromValue(int number)
        {
            displaySlots.Clear();
            string valueText = Mathf.Max(0, number).ToString();
            if (minDigitCount > valueText.Length)
                valueText = valueText.PadLeft(minDigitCount, '0');

            displayDigitCount = Mathf.Max(1, valueText.Length);
            for (int digitIndex = 0; digitIndex < valueText.Length; digitIndex++)
            {
                int digit = valueText[digitIndex] - '0';
                MatchPattern pattern = SevenSegmentUI.FindDigitPattern(digit);
                if (pattern == null)
                    continue;

                for (int i = 0; i < pattern.segments.Length; i++)
                {
                    displaySlots.Add(new MatchSlot
                    {
                        digitIndex = digitIndex,
                        segmentIndex = pattern.segments[i],
                        piece = new MatchPiece
                        {
                            id = $"display_{digitIndex}_{pattern.segments[i]}",
                            kind = locked ? MatchPieceKind.Locked : MatchPieceKind.Normal
                        }
                    });
                }
            }

            segmentState = SerializeSegmentState(displaySlots, displayDigitCount);
        }

        private void SetDisplayFromSlots(IReadOnlyList<MatchSlot> slots, int digitCount)
        {
            displaySlots.Clear();
            int highest = -1;
            if (slots != null)
            {
                for (int i = 0; i < slots.Count; i++)
                {
                    MatchSlot source = slots[i];
                    if (source == null)
                        continue;

                    highest = Mathf.Max(highest, source.digitIndex);
                    if (source.piece == null)
                        continue;

                    displaySlots.Add(new MatchSlot
                    {
                        digitIndex = source.digitIndex,
                        segmentIndex = source.segmentIndex,
                        piece = CopyPiece(source.piece)
                    });
                }
            }

            displayDigitCount = Mathf.Max(1, digitCount, highest + 1, minDigitCount);
            segmentState = SerializeSegmentState(displaySlots, displayDigitCount);
        }

        private bool TryApplySegmentState(string savedState)
        {
            if (string.IsNullOrWhiteSpace(savedState))
                return false;

            string[] parts = savedState.Split('|');
            if (parts.Length == 0 || !int.TryParse(parts[0], out int parsedDigitCount))
                return false;

            displaySlots.Clear();
            displayDigitCount = Mathf.Max(1, parsedDigitCount, minDigitCount);
            if (parts.Length > 1 && !string.IsNullOrWhiteSpace(parts[1]))
            {
                string[] entries = parts[1].Split(',');
                for (int i = 0; i < entries.Length; i++)
                {
                    string[] fields = entries[i].Split(':');
                    if (fields.Length < 3)
                        continue;
                    if (!int.TryParse(fields[0], out int digitIndex) || !int.TryParse(fields[1], out int segmentIndex))
                        continue;

                    displaySlots.Add(new MatchSlot
                    {
                        digitIndex = digitIndex,
                        segmentIndex = segmentIndex,
                        piece = new MatchPiece
                        {
                            id = $"display_{digitIndex}_{segmentIndex}",
                            kind = ParsePieceKind(fields[2])
                        }
                    });
                }
            }

            segmentState = SerializeSegmentState(displaySlots, displayDigitCount);
            return true;
        }

        private static string SerializeSegmentState(IReadOnlyList<MatchSlot> slots, int digitCount)
        {
            List<string> entries = new List<string>();
            if (slots != null)
            {
                for (int i = 0; i < slots.Count; i++)
                {
                    MatchSlot slot = slots[i];
                    if (slot == null || slot.piece == null)
                        continue;

                    entries.Add($"{slot.digitIndex}:{slot.segmentIndex}:{PieceKindCode(slot.piece.kind)}");
                }
            }

            entries.Sort();
            return $"{Mathf.Max(1, digitCount)}|{string.Join(",", entries)}";
        }

        private static MatchPiece CopyPiece(MatchPiece source)
        {
            if (source == null)
                return null;

            return new MatchPiece
            {
                id = source.id,
                kind = source.kind
            };
        }

        private static string PieceKindCode(MatchPieceKind kind)
        {
            switch (kind)
            {
                case MatchPieceKind.Added:
                    return "A";
                case MatchPieceKind.Locked:
                    return "L";
                default:
                    return "N";
            }
        }

        private static MatchPieceKind ParsePieceKind(string code)
        {
            switch ((code ?? string.Empty).Trim().ToUpperInvariant())
            {
                case "A":
                    return MatchPieceKind.Added;
                case "L":
                    return MatchPieceKind.Locked;
                default:
                    return MatchPieceKind.Normal;
            }
        }

        private static void ClearChildren(Transform root)
        {
            for (int i = root.childCount - 1; i >= 0; i--)
            {
                GameObject child = root.GetChild(i).gameObject;
                if (Application.isPlaying)
                    Destroy(child);
                else
                    DestroyImmediate(child);
            }
        }

        private static HashSet<string> BuildShapeSet(int number, int minimumDigits)
        {
            HashSet<string> shape = new HashSet<string>();
            string valueText = number.ToString();
            if (minimumDigits > valueText.Length)
                valueText = valueText.PadLeft(minimumDigits, '0');
            for (int digitIndex = 0; digitIndex < valueText.Length; digitIndex++)
            {
                int digit = valueText[digitIndex] - '0';
                MatchPattern pattern = SevenSegmentUI.FindDigitPattern(digit);
                if (pattern == null)
                    continue;

                for (int i = 0; i < pattern.segments.Length; i++)
                    shape.Add($"{digitIndex}:{pattern.segments[i]}");
            }

            return shape;
        }

        private static HashSet<string> BuildShapeSet(IReadOnlyList<MatchSlot> slots)
        {
            HashSet<string> shape = new HashSet<string>();
            if (slots == null)
                return shape;

            for (int i = 0; i < slots.Count; i++)
            {
                MatchSlot slot = slots[i];
                if (slot == null || slot.piece == null)
                    continue;

                shape.Add($"{slot.digitIndex}:{slot.segmentIndex}");
            }

            return shape;
        }
    }

    public sealed class SevenSegmentEditPopup : MonoBehaviour, IPointerClickHandler
    {
        private const float PopupDigitHeight = 250f;

        private readonly MatchEditSession session = new MatchEditSession();
        private readonly List<SevenSegmentPopupSlot> slotViews = new List<SevenSegmentPopupSlot>();
        private readonly HashSet<string> itemErasedOriginalAddresses = new HashSet<string>();
        private readonly HashSet<string> originalShape = new HashSet<string>();
        private EditableSevenSegmentBox owner;
        private ItemInventory inventory;
        private ItemEditMode itemMode;
        private FormulaBox editingBox;
        private RectTransform editPanel;
        private RectTransform digitRoot;
        private RectTransform heldPreview;
        private Canvas canvas;
        private Text messageText;
        private Text movesText;
        private Text extraMatchCountText;
        private Text eraserCountText;
        private int spentExtraMatches;
        private int spentErasers;
        private int spentTemporaryExtraMatches;
        private int spentTemporaryErasers;

        public static void Open(EditableSevenSegmentBox owner)
        {
            if (owner == null)
                return;

            Canvas canvas = owner.GetComponentInParent<Canvas>();
            if (canvas == null)
                return;

            SevenSegmentEditPopup popup = FindOrCreate(canvas);
            popup.Initialize(owner);
        }

        private static SevenSegmentEditPopup FindOrCreate(Canvas canvas)
        {
            Transform existing = FindExistingPopupRoot(canvas);
            if (existing != null)
            {
                EnsurePopupRoot(existing.gameObject);
                if (!existing.TryGetComponent(out SevenSegmentEditPopup existingPopup))
                    existingPopup = existing.gameObject.AddComponent<SevenSegmentEditPopup>();
                return existingPopup;
            }

            GameObject popupObject = new GameObject("SevenSegmentEditPopup", typeof(RectTransform), typeof(CanvasRenderer), typeof(Image), typeof(SevenSegmentEditPopup));
            popupObject.transform.SetParent(canvas.transform, false);
            EnsurePopupRoot(popupObject);

            return popupObject.GetComponent<SevenSegmentEditPopup>();
        }

        private static Transform FindExistingPopupRoot(Canvas canvas)
        {
            if (canvas == null)
                return null;

            Transform direct = canvas.transform.Find("SevenSegmentEditPopup");
            if (direct != null)
                return direct;

            RectTransform[] children = canvas.GetComponentsInChildren<RectTransform>(true);
            for (int i = 0; i < children.Length; i++)
            {
                RectTransform child = children[i];
                if (child != null && child.name == "SevenSegmentEditPopup")
                    return child;
            }

            return null;
        }

        private static void EnsurePopupRoot(GameObject popupObject)
        {
            RectTransform rect = popupObject.GetComponent<RectTransform>();
            if (rect == null)
                rect = popupObject.AddComponent<RectTransform>();
            rect.anchorMin = Vector2.zero;
            rect.anchorMax = Vector2.one;
            rect.offsetMin = Vector2.zero;
            rect.offsetMax = Vector2.zero;

            Image overlay = popupObject.GetComponent<Image>();
            if (overlay == null)
                overlay = popupObject.AddComponent<Image>();
            overlay.color = new Color(0.02f, 0.025f, 0.035f, 0.82f);
        }

        private void Initialize(EditableSevenSegmentBox source)
        {
            if (gameObject.activeSelf && owner != null)
            {
                RefundSpentItems();
                HideHeldPreview();
            }

            gameObject.SetActive(true);
            transform.SetAsLastSibling();

            owner = source;
            canvas = owner.GetComponentInParent<Canvas>();
            GameBootstrap bootstrap = FindFirstObjectByType<GameBootstrap>(FindObjectsInactive.Include);
            inventory = bootstrap != null && bootstrap.RunContext != null ? bootstrap.RunContext.itemInventory : null;
            itemMode = ItemEditMode.None;
            spentExtraMatches = 0;
            spentErasers = 0;
            spentTemporaryExtraMatches = 0;
            spentTemporaryErasers = 0;
            editingBox = FormulaBox.Number("seven_segment_popup", owner.Value, false);
            session.Open(editingBox);
            PopulateSlotsFromOwner();
            StoreOriginalShape();
            itemErasedOriginalAddresses.Clear();
            EnsureLayout();
            ShowMessage(string.Empty);
            RefreshSlots();
        }

        private void Update()
        {
            UpdateHeldPreviewPosition();
        }

        private void PopulateSlotsFromValue(int number)
        {
            string valueText = Mathf.Max(0, number).ToString();
            if (owner != null && owner.MinDigitCount > valueText.Length)
                valueText = valueText.PadLeft(owner.MinDigitCount, '0');
            for (int digitIndex = 0; digitIndex < valueText.Length; digitIndex++)
            {
                int digit = valueText[digitIndex] - '0';
                MatchPattern pattern = SevenSegmentUI.FindDigitPattern(digit);
                if (pattern == null)
                    continue;

                for (int i = 0; i < pattern.segments.Length; i++)
                {
                    session.slots.Add(new MatchSlot
                    {
                        digitIndex = digitIndex,
                        segmentIndex = pattern.segments[i],
                        piece = new MatchPiece
                        {
                            id = $"digit_{digitIndex}_segment_{pattern.segments[i]}",
                            kind = owner.Locked ? MatchPieceKind.Locked : MatchPieceKind.Normal
                        }
                    });
                }
            }
        }

        private void PopulateSlotsFromOwner()
        {
            if (owner == null)
            {
                PopulateSlotsFromValue(0);
                return;
            }

            session.slots.Clear();
            List<MatchSlot> slots = owner.CopyDisplaySlots();
            for (int i = 0; i < slots.Count; i++)
                session.slots.Add(slots[i]);
        }

        private void EnsureLayout()
        {
            if (editPanel != null)
                return;

            Transform existingPanel = transform.Find("Panel");
            if (existingPanel is RectTransform existingRect)
            {
                BindExistingLayout(existingRect);
                return;
            }

            BuildLayout();
        }

        private void BindExistingLayout(RectTransform panel)
        {
            editPanel = panel;
            digitRoot = panel.Find("Digits") as RectTransform;
            messageText = FindText(panel, "Message");
            movesText = FindText(panel, "Moves");
            extraMatchCountText = FindText(panel, "ItemPanel/ExtraMatchButton/Badge/Count");
            eraserCountText = FindText(panel, "ItemPanel/EraserButton/Badge/Count");
            BindButton(panel, "ResetButton", ResetPopup);
            BindButton(panel, "CancelButton", ClosePopup);
            BindButton(panel, "DoneButton", CommitPopup);
            BindButton(panel, "ItemPanel/ExtraMatchButton", () => SelectItemMode(ItemEditMode.ExtraMatch));
            BindButton(panel, "ItemPanel/EraserButton", () => SelectItemMode(ItemEditMode.Eraser));
        }

        private static Text FindText(Transform root, string path)
        {
            Transform child = root != null ? root.Find(path) : null;
            return child != null ? child.GetComponent<Text>() : null;
        }

        private static void BindButton(Transform root, string path, UnityAction action)
        {
            Transform child = root != null ? root.Find(path) : null;
            Button button = child != null ? child.GetComponent<Button>() : null;
            if (button == null)
                return;

            button.onClick.RemoveAllListeners();
            button.onClick.AddListener(action);
        }

        private void BuildLayout()
        {
            RectTransform panel = SevenSegmentUI.CreatePanel("Panel", transform, new Color(0.12f, 0.13f, 0.17f, 0.98f));
            editPanel = panel;
            panel.anchorMin = new Vector2(0.5f, 0.5f);
            panel.anchorMax = new Vector2(0.5f, 0.5f);
            panel.pivot = new Vector2(0.5f, 0.5f);
            panel.anchoredPosition = Vector2.zero;
            panel.sizeDelta = new Vector2(820f, 620f);

            digitRoot = SevenSegmentUI.CreateRect("Digits", panel);
            digitRoot.anchoredPosition = new Vector2(0f, 94f);
            digitRoot.sizeDelta = new Vector2(680f, PopupDigitHeight);

            messageText = SevenSegmentUI.CreateText("Message", panel, string.Empty, 24, new Color(1f, 0.58f, 0.36f, 1f), TextAnchor.MiddleCenter);
            SetRect(messageText.rectTransform, new Vector2(0f, 0f), new Vector2(1f, 0f), new Vector2(0f, 262f), new Vector2(0f, 44f));

            movesText = SevenSegmentUI.CreateText("Moves", panel, string.Empty, 22, new Color(0.72f, 0.78f, 0.88f, 1f), TextAnchor.MiddleCenter);
            SetRect(movesText.rectTransform, new Vector2(0f, 0f), new Vector2(1f, 0f), new Vector2(0f, 224f), new Vector2(0f, 38f));

            Button resetButton = CreateButton("ResetButton", panel, "Reset", new Vector2(-202f, -258f), new Vector2(156f, 72f));
            resetButton.onClick.AddListener(ResetPopup);

            Button cancelButton = CreateButton("CancelButton", panel, "Cancel", new Vector2(0f, -258f), new Vector2(156f, 72f));
            cancelButton.onClick.AddListener(ClosePopup);

            Button doneButton = CreateButton("DoneButton", panel, "Done", new Vector2(202f, -258f), new Vector2(156f, 72f));
            doneButton.onClick.AddListener(CommitPopup);

            CreateItemPanel(panel);
        }

        private void CreateItemPanel(RectTransform parent)
        {
            RectTransform itemPanel = SevenSegmentUI.CreatePanel("ItemPanel", parent, new Color(0.14f, 0.16f, 0.20f, 0.94f));
            itemPanel.anchoredPosition = new Vector2(0f, -158f);
            itemPanel.sizeDelta = new Vector2(364f, 116f);

            CreateItemButton(itemPanel, "ExtraMatchButton", new Vector2(-58f, 0f), new Color(1f, 0.28f, 0.28f, 1f), ItemEditMode.ExtraMatch, out extraMatchCountText);
            CreateItemButton(itemPanel, "EraserButton", new Vector2(58f, 0f), new Color(0.95f, 0.97f, 1f, 1f), ItemEditMode.Eraser, out eraserCountText);
            RefreshItemCounts();
        }

        private void CreateItemButton(RectTransform parent, string name, Vector2 position, Color itemColor, ItemEditMode mode, out Text countText)
        {
            RectTransform slot = SevenSegmentUI.CreatePanel(name, parent, new Color(0.20f, 0.22f, 0.29f, 0.96f));
            slot.anchoredPosition = position;
            slot.sizeDelta = new Vector2(88f, 88f);

            Button button = slot.gameObject.AddComponent<Button>();
            button.onClick.AddListener(() => SelectItemMode(mode));

            Text icon = SevenSegmentUI.CreateText("Icon", slot, mode == ItemEditMode.ExtraMatch ? "+" : "-", 31, itemColor, TextAnchor.MiddleCenter);
            SetRect(icon.rectTransform, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);

            RectTransform badge = SevenSegmentUI.CreatePanel("Badge", slot, new Color(0.12f, 0.13f, 0.17f, 0.98f));
            badge.anchorMin = new Vector2(1f, 1f);
            badge.anchorMax = new Vector2(1f, 1f);
            badge.anchoredPosition = new Vector2(-12f, -12f);
            badge.sizeDelta = new Vector2(38f, 38f);

            countText = SevenSegmentUI.CreateText("Count", badge, "0", 22, Color.white, TextAnchor.MiddleCenter);
            SetRect(countText.rectTransform, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
        }

        private Button CreateButton(string name, RectTransform parent, string label, Vector2 position, Vector2 size)
        {
            RectTransform rect = SevenSegmentUI.CreatePanel(name, parent, new Color(0.21f, 0.24f, 0.31f, 1f));
            rect.anchoredPosition = position;
            rect.sizeDelta = size;
            Button button = rect.gameObject.AddComponent<Button>();

            Text text = SevenSegmentUI.CreateText("Label", rect, label, 26, Color.white, TextAnchor.MiddleCenter);
            SetRect(text.rectTransform, Vector2.zero, Vector2.one, Vector2.zero, Vector2.zero);
            return button;
        }

        private void RefreshSlots()
        {
            ClearChildren(digitRoot);
            slotViews.Clear();

            int digitCount = CurrentDigitCount();
            float digitWidth = 150f;
            float gap = 28f;
            float totalWidth = digitCount * digitWidth + Mathf.Max(0, digitCount - 1) * gap;
            float startX = -totalWidth * 0.5f + digitWidth * 0.5f;

            for (int digitIndex = 0; digitIndex < digitCount; digitIndex++)
            {
                RectTransform singleDigit = SevenSegmentUI.CreateRect($"Digit{digitIndex}", digitRoot);
                singleDigit.anchoredPosition = new Vector2(startX + digitIndex * (digitWidth + gap), 0f);
                singleDigit.sizeDelta = new Vector2(digitWidth, PopupDigitHeight);

                for (int segmentIndex = 0; segmentIndex <= (int)MatchSegment.Middle; segmentIndex++)
                {
                    SevenSegmentPopupSlot slot = SevenSegmentUI.CreateSlot(singleDigit, digitIndex, segmentIndex, owner.MatchColor, OnSlotClicked);
                    slot.SetOccupied(FindSlot(digitIndex, segmentIndex), owner.MatchColor, owner.AddedMatchColor, owner.LockedMatchColor);
                    slotViews.Add(slot);
                }
            }

            if (movesText != null)
                movesText.text = $"Moves {CountCurrentMoveDifference()}";
            RefreshItemCounts();
        }

        private void OnSlotClicked(SevenSegmentPopupSlot view)
        {
            if (view == null)
                return;

            if (itemMode != ItemEditMode.None)
            {
                HandleItemSlotClick(view);
                return;
            }

            MatchEditResult result = session.IsHoldingPiece
                ? session.TryPlace(view.DigitIndex, view.SegmentIndex)
                : session.TryPickUp(view.DigitIndex, view.SegmentIndex);

            if (!result.success)
            {
                ShowMessage(result.message);
                return;
            }

            if (session.IsHoldingPiece)
                ShowHeldPreview();
            else
                HideHeldPreview();

            ShowMessage(string.Empty);
            RefreshSlots();
        }

        private void CommitPopup()
        {
            int proposedDifference = CountCurrentMoveDifference();
            if (owner != null && !owner.CanCommitMoveDifference(proposedDifference))
            {
                ShowMessage("Not enough moves.");
                return;
            }

            MatchEditResult result = session.Commit();
            if (!result.success)
            {
                ShowMessage(result.message);
                return;
            }

            owner.SetValueFromPopup(editingBox.numberValue, session.slots, CurrentDigitCount(), proposedDifference);
            RegisterCommittedItemSpend(spentExtraMatches, spentTemporaryExtraMatches, spentErasers, spentTemporaryErasers);
            spentExtraMatches = 0;
            spentErasers = 0;
            spentTemporaryExtraMatches = 0;
            spentTemporaryErasers = 0;
            GameEventHub.RaiseItemInventoryChanged();
            ClosePopup();
        }

        private void ResetPopup()
        {
            RefundSpentItems();
            session.slots.Clear();
            session.Open(editingBox);
            PopulateSlotsFromOwner();
            StoreOriginalShape();
            itemErasedOriginalAddresses.Clear();
            itemMode = ItemEditMode.None;
            HideHeldPreview();
            ShowMessage(string.Empty);
            RefreshSlots();
        }

        private void ClosePopup()
        {
            RefundSpentItems();
            HideHeldPreview();
            itemMode = ItemEditMode.None;
            owner = null;
            gameObject.SetActive(false);
        }

        private void SelectItemMode(ItemEditMode mode)
        {
            if (mode == ItemEditMode.ExtraMatch)
            {
                BeginExtraMatch();
                return;
            }

            itemMode = itemMode == mode ? ItemEditMode.None : mode;
            ShowMessage(itemMode == ItemEditMode.None ? string.Empty : $"{itemMode} mode");
        }

        private void BeginExtraMatch()
        {
            if (session.IsHoldingPiece)
            {
                ShowMessage("Place the held match first.");
                return;
            }

            if (inventory == null || inventory.GetCount(ItemType.ExtraMatch) <= 0)
            {
                ShowMessage("No extra matches left.");
                return;
            }

            if (!inventory.TryConsume(ItemType.ExtraMatch, out bool consumedTemporary))
            {
                ShowMessage("No extra matches left.");
                return;
            }

            MatchEditResult addResult = session.AddExtraMatch(new MatchPiece
            {
                id = $"added_held_{spentExtraMatches + 1}",
                kind = MatchPieceKind.Added
            });

            if (!addResult.success)
            {
                inventory.Add(ItemType.ExtraMatch, 1);
                ShowMessage(addResult.message);
                RefreshItemCounts();
                return;
            }

            TrackSpentExtraMatch(consumedTemporary);
            RegisterBattleItemUse();
            ApplyItemUseEffects(ItemType.ExtraMatch);
            itemMode = ItemEditMode.None;
            ShowHeldPreview();
            ShowMessage("Place the extra match.");
            GameEventHub.RaiseItemInventoryChanged();
            RefreshSlots();
        }

        private void HandleItemSlotClick(SevenSegmentPopupSlot view)
        {
            if (session.IsHoldingPiece)
            {
                ShowMessage("Place the held match first.");
                return;
            }

            if (itemMode == ItemEditMode.ExtraMatch)
                UseExtraMatch(view);
            else if (itemMode == ItemEditMode.Eraser)
                UseEraser(view);
        }

        private void UseExtraMatch(SevenSegmentPopupSlot view)
        {
            if (inventory == null || inventory.GetCount(ItemType.ExtraMatch) <= 0)
            {
                ShowMessage("No extra matches left.");
                return;
            }

            MatchSlot existing = FindSlot(view.DigitIndex, view.SegmentIndex);
            if (existing != null && existing.piece != null)
            {
                ShowMessage("That slot already has a match.");
                return;
            }

            if (!inventory.TryConsume(ItemType.ExtraMatch, out bool consumedTemporary))
            {
                ShowMessage("No extra matches left.");
                return;
            }

            MatchEditResult addResult = session.AddExtraMatch(new MatchPiece
            {
                id = $"added_{view.DigitIndex}_{view.SegmentIndex}_{spentExtraMatches + 1}",
                kind = MatchPieceKind.Added
            });

            if (!addResult.success)
            {
                inventory.Add(ItemType.ExtraMatch, 1);
                ShowMessage(addResult.message);
                RefreshItemCounts();
                return;
            }

            MatchEditResult placeResult = session.TryPlace(view.DigitIndex, view.SegmentIndex);
            if (!placeResult.success)
            {
                session.DropHeldPieceOutsideTable();
                inventory.Add(ItemType.ExtraMatch, 1);
                ShowMessage(placeResult.message);
                RefreshSlots();
                return;
            }

            TrackSpentExtraMatch(consumedTemporary);
            RegisterBattleItemUse();
            ApplyItemUseEffects(ItemType.ExtraMatch);
            itemMode = ItemEditMode.None;
            ShowMessage(string.Empty);
            GameEventHub.RaiseItemInventoryChanged();
            RefreshSlots();
        }

        public void OnPointerClick(PointerEventData eventData)
        {
            if (!session.IsHoldingPiece)
                return;

            Camera eventCamera = GetEventCamera();
            if (editPanel != null && RectTransformUtility.RectangleContainsScreenPoint(editPanel, eventData.position, eventCamera))
                return;

            if (session.heldPiece != null && session.heldPiece.IsAdded)
            {
                MatchEditResult result = session.DropHeldPieceOutsideTable();
                if (!result.success)
                {
                    ShowMessage(result.message);
                    return;
                }

                RefundHeldExtraMatch();
                HideHeldPreview();
                itemMode = ItemEditMode.None;
                ShowMessage(string.Empty);
                GameEventHub.RaiseItemInventoryChanged();
                RefreshSlots();
                return;
            }

            ShowMessage("Place the held match first.");
        }

        private void UseEraser(SevenSegmentPopupSlot view)
        {
            if (inventory == null || inventory.GetCount(ItemType.Eraser) <= 0)
            {
                ShowMessage("No erasers left.");
                return;
            }

            MatchSlot slot = FindSlot(view.DigitIndex, view.SegmentIndex);
            if (slot == null || slot.piece == null)
            {
                ShowMessage("No match exists in that slot.");
                return;
            }

            if (!slot.piece.CanErase)
            {
                ShowMessage("Locked matches cannot be erased.");
                return;
            }

            bool erasingAddedMatch = slot.piece.IsAdded;
            if (!inventory.TryConsume(ItemType.Eraser, out bool consumedTemporary))
            {
                ShowMessage("No erasers left.");
                return;
            }

            MatchEditResult result = session.TryErase(view.DigitIndex, view.SegmentIndex);
            if (!result.success)
            {
                inventory.Add(ItemType.Eraser, 1);
                ShowMessage(result.message);
                RefreshItemCounts();
                return;
            }

            TrackSpentEraser(consumedTemporary);
            if (!erasingAddedMatch)
                itemErasedOriginalAddresses.Add(Address(view.DigitIndex, view.SegmentIndex));
            RegisterBattleItemUse();
            ApplyItemUseEffects(ItemType.Eraser);
            if (erasingAddedMatch)
            {
                if (spentTemporaryExtraMatches > 0)
                {
                    spentTemporaryExtraMatches--;
                    inventory.AddTemporary(ItemType.ExtraMatch, 1);
                }
                else if (spentExtraMatches > 0)
                {
                    spentExtraMatches--;
                    inventory.Add(ItemType.ExtraMatch, 1);
                }
                else
                {
                    inventory.Add(ItemType.ExtraMatch, 1);
                }
            }

            itemMode = ItemEditMode.None;
            ShowMessage(string.Empty);
            GameEventHub.RaiseItemInventoryChanged();
            RefreshSlots();
        }

        private void RefundSpentItems()
        {
            if (inventory == null)
                return;

            if (spentExtraMatches > 0)
                inventory.Add(ItemType.ExtraMatch, spentExtraMatches);
            if (spentErasers > 0)
                inventory.Add(ItemType.Eraser, spentErasers);
            if (spentTemporaryExtraMatches > 0)
                inventory.AddTemporary(ItemType.ExtraMatch, spentTemporaryExtraMatches);
            if (spentTemporaryErasers > 0)
                inventory.AddTemporary(ItemType.Eraser, spentTemporaryErasers);

            spentExtraMatches = 0;
            spentErasers = 0;
            spentTemporaryExtraMatches = 0;
            spentTemporaryErasers = 0;
            GameEventHub.RaiseItemInventoryChanged();
        }

        private void RefreshItemCounts()
        {
            if (extraMatchCountText != null)
                extraMatchCountText.text = inventory != null ? inventory.GetCount(ItemType.ExtraMatch).ToString() : "0";
            if (eraserCountText != null)
                eraserCountText.text = inventory != null ? inventory.GetCount(ItemType.Eraser).ToString() : "0";
        }

        private void RefundHeldExtraMatch()
        {
            if (inventory == null)
                return;

            if (spentExtraMatches > 0)
            {
                spentExtraMatches--;
                inventory.Add(ItemType.ExtraMatch, 1);
            }
            else if (spentTemporaryExtraMatches > 0)
            {
                spentTemporaryExtraMatches--;
                inventory.AddTemporary(ItemType.ExtraMatch, 1);
            }
        }

        private void TrackSpentExtraMatch(bool consumedTemporary)
        {
            if (consumedTemporary)
                spentTemporaryExtraMatches++;
            else
                spentExtraMatches++;
        }

        private void TrackSpentEraser(bool consumedTemporary)
        {
            if (consumedTemporary)
                spentTemporaryErasers++;
            else
                spentErasers++;
        }

        private static void RegisterBattleItemUse()
        {
            GameBootstrap bootstrap = FindFirstObjectByType<GameBootstrap>(FindObjectsInactive.Include);
            if (bootstrap != null && bootstrap.RunContext != null)
                bootstrap.RunContext.itemUseCountThisBattle++;
        }

        private static void ApplyItemUseEffects(ItemType itemType)
        {
            GameBootstrap bootstrap = FindFirstObjectByType<GameBootstrap>(FindObjectsInactive.Include);
            if (bootstrap != null && bootstrap.RunContext != null)
                new FantasyEffectRunner().ApplyItemUsedEffects(bootstrap.RunContext, itemType);
        }

        private static void RegisterCommittedItemSpend(int extraMatches, int temporaryExtraMatches, int erasers, int temporaryErasers)
        {
            GameBootstrap bootstrap = FindFirstObjectByType<GameBootstrap>(FindObjectsInactive.Include);
            if (bootstrap == null || bootstrap.RunContext == null)
                return;

            bootstrap.RunContext.RegisterBattleEditItemSpend(ItemType.ExtraMatch, extraMatches, temporaryExtraMatches);
            bootstrap.RunContext.RegisterBattleEditItemSpend(ItemType.Eraser, erasers, temporaryErasers);
        }

        private void ShowHeldPreview()
        {
            if (heldPreview != null)
            {
                UpdateHeldPreviewPosition();
                return;
            }

            Color previewColor = session.heldPiece != null && session.heldPiece.IsAdded ? owner.AddedMatchColor : owner.MatchColor;
            heldPreview = SevenSegmentUI.CreatePanel("HeldMatch", transform, previewColor);
            heldPreview.sizeDelta = new Vector2(104f, 18f);
            heldPreview.SetAsLastSibling();

            CanvasGroup canvasGroup = heldPreview.gameObject.AddComponent<CanvasGroup>();
            canvasGroup.blocksRaycasts = false;
            canvasGroup.interactable = false;

            Image image = heldPreview.GetComponent<Image>();
            if (image != null)
                image.raycastTarget = false;

            UpdateHeldPreviewPosition();
        }

        private void HideHeldPreview()
        {
            if (heldPreview == null)
                return;

            if (Application.isPlaying)
                Destroy(heldPreview.gameObject);
            else
                DestroyImmediate(heldPreview.gameObject);
            heldPreview = null;
        }

        private void ShowMessage(string message)
        {
            if (messageText != null)
                messageText.text = message;
        }

        private MatchSlot FindSlot(int digitIndex, int segmentIndex)
        {
            return session.slots.Find(slot => slot.SameAddress(digitIndex, segmentIndex));
        }

        private int HighestDigitIndex()
        {
            int highest = 0;
            for (int i = 0; i < session.slots.Count; i++)
                highest = Mathf.Max(highest, session.slots[i].digitIndex);
            return highest;
        }

        private int CurrentDigitCount()
        {
            return Mathf.Max(1, owner != null ? owner.DisplayDigitCount : 1, HighestDigitIndex() + 1);
        }

        private void StoreOriginalShape()
        {
            originalShape.Clear();
            foreach (MatchSlot slot in session.slots)
            {
                if (slot.piece != null)
                    originalShape.Add(Address(slot.digitIndex, slot.segmentIndex));
            }
        }

        private int CountCurrentMoveDifference()
        {
            HashSet<string> currentShape = new HashSet<string>();
            foreach (MatchSlot slot in session.slots)
            {
                if (slot.piece != null && !slot.piece.IsAdded)
                    currentShape.Add(Address(slot.digitIndex, slot.segmentIndex));
            }

            int difference = 0;
            foreach (string address in originalShape)
            {
                if (itemErasedOriginalAddresses.Contains(address))
                    continue;
                if (!currentShape.Contains(address))
                    difference++;
            }

            foreach (string address in currentShape)
            {
                if (!originalShape.Contains(address))
                    difference++;
            }

            return difference / 2;
        }

        private void UpdateHeldPreviewPosition()
        {
            if (heldPreview == null)
                return;

            RectTransformUtility.ScreenPointToLocalPointInRectangle(
                transform as RectTransform,
                Input.mousePosition,
                GetEventCamera(),
                out Vector2 localPoint);
            heldPreview.anchoredPosition = localPoint + new Vector2(26f, -18f);
        }

        private Camera GetEventCamera()
        {
            if (canvas != null && canvas.renderMode != RenderMode.ScreenSpaceOverlay)
                return canvas.worldCamera;

            return null;
        }

        private static string Address(int digitIndex, int segmentIndex)
        {
            return $"{digitIndex}:{segmentIndex}";
        }

        private static void ClearChildren(Transform root)
        {
            for (int i = root.childCount - 1; i >= 0; i--)
            {
                GameObject child = root.GetChild(i).gameObject;
                if (Application.isPlaying)
                    Destroy(child);
                else
                    DestroyImmediate(child);
            }
        }

        private static void SetRect(RectTransform rect, Vector2 anchorMin, Vector2 anchorMax, Vector2 anchoredPosition, Vector2 sizeDelta)
        {
            rect.anchorMin = anchorMin;
            rect.anchorMax = anchorMax;
            rect.pivot = new Vector2(0.5f, 0.5f);
            rect.anchoredPosition = anchoredPosition;
            rect.sizeDelta = sizeDelta;
        }
    }

    public sealed class SevenSegmentPopupSlot : MonoBehaviour, IPointerClickHandler
    {
        private System.Action<SevenSegmentPopupSlot> clicked;
        private Image image;

        public int DigitIndex { get; private set; }
        public int SegmentIndex { get; private set; }

        public void Initialize(int digitIndex, int segmentIndex, System.Action<SevenSegmentPopupSlot> onClicked)
        {
            DigitIndex = digitIndex;
            SegmentIndex = segmentIndex;
            clicked = onClicked;
            image = GetComponent<Image>();
        }

        public void SetOccupied(MatchSlot slot, Color normalColor, Color addedColor, Color lockedColor)
        {
            if (image == null)
                image = GetComponent<Image>();

            if (slot == null || slot.piece == null)
            {
                image.color = new Color(1f, 1f, 1f, 0.11f);
                return;
            }

            if (slot.piece.kind == MatchPieceKind.Locked)
                image.color = lockedColor;
            else if (slot.piece.kind == MatchPieceKind.Added)
                image.color = addedColor;
            else
                image.color = normalColor;
        }

        public void OnPointerClick(PointerEventData eventData)
        {
            clicked?.Invoke(this);
        }
    }

    internal enum ItemEditMode
    {
        None,
        ExtraMatch,
        Eraser
    }

    internal static class SevenSegmentUI
    {
        public static RectTransform CreateRect(string name, Transform parent)
        {
            GameObject go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(parent, false);
            RectTransform rect = go.GetComponent<RectTransform>();
            rect.anchorMin = new Vector2(0.5f, 0.5f);
            rect.anchorMax = new Vector2(0.5f, 0.5f);
            rect.pivot = new Vector2(0.5f, 0.5f);
            return rect;
        }

        public static RectTransform CreatePanel(string name, Transform parent, Color color)
        {
            GameObject go = new GameObject(name, typeof(RectTransform), typeof(CanvasRenderer), typeof(Image));
            go.transform.SetParent(parent, false);
            Image image = go.GetComponent<Image>();
            image.color = color;
            RectTransform rect = image.rectTransform;
            rect.anchorMin = new Vector2(0.5f, 0.5f);
            rect.anchorMax = new Vector2(0.5f, 0.5f);
            rect.pivot = new Vector2(0.5f, 0.5f);
            return rect;
        }

        public static Text CreateText(string name, Transform parent, string value, int fontSize, Color color, TextAnchor alignment)
        {
            GameObject go = new GameObject(name, typeof(RectTransform), typeof(CanvasRenderer), typeof(Text));
            go.transform.SetParent(parent, false);
            Text text = go.GetComponent<Text>();
            text.text = value;
            text.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            text.fontSize = fontSize;
            text.fontStyle = FontStyle.Bold;
            text.alignment = alignment;
            text.color = color;
            text.raycastTarget = false;
            return text;
        }

        public static void DrawDigit(RectTransform digitRoot, int digit, Color color)
        {
            MatchPattern pattern = FindDigitPattern(digit);
            if (pattern == null)
                return;

            for (int i = 0; i < pattern.segments.Length; i++)
                CreateSegment(digitRoot, pattern.segments[i], color, false);
        }

        public static void CreateDisplaySegment(RectTransform digitRoot, int segmentIndex, Color color)
        {
            CreateSegment(digitRoot, segmentIndex, color, false);
        }

        public static SevenSegmentPopupSlot CreateSlot(RectTransform digitRoot, int digitIndex, int segmentIndex, Color color, System.Action<SevenSegmentPopupSlot> clicked)
        {
            RectTransform rect = CreateSegment(digitRoot, segmentIndex, color, true);
            SevenSegmentPopupSlot slot = rect.gameObject.AddComponent<SevenSegmentPopupSlot>();
            slot.Initialize(digitIndex, segmentIndex, clicked);
            return slot;
        }

        public static MatchPattern FindDigitPattern(int digit)
        {
            foreach (MatchPattern candidate in MatchPatternTable.DigitPatterns)
            {
                if (candidate.value == digit)
                    return candidate;
            }

            return null;
        }

        private static RectTransform CreateSegment(RectTransform digitRoot, int segmentIndex, Color color, bool asSlot)
        {
            MatchSegment segment = (MatchSegment)segmentIndex;
            RectTransform rect = CreatePanel($"Segment{segmentIndex}", digitRoot, color);
            rect.anchoredPosition = SegmentPosition(segment, digitRoot.rect.height);
            rect.sizeDelta = SegmentSize(segment, digitRoot.rect.height);
            rect.localEulerAngles = new Vector3(0f, 0f, SegmentRotation(segment));

            if (!asSlot)
                rect.gameObject.AddComponent<MatchstickView>();

            return rect;
        }

        private static Vector2 SegmentPosition(MatchSegment segment, float height)
        {
            float scale = Mathf.Max(0.1f, height / 178f);
            switch (segment)
            {
                case MatchSegment.Top:
                    return new Vector2(0f, 74f) * scale;
                case MatchSegment.UpperRight:
                    return new Vector2(45f, 38f) * scale;
                case MatchSegment.LowerRight:
                    return new Vector2(45f, -38f) * scale;
                case MatchSegment.Bottom:
                    return new Vector2(0f, -74f) * scale;
                case MatchSegment.LowerLeft:
                    return new Vector2(-45f, -38f) * scale;
                case MatchSegment.UpperLeft:
                    return new Vector2(-45f, 38f) * scale;
                case MatchSegment.Middle:
                    return Vector2.zero;
                default:
                    return Vector2.zero;
            }
        }

        private static Vector2 SegmentSize(MatchSegment segment, float height)
        {
            float scale = Mathf.Max(0.1f, height / 178f);
            switch (segment)
            {
                case MatchSegment.UpperRight:
                case MatchSegment.LowerRight:
                case MatchSegment.LowerLeft:
                case MatchSegment.UpperLeft:
                    return new Vector2(14f, 72f) * scale;
                default:
                    return new Vector2(78f, 14f) * scale;
            }
        }

        private static float SegmentRotation(MatchSegment segment)
        {
            return 0f;
        }
    }
}
