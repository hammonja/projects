"""
Air transmission tables, 2.000–12.000 µm, binned to 20 nm.

Creates separate curves for:
- H2O-only transmission
- CO2-only transmission
- Total (H2O + CO2) transmission

Conditions (editable below):
- T = 20 °C
- P = 1 atm
- RH = 55% (typical UK indoor)
- Path length = 1.0 m
- CO2 = 420 ppm

Output:
- air_trans_2to12um_20nm_components.csv
  columns: wavelength_center_nm, trans_total, trans_h2o, trans_co2

Requires:
  py -m pip install hitran-api numpy

Notes:
- Wide spectral range means bigger HITRAN downloads (first run) and more compute.
- Transmittance is a fraction 0..1 (multiply by 100 for %).
"""

import numpy as np
from math import exp
from hapi import *

# -----------------------
# USER SETTINGS
# -----------------------
T = 293.15          # K (20 C)
P_atm = 1.0         # atm
path_m = 1.0        # m
RH = 0.55           # 55% RH (typical indoor)

CO2_PPM = 420.0     # ppm

# Spectral range (microns)
LAMBDA_MIN_UM = 2.0
LAMBDA_MAX_UM = 12.0

# High-res wavenumber grid for line-by-line (cm^-1)
# If runtime is heavy, increase this (e.g., 0.05 or 0.1) then re-bin to 20 nm.
NU_STEP = 0.01

# Output bin width (nm)
BIN_NM = 20.0

# Cache folder for HITRAN line data
DB_FOLDER = "hitran_cache"

# Output file
OUT_CSV = "air_trans_2to12um_20nm_components.csv"

# -----------------------
# HELPERS
# -----------------------
def esat_buck_pa(Tc: float) -> float:
    """
    Buck equation (1981) saturation vapour pressure over water.
    Input: Tc in degC
    Output: Pa
    """
    return 100.0 * 6.1121 * exp((18.678 - Tc / 234.5) * (Tc / (257.14 + Tc)))

def ppm_to_mole_fraction(ppm: float) -> float:
    return ppm * 1e-6

def wavenumber_range_from_lambda_um(lmin_um: float, lmax_um: float):
    """
    lambda (um) -> nu (cm^-1): nu = 1e4 / lambda_um
    Return (nu_min, nu_max) with nu_min < nu_max.
    """
    nu_max = 1e4 / lmin_um
    nu_min = 1e4 / lmax_um
    return nu_min, nu_max

# -----------------------
# ENVIRONMENT / MIXING RATIOS
# -----------------------
Tc = T - 273.15
p_sat = esat_buck_pa(Tc)                 # Pa
p_total = P_atm * 101325.0               # Pa
p_h2o = RH * p_sat                       # Pa
x_h2o = p_h2o / p_total                  # mole fraction

x_co2 = ppm_to_mole_fraction(CO2_PPM)
x_rest = 1.0 - (x_h2o + x_co2)
if x_rest <= 0:
    raise ValueError("Gas mole fractions sum to >= 1. Adjust RH/CO2 settings.")

print("---- Gas conditions ----")
print(f"T = {T:.2f} K ({Tc:.1f} C), P = {P_atm:.3f} atm, path = {path_m:.3f} m")
print(f"RH = {RH*100:.1f}%  -> p_sat={p_sat:.1f} Pa, p_H2O={p_h2o:.1f} Pa, x_H2O={x_h2o:.6f}")
print(f"CO2 = {CO2_PPM:.1f} ppm -> x_CO2={x_co2:.8f}")
print("------------------------\n")

# Number density (molecules/cm^3) for scaling if needed
kB = 1.380649e-23  # J/K
n_m3 = p_total / (kB * T)     # molecules/m^3
n_cm3 = n_m3 / 1e6            # molecules/cm^3
L_cm = path_m * 100.0

print(f"Number density: n = {n_cm3:.3e} molecules/cm^3")
print("------------------------\n")

# -----------------------
# SPECTRAL SETUP
# -----------------------
nu_min, nu_max = wavenumber_range_from_lambda_um(LAMBDA_MIN_UM, LAMBDA_MAX_UM)
print(f"Spectral range: {LAMBDA_MIN_UM:.3f}–{LAMBDA_MAX_UM:.3f} µm  ->  {nu_min:.3f}–{nu_max:.3f} cm^-1")
print(f"Wavenumber step: {NU_STEP} cm^-1\n")

# -----------------------
# HITRAN / HAPI SETUP
# -----------------------
db_begin(DB_FOLDER)

# HITRAN molecule IDs:
# 1 = H2O, 2 = CO2
print("Fetching HITRAN lines (first run downloads; subsequent runs use cache)...")
fetch("H2O", 1, 1, nu_min, nu_max)
fetch("CO2", 2, 1, nu_min, nu_max)

def absorption_for(table_name: str):
    nu, coef = absorptionCoefficient_Voigt(
        SourceTables=table_name,
        Environment={"T": T, "p": P_atm},
        WavenumberStep=NU_STEP,
        WavenumberRange=(nu_min, nu_max),
    )
    return np.array(nu), np.array(coef)

nu_grid, coef_h2o = absorption_for("H2O")
nu2,     coef_co2 = absorption_for("CO2")

# Sanity: grids should match
if len(nu2) != len(nu_grid) or np.nanmax(np.abs(nu2 - nu_grid)) > 1e-9:
    raise RuntimeError("H2O and CO2 wavenumber grids do not match; check NU_STEP/range.")

# -----------------------
# SCALE TO TRANSMISSION (separate curves + total)
# -----------------------
print("---- Diagnostics ----")
peak_h2o = float(np.nanmax(coef_h2o))
peak_co2 = float(np.nanmax(coef_co2))
print(f"coef_h2o peak = {peak_h2o:.3e}")
print(f"coef_co2 peak = {peak_co2:.3e}")

# Decide unit interpretation once and apply consistently to all components
# If coefficients are tiny, treat as cross-section-like and scale by number density
use_number_density = (max(peak_h2o, peak_co2) < 1e-6)

if use_number_density:
    print("Interpreting HAPI output as cross-section-like (cm^2/molecule). Scaling by number density.")
    tau_h2o = (x_h2o * coef_h2o) * n_cm3 * L_cm
    tau_co2 = (x_co2 * coef_co2) * n_cm3 * L_cm
else:
    print("Interpreting HAPI output as absorption coefficient (cm^-1). Using tau = coef * path.")
    tau_h2o = (x_h2o * coef_h2o) * L_cm
    tau_co2 = (x_co2 * coef_co2) * L_cm

tau_total = tau_h2o + tau_co2

trans_h2o = np.exp(-tau_h2o)
trans_co2 = np.exp(-tau_co2)
trans_total = np.exp(-tau_total)

print(f"tau_total peak = {float(np.nanmax(tau_total)):.3e}")
print(f"trans_total min/max = {float(np.nanmin(trans_total)):.12f} / {float(np.nanmax(trans_total)):.12f}")
print("---------------------\n")

# -----------------------
# CONVERT TO WAVELENGTH AND BIN TO 20 nm
# -----------------------
# lambda (nm) = 1e7 / nu(cm^-1)
lam_nm = 1e7 / nu_grid

# Sort by wavelength ascending
order = np.argsort(lam_nm)
lam_sorted = lam_nm[order]
t_total_sorted = trans_total[order]
t_h2o_sorted = trans_h2o[order]
t_co2_sorted = trans_co2[order]

# Define 20 nm bins from 2000 to 12000 nm
edges = np.arange(LAMBDA_MIN_UM * 1000.0, LAMBDA_MAX_UM * 1000.0 + BIN_NM, BIN_NM)

rows = []
for a, b in zip(edges[:-1], edges[1:]):
    m = (lam_sorted >= a) & (lam_sorted < b)
    center = 0.5 * (a + b)
    if np.any(m):
        rows.append(
            (center,
             float(np.mean(t_total_sorted[m])),
             float(np.mean(t_h2o_sorted[m])),
             float(np.mean(t_co2_sorted[m])))
        )
    else:
        rows.append((center, float("nan"), float("nan"), float("nan")))

# Write CSV
with open(OUT_CSV, "w", encoding="utf-8") as f:
    f.write("wavelength_center_nm,trans_total,trans_h2o,trans_co2\n")
    for w, tt, th, tc in rows:
        f.write(f"{w:.1f},{tt:.12f},{th:.12f},{tc:.12f}\n")

print(f"Wrote: {OUT_CSV}")
print("Done.")
