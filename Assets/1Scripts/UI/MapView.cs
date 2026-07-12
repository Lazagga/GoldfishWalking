using GoldfishWalking.Core;
using GoldfishWalking.Map;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;
#if UNITY_EDITOR
using UnityEditor;
#endif

namespace GoldfishWalking.UI
{
    public sealed class MapView : MonoBehaviour, IBeginDragHandler, IDragHandler
    {
        [SerializeField] private MapController mapController;
        [SerializeField] private GameBootstrap gameBootstrap;
        [SerializeField] private RectTransform layoutRoot;
        [SerializeField] private RectTransform contentRoot;
        [SerializeField] private RectTransform lineRoot;
        [SerializeField] private RectTransform nodeRoot;
        [SerializeField] private Font labelFont;

        private const int VisibleFloorRadius = 2;
        private const int VisibleLineRadius = 3;
        private const float HorizontalPadding = 110f;
        private const float NodeSize = 132f;
        private const float VerticalSpacing = 150f;

        private static readonly Color BackgroundColor = new Color(0.10f, 0.13f, 0.15f, 1f);
        private static readonly Color LineColor = new Color(0.50f, 0.58f, 0.62f, 0.42f);
        private static readonly Color LockedColor = new Color(0.22f, 0.24f, 0.25f, 1f);
        private static readonly Color CompletedColor = new Color(0.27f, 0.43f, 0.37f, 1f);
        private static readonly Color CurrentColor = new Color(0.32f, 0.62f, 0.88f, 1f);
        private static readonly Color AvailableColor = new Color(0.93f, 0.80f, 0.36f, 1f);

        private float focusedFloor;
        private RunMap renderedMap;
        private Text headerText;

        private void Awake()
        {
            ResolveReferences();
            HideScenePlaceholders();
            EnsureRoots();
        }

        private void OnEnable()
        {
            GameEventHub.StateChanged += OnStateChanged;
            HideScenePlaceholders();
            EnsureRoots();
            focusedFloor = GetCurrentFloor();
            Render();
        }

        private void OnDisable()
        {
            GameEventHub.StateChanged -= OnStateChanged;
        }

        public void Render()
        {
            ResolveReferences();
            EnsureRoots();

            RunMap map = gameBootstrap != null ? gameBootstrap.RunContext?.map : null;
            if (map == null || map.nodes.Count == 0)
            {
                focusedFloor = 0f;
                renderedMap = null;
                Clear(lineRoot);
                Clear(nodeRoot);
                UpdateHeader("MAP");
                return;
            }

            ClampFocusedFloor(map);
            if (renderedMap != map)
                BuildMap(map);

            UpdateHeader($"ACT {gameBootstrap.RunContext.act} - FLOOR {GetCurrentFloor() + 1:D2}");
            UpdateContentPosition();
            UpdateVisualStates(map);
        }

        public void SelectNode(MapNode node)
        {
            if (mapController == null || gameBootstrap == null || gameBootstrap.RunContext == null)
                return;

            mapController.SelectNode(gameBootstrap.RunContext.map, gameBootstrap.RunContext.currentNode, node);
        }

        public void OnBeginDrag(PointerEventData eventData)
        {
        }

        public void OnDrag(PointerEventData eventData)
        {
            RunMap map = gameBootstrap != null ? gameBootstrap.RunContext?.map : null;
            if (map == null)
                return;

            float spacing = GetHorizontalSpacing();
            if (spacing <= 0f)
                return;

            float previous = focusedFloor;
            focusedFloor -= eventData.delta.x / spacing;
            ClampFocusedFloor(map);

            if (!Mathf.Approximately(previous, focusedFloor))
            {
                UpdateContentPosition();
                UpdateVisualStates(map);
            }
        }

        private void OnStateChanged(GameState previous, GameState next)
        {
            if (next != GameState.Map)
                return;

            focusedFloor = GetCurrentFloor();
            Render();
        }

        private void ResolveReferences()
        {
            if (mapController == null)
                mapController = Object.FindFirstObjectByType<MapController>();

            if (gameBootstrap == null)
                gameBootstrap = Object.FindFirstObjectByType<GameBootstrap>();

            if (labelFont == null)
                labelFont = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
        }

        private void EnsureRoots()
        {
            Image background = GetComponent<Image>();
            if (background != null)
                background.color = BackgroundColor;

            RectTransform self = transform as RectTransform;
            if (self == null)
                return;

            if (layoutRoot == null)
            {
                Transform existingLayout = transform.Find("MapRuntimeLayout");
                if (existingLayout is RectTransform existingRect)
                    layoutRoot = existingRect;
            }

            if (layoutRoot == null)
                layoutRoot = CreateLayer("MapRuntimeLayout", self);

            contentRoot = FindRect("MapContent");
            if (contentRoot == null)
                contentRoot = CreateLayer("MapContent", layoutRoot);

            lineRoot = FindRect("MapContent/MapLines");
            if (lineRoot == null)
                lineRoot = CreateLayer("MapLines", contentRoot);

            nodeRoot = FindRect("MapContent/MapNodes");
            if (nodeRoot == null)
                nodeRoot = CreateLayer("MapNodes", contentRoot);

            BindHeader();
        }

        private static RectTransform CreateLayer(string layerName, RectTransform parent)
        {
            GameObject layer = new GameObject(layerName, typeof(RectTransform));
            RectTransform rect = layer.GetComponent<RectTransform>();
            rect.SetParent(parent, false);
            rect.anchorMin = Vector2.zero;
            rect.anchorMax = Vector2.one;
            rect.offsetMin = Vector2.zero;
            rect.offsetMax = Vector2.zero;
            return rect;
        }

        private void HideScenePlaceholders()
        {
            for (int i = 0; i < transform.childCount; i++)
            {
                Transform child = transform.GetChild(i);
                if (layoutRoot != null && child == layoutRoot)
                    continue;
                if (child.name == "MapRuntimeLayout")
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
            contentRoot = null;
            lineRoot = null;
            nodeRoot = null;
            headerText = null;

            for (int i = transform.childCount - 1; i >= 0; i--)
            {
                Transform child = transform.GetChild(i);
                if (child.name != "MapRuntimeLayout")
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
            EnsureRoots();
            EditorUtility.SetDirty(gameObject);
            UnityEditor.SceneManagement.EditorSceneManager.MarkSceneDirty(gameObject.scene);
        }
#endif

        private void BuildMap(RunMap map)
        {
            renderedMap = map;
            Clear(lineRoot);
            Clear(nodeRoot);

            CreateHeader();
            DrawLines(map);
            DrawNodes(map);
        }

        private void DrawLines(RunMap map)
        {
            foreach (MapNode node in map.nodes)
            {
                Vector2 start = GetLocalPosition(node);
                foreach (string nextNodeId in node.nextNodeIds)
                {
                    MapNode next = map.FindNode(nextNodeId);
                    if (next != null)
                        CreateLine(node, next, start, GetLocalPosition(next));
                }
            }
        }

        private void DrawNodes(RunMap map)
        {
            foreach (MapNode node in map.nodes)
            {
                Button button = CreateNodeButton(node);
                button.onClick.AddListener(() => SelectNode(node));
            }
        }

        private Button CreateNodeButton(MapNode node)
        {
            GameObject nodeObject = new GameObject(node.id, typeof(RectTransform), typeof(CanvasRenderer), typeof(Image), typeof(Button));
            RectTransform rect = nodeObject.GetComponent<RectTransform>();
            rect.SetParent(nodeRoot, false);
            rect.sizeDelta = new Vector2(NodeSize, NodeSize);
            rect.anchoredPosition = GetLocalPosition(node);

            Button button = nodeObject.GetComponent<Button>();
            button.transition = Selectable.Transition.None;

            Text label = CreateText("Label", rect, GetNodeLabel(node), 22, Color.white);
            label.fontStyle = FontStyle.Bold;

            Text roomLabel = CreateText("RoomLabel", rect, (node.roomIndex + 1).ToString("D2"), 13, new Color(1f, 1f, 1f, 0.78f));
            RectTransform roomRect = roomLabel.rectTransform;
            roomRect.anchorMin = new Vector2(0f, 0f);
            roomRect.anchorMax = new Vector2(1f, 0f);
            roomRect.anchoredPosition = new Vector2(0f, 12f);
            roomRect.sizeDelta = new Vector2(0f, 22f);

            return button;
        }

        private void CreateLine(MapNode from, MapNode to, Vector2 start, Vector2 end)
        {
            GameObject lineObject = new GameObject($"MapLine_{from.roomIndex}_{to.roomIndex}", typeof(RectTransform), typeof(CanvasRenderer), typeof(Image));
            RectTransform rect = lineObject.GetComponent<RectTransform>();
            rect.SetParent(lineRoot, false);

            Vector2 direction = end - start;
            rect.sizeDelta = new Vector2(direction.magnitude, 5f);
            rect.anchoredPosition = start + direction * 0.5f;
            rect.localRotation = Quaternion.Euler(0f, 0f, Mathf.Atan2(direction.y, direction.x) * Mathf.Rad2Deg);

            Image image = lineObject.GetComponent<Image>();
            image.color = LineColor;
            image.raycastTarget = false;
        }

        private void CreateHeader()
        {
            if (headerText != null || layoutRoot == null)
                return;

            headerText = CreateText("MapHeader", layoutRoot, "MAP", 32, Color.white);
            headerText.fontStyle = FontStyle.Bold;

            RectTransform rect = headerText.rectTransform;
            rect.anchorMin = new Vector2(0f, 1f);
            rect.anchorMax = new Vector2(1f, 1f);
            rect.pivot = new Vector2(0.5f, 1f);
            rect.anchoredPosition = new Vector2(0f, -28f);
            rect.sizeDelta = new Vector2(0f, 54f);
        }

        private void BindHeader()
        {
            if (layoutRoot == null)
                return;

            Transform existingHeader = layoutRoot.Find("MapHeader");
            if (existingHeader != null)
                headerText = existingHeader.GetComponent<Text>();

            CreateHeader();
        }

        private RectTransform FindRect(string path)
        {
            if (layoutRoot == null)
                return null;

            Transform found = layoutRoot.Find(path);
            return found as RectTransform;
        }

        private void UpdateHeader(string text)
        {
            CreateHeader();
            if (headerText != null)
                headerText.text = text;
        }

        private Text CreateText(string objectName, RectTransform parent, string text, int fontSize, Color color)
        {
            GameObject textObject = new GameObject(objectName, typeof(RectTransform), typeof(CanvasRenderer), typeof(Text));
            RectTransform rect = textObject.GetComponent<RectTransform>();
            rect.SetParent(parent, false);
            rect.anchorMin = Vector2.zero;
            rect.anchorMax = Vector2.one;
            rect.offsetMin = Vector2.zero;
            rect.offsetMax = Vector2.zero;

            Text label = textObject.GetComponent<Text>();
            label.text = text;
            label.font = labelFont;
            label.fontSize = fontSize;
            label.color = color;
            label.alignment = TextAnchor.MiddleCenter;
            label.raycastTarget = false;
            return label;
        }

        private Vector2 GetLocalPosition(MapNode node)
        {
            float x = node.roomIndex * GetHorizontalSpacing();
            float y = node.laneIndex * VerticalSpacing;
            return new Vector2(x, y);
        }

        private void UpdateContentPosition()
        {
            if (contentRoot != null)
                contentRoot.anchoredPosition = new Vector2(-focusedFloor * GetHorizontalSpacing(), 0f);
        }

        private void UpdateVisualStates(RunMap map)
        {
            foreach (MapNode node in map.nodes)
            {
                Transform nodeTransform = nodeRoot != null ? nodeRoot.Find(node.id) : null;
                if (nodeTransform == null)
                    continue;

                bool current = IsCurrentNode(node);
                bool completed = map.IsCompleted(node);
                bool selectable = map.CanSelect(node, gameBootstrap.RunContext.currentNode);
                bool visible = IsFloorVisible(node.roomIndex);

                if (nodeTransform.TryGetComponent(out Image image))
                {
                    image.color = current ? CurrentColor : completed ? CompletedColor : selectable ? AvailableColor : LockedColor;
                }

                if (nodeTransform.TryGetComponent(out Button button))
                    button.interactable = visible && selectable;
            }

            if (lineRoot == null)
                return;

            for (int i = 0; i < lineRoot.childCount; i++)
            {
                Transform line = lineRoot.GetChild(i);
                int fromFloor;
                int toFloor;
                ParseLineFloors(line.name, out fromFloor, out toFloor);
                bool visible = IsLineFloorVisible(fromFloor) || IsLineFloorVisible(toFloor);

                if (line.TryGetComponent(out Image image))
                    image.color = visible ? LineColor : WithAlpha(LineColor, LineColor.a);
            }
        }

        private static Color WithAlpha(Color color, float alpha)
        {
            return new Color(color.r, color.g, color.b, alpha);
        }

        private float GetHorizontalSpacing()
        {
            RectTransform self = transform as RectTransform;
            float width = self != null ? self.rect.width : 0f;
            if (width <= 0f)
                width = 1080f;

            return Mathf.Max(NodeSize + 18f, (width - HorizontalPadding * 2f) / (VisibleFloorRadius * 2f));
        }

        private int GetCurrentFloor()
        {
            return gameBootstrap != null && gameBootstrap.RunContext != null
                ? Mathf.Max(0, gameBootstrap.RunContext.roomIndex)
                : 0;
        }

        private bool IsFloorVisible(int floor)
        {
            return Mathf.Abs(floor - focusedFloor) <= VisibleFloorRadius + 0.01f;
        }

        private bool IsLineFloorVisible(int floor)
        {
            return Mathf.Abs(floor - focusedFloor) <= VisibleLineRadius + 0.01f;
        }

        private bool IsCurrentNode(MapNode node)
        {
            return gameBootstrap != null &&
                   gameBootstrap.RunContext != null &&
                   gameBootstrap.RunContext.currentNode != null &&
                   gameBootstrap.RunContext.currentNode.id == node.id;
        }

        private void ClampFocusedFloor(RunMap map)
        {
            int currentFloor = GetCurrentFloor();
            int maxFloor = Mathf.Min(currentFloor, GetMaxFloor(map));
            focusedFloor = Mathf.Clamp(focusedFloor, 0f, maxFloor);
        }

        private static int GetMaxFloor(RunMap map)
        {
            int maxRoomIndex = 0;
            for (int i = 0; i < map.nodes.Count; i++)
                maxRoomIndex = Mathf.Max(maxRoomIndex, map.nodes[i].roomIndex);

            return maxRoomIndex;
        }

        private static void ParseLineFloors(string lineName, out int fromFloor, out int toFloor)
        {
            fromFloor = 0;
            toFloor = 0;
            string[] parts = lineName.Split('_');
            if (parts.Length < 3)
                return;

            int.TryParse(parts[1], out fromFloor);
            int.TryParse(parts[2], out toFloor);
        }

        private static string GetNodeLabel(MapNode node)
        {
            switch (node.nodeType)
            {
                case MapNodeType.Start:
                    return "GO";
                case MapNodeType.NormalBattle:
                    return "B";
                case MapNodeType.EliteBattle:
                    return "E";
                case MapNodeType.Rest:
                    return "R";
                case MapNodeType.Shop:
                    return "S";
                case MapNodeType.Boss:
                    return "BO";
                default:
                    return "?";
            }
        }

        private static void Clear(RectTransform root)
        {
            if (root == null)
                return;

            for (int i = root.childCount - 1; i >= 0; i--)
            {
                GameObject child = root.GetChild(i).gameObject;
                child.SetActive(false);
                child.transform.SetParent(null, false);
                Destroy(child);
            }
        }
    }
}
