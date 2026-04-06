# Copyright (C) 2024-2026 Kenes Yerassyl
# This file is part of Ziyatron EEG Annotator.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.


from dataclasses import dataclass


@dataclass()
class Config:
    app_name: str = "Annotate"
    # diagnosis options
    diagnosis = [
        'AR',
        'BR',
        'TR',
        'DR',
        'MR',
        'AOR',
        'DSR',
        'PHS',
        'SHW',
        'SPW',
        'GED',
        'LED',
        'EYBL',
        'ARTF',
        'BCKG',
        'SEIZ',
        'FNSZ',
        'GNSZ',
        'SPSZ',
        'CPSZ',
        'ABSZ',
        'TNSZ',
        'CNSZ',
        'TCSZ',
        'ATSZ',
        'MYSZ',
        'NESZ',
        'INTR',
        'SLOW',
        'KCOMP',
        'SLPSP',
        'VERX',
        'EYEM',
        'CHEW',
        'SHIV',
        'MUSC',
        'EMA',
        'ELST',
        'CALB',
        'HPHS',
        'TRIP',
        '6SP',
        'HYPHYP',
        'EMA',
        'NDAR',
        'ASSA',
        'BSSA',
        'TSSA',
        'DSSA',
        'IFCN',
    ]
    pan_ammount: int = 10
