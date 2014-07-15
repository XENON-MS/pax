"""
This sets up variables for the various unit abbreviations, ensuring we always
have a 'consistent' unit system.
You can change base_units without breaking the consistency of any physical
relations

Please change comments in this code if you change any units. Better yet, don't
change any units!

WARNING
    The unit system is not fully consistent, since the unit for energy is set
    separately from mass, time, and distance
    If you do mechanics this is a SERIOUSLY BAD IDEA
    We, however, only ever need mass for density
"""
import math

electron_charge_SI = 1.60217657 * 10 ** (-19)
boltzmannConstant_SI = 1.3806488 * 10 ** (-23)
base_units = {
    'm': 10 ** 2,  # distances in cm
    's': 10 ** 9,  # times in ns
    'eV': 1,  # energies in eV
    # charge in number of electrons (so voltage will be in Volts)
    'C': 1 / electron_charge_SI,
    'g': 1,  # masses in grams... please see comment above!
    'K': 1,  # Temperature in Kelvins
}
base_units['Hz'] = 1 / base_units['s']
base_units['J'] = base_units['eV'] / electron_charge_SI
base_units['V'] = base_units['J'] / base_units['C']
# Current will be in electrons/ns!
base_units['A'] = base_units['C'] / base_units['s']
base_units['Ohm'] = base_units['V'] / base_units['A']  # Resistance in eV/ns
electron_charge = electron_charge_SI * base_units['C']
boltzmannConstant = boltzmannConstant_SI * base_units['J'] / base_units['K']

prefixes = {'': 0, 'n': -9, 'u': -6, 'm': -3, 'c': -2, 'k': 3, 'M': 6, 'G': 9}

for (name, value) in list(base_units.items()):
    for (p_name, p_factor) in list(prefixes.items()):
        # Float makes sure units might work even for poor fellas who forget to
        # from __future__ import division -- not tested though
        vars()[p_name + name] = float(10 ** (p_factor) * value)


def unit_name(unit, base_unit):
    """
    Hack to get unit name back
    unit_name(ns,'s') will give 'ns'
    """
    power = int(math.log10(unit / base_units[base_unit]))
    for p_name, p_factor in list(prefixes.items()):
        if p_factor == power:
            return p_name + base_unit