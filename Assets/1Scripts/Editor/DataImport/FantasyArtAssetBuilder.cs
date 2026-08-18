using System;
using System.Collections.Generic;
using System.Linq;
using GoldfishWalking.Data;
using UnityEditor;
using UnityEngine;

namespace GoldfishWalking.Editor.DataImport
{
    internal static class FantasyArtAssetBuilder
    {
        private const string AtlasPath = "Assets/Art/fantasy/fantasies.png";
        private const int CellSize = 16;
        private const int FantasyCount = 69;

        public static void Build(List<FantasyData> fantasies, List<string> errors, List<string> warnings)
        {
            AssetDatabase.Refresh();
            TextureImporter importer = AssetImporter.GetAtPath(AtlasPath) as TextureImporter;
            Texture2D texture = AssetDatabase.LoadAssetAtPath<Texture2D>(AtlasPath);
            if (importer == null || texture == null)
            {
                errors.Add($"Fantasy atlas not found: {AtlasPath}");
                return;
            }

            int columns = texture.width / CellSize;
            List<SpriteMetaData> metadata = new List<SpriteMetaData>(FantasyCount);
            for (int index = 0; index < FantasyCount; index++)
            {
                int column = index % columns;
                int rowFromTop = index / columns;
                metadata.Add(new SpriteMetaData
                {
                    name = $"fantasy_{index + 1:000}",
                    rect = new Rect(column * CellSize, texture.height - (rowFromTop + 1) * CellSize, CellSize, CellSize),
                    alignment = (int)SpriteAlignment.Center,
                    pivot = new Vector2(0.5f, 0.5f)
                });
            }

            importer.textureType = TextureImporterType.Sprite;
            importer.spriteImportMode = SpriteImportMode.Multiple;
            importer.spritePixelsPerUnit = CellSize;
            importer.filterMode = FilterMode.Point;
            importer.textureCompression = TextureImporterCompression.Uncompressed;
            importer.mipmapEnabled = false;
            importer.alphaIsTransparency = true;
#pragma warning disable CS0618
            importer.spritesheet = metadata.ToArray();
#pragma warning restore CS0618
            importer.SaveAndReimport();

            Sprite[] sprites = AssetDatabase.LoadAllAssetsAtPath(AtlasPath).OfType<Sprite>()
                .OrderBy(sprite => sprite.name, StringComparer.Ordinal)
                .ToArray();
            List<FantasyData> ordered = fantasies.OrderBy(fantasy => fantasy.sourceId)
                .ThenBy(fantasy => fantasy.id, StringComparer.Ordinal)
                .ToList();
            if (ordered.Count != FantasyCount)
                warnings.Add($"Fantasy atlas contains {FantasyCount} icons but imported fantasy count is {ordered.Count}.");

            int count = Mathf.Min(ordered.Count, sprites.Length);
            for (int i = 0; i < count; i++)
                ordered[i].iconSprite = sprites[i];
        }
    }
}
