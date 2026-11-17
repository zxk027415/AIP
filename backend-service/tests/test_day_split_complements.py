# -*- coding: utf-8 -*-
# @AI_GENERATED
from datetime import datetime, timedelta

from services.iterative_labeling.day_split_complements import complement_intervals, merge_intervals

DAY0 = datetime(2020, 5, 7)


def test_merge_and_complement_rest_of_day() -> None:
    fault = (DAY0 + timedelta(hours=8), DAY0 + timedelta(hours=10))
    already_normal = (DAY0 + timedelta(hours=10), DAY0 + timedelta(hours=15))
    holes = complement_intervals(DAY0, DAY0 + timedelta(days=1), [fault, already_normal])
    assert holes == [
        (DAY0, DAY0 + timedelta(hours=8)),
        (DAY0 + timedelta(hours=15), DAY0 + timedelta(days=1)),
    ]


def test_full_day_occupied_has_no_holes() -> None:
    day = (DAY0, DAY0 + timedelta(days=1))
    assert complement_intervals(DAY0, DAY0 + timedelta(days=1), [day]) == []
    assert merge_intervals([(DAY0, DAY0 + timedelta(hours=3)), (DAY0 + timedelta(hours=2), DAY0 + timedelta(hours=4))]) == [
        (DAY0, DAY0 + timedelta(hours=4))
    ]
# @AI_GENERATED: end
