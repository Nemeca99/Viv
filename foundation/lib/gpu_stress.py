"""GPU compute + VRAM stress via OpenCL — RTX 3060 Ti class workloads."""
from __future__ import annotations

import multiprocessing as mp
import os
import time
from enum import Enum

import numpy as np


class GpuStressMode(str, Enum):
    NORMAL = "normal"
    EXTREME = "extreme"
    RTX = "rtx"  # heavy FP32 path-tracing-style compute


def _find_nvidia_gpu():
    import pyopencl as cl

    for plat in cl.get_platforms():
        for dev in plat.get_devices(device_type=cl.device_type.GPU):
            name = dev.name.upper()
            if "NVIDIA" in name or "GEFORCE" in name or "RTX" in name:
                return dev
    for plat in cl.get_platforms():
        gpus = plat.get_devices(device_type=cl.device_type.GPU)
        if gpus:
            return gpus[0]
    return None


def _opencl_burn(mode: GpuStressMode = GpuStressMode.NORMAL) -> None:
    import pyopencl as cl

    gpu_dev = _find_nvidia_gpu()
    if gpu_dev is None:
        raise SystemExit("No OpenCL GPU found")
    ctx = cl.Context([gpu_dev])
    queue = cl.CommandQueue(ctx)

    if mode == GpuStressMode.RTX:
        n_rays = int(os.environ.get("VIV_GPU_RT_RAYS", "65536"))
        n_bounce = int(os.environ.get("VIV_GPU_RT_BOUNCES", "8"))
        buf = np.random.randn(n_rays, 4).astype(np.float32)
        gpu_buf = cl.Buffer(ctx, cl.mem_flags.READ_WRITE | cl.mem_flags.COPY_HOST_PTR, hostbuf=buf)
        prg = cl.Program(
            ctx,
            f"""
            __kernel void path_trace(__global float4* rays, const int bounces) {{
                int i = get_global_id(0);
                float4 r = rays[i];
                float x = r.x, y = r.y, z = r.z, t = r.w;
                for (int b = 0; b < bounces; b++) {{
                    float len = sqrt(x*x + y*y + z*z + 1e-6f);
                    x /= len; y /= len; z /= len;
                    float nx = sin(x * 12.9898f + y * 78.233f + t) * 43758.5453f;
                    nx = nx - floor(nx);
                    x += nx * 0.01f; y += cos(nx * 6.28f) * 0.01f;
                    z += sin(nx * 3.14f) * 0.01f;
                    t += x*y + z*z;
                }}
                rays[i] = (float4)(x, y, z, t);
            }}
            """,
        ).build()
        kernel = cl.Kernel(prg, "path_trace")
        bounce_arg = np.int32(n_bounce)
        while True:
            kernel(queue, (n_rays,), None, gpu_buf, bounce_arg)
            queue.finish()
        return

    n = 4096 if mode == GpuStressMode.EXTREME else 2048
    a = np.random.randn(n, n).astype(np.float32)
    b = np.random.randn(n, n).astype(np.float32)
    a_buf = cl.Buffer(ctx, cl.mem_flags.READ_ONLY | cl.mem_flags.COPY_HOST_PTR, hostbuf=a)
    b_buf = cl.Buffer(ctx, cl.mem_flags.READ_ONLY | cl.mem_flags.COPY_HOST_PTR, hostbuf=b)
    c_buf = cl.Buffer(ctx, cl.mem_flags.WRITE_ONLY, a.nbytes)
    prg = cl.Program(
        ctx,
        """
        __kernel void mm(const int N, __global float* A, __global float* B, __global float* C) {
            int row = get_global_id(0);
            int col = get_global_id(1);
            if (row >= N || col >= N) return;
            float sum = 0.0f;
            for (int k = 0; k < N; k++)
                sum += A[row*N+k] * B[k*N+col];
            C[row*N+col] = sum;
        }
        """,
    ).build()
    while True:
        prg.mm(queue, (n, n), None, np.int32(n), a_buf, b_buf, c_buf)
        queue.finish()


def _vram_apocalypse(aggressive: bool = False) -> None:
    import pyopencl as cl

    gpu_dev = _find_nvidia_gpu()
    if gpu_dev is None:
        return
    ctx = cl.Context([gpu_dev])
    holder: list[cl.Buffer] = []
    chunk = 128 * 1024 * 1024 if aggressive else 64 * 1024 * 1024
    batch = 24 if aggressive else 16
    while True:
        try:
            for _ in range(batch):
                holder.append(cl.Buffer(ctx, cl.mem_flags.READ_WRITE, chunk))
        except (cl.MemoryError, cl.RuntimeError):
            if len(holder) > 32:
                holder = holder[-16:]
        time.sleep(0.01 if aggressive else 0.02)


def launch_gpu_stress(
    mode: str | GpuStressMode = GpuStressMode.NORMAL,
    *,
    burn_procs: int | None = None,
) -> list[mp.Process]:
    m = GpuStressMode(mode) if isinstance(mode, str) else mode
    aggressive = m in (GpuStressMode.EXTREME, GpuStressMode.RTX)
    n_burn = burn_procs
    if n_burn is None:
        n_burn = 3 if m == GpuStressMode.RTX else (2 if m == GpuStressMode.EXTREME else 2)
    procs: list[mp.Process] = []
    for _ in range(n_burn):
        p = mp.Process(target=_opencl_burn, args=(m,), daemon=True)
        p.start()
        procs.append(p)
    mp.Process(target=_vram_apocalypse, args=(aggressive,), daemon=True).start()
    return procs


def stop_gpu_stress(procs: list[mp.Process]) -> None:
    for p in procs:
        p.terminate()
    for p in procs:
        p.join(timeout=3.0)
