"""Bit error rate of common CubeSat modulations in AWGN (uncoded)."""

from __future__ import annotations

import numpy as np
from scipy.optimize import brentq
from scipy.special import erfc


def q_function(x):
    return 0.5 * erfc(np.asarray(x) / np.sqrt(2.0))


def _bpsk(ebn0):
    return q_function(np.sqrt(2.0 * ebn0))


def _8psk(ebn0):
    # Gray-coded nearest-neighbour approximation.
    return (2.0 / 3.0) * q_function(np.sqrt(6.0 * ebn0) * np.sin(np.pi / 8.0))


def _bfsk_coherent(ebn0):
    return q_function(np.sqrt(ebn0))


def _bfsk_noncoherent(ebn0):
    return 0.5 * np.exp(-ebn0 / 2.0)


def _gmsk(ebn0):
    # Murota & Hirade approximation for BT = 0.25 (alpha = 0.68). Slightly
    # pessimistic for the BT = 0.5 common on amateur-band CubeSats.
    return q_function(np.sqrt(2.0 * 0.68 * ebn0))


# name -> (BER(Eb/N0 linear), bits per symbol)
MODULATIONS = {
    "bpsk": (_bpsk, 1),
    "qpsk": (_bpsk, 2),  # Gray-coded QPSK has the same BER as BPSK
    "8psk": (_8psk, 3),
    "bfsk_coherent": (_bfsk_coherent, 1),
    "bfsk_noncoherent": (_bfsk_noncoherent, 1),
    "gmsk": (_gmsk, 1),
}


def bit_error_rate(modulation: str, ebn0_db):
    ber, _ = MODULATIONS[modulation]
    return ber(10.0 ** (np.asarray(ebn0_db) / 10.0))


def bits_per_symbol(modulation: str) -> int:
    return MODULATIONS[modulation][1]


def required_ebn0_db(modulation: str, target_ber: float) -> float:
    """Uncoded Eb/N0 (dB) at which the modulation reaches `target_ber`.

    The search bracket stops at 25 dB, where every supported curve is still
    far above float underflow; any target_ber >= 1e-12 is reached well before.
    """
    return brentq(lambda x: np.log(bit_error_rate(modulation, x) / target_ber), -10.0, 25.0, xtol=1e-6)
