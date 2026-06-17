import sys
sys.path.insert(0, '.')
sys.path.insert(0, '..')

from services.operator_backends.extract_time_features import OPERATOR_ID as id1, execute as ex1
print(f'extract_time_features: OPERATOR_ID={id1}')

from services.operator_backends.holiday_features import OPERATOR_ID as id2, execute as ex2
print(f'holiday_features: OPERATOR_ID={id2}')

from services.operator_backends.workday_features import OPERATOR_ID as id3, execute as ex3
print(f'workday_features: OPERATOR_ID={id3}')

from services.operator_backends.rolling_statistics import OPERATOR_ID as id4, execute as ex4
print(f'rolling_statistics: OPERATOR_ID={id4}')

from services.operator_backends.create_lag_features import OPERATOR_ID as id5, execute as ex5
print(f'create_lag_features: OPERATOR_ID={id5}')

from services.operator_backends.diff_features import OPERATOR_ID as id6, execute as ex6
print(f'diff_features: OPERATOR_ID={id6}')

from services.operator_backends.pct_change_features import OPERATOR_ID as id7, execute as ex7
print(f'pct_change_features: OPERATOR_ID={id7}')

from services.operator_backends.extract_statistical_features import OPERATOR_ID as id8, execute as ex8
print(f'extract_statistical_features: OPERATOR_ID={id8}')

from services.operator_backends.peak_valley_features import OPERATOR_ID as id9, execute as ex9
print(f'peak_valley_features: OPERATOR_ID={id9}')

from services.operator_backends.shift_features import OPERATOR_ID as id10, execute as ex10
print(f'shift_features: OPERATOR_ID={id10}')

print('\nAll 10 feature engineering operators imported successfully!')
