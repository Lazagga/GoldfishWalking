using Unity.VisualScripting;
using UnityEngine;
using UnityEngine.UI;

public class Match : MonoBehaviour
{
    private Image Source;
    public int Filled;

    void Awake()
    {
        Source = GetComponent<Image>();
    }

    public void Setting(int num)
    {
        Filled = num;
        if (num == 1) Source.sprite = GameManager.instance.MatchImage;
        if (num == 0) Source.sprite = GameManager.instance.EmptyImage;
    }

    public void OnMouseDown()
    {
        if (Filled == 1 && !GameManager.instance.Match)
        {
            if(GameManager.instance.MoveCount == 0)
            {
                //Caution Message
                return;
            }
            Source.sprite = GameManager.instance.EmptyImage;
            GameManager.instance.Match = true;
        }
        else if (Filled == 0 && GameManager.instance.Match)
        {
            Source.sprite = GameManager.instance.MatchImage;
            GameManager.instance.Match = false;
            GameManager.instance.MoveCount--;
        }
    }
}
