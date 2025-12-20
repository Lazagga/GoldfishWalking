using System.Collections;
using UnityEngine;

public class StageManager : MonoBehaviour
{
    public int PlayerNum, EnemyNum, EnemyTimes;
    public int PlayerScore, EnemyScore, TimesScore;
    public GameObject PlayerBoard, EnemyBoard, TimesBoard;

    public int PlayerHP, EnemyHP;

    public GameObject CautionMessage;

    public GameObject Player, Enemy;
    private Animator PlayerAnim, EnemyAnim;

    void Start()
    {
        PlayerAnim = Player.GetComponent<Animator>();
        EnemyAnim = Enemy.GetComponent<Animator>();
        Stage();

        PlayerBoard.SetActive(false);
        EnemyBoard.SetActive(false);
        TimesBoard.SetActive(false);
    }

    // Update is called once per frame
    void Update()
    {
        
    }

    public void Stage()
    {
        PlayerNum = Random.Range(10, 99);
        EnemyNum = Random.Range(10, 99);
        EnemyTimes = Random.Range(1, 9);

        PlayerBoard.GetComponent<DigitsManager>().SetDigits(PlayerNum);
        EnemyBoard.GetComponent<DigitsManager>().SetDigits(EnemyNum);
        TimesBoard.GetComponent<DigitsManager>().SetDigits(EnemyTimes);
    }

    public void ResetDigits()
    {
        PlayerBoard.GetComponent<DigitsManager>().SetDigits(PlayerNum);
        EnemyBoard.GetComponent<DigitsManager>().SetDigits(EnemyNum);
        TimesBoard.GetComponent<DigitsManager>().SetDigits(EnemyTimes);
    }

    public void ClosePlayerBoard()
    {
        PlayerScore = PlayerBoard.GetComponent<DigitsManager>().GetNumber();
        if (PlayerScore < 0)
        {
            //Caution Message
            return;
        }
        PlayerBoard.SetActive(false);
    }

    public void CloseEnemyBoard()
    {
        EnemyScore = EnemyBoard.GetComponent<DigitsManager>().GetNumber();
        if (EnemyScore < 0)
        {
            //Caution Message
            return;
        }
        EnemyBoard.SetActive(false);
    }

    public void CloseTimesBoard()
    {
        TimesScore = TimesBoard.GetComponent<DigitsManager>().GetNumber();
        if (TimesScore < 0)
        {
            //Caution Message
            return;
        }
        TimesBoard.SetActive(false);
    }

    public void EndPhase()
    {
        StartCoroutine(Fight());
    }

    public IEnumerator Fight()
    {
        PlayerAnim.SetTrigger("Attack");
        yield return new WaitForSeconds(1.0f);
        EnemyAnim.SetTrigger("Damage");
        EnemyHP -= PlayerScore;
        yield return new WaitForSeconds(1.0f);

        if (EnemyHP < 0)
        {
            PlayerWin();
            yield break;
        }

        yield return new WaitForSeconds(2.0f);
        EnemyAnim.SetTrigger("Attack");
        yield return new WaitForSeconds(1.0f);
        PlayerAnim.SetTrigger("Damage");
        PlayerHP -= EnemyScore * EnemyTimes;
    }

    public void PlayerWin()
    {
        //show reward
    }
}
