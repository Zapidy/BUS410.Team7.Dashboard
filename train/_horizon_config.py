"""Shared horizon + fold config for all round7 training scripts.

ROUND7_HORIZON env var: 1, 3, or 6.
- 1: legacy h+1, kept for sanity checks
- 3: PRIMARY — forecast 2027 from 2024 features
- 6: long-horizon — forecast 2030 ("2030 scenario") from 2024 features

Each fold's test_end + HORIZON must be ≤ 2024 so target is observable.

For h+1: 8 standard folds.
For h+3: 8 folds shifted earlier.
For h+6: only 6 folds possible (less data → less statistical power).
"""
from __future__ import annotations
import os

HORIZON = int(os.environ.get("ROUND7_HORIZON", "3"))
TARGET = f"target_becomes_service_desert_h{HORIZON}"
DATA_END = 2024


def build_folds(horizon: int = HORIZON) -> list:
    if horizon == 1:
        return [
            ("F1", 2009, 2014, 2015, 2016, 2017),
            ("F2", 2009, 2015, 2016, 2017, 2018),
            ("F3", 2009, 2016, 2017, 2018, 2019),
            ("F4", 2009, 2017, 2018, 2019, 2020),
            ("F5", 2009, 2018, 2019, 2020, 2021),
            ("F6", 2009, 2019, 2020, 2021, 2022),
            ("F7", 2009, 2020, 2021, 2022, 2023),
            ("F8", 2009, 2021, 2022, 2023, 2024),
        ]
    if horizon == 3:
        return [
            ("F1", 2009, 2012, 2013, 2014, 2015),
            ("F2", 2009, 2013, 2014, 2015, 2016),
            ("F3", 2009, 2014, 2015, 2016, 2017),
            ("F4", 2009, 2015, 2016, 2017, 2018),
            ("F5", 2009, 2016, 2017, 2018, 2019),
            ("F6", 2009, 2017, 2018, 2019, 2020),
            ("F7", 2009, 2018, 2019, 2020, 2021),
            ("F8", 2009, 2019, 2020, 2021, 2021),  # collapsed to 1-yr test at the edge
        ]
    if horizon == 6:
        return [
            ("F1", 2009, 2010, 2011, 2012, 2013),
            ("F2", 2009, 2011, 2012, 2013, 2014),
            ("F3", 2009, 2012, 2013, 2014, 2015),
            ("F4", 2009, 2013, 2014, 2015, 2016),
            ("F5", 2009, 2014, 2015, 2016, 2017),
            ("F6", 2009, 2015, 2016, 2017, 2018),
        ]
    raise ValueError(f"Unsupported HORIZON: {horizon}")


FOLDS = build_folds(HORIZON)


def precovid_postcovid_splits(horizon: int = HORIZON):
    """For regime_split.py. Returns ((train_yrs, val_yr, test_yrs), ...)
    pre-COVID and post-COVID equivalents adjusted for horizon."""
    if horizon == 1:
        pre = ((2009, 2017), 2018, (2018, 2019))
        post = ((2020, 2021), 2022, (2023, 2024))
    elif horizon == 3:
        pre = ((2009, 2014), 2015, (2015, 2016))
        post = ((2018, 2019), 2020, (2020, 2021))
    elif horizon == 6:
        pre = ((2009, 2011), 2012, (2012, 2013))
        post = ((2014, 2015), 2016, (2017, 2018))
    else:
        raise ValueError(horizon)
    return pre, post
