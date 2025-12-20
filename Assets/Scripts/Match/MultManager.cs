using UnityEngine;
using System.Collections.Generic;

public class MultManager : MonoBehaviour
{
    public GameObject matchstickPrefab;
    public MatchManager matchManager;

    public int[] slotState = {0,0,0,0,0,0,0};

    private string[] properStrs = new string[] {
        "11", // * 
        "01", // /
    };
    public void SetNumber(int digit)
    {
        if(digit < 0 || digit > 9)
            return;
        
        for(int i = 0; i < 7; i++)
        {
            SetMatchstick(i, properStrs[digit][i] == '1' ? 1 : 0);
        }
    }

    public void SetSlots(List<int> state)
    {
        for(int i = 0; i < 7; i++)
        {
            SetMatchstick(i, state[i]);
        }
    }

    private void SetMatchstick(int slotNo, int state)
    {
        Transform slot = transform.GetChild(slotNo);

        if(slot.childCount > 0)
            Destroy( slot.GetChild(0).gameObject );

        if(state == 1)
        {
            GameObject matchstick = Instantiate(matchstickPrefab);
            matchstick.GetComponent<Matchstick>().matchManager = matchManager;

            matchstick.transform.SetParent(slot);
            matchstick.transform.SetPositionAndRotation(slot.position, slot.rotation);
        }
        
        slotState[slotNo] = state;
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
