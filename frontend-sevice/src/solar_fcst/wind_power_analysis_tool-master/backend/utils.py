import pandas as pd
import numpy as np

def resample_both_dimensions(df, target_freq='15T'):
    """
    对 timestamp 和 forecast_time 两个维度都进行 resample
    """
    df = df.copy()
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['forecast_time'] = pd.to_datetime(df['forecast_time'])

    # 第一步：对 timestamp 维度 resample
    temp_results = []
    for forecast_time_val, group in df.groupby('forecast_time'):
        group = group.sort_values('timestamp')

        original_time = group['timestamp'].astype(np.int64).values
        new_timestamps = pd.date_range(
            start=group['timestamp'].min(),
            end=group['timestamp'].max(),
            freq=target_freq
        )
        new_time = new_timestamps.astype(np.int64).values

        result_dict = {'timestamp': new_timestamps, 'forecast_time': forecast_time_val, 'prediction': np.interp(
            new_time,
            original_time,
            group['prediction'].values
        )}

        temp_results.append(pd.DataFrame(result_dict))

    df_temp = pd.concat(temp_results, ignore_index=True)
    return df_temp.sort_values(['forecast_time', 'timestamp']).reset_index(drop=True)