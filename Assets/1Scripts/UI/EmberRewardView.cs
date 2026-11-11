using System.Collections;
using System.Collections.Generic;
using GoldfishWalking.Core;
using UnityEngine;
using UnityEngine.UI;

namespace GoldfishWalking.UI
{
    public sealed class EmberRewardView : MonoBehaviour
    {
        private const float FlightDuration = 1.15f;
        private const float OrbitRadiusX = 118f;
        private const float OrbitRadiusY = 58f;
        private readonly List<RectTransform> orbitingEmbers = new List<RectTransform>();

        private GameBootstrap bootstrap;
        private RectTransform playerPortrait;
        private RectTransform monsterPortrait;
        private RectTransform backLayer;
        private RectTransform frontLayer;
        private Image inputBlocker;
        private Coroutine flightRoutine;
        private bool handedOffToReward;

        private void Awake()
        {
            ResolveReferences();
            EnsureLayers();
        }

        private void OnEnable()
        {
            GameEventHub.StateChanged += OnStateChanged;
            ResolveReferences();
            EnsureLayers();
            handedOffToReward = false;
            RebuildOrbitingEmbers();
            if (bootstrap?.StateMachine?.CurrentState == GameState.EmberReward)
                BeginFlight();
        }

        private void OnDisable()
        {
            GameEventHub.StateChanged -= OnStateChanged;
            if (flightRoutine != null)
                StopCoroutine(flightRoutine);
            flightRoutine = null;
        }

        private void LateUpdate()
        {
            if (handedOffToReward || bootstrap?.RunContext == null || playerPortrait == null)
                return;
            if (orbitingEmbers.Count != bootstrap.RunContext.fantasyEmbers.Count)
                RebuildOrbitingEmbers();
            UpdateOrbitingEmbers();
        }

        public bool TryHandoffOrbitingEmbers(RectTransform destination, List<RectTransform> result)
        {
            if (destination == null || result == null || orbitingEmbers.Count != 3)
                return false;

            handedOffToReward = true;
            result.Clear();
            for (int i = 0; i < orbitingEmbers.Count; i++)
            {
                RectTransform ember = orbitingEmbers[i];
                Vector3 world = ember.position;
                ember.SetParent(destination, true);
                ember.anchoredPosition = WorldToLocal(destination, world);
                ember.localScale = Vector3.one;
                result.Add(ember);
            }
            orbitingEmbers.Clear();
            return true;
        }

        private void OnStateChanged(GameState previous, GameState next)
        {
            if (next == GameState.Battle)
            {
                handedOffToReward = false;
                RebuildOrbitingEmbers();
            }
            else if (next == GameState.EmberReward)
            {
                BeginFlight();
            }
        }

        private void BeginFlight()
        {
            if (flightRoutine != null || bootstrap?.RunContext == null || !bootstrap.RunContext.hasPendingEmber)
                return;
            flightRoutine = StartCoroutine(PlayFlightToOrbit());
        }

        private IEnumerator PlayFlightToOrbit()
        {
            if (inputBlocker != null)
                inputBlocker.raycastTarget = true;

            int destinationIndex = orbitingEmbers.Count;
            int completedCount = destinationIndex + 1;
            RectTransform ember = CreateEmberVisual(frontLayer, "FlyingEmber", bootstrap.RunContext.pendingEmber);
            Vector2 start = monsterPortrait != null ? LocalCenter(monsterPortrait, frontLayer) : new Vector2(560f, 0f);
            float elapsed = 0f;
            while (elapsed < FlightDuration)
            {
                elapsed += Time.unscaledDeltaTime;
                float t = Mathf.Clamp01(elapsed / FlightDuration);
                float eased = 1f - Mathf.Pow(1f - t, 3f);
                float phase = CurrentOrbitTime() + destinationIndex * Mathf.PI * 2f / completedCount;
                RectTransform targetLayer = OrbitLayer(phase);
                if (ember.parent != targetLayer)
                    ReparentKeepingPosition(ember, targetLayer);
                Vector2 target = OrbitPosition(targetLayer, phase);
                Vector2 localStart = WorldToLocal(targetLayer, frontLayer.TransformPoint(start));
                Vector2 point = Vector2.Lerp(localStart, target, eased);
                point.y += Mathf.Sin(t * Mathf.PI) * 150f;
                ember.anchoredPosition = point;
                ember.localScale = Vector3.one * Mathf.Lerp(1.45f, 1f, eased);
                yield return null;
            }

            float finalPhase = CurrentOrbitTime() + destinationIndex * Mathf.PI * 2f / completedCount;
            RectTransform finalLayer = OrbitLayer(finalPhase);
            if (ember.parent != finalLayer)
                ReparentKeepingPosition(ember, finalLayer);
            ember.anchoredPosition = OrbitPosition(finalLayer, finalPhase);
            ember.localScale = Vector3.one;
            ember.name = $"OrbitingEmber_{destinationIndex + 1}";
            orbitingEmbers.Add(ember);
            flightRoutine = null;
            if (inputBlocker != null)
                inputBlocker.raycastTarget = false;
            GameEventHub.RaiseEmberAnimationCompleted();
        }

        private void UpdateOrbitingEmbers()
        {
            int count = orbitingEmbers.Count;
            float time = CurrentOrbitTime();
            for (int i = 0; i < count; i++)
            {
                float phase = time + i * Mathf.PI * 2f / Mathf.Max(1, count);
                RectTransform layer = OrbitLayer(phase);
                RectTransform ember = orbitingEmbers[i];
                if (ember.parent != layer)
                    ReparentKeepingPosition(ember, layer);
                ember.anchoredPosition = OrbitPosition(layer, phase);
                float flicker = 1f + Mathf.Sin(Time.unscaledTime * 9f + i * 1.7f) * 0.08f;
                ember.localScale = Vector3.one * flicker;
            }
        }

        private float CurrentOrbitTime()
        {
            return Time.unscaledTime * 0.75f;
        }

        private RectTransform OrbitLayer(float phase)
        {
            return Mathf.Sin(phase) > 0f ? backLayer : frontLayer;
        }

        private Vector2 OrbitPosition(RectTransform layer, float phase)
        {
            Vector2 center = LocalCenter(playerPortrait, layer);
            return center + new Vector2(Mathf.Cos(phase) * OrbitRadiusX, Mathf.Sin(phase) * OrbitRadiusY + 12f);
        }

        private void ResolveReferences()
        {
            if (bootstrap == null)
                bootstrap = FindFirstObjectByType<GameBootstrap>(FindObjectsInactive.Include);
            playerPortrait = FindNamedRect(transform, "PlayerPortrait");
            monsterPortrait = FindNamedRect(transform, "MonsterPortrait");
        }

        private void EnsureLayers()
        {
            if (playerPortrait == null || playerPortrait.parent == null)
                return;
            RectTransform parent = playerPortrait.parent as RectTransform;
            backLayer = GetOrCreateLayer(parent, "EmberBackLayer");
            frontLayer = GetOrCreateLayer(parent, "EmberFrontLayer");

            backLayer.SetAsLastSibling();
            frontLayer.SetAsLastSibling();
            backLayer.SetSiblingIndex(playerPortrait.GetSiblingIndex());
            frontLayer.SetSiblingIndex(playerPortrait.GetSiblingIndex() + 1);

            Transform blockerTransform = transform.Find("EmberInputBlocker");
            GameObject blocker = blockerTransform != null ? blockerTransform.gameObject
                : new GameObject("EmberInputBlocker", typeof(RectTransform), typeof(CanvasRenderer), typeof(Image));
            if (blockerTransform == null)
                blocker.transform.SetParent(transform, false);
            RectTransform blockerRect = blocker.GetComponent<RectTransform>();
            Stretch(blockerRect);
            inputBlocker = blocker.GetComponent<Image>();
            inputBlocker.color = Color.clear;
            inputBlocker.raycastTarget = false;
        }

        private static RectTransform GetOrCreateLayer(RectTransform parent, string name)
        {
            Transform existing = parent.Find(name);
            if (existing is RectTransform existingRect)
                return existingRect;
            GameObject layer = new GameObject(name, typeof(RectTransform));
            RectTransform rect = layer.GetComponent<RectTransform>();
            rect.SetParent(parent, false);
            Stretch(rect);
            return rect;
        }

        private void RebuildOrbitingEmbers()
        {
            if (handedOffToReward)
                return;
            for (int i = 0; i < orbitingEmbers.Count; i++)
                if (orbitingEmbers[i] != null) Destroy(orbitingEmbers[i].gameObject);
            orbitingEmbers.Clear();
            if (bootstrap?.RunContext?.fantasyEmbers == null || frontLayer == null)
                return;
            for (int i = 0; i < bootstrap.RunContext.fantasyEmbers.Count; i++)
                orbitingEmbers.Add(CreateEmberVisual(frontLayer, $"OrbitingEmber_{i + 1}", bootstrap.RunContext.fantasyEmbers[i]));
            UpdateOrbitingEmbers();
        }

        public static RectTransform CreateEmberVisual(RectTransform parent, string objectName, FantasyEmberType type)
        {
            GameObject root = new GameObject(objectName, typeof(RectTransform), typeof(CanvasGroup));
            RectTransform rect = root.GetComponent<RectTransform>();
            rect.SetParent(parent, false);
            rect.sizeDelta = new Vector2(28f, 36f);
            Color outer = type == FantasyEmberType.Blue
                ? new Color(0.20f, 0.72f, 1f, 1f)
                : new Color(0.96f, 0.98f, 1f, 1f);
            Color inner = type == FantasyEmberType.Blue
                ? new Color(0.72f, 0.94f, 1f, 1f)
                : new Color(1f, 0.88f, 0.48f, 1f);
            CreateDiamond(rect, "Glow", new Vector2(25f, 25f), new Vector2(0f, -1f), new Color(outer.r, outer.g, outer.b, 0.24f));
            CreateDiamond(rect, "OuterFlame", new Vector2(18f, 18f), new Vector2(0f, -2f), outer);
            CreateDiamond(rect, "FlameTip", new Vector2(11f, 11f), new Vector2(2f, 10f), outer);
            CreateDiamond(rect, "InnerFlame", new Vector2(9f, 9f), new Vector2(0f, -3f), inner);
            return rect;
        }

        private static void CreateDiamond(RectTransform parent, string name, Vector2 size, Vector2 position, Color color)
        {
            GameObject piece = new GameObject(name, typeof(RectTransform), typeof(CanvasRenderer), typeof(Image));
            RectTransform rect = piece.GetComponent<RectTransform>();
            rect.SetParent(parent, false);
            rect.sizeDelta = size;
            rect.anchoredPosition = position;
            rect.localRotation = Quaternion.Euler(0f, 0f, 45f);
            Image image = piece.GetComponent<Image>();
            image.color = color;
            image.raycastTarget = false;
        }

        private static void ReparentKeepingPosition(RectTransform child, RectTransform parent)
        {
            Vector3 world = child.position;
            child.SetParent(parent, true);
            child.anchoredPosition = WorldToLocal(parent, world);
        }

        private static Vector2 LocalCenter(RectTransform source, RectTransform destination)
        {
            return WorldToLocal(destination, source.TransformPoint(source.rect.center));
        }

        private static Vector2 WorldToLocal(RectTransform parent, Vector3 world)
        {
            Vector3 local = parent.InverseTransformPoint(world);
            return new Vector2(local.x, local.y);
        }

        private static void Stretch(RectTransform rect)
        {
            rect.anchorMin = Vector2.zero;
            rect.anchorMax = Vector2.one;
            rect.offsetMin = Vector2.zero;
            rect.offsetMax = Vector2.zero;
        }

        private static RectTransform FindNamedRect(Transform root, string targetName)
        {
            RectTransform[] rects = root.GetComponentsInChildren<RectTransform>(true);
            for (int i = 0; i < rects.Length; i++)
                if (rects[i].name == targetName) return rects[i];
            return null;
        }
    }
}
