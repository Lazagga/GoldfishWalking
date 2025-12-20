using System;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.Rendering;

public class DigitManager : MonoBehaviour
{
    public GameObject matchstickPrefab;
    public MatchManager matchManager;

    private string[] properStrs = new string[] {
        "1111110", // 0 
        "0110000", // 1
        "1101101", // 2
        "1111001", // 3
        "0110011", // 4
        "1011011", // 5
        "1011111", // 6
        "1110000", // 7
        "1111111", // 8
        "1111011"  // 9
    };
    
    public void SetNumber(int digit)
    {
        if(digit < 0 || digit > 9)
            return;
        
        for(int i = 0; i < 7; i++)
        {
            Transform slot = transform.GetChild(i);

            if(properStrs[digit][i] == '1' && slot.childCount == 0)
            {
                GameObject matchstick = Instantiate(matchstickPrefab);
                matchstick.GetComponent<Matchstick>().matchManager = matchManager;

                matchstick.transform.SetParent(slot);
                matchstick.transform.SetPositionAndRotation(slot.position, slot.rotation);
            }
            else if(properStrs[digit][i] == '0' && slot.childCount == 1)
            {
                Destroy( slot.GetChild(0).gameObject );
            }
        }
    }

    public int GetNumber()
    {
        string hasMatch = "";

        for(int i = 0; i < 7; i++)
        {
            hasMatch += transform.GetChild(i).childCount>=1 ? "1": "0";
        }

        for(int i = 0; i<10; ++i)
        {
            if(hasMatch.Equals(properStrs[i]))
                return i;
        }

        return -1;
    }
}
