import numpy as np
import pytest

from simcore.link.modulation import MODULATIONS, bit_error_rate, bits_per_symbol, required_ebn0_db


@pytest.mark.parametrize(
    "modulation, expected_db",
    [
        ("bpsk", 9.59),  # classic textbook value at 1e-5
        ("qpsk", 9.59),
        ("bfsk_coherent", 12.60),
        ("bfsk_noncoherent", 13.35),  # 2 ln(5e4)
    ],
)
def test_required_ebn0_at_1e5(modulation, expected_db):
    assert required_ebn0_db(modulation, 1e-5) == pytest.approx(expected_db, abs=0.01)


def test_noncoherent_fsk_closed_form():
    ebn0 = 2 * np.log(0.5 / 1e-5)
    assert required_ebn0_db("bfsk_noncoherent", 1e-5) == pytest.approx(10 * np.log10(ebn0), abs=1e-4)


@pytest.mark.parametrize("modulation", sorted(MODULATIONS))
def test_ber_monotonic_and_inverse_consistent(modulation):
    x = np.linspace(-5, 20, 200)
    ber = bit_error_rate(modulation, x)
    assert np.all(np.diff(ber) < 0)
    for target in (1e-3, 1e-6, 1e-12):
        assert bit_error_rate(modulation, required_ebn0_db(modulation, target)) == pytest.approx(target, rel=1e-4)


def test_ordering_of_power_efficiency():
    # More robust modulations need less Eb/N0.
    req = {m: required_ebn0_db(m, 1e-5) for m in MODULATIONS}
    assert req["bpsk"] < req["gmsk"] < req["bfsk_coherent"] < req["8psk"] < req["bfsk_noncoherent"]


def test_bits_per_symbol():
    assert [bits_per_symbol(m) for m in ("bpsk", "qpsk", "8psk")] == [1, 2, 3]
