using System.Collections.Generic;
using TMPro;
using UnityEditor.Analytics;
using UnityEngine;

public class MatchManager : MonoBehaviour
{
    public GameObject matchstickPrefab;
    public GameObject matchSlotPrefab;

    private List<Transform> slots = new List<Transform>();
    public List<DigitManager> digitManagers = new List<DigitManager>();
    public TextMeshProUGUI text = null;
    public Transform selectedMatch = null;


    void Awake()
    {
        foreach(DigitManager digitManager in digitManagers){
            for(int i = 0; i < 7; ++i)
            {
                slots.Add(digitManager.transform.GetChild(i));
            }
        }
    }

    private void OnEnable()
    {
        SetNumber(GameManager.instance.ChangedNumber);
    }

    private void OnDisable()
    {
        GameManager.instance.ChangedNumber = GetNumber();
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

    void Update()
    {
        text.text = this.GetNumber().ToString();
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
