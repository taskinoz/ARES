"""Rotation helpers shared by the Respawn model readers (from r2-model-compiler)."""
import math


def matrix_angles(m):
    fwd = (m[0][0], m[1][0], m[2][0])
    left = (m[0][1], m[1][1], m[2][1])
    xy = math.sqrt(fwd[0] ** 2 + fwd[1] ** 2)
    if xy > 1e-10:
        yaw = math.atan2(fwd[1], fwd[0])
        pitch = math.atan2(-fwd[2], xy)
        roll = math.atan2(left[2], m[2][2])
    else:
        yaw = math.atan2(-left[0], left[1])
        pitch = math.atan2(-fwd[2], xy)
        roll = 0.0
    return (roll, pitch, yaw)


def quat_matrix(q):
    x, y, z, w = q
    m = [[0.0] * 4 for _ in range(3)]
    m[0][0] = 1 - 2 * y * y - 2 * z * z
    m[1][0] = 2 * x * y + 2 * w * z
    m[2][0] = 2 * x * z - 2 * w * y
    m[0][1] = 2 * x * y - 2 * w * z
    m[1][1] = 1 - 2 * x * x - 2 * z * z
    m[2][1] = 2 * y * z + 2 * w * x
    m[0][2] = 2 * x * z + 2 * w * y
    m[1][2] = 2 * y * z - 2 * w * x
    m[2][2] = 1 - 2 * x * x - 2 * y * y
    return m


def unpack_q64(v):
    x = ((v & 0x1FFFFF) - 1048576) * (1 / 1048576.5)
    y = (((v >> 21) & 0x1FFFFF) - 1048576) * (1 / 1048576.5)
    z = (((v >> 42) & 0x1FFFFF) - 1048576) * (1 / 1048576.5)
    d = 1 - (x * x + y * y + z * z)
    w = math.sqrt(d) if d > 0 else 0.0
    if v >> 63:
        w = -w
    return (x, y, z, w)
