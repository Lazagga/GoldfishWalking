using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;
using UnityEngine.UI;

namespace GoldfishWalking.Editor
{
    public static class PlayerArtAssetBuilder
    {
        private const string SourceRoot = "Assets/Art/player";
        private const string OutputRoot = "Assets/Art/Generated/Player";
        public const string ControllerPath = OutputRoot + "/Player.controller";

        public static (Sprite sprite, RuntimeAnimatorController controller) Build()
        {
            EnsureFolder(OutputRoot);
            for (int index = 0; index < 7; index++)
                ConfigureTexture($"{SourceRoot}/mainchar_idle_{index:D4}.png");
            for (int index = 0; index < 6; index++)
                ConfigureTexture($"{SourceRoot}/mainchar_attack_{index:D4}.png");
            Sprite[] idleFrames = Enumerable.Range(0, 7)
                .Select(index => LoadSprite($"{SourceRoot}/mainchar_idle_{index:D4}.png"))
                .Where(sprite => sprite != null)
                .ToArray();
            if (idleFrames.Length != 7)
                throw new InvalidOperationException($"mainchar idle 프레임은 7개여야 합니다. 현재: {idleFrames.Length}");

            AnimationClip idle = CreateOrUpdateClip(OutputRoot + "/Player_Idle.anim", idleFrames, 8f);
            AnimatorController controller = AssetDatabase.LoadAssetAtPath<AnimatorController>(ControllerPath);
            if (controller == null)
                controller = AnimatorController.CreateAnimatorControllerAtPath(ControllerPath);
            AnimatorStateMachine machine = controller.layers[0].stateMachine;
            AnimatorState state = machine.states.Select(item => item.state).FirstOrDefault(item => item.name == "Idle")
                                  ?? machine.AddState("Idle");
            state.motion = idle;
            machine.defaultState = state;
            EditorUtility.SetDirty(controller);
            AssetDatabase.SaveAssets();
            return (idleFrames[0], controller);
        }

        private static Sprite LoadSprite(string path)
        {
            return AssetDatabase.LoadAssetAtPath<Sprite>(path);
        }

        private static void ConfigureTexture(string path)
        {
            TextureImporter importer = AssetImporter.GetAtPath(path) as TextureImporter;
            if (importer == null)
                throw new InvalidOperationException($"플레이어 이미지를 가져올 수 없습니다: {path}");
            importer.textureType = TextureImporterType.Sprite;
            importer.spriteImportMode = SpriteImportMode.Single;
            importer.spritePixelsPerUnit = 32f;
            importer.spritePivot = new Vector2(0.5f, 0.5f);
            importer.alphaIsTransparency = true;
            importer.mipmapEnabled = false;
            importer.filterMode = FilterMode.Point;
            importer.wrapMode = TextureWrapMode.Clamp;
            importer.textureCompression = TextureImporterCompression.Uncompressed;
            importer.SaveAndReimport();
        }

        private static AnimationClip CreateOrUpdateClip(string path, Sprite[] frames, float fps)
        {
            AnimationClip clip = AssetDatabase.LoadAssetAtPath<AnimationClip>(path);
            if (clip == null)
            {
                clip = new AnimationClip();
                AssetDatabase.CreateAsset(clip, path);
            }
            clip.name = Path.GetFileNameWithoutExtension(path);
            clip.frameRate = fps;
            EditorCurveBinding binding = new EditorCurveBinding { path = string.Empty, type = typeof(Image), propertyName = "m_Sprite" };
            ObjectReferenceKeyframe[] keys = frames.Select((frame, index) => new ObjectReferenceKeyframe
            {
                time = index / fps,
                value = frame
            }).ToArray();
            AnimationUtility.SetObjectReferenceCurve(clip, binding, keys);
            SerializedObject serializedClip = new SerializedObject(clip);
            SerializedProperty loopTime = serializedClip.FindProperty("m_AnimationClipSettings.m_LoopTime");
            if (loopTime != null)
                loopTime.boolValue = true;
            serializedClip.ApplyModifiedPropertiesWithoutUndo();
            EditorUtility.SetDirty(clip);
            return clip;
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
