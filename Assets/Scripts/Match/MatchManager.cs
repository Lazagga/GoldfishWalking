using System;
using System.Collections.Generic;
using TMPro;
using UnityEngine;

public class MatchManager : MonoBehaviour
{
    public GameObject matchstickPrefab;
    private List<Transform> slots = new List<Transform>();
    public List<int> slotStateOriginal = new List<int>();

    public int usedMoveInThisPanel = 0;

    public Transform digitManagersContainer;
    private List<DigitManager> digitManagers = new List<DigitManager>();
    public TextMeshProUGUI text = null;
    public Transform selectedMatch = null;


    void Awake()
    {
        for(int i = 0; i < digitManagersContainer.childCount; i++)
        {
            digitManagers.Add(digitManagersContainer.GetChild(i).GetComponent<DigitManager>());
        }

        foreach(DigitManager digitManager in digitManagers){
            for(int i = 0; i < 7; ++i)
            {
                slots.Add(digitManager.transform.GetChild(i));
            }
        }
    }

    public void Init(int num)
    {
        SetNumber(num);
        if (slotStateOriginal.Count == 0)
        {
            SaveCurrentState();
        }
    }

    public void SaveCurrentState()
    {
        foreach(DigitManager digitManager in digitManagers){
            slotStateOriginal.AddRange(digitManager.slotState);
        }
    }

    public void Reset()
    {
        slotStateOriginal.Clear();
        usedMoveInThisPanel = 0;
        if (gameObject.activeInHierarchy)
        {
            SaveCurrentState();
        }
    }

    
    
    void Update()
    {
        text.text = GetNumber().ToString();
    }

    public void UpdateState()
    {
        List<int> hasMatchIndexes = new List<int>();

        for(int i=0; i<slots.Count; i++)
        {
            if( slots[i].childCount > 0 )
                hasMatchIndexes.Add(i);
        }

        usedMoveInThisPanel = 0;
        foreach(int i in hasMatchIndexes)
        {
            if( slotStateOriginal[i] == 0 )
            {
                usedMoveInThisPanel++;
            }
        }
        GameManager.instance.UpdateMoveCount();
    }

    public Transform GetNearestSlot(Vector3 pos)
    {
        Transform bestSlot = null;
        float bestDist = float.MaxValue;

        foreach(Transform slot in slots)
        {
            if(slot.childCount >= 1) continue; // 이미 다른 성냥이 들어가있으면 skip

            float distSq = (pos - slot.position).sqrMagnitude;
            
            if(distSq > 3000f || bestDist < distSq) continue;
            
            bestSlot = slot;
            bestDist = distSq;
        }

        return bestSlot;
    }

    public void SetNumber(int num)
    {
        for (int i = digitManagers.Count - 1; i >= 0; i--){
            digitManagers[i].SetNumber(num % 10);
            num /= 10;
        }
    }

    public int GetNumber()
    {
        int res = 0;

        foreach(DigitManager digitManager in digitManagers){
            int digit = digitManager.GetNumber();
            if(digit < 0) {
                res = -1;
                break;
            }
            res = res * 10 + digit;
        }

        return res;
    }
}
