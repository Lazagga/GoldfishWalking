using System;
using UnityEngine;

[CreateAssetMenu(fileName = "PlayerRunData", menuName = "GoldfishWalking/PlayerRunData")]
public class PlayerRunData : ScriptableObject
{
    [Header("Stats")]
    public int health = 80;
    public int maxHealth = 80;
    public int maxMoveCount = 2;
    public bool isBuffed = false;

    public event Action<int> OnHealthChanged;
    public event Action<int> OnMaxMoveCountChanged;

    public void ChangeHealth(int delta)
    {
        health = Mathf.Clamp(health + delta, 0, maxHealth);
        OnHealthChanged?.Invoke(health);
    }

    public void AddMaxMoveCount()
    {
        maxMoveCount++;
        OnMaxMoveCountChanged?.Invoke(maxMoveCount);
    }

    public void ResetForNewRun()
    {
        health = maxHealth;
        maxMoveCount = 2;
        isBuffed = false;
    }
}
