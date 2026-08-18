using System;
using System.Collections.Generic;
using System.Linq;
using GoldfishWalking.Data;
using GoldfishWalking.Core;
using GoldfishWalking.Match;
using GoldfishWalking.UI;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

namespace GoldfishWalking.Editor
{
    public static class SceneArtReferenceBinder
    {
        private const string MainScenePath = "Assets/Scenes/GumBwing_Er.unity";

        [MenuItem("GoldfishWalking/Art/Apply Direct Art References To Main Scene")]
        public static void ApplyToMainScene()
        {
            Scene scene = SceneManager.GetActiveScene();
            if (scene.path != MainScenePath)
                scene = EditorSceneManager.OpenScene(MainScenePath, OpenSceneMode.Single);

            GameObject monsterPortrait = FindInScene(scene, "MonsterPortrait");
            ConfigurePortrait(monsterPortrait, null, null);

            (Sprite playerSprite, RuntimeAnimatorController playerController) = PlayerArtAssetBuilder.Build();
            GameObject playerPortrait = FindInScene(scene, "PlayerPortrait") ?? FindInScene(scene, "PlayerSpritePlaceholder");
            ConfigurePortrait(playerPortrait, playerSprite, playerController);
            playerPortrait.name = "PlayerPortrait";

            Sprite shopkeeperSprite = AssetDatabase.LoadAllAssetsAtPath("Assets/Art/shop/shopkeeper.png")
                .OfType<Sprite>()
                .OrderBy(sprite => sprite.name, StringComparer.Ordinal)
                .FirstOrDefault();
            RuntimeAnimatorController shopkeeperController = AssetDatabase.LoadAssetAtPath<RuntimeAnimatorController>(
                "Assets/Art/Generated/Shop/Shopkeeper.controller");
            GameObject shopkeeperPortrait = FindInScene(scene, "ShopkeeperPortrait");
            ConfigurePortrait(shopkeeperPortrait, shopkeeperSprite, shopkeeperController);

            ApplyUiSkin(scene);
            ApplyBattleBackgrounds(scene);
            ApplyBattleLayout(scene);

            EditorSceneManager.MarkSceneDirty(scene);
            EditorSceneManager.SaveScene(scene);
            Debug.Log("GumBwing_Er.unity의 몬스터/상점 초상을 Image + Animator 직접 참조 방식으로 전환했습니다.");
        }

        private static void ApplyBattleBackgrounds(Scene scene)
        {
            BattleView battleView = scene.GetRootGameObjects()
                .SelectMany(root => root.GetComponentsInChildren<BattleView>(true))
                .FirstOrDefault();
            if (battleView == null)
                throw new InvalidOperationException("BattleView를 찾을 수 없습니다.");

            Sprite act1 = LoadFirstSprite("Assets/Art/Background/1막.png");
            Sprite act2 = LoadFirstSprite("Assets/Art/Background/2막.png");
            Sprite act3 = LoadFirstSprite("Assets/Art/Background/3막.png");
            if (act1 == null || act2 == null || act3 == null)
                throw new InvalidOperationException("Assets/Art/Background의 1막, 2막, 3막 배경 Sprite를 모두 찾을 수 없습니다.");

            battleView.ConfigureBackgrounds(act1, act2, act3);
            EditorUtility.SetDirty(battleView);
        }

        private static Sprite LoadFirstSprite(string path)
        {
            return AssetDatabase.LoadAllAssetsAtPath(path).OfType<Sprite>().FirstOrDefault();
        }

        private static void ApplyUiSkin(Scene scene)
        {
            List<string> errors = new List<string>();
            UiSkinData skin = UiAtlasAssetBuilder.Build(errors);
            if (skin == null)
                throw new InvalidOperationException(string.Join(Environment.NewLine, errors));

            GameObject[] roots = scene.GetRootGameObjects();
            Button[] buttons = roots.SelectMany(root => root.GetComponentsInChildren<Button>(true)).ToArray();
            HashSet<Image> buttonImages = new HashSet<Image>();
            foreach (Button button in buttons)
            {
                Image image = button.targetGraphic as Image ?? button.GetComponent<Image>();
                if (image != null)
                    buttonImages.Add(image);
            }

            foreach (IGrouping<Transform, Button> group in buttons.GroupBy(button => button.transform.parent))
            {
                Button[] normalButtons = group.Where(button => !TryApplySpecialButton(button, skin))
                    .OrderBy(button => button.transform.GetSiblingIndex())
                    .ToArray();
                for (int i = 0; i < normalButtons.Length; i++)
                {
                    Sprite sprite = normalButtons.Length == 1 ? skin.singleButton
                        : i == 0 ? skin.connectedLeftButton
                        : i == normalButtons.Length - 1 ? skin.connectedRightButton
                        : skin.connectedMiddleButton;
                    ApplyButtonSprite(normalButtons[i], sprite);
                }
            }

            Image[] images = roots.SelectMany(root => root.GetComponentsInChildren<Image>(true)).ToArray();
            foreach (Image image in images)
            {
                if (buttonImages.Contains(image) || !IsTextPanel(image.gameObject.name))
                    continue;
                image.sprite = skin.textPanel;
                image.type = Image.Type.Sliced;
                image.color = Color.white;
            }

            foreach (FantasyListView fantasyList in roots.SelectMany(root => root.GetComponentsInChildren<FantasyListView>(true)))
            {
                fantasyList.ConfigureSkin(skin);
                EditorUtility.SetDirty(fantasyList);
            }

            GameBootstrap bootstrap = roots.SelectMany(root => root.GetComponentsInChildren<GameBootstrap>(true)).FirstOrDefault();
            if (bootstrap == null)
                throw new InvalidOperationException("GameBootstrap을 찾을 수 없습니다.");
            MatchstickVisualSettings matchSettings = bootstrap.GetComponent<MatchstickVisualSettings>();
            if (matchSettings == null)
                matchSettings = bootstrap.gameObject.AddComponent<MatchstickVisualSettings>();
            Sprite matchSprite = AssetDatabase.LoadAllAssetsAtPath("Assets/Image/Match.png").OfType<Sprite>().FirstOrDefault();
            if (matchSprite == null)
                throw new InvalidOperationException("Assets/Image/Match.png의 Sprite를 찾을 수 없습니다.");
            matchSettings.Configure(matchSprite, skin);
            EditorUtility.SetDirty(matchSettings);

            foreach (Transform consumablePanel in roots.SelectMany(root => root.GetComponentsInChildren<Transform>(true))
                         .Where(item => item.name == "ConsumablePanel"))
            {
                if (consumablePanel is RectTransform panelRect)
                    panelRect.sizeDelta = new Vector2(Mathf.Max(364f, panelRect.sizeDelta.x), 132f);
                for (int i = 0; i < consumablePanel.childCount; i++)
                {
                    if (!(consumablePanel.GetChild(i) is RectTransform slot))
                        continue;
                    float width = slot.sizeDelta.x > 0f ? slot.sizeDelta.x : 88f;
                    slot.sizeDelta = new Vector2(width, width);
                    Image image = slot.GetComponent<Image>();
                    if (image != null)
                    {
                        image.sprite = skin.singleButton;
                        image.type = Image.Type.Sliced;
                        image.color = Color.white;
                    }
                }
            }
        }

        private static void ApplyBattleLayout(Scene scene)
        {
            SetRect(scene, "PlayerFormulaPanel", new Vector2(-560f, 155f), new Vector2(304f, 126f));
            SetRect(scene, "MonsterFormulaPanel", new Vector2(-374f, 155f), new Vector2(504f, 126f));
            SetRect(scene, "PlayerPortrait", new Vector2(-560f, -165f), new Vector2(260f, 260f));
            SetRect(scene, "MonsterPortrait", new Vector2(560f, -125f), new Vector2(340f, 340f));
        }

        private static void SetRect(Scene scene, string objectName, Vector2 anchoredPosition, Vector2 size)
        {
            GameObject target = FindInScene(scene, objectName);
            if (target == null || !(target.transform is RectTransform rect))
                throw new InvalidOperationException($"{objectName} RectTransform을 찾을 수 없습니다.");
            rect.anchoredPosition = anchoredPosition;
            rect.sizeDelta = size;
            EditorUtility.SetDirty(rect);
        }

        private static bool TryApplySpecialButton(Button button, UiSkinData skin)
        {
            string name = button.gameObject.name;
            Sprite sprite = null;
            if (name.Equals("NextButton", StringComparison.OrdinalIgnoreCase))
                sprite = skin.nextButton;
            else if (name.Equals("ResetButton", StringComparison.OrdinalIgnoreCase)
                     || name.Equals("RerollButton", StringComparison.OrdinalIgnoreCase))
                sprite = skin.resetButton;
            else if (name.Equals("CloseButton", StringComparison.OrdinalIgnoreCase))
                sprite = skin.closeButton;
            if (sprite == null)
                return false;

            ApplyButtonSprite(button, sprite, false);
            foreach (Text label in button.GetComponentsInChildren<Text>(true))
                label.enabled = false;
            return true;
        }

        private static void ApplyButtonSprite(Button button, Sprite sprite, bool sliced = true)
        {
            Image image = button.targetGraphic as Image ?? button.GetComponent<Image>();
            if (image == null)
                return;
            image.sprite = sprite;
            image.type = sliced ? Image.Type.Sliced : Image.Type.Simple;
            image.preserveAspect = !sliced;
            image.color = Color.white;
            button.targetGraphic = image;
            foreach (Graphic graphic in button.GetComponentsInChildren<Graphic>(true))
            {
                if (graphic != image)
                    graphic.raycastTarget = false;
            }
        }

        private static bool IsTextPanel(string name)
        {
            return name.EndsWith("Panel", StringComparison.OrdinalIgnoreCase)
                   || name.IndexOf("Tooltip", StringComparison.OrdinalIgnoreCase) >= 0
                   || name.IndexOf("Description", StringComparison.OrdinalIgnoreCase) >= 0
                   || name.IndexOf("Console", StringComparison.OrdinalIgnoreCase) >= 0;
        }

        private static void ConfigurePortrait(GameObject target, Sprite sprite, RuntimeAnimatorController controller)
        {
            if (target == null)
                throw new InvalidOperationException("씬에서 초상 오브젝트를 찾지 못했습니다.");

            GameObjectUtility.RemoveMonoBehavioursWithMissingScript(target);
            RawImage rawImage = target.GetComponent<RawImage>();
            Text placeholderText = target.GetComponent<Text>();
            Color color = rawImage != null ? rawImage.color : placeholderText != null ? placeholderText.color : Color.white;
            bool raycastTarget = rawImage != null && rawImage.raycastTarget;
            if (rawImage != null)
                UnityEngine.Object.DestroyImmediate(rawImage, true);
            if (placeholderText != null)
                UnityEngine.Object.DestroyImmediate(placeholderText, true);

            Image image = target.GetComponent<Image>();
            if (image == null)
                image = target.AddComponent<Image>();
            image.color = color;
            image.raycastTarget = raycastTarget;
            image.preserveAspect = true;
            image.sprite = sprite;
            image.enabled = sprite != null;

            Animator animator = target.GetComponent<Animator>();
            if (animator == null)
                animator = target.AddComponent<Animator>();
            animator.updateMode = AnimatorUpdateMode.UnscaledTime;
            animator.runtimeAnimatorController = controller;
        }

        private static GameObject FindInScene(Scene scene, string objectName)
        {
            foreach (GameObject root in scene.GetRootGameObjects())
            {
                Transform match = root.GetComponentsInChildren<Transform>(true)
                    .FirstOrDefault(item => item.name == objectName);
                if (match != null)
                    return match.gameObject;
            }
            return null;
        }
    }
}
