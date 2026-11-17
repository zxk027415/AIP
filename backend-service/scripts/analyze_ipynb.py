# @AI_GENERATED: Kiro v1.0
"""
系统分析ipynb中的数据流
"""

import json

with open('backend/data/demo/solar-power-forecasting.ipynb', 'r', encoding='utf-8') as f:
    nb = json.load(f)

print('=== ipynb 完整代码分析 ===')
print()

for i, cell in enumerate(nb['cells']):
    if cell['cell_type'] == 'code':
        source = ''.join(cell['source'])
        # 只打印关键代码单元格
        keywords = ['read_csv', 'DC_POWER', 'scaler', 'create_sequences', 
                   'split', 'Sequential', 'LSTM', 'predict', 
                   'inverse_transform', 'actual_values', 'predicted_values', 'plt.plot']
        if any(kw in source for kw in keywords):
            print(f'=== Cell {i} ===')
            print(source)
            print()
            print('-' * 80)
            print()
# @AI_GENERATED: end
