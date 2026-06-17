# @AI_GENERATED: Kiro v1.0
"""分析ipynb中绘图部分的数据来源"""

import json
import os

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'demo')

def main():
    with open(os.path.join(DATA_DIR, 'solar-power-forecasting.ipynb'), 'r', encoding='utf-8') as f:
        nb = json.load(f)
    
    print("=== ipynb 关键代码分析 ===")
    print()
    
    for i, cell in enumerate(nb['cells']):
        if cell['cell_type'] == 'code':
            source = ''.join(cell['source'])
            # 查找绘图相关的代码
            keywords = ['plt.plot', 'actual_values', 'predicted_values', 'inverse_transform']
            if any(kw in source for kw in keywords):
                print(f"=== Cell {i} ===")
                print(source)
                print()

if __name__ == '__main__':
    main()
# @AI_GENERATED: end
