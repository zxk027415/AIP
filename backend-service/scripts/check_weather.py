import pandas as pd
df = pd.read_csv('backend/data/demo/Plant_1_Weather_Sensor_Data.csv')
print('列:', df.columns.tolist())
print('形状:', df.shape)
print(df.head(3))
