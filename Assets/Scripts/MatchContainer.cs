using NUnit.Framework;
using UnityEngine;
using UnityEngine.Rendering;

public class MatchContainer : MonoBehaviour
{
    public int getNum()
    {
        string hasMatch = "";
        string[] properStrs = new string[] {
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
