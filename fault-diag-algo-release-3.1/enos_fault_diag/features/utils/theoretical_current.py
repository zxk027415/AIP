import numpy as np


def get_theoretical_current(temp, irra, pmp):
    """
    calculate theoretical current according to temperature, irradiance and pmp0
    :parameter
        temp: float
            effective temperature
        irra: float
            effective irradiance
        pmp: float
            optimal current
    :return:
        theo_cur:
            theoretical current
    """
    if np.isnan(temp):
        temp = 25

    T0 = 25  # reference temperature
    E0 = 1000  # reference effective irradiance(1000w/m2)
    gama = -0.4 * 0.01  # temperature correction

    if irra > 125:
        current = irra / E0 * pmp * (1 + gama * (temp - T0))
    else:
        current = irra / E0 * pmp
    return current


def add_theoretical_current(data, pmp_field, irra_field, temp_field):
    """
    A temporary function to add theoretical current to data
    """
    df = data.copy()
    df['i_cal'] = df.apply(
        lambda x: get_theoretical_current(
            x[temp_field], x[irra_field], x[pmp_field]), axis=1)
    df.drop([pmp_field, irra_field, temp_field], axis=1, inplace=True)
    return df
