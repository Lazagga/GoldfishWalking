using System.Collections.Generic;
using TMPro;
using UnityEditor.Analytics;
using UnityEngine;

public class MatchManager : MonoBehaviour
{
    private static MatchManager instance = null;
    public static MatchManager Instance
    {
        get
        {
            if (null == instance)
            {
                return null;
            }
            return instance;
        }
    }

    public GameObject matchstickPrefab;
    public GameObject matchSlotPrefab;

    private List<Transform> slots = new List<Transform>();
    private MatchContainer sevenSeg = null;
    public TextMeshProUGUI text = null;
    public Transform selectedMatch = null;


    void Awake()
    {
        if(instance == null)
        {
            instance = this;
        }
        else
        {
            Destroy(this.gameObject);
        }

        sevenSeg = transform.GetChild(0).GetComponent<MatchContainer>();
        for(int i = 0; i < 7; ++i)
        {
            slots.Add(sevenSeg.transform.GetChild(i));
        }
    }


    public Transform getNearestSlot(Vector3 pos)
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
        text.text = sevenSeg.getNum().ToString();
    }

    public int GetNumber()
    {
        return sevenSeg.getNum();
    }
}
