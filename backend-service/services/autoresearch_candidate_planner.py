from typing import Any, Dict, List, Optional


class AutoResearchCandidatePlanner:
    DIRECTIONS = ("parameter", "feature", "model", "data", "risk")
    DIRECTION_TO_LAYER = {
        "parameter": "training",
        "feature": "feature",
        "model": "model",
        "data": "data",
        "risk": "model",
    }

    def build_scoreboard(self, run_state: Dict[str, Any]) -> Dict[str, Any]:
        scoreboard: Dict[str, Dict[str, Any]] = {
            direction: {
                "attempts": 0,
                "successes": 0,
                "failures": 0,
                "timeout_count": 0,
                "negative_score_count": 0,
                "ineffective_count": 0,
                "best_score_advantage": None,
                "last_tried_iteration": None,
                "coverage_gap": 0,
            }
            for direction in self.DIRECTIONS
        }

        groups = self._collect_groups(run_state)
        for group in groups:
            if not isinstance(group, dict):
                continue
            direction = self.normalize_direction(group.get("target_direction") or group.get("selected_layer"))
            row = scoreboard[direction]
            row["attempts"] += 1
            iteration = self._safe_int(group.get("iteration"))
            if iteration is not None:
                last = row.get("last_tried_iteration")
                row["last_tried_iteration"] = iteration if last is None else max(int(last), iteration)

            status = str(group.get("status") or "").lower()
            error = str(group.get("error") or group.get("error_message") or "").lower()
            if status == "success":
                row["successes"] += 1
                adv = self._safe_float(group.get("score_advantage"))
                mape_improvement = self._safe_float(group.get("mape_improvement"))
                if adv is not None:
                    best = row.get("best_score_advantage")
                    row["best_score_advantage"] = adv if best is None else max(float(best), adv)
                if (adv is not None and adv <= 0) or (mape_improvement is not None and mape_improvement <= 0):
                    row["negative_score_count"] += 1
                    row["ineffective_count"] += 1
            elif status in {"failed", "error", "cancelled", "pruned"} or error:
                row["failures"] += 1
            if "timeout" in error:
                row["timeout_count"] += 1

        max_attempts = max((int(v["attempts"]) for v in scoreboard.values()), default=0)
        for direction, row in scoreboard.items():
            row["coverage_gap"] = max_attempts - int(row["attempts"])
            row["direction_coverage"] = round(int(row["attempts"]) / max(max_attempts, 1), 6)
            row["direction"] = direction
            row["target_layer"] = self.DIRECTION_TO_LAYER[direction]
        return scoreboard

    def exploration_health(self, run_state: Dict[str, Any], active_layers: Optional[List[str]] = None) -> Dict[str, Any]:
        scoreboard = self.build_scoreboard(run_state or {})
        groups = self._collect_groups(run_state or {})
        primary_counts = {direction: 0 for direction in self.DIRECTIONS}
        total_primary = 0
        for group in groups:
            if not isinstance(group, dict):
                continue
            raw_idx = group.get("group_idx")
            is_primary = bool(group.get("is_primary"))
            if raw_idx is not None:
                try:
                    is_primary = int(raw_idx) == 0
                except (TypeError, ValueError):
                    pass
            if not is_primary:
                continue
            direction = self.normalize_direction(group.get("target_direction") or group.get("selected_layer"))
            primary_counts[direction] += 1
            total_primary += 1

        primary_ratios = {
            direction: round(count / max(total_primary, 1), 6)
            for direction, count in primary_counts.items()
        }
        active = {str(x) for x in (active_layers or []) if str(x)}
        layer_status = {}
        for direction in self.DIRECTIONS:
            layer = self.DIRECTION_TO_LAYER[direction]
            row = scoreboard[direction]
            layer_status[direction] = {
                "target_layer": layer,
                "active": (layer in active) if active else None,
                "attempts": int(row.get("attempts") or 0),
                "planner_reason": self._reason(direction, row, active_layers),
            }

        recommended = self.recommend_primary_direction(run_state or {}, active_layers=active_layers)
        parameter_ratio = primary_ratios.get("parameter", 0.0)
        proposal_source = self._proposal_source(run_state or {})
        return {
            "scoreboard": scoreboard,
            "direction_coverage": {
                direction: row.get("direction_coverage", 0.0)
                for direction, row in scoreboard.items()
            },
            "primary_direction_counts": primary_counts,
            "primary_direction_ratio": primary_ratios,
            "parameter_overdominance": bool(total_primary >= 4 and parameter_ratio >= 0.6),
            "recommended_primary_direction": recommended.get("direction"),
            "primary_rotation_reason": recommended.get("reason"),
            "layer_activation_status": layer_status,
            "directions_needing_attention": [
                direction for direction, row in scoreboard.items()
                if int(row.get("ineffective_count") or 0) > 0 or int(row.get("timeout_count") or 0) > 0
            ],
            "ineffective_count": sum(int(row.get("ineffective_count") or 0) for row in scoreboard.values()),
            "negative_score_count": sum(int(row.get("negative_score_count") or 0) for row in scoreboard.values()),
            "llm_used": proposal_source == "glm",
            "rule_fallback": proposal_source != "glm",
            "proposal_source": proposal_source,
        }

    def recommend_primary_direction(
        self,
        run_state: Dict[str, Any],
        active_layers: Optional[List[str]] = None,
    ) -> Dict[str, str]:
        scoreboard = self.build_scoreboard(run_state or {})
        groups = self._collect_groups(run_state or {})
        primary_counts = {direction: 0 for direction in self.DIRECTIONS}
        recent_main = []
        for group in groups:
            if not isinstance(group, dict):
                continue
            is_primary = bool(group.get("is_primary"))
            if group.get("group_idx") is not None:
                try:
                    is_primary = int(group.get("group_idx")) == 0
                except (TypeError, ValueError):
                    pass
            if not is_primary:
                continue
            direction = self.normalize_direction(group.get("target_direction") or group.get("selected_layer"))
            primary_counts[direction] += 1
            recent_main.append(group)
        total_primary = sum(primary_counts.values())
        parameter_ratio = primary_counts["parameter"] / max(total_primary, 1)

        candidate_rows = []
        for direction in self.DIRECTIONS:
            if direction == "parameter":
                continue
            row = scoreboard[direction]
            attempts = int(row.get("attempts") or 0)
            best = self._safe_float(row.get("best_score_advantage"))
            ineffective = int(row.get("ineffective_count") or 0)
            timeouts = int(row.get("timeout_count") or 0)
            candidate_rows.append((
                1 if best is not None and best > 0 else 0,
                int(row.get("coverage_gap") or 0),
                -ineffective,
                -timeouts,
                -attempts,
                direction,
            ))
        candidate_rows.sort(reverse=True)
        fallback = candidate_rows[0][5] if candidate_rows else "feature"
        if total_primary >= 4 and parameter_ratio >= 0.6:
            return {"direction": fallback, "reason": f"parameter_overdominance ratio={parameter_ratio:.2f}"}
        stagnant = self._recent_primary_stagnant(recent_main[-4:])
        if stagnant:
            return {"direction": fallback, "reason": "recent_primary_stagnating"}
        return {"direction": "parameter", "reason": "default_exploit_parameter"}

    def build_slots(
        self,
        batch_size: int,
        iteration: int,
        run_state: Dict[str, Any],
        active_layers: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        size = max(1, int(batch_size or 1))
        scoreboard = self.build_scoreboard(run_state or {})
        recommended = self.recommend_primary_direction(run_state or {}, active_layers=active_layers)
        directions = self._direction_plan(size, int(iteration or 1), scoreboard, recommended.get("direction") or "parameter")
        active = {str(x) for x in (active_layers or []) if str(x)}

        slots: List[Dict[str, Any]] = []
        for idx, direction in enumerate(directions):
            layer = self.DIRECTION_TO_LAYER[direction]
            role = self._role_for(idx, direction)
            source = "primary" if idx == 0 else "planner"
            if idx > 0 and active and layer in active:
                source = "registry_targeted"
            elif idx > 0:
                source = "memory_random"
            slots.append({
                "group_idx": idx,
                "target_direction": direction,
                "target_layer": layer,
                "exploration_role": role,
                "candidate_source": source,
                "planner_reason": self._reason(direction, scoreboard[direction], active_layers),
                "recommended_primary_direction": recommended.get("direction") if idx == 0 else None,
                "primary_rotation_reason": recommended.get("reason") if idx == 0 else None,
            })
        return slots

    def normalize_direction(self, value: Any) -> str:
        raw = str(value or "").lower().strip()
        if raw in self.DIRECTIONS:
            return raw
        if raw in {"training", "parameter", "params", "global_config"}:
            return "parameter"
        if raw in {"feature", "features", "structure"}:
            return "feature"
        if raw in {"model", "models", "ensemble"}:
            return "model"
        if raw in {"data", "window", "windows"}:
            return "data"
        if raw in {"risk", "risky", "exploration"}:
            return "risk"
        return "parameter"

    def direction_for_layer(self, layer: Any) -> str:
        return self.normalize_direction(layer)

    def _direction_plan(
        self,
        batch_size: int,
        iteration: int,
        scoreboard: Dict[str, Dict[str, Any]],
        primary_direction: str = "parameter",
    ) -> List[str]:
        if batch_size >= len(self.DIRECTIONS):
            plan = list(self.DIRECTIONS)[:batch_size]
            if primary_direction in plan and primary_direction != plan[0]:
                plan.remove(primary_direction)
                plan.insert(0, primary_direction)
            return plan
        if batch_size == 1:
            return [primary_direction if primary_direction in self.DIRECTIONS else "parameter"]

        plan = [primary_direction if primary_direction in self.DIRECTIONS else "parameter"]
        if batch_size == 2:
            plan.append(self._pick_gap_direction(scoreboard, exclude=set(plan), candidates=list(self.DIRECTIONS[1:])))
            return plan

        middle = "feature" if iteration % 2 else "model"
        tail = "data" if iteration % 2 else "risk"
        middle = self._pick_gap_direction(scoreboard, exclude=set(plan), candidates=[middle, "feature", "model"])
        plan.append(middle)
        tail = self._pick_gap_direction(scoreboard, exclude=set(plan), candidates=[tail, "data", "risk"])
        plan.append(tail)
        while len(plan) < batch_size:
            plan.append(self._pick_gap_direction(scoreboard, exclude=set(plan), candidates=list(self.DIRECTIONS)))
        return plan[:batch_size]

    def _pick_gap_direction(
        self,
        scoreboard: Dict[str, Dict[str, Any]],
        exclude: set,
        candidates: List[str],
    ) -> str:
        ranked = []
        for direction in candidates:
            if direction in exclude:
                continue
            row = scoreboard.get(direction) or {}
            timeout_count = int(row.get("timeout_count") or 0)
            coverage_gap = int(row.get("coverage_gap") or 0)
            ranked.append((
                1 if timeout_count == 0 else 0,
                coverage_gap - timeout_count,
                -int(row.get("attempts") or 0),
                direction,
            ))
        if not ranked:
            return "parameter"
        ranked.sort(reverse=True)
        return ranked[0][3]

    def _collect_groups(self, run_state: Dict[str, Any]) -> List[Dict[str, Any]]:
        groups: List[Dict[str, Any]] = []
        for item in run_state.get("iterations") or []:
            if not isinstance(item, dict):
                continue
            iteration = item.get("iteration") or item.get("iteration_no")
            batch_groups = item.get("batch_groups")
            if isinstance(batch_groups, list) and batch_groups:
                for group in batch_groups:
                    if isinstance(group, dict):
                        merged = dict(group)
                        merged.setdefault("iteration", iteration)
                        groups.append(merged)
            else:
                groups.append({
                    "iteration": iteration,
                    "target_direction": item.get("target_direction") or item.get("selected_layer"),
                    "selected_layer": item.get("selected_layer") or (item.get("sampled_layers") or [None])[0],
                    "status": item.get("status"),
                    "score_advantage": (item.get("evaluation") or {}).get("score_advantage"),
                    "error": item.get("error"),
                })
        latest = run_state.get("latest_batch_groups")
        if isinstance(latest, list):
            for group in latest:
                if isinstance(group, dict):
                    groups.append(dict(group))
        return groups

    def _role_for(self, idx: int, direction: str) -> str:
        if idx == 0:
            return "exploit"
        if direction in {"feature", "model"}:
            return "diversify"
        return "explore_risk"

    def _reason(
        self,
        direction: str,
        row: Dict[str, Any],
        active_layers: Optional[List[str]],
    ) -> str:
        parts = [
            f"target={direction}",
            f"attempts={int(row.get('attempts') or 0)}",
            f"coverage_gap={int(row.get('coverage_gap') or 0)}",
        ]
        if int(row.get("timeout_count") or 0) > 0:
            parts.append(f"timeouts={int(row.get('timeout_count') or 0)}")
        layer = self.DIRECTION_TO_LAYER[direction]
        if active_layers and layer not in {str(x) for x in active_layers}:
            parts.append("layer_not_active")
        return "; ".join(parts)

    def _safe_int(self, value: Any) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _safe_float(self, value: Any) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _recent_primary_stagnant(self, rows: List[Dict[str, Any]]) -> bool:
        if len(rows) < 3:
            return False
        values = []
        for row in rows:
            val = self._safe_float(row.get("mape_improvement") or row.get("score_advantage"))
            if val is not None:
                values.append(val)
        return len(values) >= 3 and max(values) <= 0

    def _proposal_source(self, run_state: Dict[str, Any]) -> str:
        latest = run_state.get("latest_auto_proposal")
        if isinstance(latest, dict):
            meta = latest.get("glm_meta") if isinstance(latest.get("glm_meta"), dict) else {}
            if int(meta.get("candidates_count") or 0) > 0:
                return "glm"
            if int(meta.get("memory_hit_count") or 0) > 0:
                return "memory"
        slots = run_state.get("candidate_planner_slots")
        if isinstance(slots, list) and slots:
            sources = {str(slot.get("candidate_source") or slot.get("source") or "") for slot in slots if isinstance(slot, dict)}
            if "glm" in sources:
                return "glm"
            if any("memory" in s for s in sources):
                return "memory"
            if any("registry" in s for s in sources):
                return "registry_rule"
        return "rule"
