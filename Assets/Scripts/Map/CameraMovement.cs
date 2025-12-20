using System;
using UnityEngine;

public class CameraMovement : MonoBehaviour
{
    [Header("Lerp Settings")]
    public float lerpSpeed = 6f;
    public float stopThreshold = 0.01f;

    [Header("Z")]
    public float fixedZ = -10f;

    private Vector3 targetPos;
    private bool hasTarget;

    private Action onArrived;

    public bool IsMoving => hasTarget;

    private void Awake()
    {
        var p = transform.position;
        targetPos = new Vector3(p.x, p.y, fixedZ);
        transform.position = targetPos;
        hasTarget = false;
    }

    private void LateUpdate()
    {
        if (!hasTarget) return;

        transform.position = Vector3.Lerp(
            transform.position,
            targetPos,
            Time.deltaTime * lerpSpeed
        );

        if (Vector3.Distance(transform.position, targetPos) < stopThreshold)
        {
            transform.position = targetPos;
            hasTarget = false;

            var cb = onArrived;
            onArrived = null;
            cb?.Invoke();
        }
    }

    public void MoveTo(Vector3 worldPos, Action onArrived = null)
    {
        targetPos = new Vector3(worldPos.x, worldPos.y, fixedZ);
        hasTarget = true;
        this.onArrived = onArrived;
    }
}
