"""cuStateVec execution path — NVIDIA's purpose-built statevector kernels.

The CuPy path in `qaoa_core` is real GPU code: the statevector lives in device
memory and every operation is a CUDA kernel. But it applies gates with generic
array machinery — a stride reshape plus arithmetic that materialises two
half-width temporaries per gate. cuStateVec applies the same gate with kernels
written for exactly this access pattern, in place, with no temporaries.

Both halves of a QAOA layer map onto cuStateVec primitives:

  * **Cost unitary** exp(-i γ H_C). H_C is diagonal, so this is a diagonal
    matrix over all n qubits — `applyGeneralizedPermutationMatrix` with a NULL
    permutation and our phase vector as the diagonal.
  * **Mixer** RX(2β) on each qubit — `applyMatrix`, one 2x2 per qubit.

This module is a thin, explicit wrapper. It deliberately does not hide failure:
if cuStateVec is unavailable or errors, `open_context()` returns None and the
caller keeps the CuPy path, but nothing silently claims a cuStateVec run that
did not happen — `active` is what the UI reports.
"""

from __future__ import annotations

from typing import Any

import numpy as np


class CuStateVecContext:
    """Owns a cuStateVec handle and applies QAOA operators through it.

    One handle per process is the intended usage; creating one per call is
    expensive. Use `open_context()` rather than constructing directly.
    """

    def __init__(self, n_qubits: int) -> None:
        import cuquantum
        from cuquantum.bindings import custatevec as cusv

        self._cusv = cusv
        self.n_qubits = int(n_qubits)
        self.handle = cusv.create()
        self.active = True
        self.gate_calls = 0

        # cudaDataType lives at the cuquantum top level, NOT on the custatevec
        # bindings module — it moved there by 26.6. ComputeType and MatrixLayout
        # remain on the bindings module.
        self._C64 = cuquantum.cudaDataType.CUDA_C_64F
        self._COMPUTE = cusv.ComputeType.COMPUTE_64F
        self._ROW = cusv.MatrixLayout.ROW

    # ── Operators ────────────────────────────────────────────────────────────

    def apply_matrix_1q(self, sv: Any, target: int, matrix: list) -> None:
        """Apply a 2x2 matrix to `target`, in place, on the device.

        `matrix` is row-major [m00, m01, m10, m11]. Kept on the host: it is 64
        bytes, and cuStateVec accepts a host pointer for the operator.
        """
        m = np.asarray(matrix, dtype=np.complex128).reshape(2, 2)
        self._cusv.apply_matrix(
            self.handle, sv.data.ptr, self._C64, self.n_qubits,
            m.ctypes.data, self._C64, self._ROW,
            0,                      # adjoint
            [int(target)], 1,       # targets
            [], [], 0,              # controls
            self._COMPUTE,
            0, 0,                   # workspace (none needed for 1-qubit)
        )
        self.gate_calls += 1

    def apply_diagonal(self, sv: Any, phases: Any) -> None:
        """Apply a full-width diagonal unitary held in device memory.

        `phases` is a length-2^n complex128 CuPy array — exp(-i γ H(x)) for every
        basis state. Passing a NULL permutation makes this a pure diagonal
        multiply executed by cuStateVec rather than by CuPy broadcasting.
        """
        self._cusv.apply_generalized_permutation_matrix(
            self.handle, sv.data.ptr, self._C64, self.n_qubits,
            0,                                   # permutation = NULL (identity)
            phases.data.ptr, self._C64,
            0,                                   # adjoint
            list(range(self.n_qubits)), self.n_qubits,
            [], [], 0,                           # controls
            0, 0,                                # workspace
        )
        self.gate_calls += 1

    # ── Lifecycle ────────────────────────────────────────────────────────────

    def close(self) -> None:
        if getattr(self, "active", False):
            try:
                self._cusv.destroy(self.handle)
            finally:
                self.active = False

    def __enter__(self) -> CuStateVecContext:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:  # noqa: S110 - a destructor must never raise
            pass


def open_context(n_qubits: int) -> CuStateVecContext | None:
    """Return a working context, or None if cuStateVec cannot be used here.

    Returning None rather than raising is deliberate: the CuPy path is a correct
    fallback, and a missing accelerator should degrade performance, not
    availability. The caller reports which path actually ran.
    """
    try:
        return CuStateVecContext(n_qubits)
    except Exception:
        return None


def probe() -> dict:
    """Report whether cuStateVec is importable and functional on this machine.

    Actually creates and destroys a handle — importability alone does not prove
    the library will run, and this is the value the UI displays.
    """
    info: dict[str, Any] = {"available": False, "version": None, "detail": ""}
    try:
        import cuquantum
        from cuquantum.bindings import custatevec as cusv

        info["version"] = getattr(cuquantum, "__version__", "unknown")
        h = cusv.create()
        cusv.destroy(h)
        info["available"] = True
        info["detail"] = f"cuStateVec {info['version']} — handle created and destroyed"
    except Exception as exc:
        info["detail"] = f"{type(exc).__name__}: {exc}"
    return info
