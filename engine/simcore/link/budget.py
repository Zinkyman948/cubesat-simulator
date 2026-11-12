"""Link budget evaluation.

`LinkModel` holds the geometry-independent parts of a link (EIRP, G/T,
required Eb/N0) and evaluates the geometry-dependent parts over arrays of
range, range-rate and elevation.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from simcore.link import modulation
from simcore.link.antenna import peak_gain_dbi
from simcore.link.rf import (
    BOLTZMANN_DBW,
    C_LIGHT_KM_S,
    atmospheric_path_factor,
    db,
    doppler_shift_hz,
    free_space_path_loss_db,
    system_noise_temperature_k,
)
from simcore.scenario.models import LinkConfig, Receiver


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
    # Spacecraft-side antenna: gain toward the station and angle from its axis.
    sc_antenna_gain_dbi: np.ndarray
    sc_antenna_angle_deg: np.ndarray

    def to_dict(self) -> dict:
        return {k: np.asarray(v).tolist() for k, v in self.__dict__.items()}


def receiver_noise_temperature_k(rx: Receiver) -> float:
    if rx.system_noise_temp_k is not None:
        return rx.system_noise_temp_k
    return system_noise_temperature_k(rx.antenna_noise_temp_k, rx.noise_figure_db, rx.line_loss_db)


class LinkModel:
    def __init__(self, config: LinkConfig):
        self.config = config
        f = config.frequency_hz
        tx, rx = config.transmitter, config.receiver

        # Peak gains; the spacecraft side varies with attitude (see evaluate).
        self.tx_antenna_gain_dbi = peak_gain_dbi(tx.antenna, f)
        self.rx_antenna_gain_dbi = peak_gain_dbi(rx.antenna, f)
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

    def evaluate(
        self,
        range_km,
        range_rate_km_s,
        elevation_rad,
        sc_gain_dbi=None,
        sc_angle_deg=None,
    ) -> LinkSamples:
        """Link quantities over arrays of geometry.

        `sc_gain_dbi` is the spacecraft antenna's gain toward the station at
        each epoch (from attitude and pattern); without it the peak gain is used.
        """
        cfg = self.config
        range_km = np.asarray(range_km, dtype=float)
        path_loss = free_space_path_loss_db(range_km, cfg.frequency_hz)
        atm_loss = cfg.losses.atmospheric_zenith_db * atmospheric_path_factor(elevation_rad)

        downlink = cfg.direction == "downlink"
        sc_peak = self.tx_antenna_gain_dbi if downlink else self.rx_antenna_gain_dbi
        sc_gain = np.broadcast_to(sc_peak if sc_gain_dbi is None else sc_gain_dbi, range_km.shape)
        tx_gain = sc_gain if downlink else self.tx_antenna_gain_dbi
        rx_gain = self.rx_antenna_gain_dbi if downlink else sc_gain
        eirp = self.eirp_dbw - self.tx_antenna_gain_dbi + tx_gain

        received_dbw = eirp - path_loss - atm_loss - self.fixed_losses_db + rx_gain
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
            sc_antenna_gain_dbi=np.array(sc_gain, dtype=float),
            sc_antenna_angle_deg=np.broadcast_to(
                np.nan if sc_angle_deg is None else sc_angle_deg, range_km.shape
            ).astype(float),
        )
