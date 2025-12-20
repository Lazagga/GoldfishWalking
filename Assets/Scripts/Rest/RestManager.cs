using UnityEngine;
using UnityEngine.SceneManagement;

public class RestManager : MonoBehaviour
{
    public void OnDone()
    {
        //fade
        SceneManager.LoadScene("Map");
    }
}
