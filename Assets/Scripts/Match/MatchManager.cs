using System.Collections.Generic;
using TMPro;
using UnityEngine;

public class MatchManager : MonoBehaviour
{
    public GameObject matchstickPrefab;
    private List<Transform> slots = new();
    public List<int> slotStateOriginal = new();

    public int usedMoveInThisPanel = 0;

    public Transform digitManagersContainer;
    private List<DigitManager> digitManagers = new();
    public TextMeshProUGUI text = null;
    public Transform selectedMatch = null;

    private void Awake()
    {
        for (int i = 0; i < digitManagersContainer.childCount; i++)
            digitManagers.Add(digitManagersContainer.GetChild(i).GetComponent<DigitManager>());

        foreach (var dm in digitManagers)
            for (int i = 0; i < 7; i++)
                slots.Add(dm.transform.GetChild(i));
    }

    public void Init(int num)
    {
        SetNumber(num);
        if (slotStateOriginal.Count == 0)
            SaveCurrentState();
    }

    public void SaveCurrentState()
    {
        foreach (var dm in digitManagers)
            slotStateOriginal.AddRange(dm.slotState);
    }

    public void Reset()
    {
        slotStateOriginal.Clear();
        usedMoveInThisPanel = 0;
        if (gameObject.activeInHierarchy)
            SaveCurrentState();
    }

    private void Update()
    {
        if (text != null)
            text.text = GetNumber().ToString();
    }

    public void UpdateState()
    {
        usedMoveInThisPanel = 0;

        for (int i = 0; i < slots.Count; i++)
        {
            if (slots[i].childCount > 0 && slotStateOriginal.Count > i && slotStateOriginal[i] == 0)
                usedMoveInThisPanel++;
        }

        GameEvents.MatchMoved(); // GameManager.instance 직접 호출 제거
    }

    public Transform GetNearestSlot(Vector3 pos)
    {
        Transform bestSlot = null;
        float bestDist = float.MaxValue;

        foreach (var slot in slots)
        {
            if (slot.childCount >= 1) continue;

            float distSq = (pos - slot.position).sqrMagnitude;
            if (distSq > 3000f || bestDist < distSq) continue;

            bestSlot = slot;
            bestDist = distSq;
        }

        return bestSlot;
    }

    public void SetNumber(int num)
    {
        for (int i = digitManagers.Count - 1; i >= 0; i--)
        {
            digitManagers[i].SetNumber(num % 10);
            num /= 10;
        }
    }

    public int GetNumber()
    {
        int res = 0;
        foreach (var dm in digitManagers)
        {
            int digit = dm.GetNumber();
            if (digit < 0) return -1;
            res = res * 10 + digit;
        }
        return res;
    }
}
