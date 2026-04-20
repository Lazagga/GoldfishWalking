using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

public class TitleManager : MonoBehaviour
{
    public Slider volumeSlider;
    public Animator OptionAnim;

    private void Update()
    {
        AudioManager.instance.VolumeControl(volumeSlider.value);
    }

    public void OnStart()
    {
        SceneManager.LoadScene("Game"); // "Map" 씬 제거 → 단일 "Game" 씬으로
    }

    public void OnOption()
    {
        OptionAnim.SetTrigger("Up");
    }

    public void OnDone()
    {
        OptionAnim.SetTrigger("Down");
    }

    public void OnExit()
    {
        Application.Quit();
    }
}
