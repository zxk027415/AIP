"""
autoresearch_v6_services.py
第六代 AutoResearch 四个核心 service 的最小接口雏形（T8 产出）。

四个 service：
  - Analyst: 从 dataset profile、window error、历史 evidence 生成研究问题
  - ResearchActionPlanner: 把研究问题映射成 action，做 novelty/risk/cost 排序
  - PatchCompiler: 把 action 编译成现有 runtime patch，负责白名单和结构合法性
  - EvidenceCritic: 评价证据强度、失败原因、是否入复验、是否沉淀知识

设计原则：
  - 接口先于实现：先定义输入输出 schema，主循环只调接口
  - 可单元测试覆盖
  - 不一次性重写 _run_autoresearch_task，通过插入点渐进替换
"""

from typing import Any, Dict, List, Optional

from .autoresearch_research_action import (
    EvidenceLedgerEntry,
    ProfileSignal,
    ResearchAction,
    ResearchQualityMetrics,
)
from .autoresearch_novelty_gate import AutoResearchNoveltyGate, NoveltyGateResult


class AnalystService:
    """从数据画像和历史 evidence 生成研究问题。

    输入：TrainProfile / CrossWindowPattern / 历史 evidence_records
    输出：结构化 research_questions 列表
    """

    def generate_questions(
        self,
        *,
        profile_signal: ProfileSignal,
        evidence_records: List[Dict[str, Any]],
        existing_questions: List[Dict[str, Any]],
        max_questions: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        基于画像信号和历史证据，生成新的研究问题。

        Args:
            profile_signal（画像信号）: ProfileSignal 实例
            evidence_records（历史证据）: 已有 evidence
            existing_questions（已有问题）: 当前 run 的问题列表
            max_questions（最大问题数）: 本轮最多输出几个

        Returns:
            研究问题列表，每个含 question, target_direction, target_layer,
            candidate_causes, next_experiment_goal, priority, evidence_refs
        """
        questions: List[Dict[str, Any]] = []

        # 基于波动判断
        if profile_signal.volatility_level == "high":
            questions.append({
                "question": "高波动场景下，更宽的 rolling 窗口族是否能改善尾部误差？",
                "target_direction": "feature",
                "target_layer": "feature",
                "candidate_causes": ["volatility_high", "tail_error"],
                "next_experiment_goal": "尝试 rolling_window_family action",
                "priority": 1.2,
                "evidence_refs": [],
            })

        # 基于周末敏感
        if profile_signal.weekend_sensitive:
            questions.append({
                "question": "日历特征（节假日/工作日）是否在周末误差改善上有显著贡献？",
                "target_direction": "feature",
                "target_layer": "feature",
                "candidate_causes": ["weekend_sensitive", "calendar_effect"],
                "next_experiment_goal": "执行 calendar_feature_ablation",
                "priority": 1.1,
                "evidence_refs": [],
            })

        # 基于漂移
        if profile_signal.drift_strength > 0.3:
            questions.append({
                "question": "近期数据漂移是否意味着短训练窗口比长窗口更有效？",
                "target_direction": "parameter",
                "target_layer": "training",
                "candidate_causes": ["drift_strong", "concept_drift"],
                "next_experiment_goal": "对比 short_window_probe vs long_window_probe",
                "priority": 1.3,
                "evidence_refs": [],
            })

        # 基于噪声水平
        if profile_signal.noise_level == "high":
            questions.append({
                "question": "高噪声环境下，模型正则化收紧是否改善泛化？",
                "target_direction": "model",
                "target_layer": "model",
                "candidate_causes": ["noise_high", "overfitting_risk"],
                "next_experiment_goal": "执行 model_regularization_profile",
                "priority": 1.0,
                "evidence_refs": [],
            })

        # 通用：调参投入产出
        if not any(q.get("next_experiment_goal", "").startswith("调参") for q in existing_questions):
            questions.append({
                "question": "当前调参强度（n_trials）的边际收益是否已递减？",
                "target_direction": "parameter",
                "target_layer": "training",
                "candidate_causes": ["diminishing_returns"],
                "next_experiment_goal": "执行 tuning_intensity_sweep",
                "priority": 0.8,
                "evidence_refs": [],
            })

        return questions[:max_questions]


class ResearchActionPlanner:
    """把研究问题映射成可执行 action，做 novelty/risk/cost 排序。

    输入：research_questions + available_actions + profile_signal + evidence
    输出：ranked action list（含 reason）
    """

    def __init__(self):
        self._novelty_gate = AutoResearchNoveltyGate()
        self._compiler: Optional["PatchCompiler"] = None

    @property
    def compiler(self) -> "PatchCompiler":
        if self._compiler is None:
            self._compiler = PatchCompiler()
        return self._compiler

    def plan(
        self,
        *,
        questions: List[Dict[str, Any]],
        available_actions: List[ResearchAction],
        profile_signal: ProfileSignal,
        evidence_records: List[Dict[str, Any]],
        candidate_pool: List[Dict[str, Any]],
        run_iterations: List[Dict[str, Any]],
        run_state: Optional[Dict[str, Any]] = None,
        max_actions: int = 3,
    ) -> List[Dict[str, Any]]:
        """
        从问题出发，选择最优 actions 并排序，包含 variant 选择。

        Args:
            run_state（运行状态，可选）: 用于读取/更新 action_variant_cursor

        Returns:
            排序后的 action 计划列表，每项含：
              action_id, action（ResearchAction dict）, reason, novelty_gate_result,
              priority_score, stage, variant_index, patch_fingerprint
        """
        state = run_state if run_state is not None else {}
        tested_fps = self._collect_tested_fingerprints(state, evidence_records, candidate_pool)

        # Step 1: 过滤画像适用的 actions
        applicable = [a for a in available_actions if profile_signal.action_applicable(a)]

        # Step 2: 问题 → action 映射（通过 target_direction + target_layer 匹配）
        scored: List[Dict[str, Any]] = []
        exhausted: List[Dict[str, Any]] = []
        for action in applicable:
            # 匹配相关问题
            matching_questions = [
                q for q in questions
                if q.get("target_direction") == action.target_direction
                and q.get("target_layer") == action.target_layer
            ]
            if not matching_questions and questions:
                priority = 0.3
            else:
                priority = max((float(q.get("priority") or 1.0) for q in matching_questions), default=1.0)

            # Step 3: novelty gate
            gate_result = self._novelty_gate.evaluate(
                patch_fingerprint="",
                changed_variables=list(action.patch_template.get("global_config", {}).keys())
                    + list(action.patch_template.get("node_params", {}).keys()),
                action_id=action.action_id,
                evidence_records=evidence_records,
                candidate_pool=candidate_pool,
                run_iterations=run_iterations,
            )

            if gate_result.decision == "skip":
                continue

            if gate_result.decision == "deprioritize":
                priority *= 0.5

            # Step 4 (T8.1/T8.2): variant 选择
            variant_index = self.compiler.next_untested_variant(action, tested_fps)
            if variant_index is None:
                # action exhausted: 所有 variant 都测过了
                exhausted.append({
                    "action_id": action.action_id,
                    "action": action.to_dict(),
                    "reason": "exhausted: all variants tested",
                    "priority_score": priority,
                    "matching_questions": [q.get("question", "")[:60] for q in matching_questions[:2]],
                })
                continue

            variant_fp = self.compiler.variant_fingerprint(action, variant_index)

            # 风险降权
            risk_penalty = {"low": 1.0, "medium": 0.85, "high": 0.7}.get(action.risk_level, 1.0)

            scored.append({
                "action_id": action.action_id,
                "action": action.to_dict(),
                "reason": f"matched_questions={len(matching_questions)}, gate={gate_result.decision}, variant={variant_index}",
                "novelty_gate_result": gate_result.to_dict(),
                "priority_score": round(priority * risk_penalty, 4),
                "stage": action.stage,
                "variant_index": variant_index,
                "patch_fingerprint": variant_fp,
                "matching_questions": [q.get("question", "")[:60] for q in matching_questions[:2]],
            })

        # Step 5: 按 priority_score 降序排序
        scored.sort(key=lambda x: x["priority_score"], reverse=True)

        # Step 6 (T8.3): batch 分配策略 — 优先不同 action（探索宽度）
        selected = self._select_batch(scored, max_actions=max_actions, tested_fps=tested_fps)

        # P1-2 fix: exhausted actions → 尝试 fallback
        if len(selected) < max_actions:
            selected = self._fill_with_fallbacks(
                selected, exhausted, available_actions, tested_fps, max_actions
            )

        # P1-3 fix: 不在 plan() 中更新 tested —— 只返回计划
        # cursor 更新改为由调用方在 evidence 成功落账后调用 commit_plan_result()

        return selected

    def commit_plan_result(self, state: Dict[str, Any], executed_plans: List[Dict[str, Any]]) -> None:
        """在回测成功提交/evidence 落账后，才更新 variant cursor（P1-3 fix）。

        Args:
            state（run_state）: 当前 run 状态
            executed_plans（已执行的计划列表）: 只含真正跑完回测的 plan items
        """
        self._update_variant_cursor(state, executed_plans)

    def _fill_with_fallbacks(
        self,
        selected: List[Dict[str, Any]],
        exhausted: List[Dict[str, Any]],
        available_actions: List[ResearchAction],
        tested_fps: set,
        max_actions: int,
    ) -> List[Dict[str, Any]]:
        """P1-2 fix: 当主选 action 不足时，从 exhausted action 的 fallback_actions 中补充。"""
        if len(selected) >= max_actions:
            return selected

        selected_ids = {s["action_id"] for s in selected}
        action_map = {a.action_id: a for a in available_actions}
        tried_fallbacks: set = set()

        for item in exhausted:
            if len(selected) >= max_actions:
                break
            action = ResearchAction.from_dict(item["action"])
            for fb_id in action.fallback_actions:
                if fb_id in selected_ids or fb_id in tried_fallbacks:
                    continue
                tried_fallbacks.add(fb_id)
                fb_action = action_map.get(fb_id)
                if fb_action is None:
                    continue
                vi = self.compiler.next_untested_variant(fb_action, tested_fps)
                if vi is None:
                    continue
                fp = self.compiler.variant_fingerprint(fb_action, vi)
                if fp in tested_fps:
                    continue
                selected.append({
                    "action_id": fb_id,
                    "action": fb_action.to_dict(),
                    "reason": f"fallback from exhausted {action.action_id}",
                    "novelty_gate_result": {"decision": "pass", "reason": "fallback", "confidence": 0.0},
                    "priority_score": item.get("priority_score", 0.5) * 0.8,
                    "stage": fb_action.stage,
                    "variant_index": vi,
                    "patch_fingerprint": fp,
                    "matching_questions": [],
                })
                selected_ids.add(fb_id)
                if fp:
                    tested_fps.add(fp)
                if len(selected) >= max_actions:
                    break

        return selected

    def _collect_tested_fingerprints(
        self,
        state: Dict[str, Any],
        evidence_records: List[Dict[str, Any]],
        candidate_pool: List[Dict[str, Any]],
    ) -> set:
        """收集所有已测试的 patch fingerprints。"""
        fps = set()
        # 从 evidence
        for e in evidence_records:
            if isinstance(e, dict):
                fp = str(e.get("patch_fingerprint") or "")
                if fp:
                    fps.add(fp)
        # 从候选池
        for c in candidate_pool:
            if isinstance(c, dict):
                sig = str(c.get("candidate_signature") or c.get("patch_fingerprint") or "")
                if sig:
                    fps.add(sig)
        # 从 variant cursor 历史
        tested = state.get("action_tested_fingerprints") or {}
        for action_fps in tested.values():
            if isinstance(action_fps, list):
                fps.update(str(f) for f in action_fps if f)
        return fps

    def _select_batch(
        self,
        scored: List[Dict[str, Any]],
        max_actions: int,
        tested_fps: set,
    ) -> List[Dict[str, Any]]:
        """
        从排序后的候选中选取 batch（T8.3）。

        策略：优先不同 action（探索宽度）。如果排名第一的 action priority
        远高于其他（>= 2x），允许同一 action 占多个 slot。
        """
        if not scored:
            return []

        selected: List[Dict[str, Any]] = []
        used_action_ids: set = set()
        used_fingerprints: set = set(tested_fps)

        # 第一轮：每个 action 最多选一个
        for item in scored:
            if len(selected) >= max_actions:
                break
            aid = item["action_id"]
            fp = item.get("patch_fingerprint", "")
            if aid not in used_action_ids and fp not in used_fingerprints:
                selected.append(item)
                used_action_ids.add(aid)
                if fp:
                    used_fingerprints.add(fp)

        # 第二轮：如果 slot 没填满且第一名 priority 远高于其他，用同 action 的不同 variant 补
        if len(selected) < max_actions and scored:
            top_action_id = scored[0]["action_id"]
            top_priority = scored[0]["priority_score"]
            second_priority = scored[1]["priority_score"] if len(scored) > 1 else 0

            if top_priority >= second_priority * 2:
                top_action = ResearchAction.from_dict(scored[0]["action"])
                cursor = (selected[-1]["variant_index"] if selected else -1) + 1
                while len(selected) < max_actions:
                    vi = self.compiler.next_untested_variant(top_action, used_fingerprints)
                    if vi is None:
                        break
                    fp = self.compiler.variant_fingerprint(top_action, vi)
                    if fp in used_fingerprints:
                        break
                    selected.append({
                        **scored[0],
                        "variant_index": vi,
                        "patch_fingerprint": fp,
                        "reason": f"batch_fill: same action, variant={vi}",
                    })
                    used_fingerprints.add(fp)

        return selected[:max_actions]

    def _update_variant_cursor(self, state: Dict[str, Any], selected: List[Dict[str, Any]]) -> None:
        """更新 run_state 中的 variant cursor 和 tested fingerprints（T8.2）。"""
        cursor = state.setdefault("action_variant_cursor", {})
        tested = state.setdefault("action_tested_fingerprints", {})

        for item in selected:
            aid = item["action_id"]
            vi = item.get("variant_index", 0)
            fp = item.get("patch_fingerprint", "")

            # 更新 cursor
            cursor[aid] = max(int(cursor.get(aid) or 0), vi + 1)

            # 记录 tested fingerprint
            if fp:
                if aid not in tested:
                    tested[aid] = []
                if fp not in tested[aid]:
                    tested[aid].append(fp)
                # 限制记录长度
                tested[aid] = tested[aid][-50:]


class PatchCompiler:
    """把 ResearchAction 编译成 runtime patch。

    输入：ResearchAction + 当前 baseline 配置
    输出：可提交回测的 runtime_patch dict

    职责：
      - 白名单校验
      - 结构合法性检查
      - max_changed_variables 限制
    """

    # 允许修改的 global_config key 白名单
    _ALLOWED_GLOBAL_KEYS = {
        "train_days", "daily_horizon", "ensemble_mode",
        "xgb_eta_high", "xgb_max_depth_high", "xgb_subsample_high",
        "lgb_num_leaves_high", "lgb_learning_rate_high",
        "cb_depth_high", "cb_learning_rate_high",
    }

    # 允许修改的 node_param 目标
    _ALLOWED_NODE_FUNCTIONS = {
        "auto_tune_xgboost", "create_lag_features", "rolling_statistics",
        "sliding_window", "ensemble_forecast", "load_csv",
        "holiday_features", "workday_features", "diff_features",
        "extract_statistical_features",
    }

    def compile(
        self,
        action: ResearchAction,
        *,
        variant_index: int = 0,
    ) -> Dict[str, Any]:
        """
        编译 action 为 runtime patch。

        Args:
            action（研究动作）: ResearchAction 实例
            variant_index（变体索引）: 展开后的 variant 序号

        Returns:
            runtime_patch dict，含 global_config_patch / node_param_patches / structure_patches
            以及 metadata（action_id, changed_variables, risk_level）

        Raises:
            ValueError: 白名单校验失败
        """
        template = action.patch_template
        patch: Dict[str, Any] = {
            "global_config_patch": {},
            "node_param_patches": [],
            "structure_patches": {},
            "metadata": {
                "action_id": action.action_id,
                "action_type": action.action_type,
                "target_direction": action.target_direction,
                "target_layer": action.target_layer,
                "risk_level": action.risk_level,
                "max_changed_variables": action.max_changed_variables,
                "changed_variables": [],
            },
        }

        changed: List[str] = []

        # 处理 variants 模式（显式枚举）
        if "variants" in template:
            variants = template["variants"]
            if isinstance(variants, list) and variants:
                idx = min(variant_index, len(variants) - 1)
                template = variants[idx]

        # 收集所有参数的候选值列表，用于笛卡尔积解码
        param_slots: List[tuple] = []  # [(location, key, values)]

        for key, value in (template.get("global_config") or {}).items():
            if isinstance(value, list) and value:
                param_slots.append(("gc", key, value))
            else:
                param_slots.append(("gc", key, [value]))

        for func_id, params in (template.get("node_params") or {}).items():
            if not isinstance(params, dict):
                continue
            for param_key, param_value in params.items():
                if isinstance(param_value, list) and param_value:
                    param_slots.append(("np", f"{func_id}.{param_key}", param_value))
                else:
                    param_slots.append(("np", f"{func_id}.{param_key}", [param_value]))

        for func_id, value in (template.get("structure_switches") or {}).items():
            if isinstance(value, list) and value:
                param_slots.append(("ss", func_id, value))
            else:
                param_slots.append(("ss", func_id, [value]))

        mf = template.get("model_focus")
        if isinstance(mf, list) and mf:
            if isinstance(mf[0], list):
                param_slots.append(("mf", "model_focus", mf))
            else:
                param_slots.append(("mf", "model_focus", [mf]))

        # 笛卡尔积解码：把 flat variant_index 转为各参数的局部 index
        local_indices = self._decode_variant_index(variant_index, [len(s[2]) for s in param_slots])

        # 按解码结果填充 patch
        for i, (location, key, values) in enumerate(param_slots):
            local_idx = local_indices[i]
            actual = values[local_idx]

            if location == "gc":
                if key not in self._ALLOWED_GLOBAL_KEYS:
                    raise ValueError(f"global_config key '{key}' 不在白名单中")
                patch["global_config_patch"][key] = actual
                changed.append(key)
            elif location == "np":
                func_id, param_key = key.split(".", 1)
                if func_id not in self._ALLOWED_NODE_FUNCTIONS:
                    raise ValueError(f"node_function_id '{func_id}' 不在白名单中")
                # 合并到同一 func_id 的 node_patch
                existing = next((np for np in patch["node_param_patches"] if np["node_function_id"] == func_id), None)
                if existing is None:
                    existing = {"node_function_id": func_id, "params": {}}
                    patch["node_param_patches"].append(existing)
                existing["params"][param_key] = actual
                changed.append(key)
            elif location == "ss":
                if key not in self._ALLOWED_NODE_FUNCTIONS:
                    raise ValueError(f"structure_switch '{key}' 不在白名单中")
                patch["structure_patches"][key] = actual
                changed.append(f"{key}.enabled")
            elif location == "mf":
                patch["global_config_patch"]["model_focus"] = actual
                changed.append("model_focus")

        # 校验 max_changed_variables
        patch["metadata"]["changed_variables"] = changed
        if len(changed) > action.max_changed_variables:
            raise ValueError(
                f"action '{action.action_id}' 变更了 {len(changed)} 个变量，"
                f"超过 max_changed_variables={action.max_changed_variables}"
            )

        return patch

    def compile_runtime_patch(
        self,
        action: ResearchAction,
        *,
        variant_index: int = 0,
        workflow: Optional[Any] = None,
        node_id_by_function: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Compile an action into the runtime patch shape used by workflows_enhanced.

        The internal compile() output is function-oriented. The AutoResearch main
        loop validates workflow-oriented patches with node_id/functionId/param_patch
        and structure_patch.node_switches, so this adapter resolves functionId to
        node_id before integration.
        """
        compiled = self.compile(action, variant_index=variant_index)
        node_map = dict(node_id_by_function or {})
        if workflow is not None:
            node_map.update(self._node_id_by_function(workflow))

        global_config_patch = dict(compiled.get("global_config_patch") or {})
        model_focus = global_config_patch.pop("model_focus", None)

        node_param_patches: List[Dict[str, Any]] = []
        for item in compiled.get("node_param_patches") or []:
            func_id = str(item.get("node_function_id") or item.get("functionId") or "").strip()
            params = item.get("params") or item.get("param_patch") or {}
            if not func_id or not isinstance(params, dict):
                continue
            node_id = str(node_map.get(func_id) or "").strip()
            if not node_id:
                raise ValueError(f"workflow 中找不到 functionId={func_id} 的 node_id")
            node_param_patches.append({
                "node_id": node_id,
                "functionId": func_id,
                "param_patch": dict(params),
            })

        node_switches: List[Dict[str, Any]] = []
        for func_id, enabled in (compiled.get("structure_patches") or {}).items():
            fid = str(func_id).strip()
            node_id = str(node_map.get(fid) or "").strip()
            if not node_id:
                raise ValueError(f"workflow 中找不到 functionId={fid} 的 node_id")
            node_switches.append({
                "node_id": node_id,
                "functionId": fid,
                "enabled": bool(enabled),
            })

        runtime_patch = {
            "global_config_patch": global_config_patch,
            "node_param_patches": node_param_patches,
            "structure_patch": {"node_switches": node_switches} if node_switches else {},
            "model_focus": model_focus if isinstance(model_focus, list) else [],
            "metadata": dict(compiled.get("metadata") or {}),
        }
        return runtime_patch

    @staticmethod
    def _node_id_by_function(workflow: Any) -> Dict[str, str]:
        """Build functionId -> node_id map from a workflow dict or pydantic model."""
        if hasattr(workflow, "dict"):
            data = workflow.dict()
        elif isinstance(workflow, dict):
            data = workflow
        else:
            data = {}
        out: Dict[str, str] = {}
        for node in data.get("nodes") or []:
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("id") or "").strip()
            cfg = ((node.get("data") or {}).get("config") or {})
            func_id = str(cfg.get("functionId") or "").strip()
            if node_id and func_id:
                out[func_id] = node_id
        return out

    @staticmethod
    def _decode_variant_index(variant_index: int, sizes: List[int]) -> List[int]:
        """把 flat variant_index 解码为各参数的局部 index（混合进制）。"""
        indices = []
        remaining = variant_index
        for size in reversed(sizes):
            if size <= 0:
                indices.append(0)
                continue
            indices.append(remaining % size)
            remaining //= size
        indices.reverse()
        return indices

    # ─── T8.1: Variant 展开与遍历 ────────────────────────────────────────────

    def expand_variants(self, action: ResearchAction, *, max_variants: int = 20) -> List[Dict[str, Any]]:
        """
        展开 action 的所有可能 variant 组合。

        规则：
          - variants 模式 → 直接返回列表
          - 单/多参数列表 → 计算笛卡尔积大小
          - 超过 max_variants 时用 LHS 采样

        Returns:
            variant 列表，每个元素含 variant_index
        """
        import random

        template = action.patch_template

        # variants 模式：直接返回
        if "variants" in template and isinstance(template["variants"], list):
            return [{"variant_index": i} for i in range(len(template["variants"]))]

        # 收集所有参数候选值的 size
        sizes: List[int] = []

        for key, value in (template.get("global_config") or {}).items():
            sizes.append(len(value) if isinstance(value, list) and value else 1)

        for func_id, params in (template.get("node_params") or {}).items():
            if not isinstance(params, dict):
                continue
            for param_key, param_value in params.items():
                sizes.append(len(param_value) if isinstance(param_value, list) and param_value else 1)

        for func_id, value in (template.get("structure_switches") or {}).items():
            sizes.append(len(value) if isinstance(value, list) and value else 1)

        mf = template.get("model_focus")
        if isinstance(mf, list) and mf and isinstance(mf[0], list):
            sizes.append(len(mf))

        if not sizes:
            return [{"variant_index": 0}]

        # 计算笛卡尔积大小
        total_combos = 1
        for s in sizes:
            total_combos *= max(s, 1)

        if total_combos <= max_variants:
            return [{"variant_index": i} for i in range(total_combos)]
        else:
            # LHS 采样
            rng = random.Random(hash(action.action_id) & 0xFFFFFFFF)
            indices = set()
            attempts = 0
            while len(indices) < max_variants and attempts < max_variants * 10:
                idx = rng.randint(0, total_combos - 1)
                indices.add(idx)
                attempts += 1
            return [{"variant_index": i} for i in sorted(indices)]

    def variant_fingerprint(self, action: ResearchAction, variant_index: int) -> str:
        """计算某 variant 的 fingerprint（不执行完整编译，只算哈希）。"""
        import hashlib
        import json

        try:
            patch = self.compile(action, variant_index=variant_index)
            content = json.dumps(
                {
                    "action_id": action.action_id,
                    "global_config_patch": patch.get("global_config_patch"),
                    "node_param_patches": patch.get("node_param_patches"),
                    "structure_patches": patch.get("structure_patches"),
                },
                sort_keys=True,
                ensure_ascii=False,
            )
            return hashlib.sha256(content.encode()).hexdigest()[:16]
        except (ValueError, IndexError):
            return ""

    def next_untested_variant(
        self,
        action: ResearchAction,
        tested_fingerprints: set,
    ) -> Optional[int]:
        """
        从 action 的 variants 中选出第一个 fingerprint 不在 tested 中的。

        Returns:
            variant_index（int）或 None（全部测完，action exhausted）
        """
        variants = self.expand_variants(action)
        for v in variants:
            idx = v["variant_index"]
            fp = self.variant_fingerprint(action, idx)
            if fp and fp not in tested_fingerprints:
                return idx
        return None


class EvidenceCritic:
    """评价证据强度，决定是否入复验池、是否沉淀知识。

    输入：回测结果 + 候选 evidence + 画像信号
    输出：evidence_strength 判定 + 后续动作建议
    """

    def evaluate(
        self,
        *,
        evidence: EvidenceLedgerEntry,
        profile_signal: Optional[ProfileSignal] = None,
        existing_knowledge_claims: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        评价单条证据，给出后续动作建议。

        Returns:
            Dict 含:
              strength_assessment（强度评估）: 确认/质疑/不足
              recommended_action（建议动作）: "enqueue_verification" / "promote" /
                  "reject" / "gather_more" / "mark_anti_pattern"
              reason（原因）: 人类可读理由
              confidence（置信度）: 0.0~1.0
        """
        strength = evidence.evidence_strength
        windows_total = evidence.windows_total
        windows_better = evidence.windows_challenger_better
        improvement = evidence.mape_improvement

        # multi_window_confirmed: 已通过复验，可以 promote 或沉淀知识
        if strength == "multi_window_confirmed":
            return {
                "strength_assessment": "confirmed",
                "recommended_action": "promote",
                "reason": f"多窗口确认通过：{windows_better}/{windows_total} 窗口胜出，改善 {improvement:.4f}",
                "confidence": 0.9,
            }

        # multi_window_rejected: 标记为 anti-pattern
        if strength == "multi_window_rejected":
            return {
                "strength_assessment": "rejected",
                "recommended_action": "mark_anti_pattern",
                "reason": f"多窗口拒绝：{windows_better}/{windows_total} 窗口胜出，不满足标准",
                "confidence": 0.85,
            }

        # single_window_positive: 有希望但需要复验
        if strength == "single_window_positive":
            if improvement > 0.5:
                return {
                    "strength_assessment": "promising",
                    "recommended_action": "enqueue_verification",
                    "reason": f"单窗口正收益 {improvement:.4f}，建议入复验池多窗口验证",
                    "confidence": 0.6,
                }
            else:
                return {
                    "strength_assessment": "marginal",
                    "recommended_action": "gather_more",
                    "reason": f"单窗口改善仅 {improvement:.4f}，证据不足以入复验",
                    "confidence": 0.4,
                }

        # single_window_negative 或 insufficient_evidence
        return {
            "strength_assessment": "insufficient",
            "recommended_action": "reject" if strength == "single_window_negative" else "gather_more",
            "reason": f"证据不足或负向：strength={strength}, improvement={improvement:.4f}",
            "confidence": 0.3,
        }

    def should_upgrade_knowledge(
        self,
        evidence: EvidenceLedgerEntry,
        existing_claims: List[Dict[str, Any]],
    ) -> bool:
        """判断证据是否应升级为 active knowledge claim。

        规则：
          - 必须是 multi_window_confirmed
          - Stage C 通过
          - 不能只是单 run 的结论
        """
        if evidence.evidence_strength != "multi_window_confirmed":
            return False
        if evidence.stage != "C":
            return False
        return True
