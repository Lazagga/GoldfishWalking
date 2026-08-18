using System;
using System.Collections.Generic;
using System.Linq;
using GoldfishWalking.Data;
using UnityEditor;
using UnityEngine;

namespace GoldfishWalking.Editor
{
    public static class UiAtlasAssetBuilder
    {
        public const string AtlasPath = "Assets/Art/ui/20260707_ui.png";
        public const string SkinPath = "Assets/Art/Generated/UI/UiSkinData.asset";

        [MenuItem("GoldfishWalking/Art/Rebuild UI Atlas")]
        public static void RebuildMenu()
        {
            List<string> errors = new List<string>();
            Build(errors);
            foreach (string error in errors)
                Debug.LogError(error);
            if (errors.Count == 0)
                Debug.Log("UI 아틀라스 8종 분할 및 UiSkinData 생성을 완료했습니다.");
        }

        public static UiSkinData Build(List<string> errors)
        {
            Texture2D texture = AssetDatabase.LoadAssetAtPath<Texture2D>(AtlasPath);
            TextureImporter importer = AssetImporter.GetAtPath(AtlasPath) as TextureImporter;
            if (texture == null || importer == null)
            {
                errors.Add($"UI 아틀라스를 찾을 수 없습니다: {AtlasPath}");
                return null;
            }
            if (texture.width != 160 || texture.height != 64)
            {
                errors.Add($"UI 아틀라스 크기는 160x64여야 합니다. 현재: {texture.width}x{texture.height}");
                return null;
            }

            SpriteMetaData[] sprites =
            {
                Sprite("UI_Next", 0, 48, 16, 16),
                Sprite("UI_Reset", 16, 48, 16, 16),
                Sprite("UI_Close", 32, 48, 16, 16),
                Sprite("UI_TextPanel", 12, 12, 56, 24, new Vector4(5, 5, 5, 5)),
                Sprite("UI_ButtonSingle", 96, 0, 16, 16, new Vector4(4, 4, 4, 4)),
                Sprite("UI_ButtonLeft", 112, 0, 16, 16, new Vector4(4, 4, 4, 4)),
                Sprite("UI_ButtonMiddle", 128, 0, 16, 16, new Vector4(4, 4, 4, 4)),
                Sprite("UI_ButtonRight", 144, 0, 16, 16, new Vector4(4, 4, 4, 4))
            };

            importer.textureType = TextureImporterType.Sprite;
            importer.spriteImportMode = SpriteImportMode.Multiple;
            importer.spritePixelsPerUnit = 16;
            importer.alphaIsTransparency = true;
            importer.mipmapEnabled = false;
            importer.filterMode = FilterMode.Point;
            importer.wrapMode = TextureWrapMode.Clamp;
            importer.textureCompression = TextureImporterCompression.Uncompressed;
#pragma warning disable 0618
            importer.spritesheet = sprites;
#pragma warning restore 0618
            importer.SaveAndReimport();

            Dictionary<string, Sprite> byName = AssetDatabase.LoadAllAssetsAtPath(AtlasPath)
                .OfType<Sprite>()
                .ToDictionary(sprite => sprite.name, StringComparer.Ordinal);
            if (byName.Count != 8)
            {
                errors.Add($"UI 아틀라스에서 8개 대신 {byName.Count}개의 Sprite가 생성됐습니다.");
                return null;
            }

            EnsureFolder("Assets/Art/Generated/UI");
            UiSkinData skin = AssetDatabase.LoadAssetAtPath<UiSkinData>(SkinPath);
            if (skin == null)
            {
                skin = ScriptableObject.CreateInstance<UiSkinData>();
                AssetDatabase.CreateAsset(skin, SkinPath);
            }
            skin.nextButton = byName["UI_Next"];
            skin.resetButton = byName["UI_Reset"];
            skin.closeButton = byName["UI_Close"];
            skin.textPanel = byName["UI_TextPanel"];
            skin.singleButton = byName["UI_ButtonSingle"];
            skin.connectedLeftButton = byName["UI_ButtonLeft"];
            skin.connectedMiddleButton = byName["UI_ButtonMiddle"];
            skin.connectedRightButton = byName["UI_ButtonRight"];
            EditorUtility.SetDirty(skin);
            AssetDatabase.SaveAssets();
            return skin;
        }

        private static SpriteMetaData Sprite(string name, float x, float y, float width, float height, Vector4 border = default)
        {
            return new SpriteMetaData
            {
                name = name,
                rect = new Rect(x, y, width, height),
                alignment = (int)SpriteAlignment.Center,
                pivot = new Vector2(0.5f, 0.5f),
                border = border
            };
        }

        private static void EnsureFolder(string path)
        {
            string current = "Assets";
            foreach (string part in path.Split('/').Skip(1))
            {
                string next = $"{current}/{part}";
                if (!AssetDatabase.IsValidFolder(next))
                    AssetDatabase.CreateFolder(current, part);
                current = next;
            }
        }
    }
}
