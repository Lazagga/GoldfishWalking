using System.Collections.Generic;
using System.ComponentModel;
using UnityEngine;

public class SmallMatchpanel : MonoBehaviour
{
    public Transform digitsContainer;
    private List<DigitManager> digitManagers = new List<DigitManager>();

    void Awake()
    {
        for(int i = 0; i<digitsContainer.childCount; i++)
        {
            digitManagers.Add(digitsContainer.GetChild(i).GetComponent<DigitManager>());
        }
    }

    public void SetNumber(int num)
    {
        for (int i = digitManagers.Count - 1; i >= 0; i--){
            digitManagers[i].SetNumber(num % 10);
            num /= 10;
        }
    }
}
