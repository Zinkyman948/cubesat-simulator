"""Link budget evaluation.

`LinkModel` holds the geometry-independent parts of a link (EIRP, G/T,
required Eb/N0) and evaluates the geometry-dependent parts over arrays of
range, range-rate and elevation.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from simcore.link import modulation
from simcore.link.rf import (
    BOLTZMANN_DBW,
    C_LIGHT_KM_S,
    atmospheric_path_factor,
    db,
    dish_gain_dbi,
    doppler_shift_hz,
    free_space_path_loss_db,
    system_noise_temperature_k,
)
from simcore.scenario.models import Antenna, LinkConfig, Receiver


@dataclass
class LinkSamples:
    """Link quantities over a set of epochs (all arrays share one shape)."""

    elevation_deg: np.ndarray
    range_km: np.ndarray
    range_rate_km_s: np.ndarray
    delay_ms: np.ndarray
    doppler_hz: np.ndarray
    path_loss_db: np.ndarray
    atmospheric_loss_db: np.ndarray
    received_power_dbm: np.ndarray
    cn0_dbhz: np.ndarray
    esn0_db: np.ndarray
    ebn0_db: np.ndarray
    margin_db: np.ndarray
    ber: np.ndarray

    def to_dict(self) -> dict:
        return {k: np.asarray(v).tolist() for k, v in self.__dict__.items()}


def antenna_gain_dbi(antenna: Antenna, frequency_hz: float) -> float:
    if antenna.gain_dbi is not None:
        return antenna.gain_dbi
    return float(dish_gain_dbi(antenna.dish_diameter_m, antenna.dish_efficiency, frequency_hz))


def receiver_noise_temperature_k(rx: Receiver) -> float:
    if rx.system_noise_temp_k is not None:
        return rx.system_noise_temp_k
    return system_noise_temperature_k(rx.antenna_noise_temp_k, rx.noise_figure_db, rx.line_loss_db)


class LinkModel:
    def __init__(self, config: LinkConfig):
        self.config = config
        f = config.frequency_hz
        tx, rx = config.transmitter, config.receiver

        self.tx_antenna_gain_dbi = antenna_gain_dbi(tx.antenna, f)
        self.rx_antenna_gain_dbi = antenna_gain_dbi(rx.antenna, f)
        self.eirp_dbw = float(db(tx.power_w)) - tx.line_loss_db + self.tx_antenna_gain_dbi
        self.system_noise_temp_k = receiver_noise_temperature_k(rx)
        self.g_over_t_dbk = self.rx_antenna_gain_dbi - float(db(self.system_noise_temp_k))

        bits = modulation.bits_per_symbol(config.modulation)
        self.symbol_rate_baud = config.data_rate_bps / (config.coding.rate * bits)
        self.uncoded_required_ebn0_db = modulation.required_ebn0_db(config.modulation, config.target_ber)
        self.required_ebn0_db = self.uncoded_required_ebn0_db - config.coding.gain_db

    @property
    def fixed_losses_db(self) -> float:
        losses = self.config.losses
        return losses.polarization_db + losses.pointing_db

    def evaluate(self, range_km, range_rate_km_s, elevation_rad) -> LinkSamples:
        cfg = self.config
        range_km = np.asarray(range_km, dtype=float)
        path_loss = free_space_path_loss_db(range_km, cfg.frequency_hz)
        atm_loss = cfg.losses.atmospheric_zenith_db * atmospheric_path_factor(elevation_rad)

        received_dbw = self.eirp_dbw - path_loss - atm_loss - self.fixed_losses_db + self.rx_antenna_gain_dbi
        cn0 = received_dbw - BOLTZMANN_DBW - db(self.system_noise_temp_k)
        # Implementation loss degrades the effective SNR seen by the demodulator.
        ebn0 = cn0 - db(cfg.data_rate_bps) - cfg.losses.implementation_db
        esn0 = ebn0 + db(cfg.data_rate_bps / self.symbol_rate_baud)
        # Approximate the coded BER curve as the uncoded one shifted by the coding gain.
        ber = modulation.bit_error_rate(cfg.modulation, ebn0 + cfg.coding.gain_db)

        return LinkSamples(
            elevation_deg=np.degrees(elevation_rad),
            range_km=range_km,
            range_rate_km_s=np.asarray(range_rate_km_s, dtype=float),
            delay_ms=range_km / C_LIGHT_KM_S * 1000.0,
            doppler_hz=doppler_shift_hz(range_rate_km_s, cfg.frequency_hz),
            path_loss_db=path_loss,
            atmospheric_loss_db=atm_loss,
            received_power_dbm=received_dbw + 30.0,
            cn0_dbhz=cn0,
            esn0_db=esn0,
            ebn0_db=ebn0,
            margin_db=ebn0 - self.required_ebn0_db,
            ber=ber,
        )
