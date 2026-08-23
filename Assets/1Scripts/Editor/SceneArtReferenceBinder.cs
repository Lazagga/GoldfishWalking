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
            ApplyAddedUiArt(scene);
            ApplyGameFont(scene);
            ApplyBattleBackgrounds(scene);
            ApplyRestSceneArt(scene);
            ApplyBattleLayout(scene);

            EditorSceneManager.MarkSceneDirty(scene);
            EditorSceneManager.SaveScene(scene);
            Debug.Log("GumBwing_Er.unity의 몬스터/상점 초상을 Image + Animator 직접 참조 방식으로 전환했습니다.");
        }

        private static void ApplyAddedUiArt(Scene scene)
        {
            GameOverDamageLogView gameOverView = scene.GetRootGameObjects()
                .SelectMany(root => root.GetComponentsInChildren<GameOverDamageLogView>(true))
                .FirstOrDefault();
            if (gameOverView != null)
                gameOverView.BuildSceneUILayout();

            GameObject mainCanvas = FindInScene(scene, "MainCanvas");
            if (mainCanvas != null)
            {
                PauseMenuView pauseMenu = mainCanvas.GetComponent<PauseMenuView>();
                if (pauseMenu == null)
                    pauseMenu = mainCanvas.AddComponent<PauseMenuView>();
                pauseMenu.BuildSceneUILayout();
                EditorUtility.SetDirty(pauseMenu);
            }

            Sprite campfire = LoadNamedSprite("Assets/Art/ui/campfire_icon.png", "campfire_icon_0");
            Sprite battle = LoadNamedSprite("Assets/Art/ui/battle_icon.png", "battle_icon_0");
            Sprite boss = LoadNamedSprite("Assets/Art/ui/boss_icon.png", "boss_icon_0");
            Sprite eraser = LoadNamedSprite("Assets/Art/ui/eraser_item_icon.png", "eraser_item_icon_0");
            Sprite matchItem = LoadNamedSprite("Assets/Art/ui/match_item_icon.png", "match_item_icon_0");
            Sprite panel = LoadNamedSprite("Assets/Art/ui/jeongwangpan.png", "jeongwangpan_0");
            Sprite left = LoadNamedSprite("Assets/Art/ui/text_container_left.png", "text_container_left_0");
            Sprite middle = LoadNamedSprite("Assets/Art/ui/text_container_middle.png", "text_container_middle_0");
            Sprite right = LoadNamedSprite("Assets/Art/ui/text_container_right.png", "text_container_right_0");
            if (new[] { campfire, battle, boss, eraser, matchItem, panel, left, middle, right }.Any(sprite => sprite == null))
                throw new InvalidOperationException("새 UI Sprite 중 하나 이상을 찾을 수 없습니다.");

            GameObject[] roots = scene.GetRootGameObjects();
            GameBootstrap bootstrap = roots.SelectMany(root => root.GetComponentsInChildren<GameBootstrap>(true)).FirstOrDefault();
            UiArtSettings settings = bootstrap != null ? bootstrap.GetComponent<UiArtSettings>() : null;
            if (bootstrap == null)
                throw new InvalidOperationException("GameBootstrap을 찾을 수 없습니다.");
            if (settings == null)
                settings = bootstrap.gameObject.AddComponent<UiArtSettings>();
            settings.Configure(campfire, battle, boss, eraser, matchItem, panel, left, middle, right);
            EditorUtility.SetDirty(settings);

            foreach (Transform consumable in roots.SelectMany(root => root.GetComponentsInChildren<Transform>(true))
                         .Where(item => item.name == "ConsumablePanel"))
            {
                for (int i = 0; i < Mathf.Min(2, consumable.childCount); i++)
                    UiArtSettings.ApplyIcon(consumable.GetChild(i), i == 0 ? matchItem : eraser);
            }

            GameObject restButton = FindInScene(scene, "RestButton");
            if (restButton != null)
            {
                Transform restIcon = restButton.transform.Find("ArtIcon");
                if (restIcon != null)
                {
                    restIcon.gameObject.SetActive(false);
                    EditorUtility.SetDirty(restIcon.gameObject);
                }
            }

            GameObject popup = FindInScene(scene, "SevenSegmentEditPopup");
            ApplyPanelSprite(popup != null ? popup.transform.Find("Panel")?.GetComponent<Image>() : null, panel);
            ApplyPanelSprite(FindInScene(scene, "RewardList")?.GetComponent<Image>(), panel);

            foreach (RectTransform counter in roots.SelectMany(root => root.GetComponentsInChildren<RectTransform>(true))
                         .Where(item => item.name == "MoveCounter"))
                ApplyTextContainer(counter, left, middle, right);
        }

        private static Sprite LoadNamedSprite(string path, string name)
        {
            return AssetDatabase.LoadAllAssetsAtPath(path).OfType<Sprite>()
                .FirstOrDefault(sprite => sprite.name == name);
        }

        private static void ApplyPanelSprite(Image image, Sprite sprite)
        {
            if (image == null)
                return;
            image.sprite = sprite;
            image.type = Image.Type.Simple;
            image.preserveAspect = false;
            image.color = Color.white;
            EditorUtility.SetDirty(image);
        }

        private static void ApplyTextContainer(RectTransform root, Sprite left, Sprite middle, Sprite right)
        {
            Image background = root.GetComponent<Image>();
            if (background != null)
                background.enabled = false;
            float height = Mathf.Max(1f, root.rect.height);
            float edgeWidth = height * 19f / 15f;
            CreateContainerPiece(root, "ContainerLeft", left, new Vector2(0f, 0f), new Vector2(0f, 1f),
                Vector2.zero, new Vector2(edgeWidth, 0f), Image.Type.Simple);
            CreateContainerPiece(root, "ContainerMiddle", middle, Vector2.zero, Vector2.one,
                new Vector2(edgeWidth, 0f), new Vector2(-edgeWidth, 0f), Image.Type.Simple);
            CreateContainerPiece(root, "ContainerRight", right, new Vector2(1f, 0f), Vector2.one,
                new Vector2(-edgeWidth, 0f), Vector2.zero, Image.Type.Simple);
        }

        private static void CreateContainerPiece(RectTransform root, string name, Sprite sprite,
            Vector2 anchorMin, Vector2 anchorMax, Vector2 offsetMin, Vector2 offsetMax, Image.Type type)
        {
            Transform existing = root.Find(name);
            GameObject go = existing != null ? existing.gameObject
                : new GameObject(name, typeof(RectTransform), typeof(CanvasRenderer), typeof(Image));
            if (existing == null)
                go.transform.SetParent(root, false);
            Image image = go.GetComponent<Image>();
            image.sprite = sprite;
            image.type = type;
            image.color = Color.white;
            image.raycastTarget = false;
            RectTransform rect = image.rectTransform;
            rect.anchorMin = anchorMin;
            rect.anchorMax = anchorMax;
            rect.offsetMin = offsetMin;
            rect.offsetMax = offsetMax;
            rect.SetAsFirstSibling();
            EditorUtility.SetDirty(go);
        }

        private static void ApplyGameFont(Scene scene)
        {
            Font defaultFont = AssetDatabase.LoadAssetAtPath<Font>("Assets/Thaleah_PixelFont/Materials/ThaleahFat_TTF.ttf");
            if (defaultFont == null)
                throw new InvalidOperationException("Free Pixel Font - Thaleah Font 에셋을 찾을 수 없습니다.");

            GameObject[] roots = scene.GetRootGameObjects();
            GameBootstrap bootstrap = roots.SelectMany(root => root.GetComponentsInChildren<GameBootstrap>(true)).FirstOrDefault();
            if (bootstrap == null)
                throw new InvalidOperationException("GameBootstrap을 찾을 수 없습니다.");
            GameFontSettings settings = bootstrap.GetComponent<GameFontSettings>();
            if (settings == null)
                settings = bootstrap.gameObject.AddComponent<GameFontSettings>();
            settings.ConfigureDefault(defaultFont);
            foreach (Text text in roots.SelectMany(root => root.GetComponentsInChildren<Text>(true)))
                EditorUtility.SetDirty(text);
            EditorUtility.SetDirty(settings);
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
            ApplyShopBackgrounds(scene, act1, act2, act3);
        }

        private static void ApplyShopBackgrounds(Scene scene, Sprite act1, Sprite act2, Sprite act3)
        {
            ShopView shopView = scene.GetRootGameObjects()
                .SelectMany(root => root.GetComponentsInChildren<ShopView>(true))
                .FirstOrDefault();
            if (shopView == null)
                throw new InvalidOperationException("ShopView not found.");

            Transform merchantPanel = shopView.transform.Find("ShopRuntimeLayout/MerchantPanel");
            if (merchantPanel == null)
                throw new InvalidOperationException("ShopRuntimeLayout/MerchantPanel not found.");

            if (merchantPanel.GetComponent<RectMask2D>() == null)
                merchantPanel.gameObject.AddComponent<RectMask2D>();

            Transform existing = merchantPanel.Find("MerchantBackground");
            GameObject backgroundObject = existing != null ? existing.gameObject
                : new GameObject("MerchantBackground", typeof(RectTransform), typeof(CanvasRenderer), typeof(Image));
            if (existing == null)
                backgroundObject.transform.SetParent(merchantPanel, false);

            Image backgroundImage = backgroundObject.GetComponent<Image>();
            RectTransform backgroundRect = backgroundImage.rectTransform;
            backgroundRect.anchorMin = Vector2.zero;
            backgroundRect.anchorMax = Vector2.one;
            backgroundRect.offsetMin = Vector2.zero;
            backgroundRect.offsetMax = Vector2.zero;
            backgroundRect.SetAsFirstSibling();
            backgroundImage.sprite = act1;
            backgroundImage.type = Image.Type.Simple;
            backgroundImage.preserveAspect = false;
            backgroundImage.color = Color.white;
            backgroundImage.raycastTarget = false;
            AspectRatioFitter backgroundFitter = backgroundObject.GetComponent<AspectRatioFitter>();
            if (backgroundFitter == null)
                backgroundFitter = backgroundObject.AddComponent<AspectRatioFitter>();
            backgroundFitter.aspectMode = AspectRatioFitter.AspectMode.EnvelopeParent;
            backgroundFitter.aspectRatio = act1.rect.width / Mathf.Max(1f, act1.rect.height);

            shopView.ConfigureBackgrounds(act1, act2, act3);
            EditorUtility.SetDirty(merchantPanel.gameObject);
            EditorUtility.SetDirty(backgroundObject);
            EditorUtility.SetDirty(shopView);
        }

        private static void ApplyRestSceneArt(Scene scene)
        {
            RestView restView = scene.GetRootGameObjects()
                .SelectMany(root => root.GetComponentsInChildren<RestView>(true))
                .FirstOrDefault();
            if (restView == null)
                throw new InvalidOperationException("RestView not found.");

            string[] campfirePaths =
            {
                "Assets/Art/Background/rest_scene_campfire_0000.png",
                "Assets/Art/Background/rest_scene_campfire_0001.png",
                "Assets/Art/Background/rest_scene_campfire_0002.png"
            };
            foreach (string path in campfirePaths)
                ConfigureFullFrameSprite(path);

            Sprite background = LoadFirstSprite("Assets/Art/Background/rest_scene_bg.png");
            Sprite lessBright = LoadFirstSprite("Assets/Art/Background/rest_scene_bg_less_bright.png");
            Sprite[] campfireFrames = campfirePaths.Select(LoadFirstSprite).ToArray();
            if (background == null || lessBright == null || campfireFrames.Any(sprite => sprite == null))
                throw new InvalidOperationException("Rest scene background or campfire sprites not found.");

            Transform layout = restView.transform.Find("RestRuntimeLayout");
            if (layout == null)
                throw new InvalidOperationException("RestRuntimeLayout not found.");

            Transform oldBackground = layout.Find("Background");
            Image oldBackgroundImage = oldBackground != null ? oldBackground.GetComponent<Image>() : null;
            if (oldBackgroundImage != null)
            {
                oldBackgroundImage.enabled = false;
                oldBackgroundImage.raycastTarget = false;
                EditorUtility.SetDirty(oldBackgroundImage);
            }

            GameObject artObject = GetOrCreateImageObject(layout, "RestSceneArt");
            RectTransform artRect = artObject.GetComponent<RectTransform>();
            artRect.anchorMin = Vector2.zero;
            artRect.anchorMax = Vector2.one;
            artRect.offsetMin = Vector2.zero;
            artRect.offsetMax = Vector2.zero;
            artRect.SetAsFirstSibling();
            Image artImage = artObject.GetComponent<Image>();
            artImage.enabled = false;
            artImage.raycastTarget = false;
            AspectRatioFitter fitter = artObject.GetComponent<AspectRatioFitter>();
            if (fitter == null)
                fitter = artObject.AddComponent<AspectRatioFitter>();
            fitter.aspectMode = AspectRatioFitter.AspectMode.WidthControlsHeight;
            fitter.aspectRatio = 4f / 3f;

            GameObject backgroundObject = GetOrCreateImageObject(artObject.transform, "Background");
            StretchImage(backgroundObject.GetComponent<Image>(), background);

            GameObject campfireObject = GetOrCreateImageObject(artObject.transform, "Campfire");
            Image campfireImage = campfireObject.GetComponent<Image>();
            campfireImage.sprite = campfireFrames[0];
            campfireImage.preserveAspect = true;
            campfireImage.raycastTarget = false;
            RectTransform fireRect = campfireImage.rectTransform;
            fireRect.anchorMin = new Vector2(104f / 240f, 1f - 144f / 180f);
            fireRect.anchorMax = new Vector2(136f / 240f, 1f - 112f / 180f);
            fireRect.offsetMin = Vector2.zero;
            fireRect.offsetMax = Vector2.zero;
            fireRect.SetAsLastSibling();

            restView.ConfigureSceneArt(background, lessBright, campfireFrames);
            EditorUtility.SetDirty(artObject);
            EditorUtility.SetDirty(backgroundObject);
            EditorUtility.SetDirty(campfireObject);
            EditorUtility.SetDirty(restView);
        }

        private static void ConfigureFullFrameSprite(string path)
        {
            TextureImporter importer = AssetImporter.GetAtPath(path) as TextureImporter;
            if (importer == null)
                return;

            TextureImporterSettings settings = new TextureImporterSettings();
            importer.ReadTextureSettings(settings);
            bool changed = importer.spriteImportMode != SpriteImportMode.Single
                || settings.spriteMeshType != SpriteMeshType.FullRect
                || importer.filterMode != FilterMode.Point
                || importer.textureCompression != TextureImporterCompression.Uncompressed;
            if (!changed)
                return;

            importer.textureType = TextureImporterType.Sprite;
            importer.spriteImportMode = SpriteImportMode.Single;
            importer.spritePivot = new Vector2(0.5f, 0.5f);
            importer.filterMode = FilterMode.Point;
            importer.textureCompression = TextureImporterCompression.Uncompressed;
            settings.spriteMode = (int)SpriteImportMode.Single;
            settings.spriteMeshType = SpriteMeshType.FullRect;
            importer.SetTextureSettings(settings);
            importer.SaveAndReimport();
        }

        private static GameObject GetOrCreateImageObject(Transform parent, string name)
        {
            Transform existing = parent.Find(name);
            GameObject target = existing != null ? existing.gameObject
                : new GameObject(name, typeof(RectTransform), typeof(CanvasRenderer), typeof(Image));
            if (existing == null)
                target.transform.SetParent(parent, false);
            return target;
        }

        private static void StretchImage(Image image, Sprite sprite)
        {
            image.sprite = sprite;
            image.type = Image.Type.Simple;
            image.preserveAspect = false;
            image.color = Color.white;
            image.raycastTarget = false;
            RectTransform rect = image.rectTransform;
            rect.anchorMin = Vector2.zero;
            rect.anchorMax = Vector2.one;
            rect.offsetMin = Vector2.zero;
            rect.offsetMax = Vector2.zero;
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
            SetRect(scene, "PlayerPortrait", new Vector2(-560f, -265f), new Vector2(260f, 260f));
            SetRect(scene, "MonsterPortrait", new Vector2(560f, -225f), new Vector2(340f, 340f));
            SetActive(scene, "DamageDebugPanel", false);
            SetActive(scene, "DebugFantasyConsole", false);
        }

        private static void SetActive(Scene scene, string objectName, bool active)
        {
            GameObject target = FindInScene(scene, objectName);
            if (target == null)
                return;
            target.SetActive(active);
            EditorUtility.SetDirty(target);
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
