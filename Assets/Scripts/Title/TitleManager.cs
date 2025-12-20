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
        SceneManager.LoadScene("Map");
    }

    public void OnOption()
    {
        OptionAnim.SetTrigger("Up");
    }

    public void OnExit()
    {
        Application.Quit();
    }

    public void OnDone()
    {
        OptionAnim.SetTrigger("Down");
    }
}
