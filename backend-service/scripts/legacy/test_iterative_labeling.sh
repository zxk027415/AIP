#!/bin/bash
# @AI_GENERATED: 旧黑盒 smoke 保留作意图参考，但当前 API 已改为 snake_case 且 dev 端口为 8081。
# DEPRECATED：脚本仍解析 loopId/datasetVersion 等旧字段，不能作为当前验收；补齐等价 TestClient smoke 后再删除。
# @AI_GENERATED: end
# 迭代标注系统快速测试脚本

set -e  # 遇到错误立即退出

API_BASE="http://localhost:8080/api/iterative-labeling"

echo "========================================="
echo "迭代标注系统快速测试"
echo "========================================="
echo ""

# 1. 创建闭环
echo "步骤 1: 创建迭代闭环..."
LOOP_RESPONSE=$(curl -s -X POST "$API_BASE/loops" \
  -H "Content-Type: application/json" \
  -d '{"slot": "default"}')

echo "响应: $LOOP_RESPONSE"
echo ""

# 提取 loopId (使用 grep 和 sed，兼容性更好)
LOOP_ID=$(echo "$LOOP_RESPONSE" | grep -o '"loopId":"[^"]*' | head -1 | sed 's/"loopId":"//')

if [ -z "$LOOP_ID" ]; then
  echo "❌ 错误: 无法创建闭环或提取 loopId"
  exit 1
fi

echo "✅ 成功创建闭环"
echo "   Loop ID: $LOOP_ID"
echo ""

# 2. 查看闭环状态
echo "步骤 2: 查看闭环状态..."
LOOP_STATE=$(curl -s "$API_BASE/loops/$LOOP_ID")
echo "$LOOP_STATE"
echo ""

# 3. 查看标签注册表
echo "步骤 3: 查看标签注册表..."
LABEL_REGISTRY=$(curl -s "$API_BASE/label-registry")
echo "$LABEL_REGISTRY"
echo ""

# 4. 查看迭代历史
echo "步骤 4: 查看迭代历史..."
ITERATIONS=$(curl -s "$API_BASE/iterations?slot=default")
echo "$ITERATIONS"
echo ""

echo "========================================="
echo "✅ 基础接口测试通过！"
echo "========================================="
echo ""
echo "下一步操作指南："
echo ""
echo "1. 准备数据集（CSV文件，包含 site_id, device_id, 特征列, fault_label）"
echo ""
echo "2. 训练模型："
echo "   curl -X POST $API_BASE/loops/$LOOP_ID/train \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{
       \"datasetVersion\": \"dataset-v1\",
       \"modelParams\": {
         \"testRatio\": 0.2,
         \"nRepeats\": 3,
         \"randomState\": 42,
         \"k\": 5
       }
     }'"
echo ""
echo "3. 预测无标签数据："
echo "   curl -X POST $API_BASE/loops/$LOOP_ID/predict \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{
       \"modelRef\": \"<上一步返回的modelRef>\",
       \"unlabeledDatasetVersion\": \"dataset-unlabeled-v1\"
     }'"
echo ""
echo "4. 创建审核会话："
echo "   curl -X POST $API_BASE/review-sessions \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{
       \"loopId\": \"$LOOP_ID\",
       \"predictionBatchId\": \"<上一步返回的predictionBatchId>\",
       \"enableLlm\": true
     }'"
echo ""
echo "5. 打开审核页面："
echo "   浏览器访问: http://localhost:5173/iterative-labeling/review/<reviewId>"
echo ""
echo "详细说明请参考: docs/specs/pv-fault-iterative-labeling-loop/QUICK_START_GUI.md"
echo ""
