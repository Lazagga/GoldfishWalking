using UnityEditor;
using UnityEngine;

namespace GoldfishWalking.Editor
{
    public sealed class PixelArtTexturePostprocessor : AssetPostprocessor
    {
        private void OnPreprocessTexture()
        {
            bool isArt = assetPath.StartsWith("Assets/Art/", System.StringComparison.OrdinalIgnoreCase);
            bool isMatch = assetPath.Equals("Assets/Image/Match.png", System.StringComparison.OrdinalIgnoreCase);
            if (!isArt && !isMatch)
                return;

            TextureImporter importer = (TextureImporter)assetImporter;
            importer.alphaIsTransparency = true;
            importer.mipmapEnabled = false;
            importer.filterMode = FilterMode.Point;
            importer.wrapMode = TextureWrapMode.Clamp;
            importer.textureCompression = TextureImporterCompression.Uncompressed;
        }
    }
}
