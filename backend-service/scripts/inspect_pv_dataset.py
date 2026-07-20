# @AI_GENERATED
import pandas as pd
df = pd.read_parquet('datasets/dataset_combined.parquet')
print('date range:', df['time'].min(), '->', df['time'].max())
print('unique dates:', df['time'].dt.date.nunique())
print('unique sites:', df['site_id'].nunique(), list(df['site_id'].unique()[:3]))
print('unique devices:', df['device_id'].nunique())
print('label counts:', dict(df['label'].value_counts()))
rows_per_day = df.groupby(df['time'].dt.date).size()
print('rows per day - min:', rows_per_day.min(), 'max:', rows_per_day.max(), 'median:', rows_per_day.median())
# @AI_GENERATED: end
