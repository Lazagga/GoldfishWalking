using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using GoldfishWalking.Data;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;
using UnityEngine.UI;

namespace GoldfishWalking.Editor.DataImport
{
    public static class MonsterArtAssetBuilder
    {
        private const string EnemyArtRoot = "Assets/Art/enemy";
        private const string GeneratedEnemyRoot = "Assets/Art/Generated/Enemies";
        private const string GeneratedShopRoot = "Assets/Art/Generated/Shop";

        [MenuItem("GoldfishWalking/Art/Rebuild Pixel Art Animations")]
        public static void RebuildFromDatabase()
        {
            MonsterDatabase database = AssetDatabase.LoadAssetAtPath<MonsterDatabase>("Assets/Data/Generated/MonsterDatabase.asset");
            if (database == null)
            {
                Debug.LogError("MonsterDatabase.asset이 없습니다. 먼저 Gameplay JSON을 가져오세요.");
                return;
            }

            List<string> errors = new List<string>();
            List<string> warnings = new List<string>();
            Build(database.monsters, errors, warnings);
            EditorUtility.SetDirty(database);
            AssetDatabase.SaveAssets();
            foreach (string warning in warnings)
                Debug.LogWarning(warning);
            foreach (string error in errors)
                Debug.LogError(error);
            Debug.Log($"픽셀 아트 애니메이션 생성 완료: 몬스터 {database.monsters.Count}종, 오류 {errors.Count}개");
        }

        public static void Build(IReadOnlyList<MonsterData> monsters, List<string> errors, List<string> warnings)
        {
            EnsureFolder(GeneratedEnemyRoot);
            EnsureFolder(GeneratedShopRoot);
            UiAtlasAssetBuilder.Build(errors);

            foreach (MonsterData monster in monsters)
            {
                monster.portraitSprite = null;
                monster.phasePortraitSprites = Array.Empty<Sprite>();
                monster.portraitAnimatorController = null;
                if (string.IsNullOrWhiteSpace(monster.sprite))
                    continue;

                string texturePath = ResolveEnemyTexture(monster.sprite);
                if (string.IsNullOrEmpty(texturePath))
                {
                    errors.Add($"[{monster.id}] presentation.sprite에 해당하는 이미지가 없습니다: {monster.sprite}");
                    continue;
                }

                int cellSize = monster.grade == MonsterGrade.Boss ? 64 : monster.grade == MonsterGrade.Elite ? 48 : 32;
                Sprite[] frames = SliceAndLoad(texturePath, cellSize, errors);
                if (frames.Length == 0)
                    continue;

                if (monster.spritePhaseCount > 0)
                {
                    int phaseCount = Mathf.Clamp(monster.spritePhaseCount, 1, frames.Length);
                    if (phaseCount != monster.spritePhaseCount)
                        warnings.Add($"[{monster.id}] phaseSprites {monster.spritePhaseCount}를 실제 스프라이트 수 {frames.Length}에 맞췄습니다.");
                    monster.phasePortraitSprites = frames.Take(phaseCount).ToArray();
                    monster.portraitSprite = monster.phasePortraitSprites[0];
                    continue;
                }

                int frameCount = Mathf.Clamp(monster.spriteIdleFrames, 1, frames.Length);
                if (frameCount != monster.spriteIdleFrames)
                    warnings.Add($"[{monster.id}] idleFrames {monster.spriteIdleFrames}를 실제 프레임 수 {frames.Length}에 맞췄습니다.");
                Sprite[] idleFrames = frames.Take(frameCount).ToArray();
                string safeName = SanitizeFileName(monster.id);
                AnimationClip clip = CreateOrUpdateClip($"{GeneratedEnemyRoot}/{safeName}_Idle.anim", idleFrames, monster.spriteFramesPerSecond);
                AnimatorController controller = CreateOrUpdateController($"{GeneratedEnemyRoot}/{safeName}.controller", clip);
                monster.portraitSprite = idleFrames[0];
                monster.portraitAnimatorController = controller;
            }

            BuildShopkeeper(errors);
        }

        private static void BuildShopkeeper(List<string> errors)
        {
            const string texturePath = "Assets/Art/shop/shopkeeper.png";
            if (AssetDatabase.LoadAssetAtPath<Texture2D>(texturePath) == null)
            {
                errors.Add($"상점 주인 이미지가 없습니다: {texturePath}");
                return;
            }

            Sprite[] frames = SliceAndLoad(texturePath, 64, errors).Take(6).ToArray();
            if (frames.Length == 0)
                return;
            AnimationClip clip = CreateOrUpdateClip($"{GeneratedShopRoot}/Shopkeeper_Idle.anim", frames, 4f);
            CreateOrUpdateController($"{GeneratedShopRoot}/Shopkeeper.controller", clip);
        }

        private static string ResolveEnemyTexture(string authoredPath)
        {
            string stem = Path.GetFileNameWithoutExtension(authoredPath.Replace('\\', '/'));
            string directPath = $"{EnemyArtRoot}/{stem}.png";
            if (AssetDatabase.LoadAssetAtPath<Texture2D>(directPath) != null)
                return directPath;

            string[] matches = AssetDatabase.FindAssets($"{stem} t:Texture2D", new[] { EnemyArtRoot });
            return matches.Length == 1 ? AssetDatabase.GUIDToAssetPath(matches[0]) : string.Empty;
        }

        private static Sprite[] SliceAndLoad(string texturePath, int cellSize, List<string> errors)
        {
            Texture2D texture = AssetDatabase.LoadAssetAtPath<Texture2D>(texturePath);
            TextureImporter importer = AssetImporter.GetAtPath(texturePath) as TextureImporter;
            if (texture == null || importer == null)
            {
                errors.Add($"텍스처를 가져올 수 없습니다: {texturePath}");
                return Array.Empty<Sprite>();
            }
            if (texture.width % cellSize != 0 || texture.height % cellSize != 0)
            {
                errors.Add($"{texturePath}: 이미지 크기 {texture.width}x{texture.height}가 셀 크기 {cellSize}로 나누어지지 않습니다.");
                return Array.Empty<Sprite>();
            }

            string stem = Path.GetFileNameWithoutExtension(texturePath);
            int columns = texture.width / cellSize;
            int rows = texture.height / cellSize;
            List<SpriteMetaData> metadata = new List<SpriteMetaData>(columns * rows);
            for (int rowFromTop = 0; rowFromTop < rows; rowFromTop++)
            for (int column = 0; column < columns; column++)
            {
                int index = rowFromTop * columns + column;
                metadata.Add(new SpriteMetaData
                {
                    name = $"{stem}_{index:D2}",
                    rect = new Rect(column * cellSize, texture.height - ((rowFromTop + 1) * cellSize), cellSize, cellSize),
                    alignment = (int)SpriteAlignment.Center,
                    pivot = new Vector2(0.5f, 0.5f)
                });
            }

            importer.textureType = TextureImporterType.Sprite;
            importer.spriteImportMode = SpriteImportMode.Multiple;
            importer.spritePixelsPerUnit = cellSize;
            importer.alphaIsTransparency = true;
            importer.mipmapEnabled = false;
            importer.filterMode = FilterMode.Point;
            importer.wrapMode = TextureWrapMode.Clamp;
            importer.textureCompression = TextureImporterCompression.Uncompressed;
#pragma warning disable 0618
            importer.spritesheet = metadata.ToArray();
#pragma warning restore 0618
            importer.SaveAndReimport();

            return AssetDatabase.LoadAllAssetsAtPath(texturePath)
                .OfType<Sprite>()
                .OrderBy(sprite => sprite.name, StringComparer.Ordinal)
                .ToArray();
        }

        private static AnimationClip CreateOrUpdateClip(string path, IReadOnlyList<Sprite> frames, float framesPerSecond)
        {
            AnimationClip clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(path);
            if (clip == null)
            {
                clip = new AnimationClip();
                AssetDatabase.CreateAsset(clip, path);
            }
            clip.name = Path.GetFileNameWithoutExtension(path);
            clip.frameRate = Mathf.Max(1f, framesPerSecond);
            EditorCurveBinding binding = new EditorCurveBinding
            {
                path = string.Empty,
                type = typeof(Image),
                propertyName = "m_Sprite"
            };
            ObjectReferenceKeyframe[] keys = new ObjectReferenceKeyframe[frames.Count];
            for (int i = 0; i < frames.Count; i++)
                keys[i] = new ObjectReferenceKeyframe { time = i / clip.frameRate, value = frames[i] };
            AnimationUtility.SetObjectReferenceCurve(clip, binding, keys);
            SerializedObject serializedClip = new SerializedObject(clip);
            SerializedProperty loopTime = serializedClip.FindProperty("m_AnimationClipSettings.m_LoopTime");
            if (loopTime != null)
                loopTime.boolValue = frames.Count > 1;
            serializedClip.ApplyModifiedPropertiesWithoutUndo();
            EditorUtility.SetDirty(clip);
            return clip;
        }

        private static AnimatorController CreateOrUpdateController(string path, AnimationClip clip)
        {
            AnimatorController controller = AssetDatabase.LoadAssetAtPath<AnimatorController>(path);
            if (controller == null)
                controller = AnimatorController.CreateAnimatorControllerAtPath(path);
            AnimatorStateMachine stateMachine = controller.layers[0].stateMachine;
            AnimatorState state = stateMachine.states.Select(item => item.state).FirstOrDefault(item => item.name == "Idle");
            if (state == null)
                state = stateMachine.AddState("Idle");
            state.motion = clip;
            stateMachine.defaultState = state;
            EditorUtility.SetDirty(controller);
            return controller;
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

        private static string SanitizeFileName(string value)
        {
            foreach (char invalid in Path.GetInvalidFileNameChars())
                value = value.Replace(invalid, '_');
            return value;
        }
    }
}
