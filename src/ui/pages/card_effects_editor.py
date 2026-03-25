#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Card effects editor (Step3A 2nd-level UI) - Fluent UI Refactored.

This dialog edits `strategy.effects` using the Step3A op schema.
It only depends on lightweight config registries (no cv/u2/game imports).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import Qt as _Qt
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

# ====== 引入 Fluent UI 现代组件 ======
from qfluentwidgets import (
    MessageBoxBase, CheckBox, ComboBox, SpinBox, DoubleSpinBox, LineEdit,
    PushButton, SmoothScrollArea, CardWidget, BodyLabel, SubtitleLabel, 
    CaptionLabel, StrongBodyLabel, FluentIcon as FIF
)

from src.config.config_repository import ConfigRepository
from src.config.effects_registry import (
    CONTEXT_HAND_CARD,
    get_operation,
    get_operations,
    get_target_kind,
    get_target_kinds,
    get_triggers,
)
from src.config.paths import get_config_path
from src.config.strategy_effects import (
    convert_legacy_action_to_ops,
    convert_legacy_target_type_to_ops,
    get_card_effect_steps,
)

# PyQt5 stubs vary across environments; keep Qt attribute access flexible.
Qt: Any = _Qt

def _safe_int(v: Any, default: int = 0) -> int:
    try:
        return int(v)
    except Exception:
        return int(default)

def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)

def _norm_select_option(v: Any) -> Optional[int]:
    if v in (1, "1", "选项1", "Option1", "option1"):
        return 1
    if v in (2, "2", "选项2", "Option2", "option2"):
        return 2
    return None

class TargetSpecEditor(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._param_widgets: Dict[str, Any] = {}

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(BodyLabel("目标:"))

        self.kind_combo = ComboBox()
        for kd in get_target_kinds():
            # 【修复】：显式指定 userData
            self.kind_combo.addItem(str(kd.get("label") or kd.get("kind") or ""), userData=str(kd.get("kind") or ""))
        self.kind_combo.currentIndexChanged.connect(self._rebuild_selector)
        layout.addWidget(self.kind_combo)

        self.selector_combo = ComboBox()
        self.selector_combo.currentIndexChanged.connect(self._rebuild_params)
        layout.addWidget(self.selector_combo)

        self.params_container = QWidget()
        self.params_layout = QHBoxLayout(self.params_container)
        self.params_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.params_container)

        layout.addStretch()
        self._rebuild_selector()

    def _current_kind(self) -> str:
        return str(self.kind_combo.currentData() or "")

    def _current_selector(self) -> str:
        return str(self.selector_combo.currentData() or "")

    def _rebuild_selector(self) -> None:
        kind = self._current_kind()
        kd = get_target_kind(kind)
        selectors = []
        if isinstance(kd, dict):
            selectors = kd.get("selectors") or []

        self.selector_combo.blockSignals(True)
        self.selector_combo.clear()
        for sd in selectors:
            if not isinstance(sd, dict):
                continue
            self.selector_combo.addItem(str(sd.get("label") or sd.get("id") or ""), userData=str(sd.get("id") or ""))
        self.selector_combo.blockSignals(False)
        self._rebuild_params()

    def _clear_params(self) -> None:
        while self.params_layout.count():
            item = self.params_layout.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.deleteLater()
        self._param_widgets = {}

    def _rebuild_params(self) -> None:
        self._clear_params()
        kind = self._current_kind()
        selector = self._current_selector()
        kd = get_target_kind(kind)
        params_schema = []
        if isinstance(kd, dict):
            for sd in kd.get("selectors") or []:
                if not isinstance(sd, dict):
                    continue
                if str(sd.get("id") or "") == selector:
                    params_schema = sd.get("params_schema") or []
                    break

        for p in params_schema:
            if not isinstance(p, dict):
                continue
            w = _build_param_widget(p)
            if w is None:
                continue
            name = str(p.get("name") or "")
            if name:
                self._param_widgets[name] = (p, w)
            self.params_layout.addWidget(w)
        self.params_layout.addStretch()

    def load(self, target_spec: Any) -> None:
        if not isinstance(target_spec, dict):
            target_spec = {}
        kind = str(target_spec.get("kind") or "")
        selector = str(target_spec.get("selector") or "")
        params = target_spec.get("params")
        if not isinstance(params, dict):
            params = {}

        idx = self.kind_combo.findData(kind)
        if idx >= 0:
            self.kind_combo.setCurrentIndex(idx)
        else:
            self.kind_combo.setCurrentIndex(0)
        self._rebuild_selector()

        sidx = self.selector_combo.findData(selector)
        if sidx >= 0:
            self.selector_combo.setCurrentIndex(sidx)
        else:
            self.selector_combo.setCurrentIndex(0)
        self._rebuild_params()

        for name, (spec, w) in list(self._param_widgets.items()):
            if name in params:
                _set_param_widget_value(spec, w, params.get(name))

    def value(self) -> Dict[str, Any]:
        kind = self._current_kind()
        selector = self._current_selector()

        params: Dict[str, Any] = {}
        for name, (spec, w) in list(self._param_widgets.items()):
            params[name] = _get_param_widget_value(spec, w)

        return {"kind": kind, "selector": selector, "params": params}

def _build_param_widget(param_spec: Dict[str, Any]) -> Optional[QWidget]:
    ptype = str(param_spec.get("type") or "")
    label = str(param_spec.get("label") or param_spec.get("name") or "")

    if ptype == "bool":
        cb = CheckBox(label)
        cb.setChecked(bool(param_spec.get("default", False)))
        return cb

    if ptype == "int":
        compact = bool(param_spec.get("compact", False))
        min_v = _safe_int(param_spec.get("min", -10**9), -10**9)
        max_v = _safe_int(param_spec.get("max", 10**9), 10**9)
        default_v = _safe_int(param_spec.get("default", 0), 0)

        if compact:
            w = QWidget()
            lay = QHBoxLayout(w)
            lay.setContentsMargins(0, 0, 0, 0)
            if label:
                lay.addWidget(BodyLabel(label))
            box = SpinBox()
            box.setRange(min_v, max_v)
            box.setValue(default_v)
            box.setMaximumWidth(80)
            lay.addWidget(box)
            return w

        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        if label:
            lay.addWidget(BodyLabel(f"{label}:"))
        box = SpinBox()
        box.setRange(min_v, max_v)
        box.setValue(default_v)
        box.setMaximumWidth(150)
        lay.addWidget(box)
        return w

    if ptype == "float":
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        if label:
            lay.addWidget(BodyLabel(f"{label}:"))
        box = DoubleSpinBox()
        box.setDecimals(3)
        box.setRange(_safe_float(param_spec.get("min", -10**9), -10**9), _safe_float(param_spec.get("max", 10**9), 10**9))
        box.setValue(_safe_float(param_spec.get("default", 0.0), 0.0))
        box.setMaximumWidth(170)
        lay.addWidget(box)
        return w

    if ptype == "str":
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        if label:
            lay.addWidget(BodyLabel(f"{label}:"))
        le = LineEdit()
        le.setText(str(param_spec.get("default", "") or ""))
        le.setMaximumWidth(220)
        lay.addWidget(le)
        return w

    if ptype == "enum":
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        if label:
            lay.addWidget(BodyLabel(f"{label}:"))
        combo = ComboBox()
        for opt in param_spec.get("options") or []:
            if not isinstance(opt, dict):
                continue
            combo.addItem(str(opt.get("label") or opt.get("value") or ""), userData=opt.get("value"))
        default = param_spec.get("default")
        didx = combo.findData(default)
        if didx >= 0:
            combo.setCurrentIndex(didx)
        lay.addWidget(combo)
        return w

    if ptype == "target_spec":
        return TargetSpecEditor()

    return None

def _find_inner_widget(container: QWidget, widget_type: Any) -> Optional[Any]:
    try:
        return container.findChild(widget_type)
    except Exception:
        return None

def _set_param_widget_value(param_spec: Dict[str, Any], widget: QWidget, value: Any) -> None:
    ptype = str(param_spec.get("type") or "")
    if ptype == "bool" and isinstance(widget, CheckBox):
        widget.setChecked(bool(value))
        return
    if ptype == "int":
        box = _find_inner_widget(widget, SpinBox)
        if box is not None:
            box.setValue(_safe_int(value, box.value()))
        return
    if ptype == "float":
        box = _find_inner_widget(widget, DoubleSpinBox)
        if box is not None:
            box.setValue(_safe_float(value, box.value()))
        return
    if ptype == "str":
        le = _find_inner_widget(widget, LineEdit)
        if le is not None:
            le.setText(str(value or ""))
        return
    if ptype == "enum":
        combo = _find_inner_widget(widget, ComboBox)
        if combo is not None:
            idx = combo.findData(value)
            if idx >= 0:
                combo.setCurrentIndex(idx)
        return
    if ptype == "target_spec" and isinstance(widget, TargetSpecEditor):
        widget.load(value)
        return

def _get_param_widget_value(param_spec: Dict[str, Any], widget: QWidget) -> Any:
    ptype = str(param_spec.get("type") or "")
    if ptype == "bool" and isinstance(widget, CheckBox):
        return bool(widget.isChecked())
    if ptype == "int":
        box = _find_inner_widget(widget, SpinBox)
        if box is not None:
            return int(box.value())
        return _safe_int(param_spec.get("default", 0), 0)
    if ptype == "float":
        box = _find_inner_widget(widget, DoubleSpinBox)
        if box is not None:
            return float(box.value())
    if ptype == "str":
        le = _find_inner_widget(widget, LineEdit)
        return str(le.text()) if le is not None else ""
    if ptype == "enum":
        combo = _find_inner_widget(widget, ComboBox)
        return combo.currentData() if combo is not None else None
    if ptype == "target_spec" and isinstance(widget, TargetSpecEditor):
        return widget.value()
    return None

class StepRow(QWidget):
    def __init__(self, *, context_kind: str, step: Dict[str, Any], on_move_up, on_move_down, on_delete, parent=None):
        super().__init__(parent)
        self.context_kind = str(context_kind or "")
        self._on_move_up = on_move_up
        self._on_move_down = on_move_down
        self._on_delete = on_delete
        self._param_widgets: Dict[str, Any] = {}

        self.op_spec: Dict[str, Any] = dict(step or {})
        if "op" not in self.op_spec:
            self.op_spec["op"] = ""

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(BodyLabel("操作:"))
        self.op_combo = ComboBox()
        for op_def in get_operations(context_kind=self.context_kind):
            self.op_combo.addItem(str(op_def.get("label") or op_def.get("op_id") or ""), userData=str(op_def.get("op_id") or ""))
        layout.addWidget(self.op_combo)

        self.params_container = QWidget()
        self.params_layout = QHBoxLayout(self.params_container)
        self.params_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.params_container)
        layout.addStretch()

        btn_up = PushButton("↑")
        btn_up.setMaximumWidth(40)
        btn_up.clicked.connect(lambda: self._on_move_up(self))
        layout.addWidget(btn_up)

        btn_down = PushButton("↓")
        btn_down.setMaximumWidth(40)
        btn_down.clicked.connect(lambda: self._on_move_down(self))
        layout.addWidget(btn_down)

        btn_del = PushButton(FIF.DELETE, "删除")
        btn_del.setMaximumWidth(80)
        btn_del.clicked.connect(lambda: self._on_delete(self))
        layout.addWidget(btn_del)

        op_id = str(self.op_spec.get("op") or "")
        idx = self.op_combo.findData(op_id)
        if idx >= 0:
            self.op_combo.setCurrentIndex(idx)
        else:
            self.op_combo.setCurrentIndex(0)
            self.op_spec["op"] = str(self.op_combo.currentData() or "")

        self.op_combo.currentIndexChanged.connect(self._on_op_changed)
        self._rebuild_params()

    def _on_op_changed(self) -> None:
        self.op_spec["op"] = str(self.op_combo.currentData() or "")
        self.op_spec = {"op": self.op_spec["op"]}
        self._rebuild_params()

    def _clear_params(self) -> None:
        while self.params_layout.count():
            item = self.params_layout.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.deleteLater()
        self._param_widgets = {}

    def _rebuild_params(self) -> None:
        self._clear_params()
        op_id = str(self.op_combo.currentData() or "")
        op_def = get_operation(op_id)
        params_schema = []
        if isinstance(op_def, dict):
            params_schema = op_def.get("params_schema") or []

        for p in params_schema:
            if not isinstance(p, dict):
                continue
            w = _build_param_widget(p)
            if w is None:
                continue
            name = str(p.get("name") or "")
            if name:
                self._param_widgets[name] = (p, w)

            if name in self.op_spec:
                _set_param_widget_value(p, w, self.op_spec.get(name))
            elif "default" in p:
                _set_param_widget_value(p, w, p.get("default"))
            self.params_layout.addWidget(w)
        self.params_layout.addStretch()

    def value(self) -> Dict[str, Any]:
        op_id = str(self.op_combo.currentData() or "")
        out: Dict[str, Any] = {"op": op_id}
        for name, (spec, w) in list(self._param_widgets.items()):
            out[name] = _get_param_widget_value(spec, w)
        return out

class RawStepRow(QWidget):
    def __init__(self, *, raw_step: Dict[str, Any], on_delete, parent=None):
        super().__init__(parent)
        self.raw_step = dict(raw_step or {})
        self._on_delete = on_delete

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(CaptionLabel("未知Step:"))
        preview = json.dumps(self.raw_step, ensure_ascii=False, sort_keys=True)
        lab = CaptionLabel(preview)
        lab.setToolTip(preview)
        lab.setStyleSheet("color: #D2691E;")
        layout.addWidget(lab)
        layout.addStretch()

        btn_del = PushButton(FIF.DELETE, "删除")
        btn_del.setMaximumWidth(80)
        btn_del.clicked.connect(lambda: self._on_delete(self))
        layout.addWidget(btn_del)

    def value(self) -> Dict[str, Any]:
        return dict(self.raw_step)

class TriggerEditor(QWidget):
    def __init__(self, *, trigger_id: str, context_kind: str, parent=None):
        super().__init__(parent)
        self.trigger_id = str(trigger_id or "")
        self.context_kind = str(context_kind or "")
        self.rows: List[QWidget] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.rows_container = QWidget()
        self.rows_layout = QVBoxLayout(self.rows_container)
        self.rows_layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.rows_container)

        btn_add = PushButton("添加新操作步骤")
        btn_add.clicked.connect(self.add_step)
        layout.addWidget(btn_add)

    def _move_row(self, row: QWidget, delta: int) -> None:
        try:
            idx = self.rows.index(row)
        except Exception:
            return
        new_idx = idx + int(delta)
        if new_idx < 0 or new_idx >= len(self.rows):
            return
        self.rows[idx], self.rows[new_idx] = self.rows[new_idx], self.rows[idx]
        self._rebuild_layout()

    def _delete_row(self, row: QWidget) -> None:
        try:
            self.rows.remove(row)
        except Exception:
            return
        try:
            row.deleteLater()
        except Exception:
            pass
        self._rebuild_layout()

    def _rebuild_layout(self) -> None:
        while self.rows_layout.count():
            item = self.rows_layout.takeAt(0)
            w = item.widget() if item is not None else None
            if w is not None:
                w.setParent(None)

        for r in self.rows:
            self.rows_layout.addWidget(r)
        self.rows_layout.addStretch()

    def clear(self) -> None:
        for r in list(self.rows):
            try:
                r.deleteLater()
            except Exception:
                pass
        self.rows = []
        self._rebuild_layout()

    def add_step(self, step: Optional[Dict[str, Any]] = None) -> None:
        step = dict(step or {})
        op_id = str(step.get("op") or "")
        op_def = get_operation(op_id) if op_id else None
        if not op_id or not isinstance(op_def, dict):
            ops = get_operations(context_kind=self.context_kind)
            if ops:
                step = {"op": str(ops[0].get("op_id") or "")}
        row = StepRow(
            context_kind=self.context_kind,
            step=step,
            on_move_up=lambda r: self._move_row(r, -1),
            on_move_down=lambda r: self._move_row(r, 1),
            on_delete=self._delete_row,
        )
        self.rows.append(row)
        self._rebuild_layout()

    def add_raw_step(self, raw_step: Dict[str, Any]) -> None:
        row = RawStepRow(raw_step=raw_step, on_delete=self._delete_row)
        self.rows.append(row)
        self._rebuild_layout()

    def load_steps(self, steps: List[Dict[str, Any]]) -> None:
        self.clear()
        for step in steps or []:
            if not isinstance(step, dict):
                continue
            op_id = step.get("op")
            if isinstance(op_id, str) and op_id:
                if op_id == "legacy_target_type":
                    for c in convert_legacy_target_type_to_ops(step.get("target_type")):
                        self.add_step(c)
                    continue
                if op_id == "legacy_action":
                    for c in convert_legacy_action_to_ops(step.get("action")):
                        self.add_step(c)
                    continue
                op_def = get_operation(op_id)
                if isinstance(op_def, dict):
                    self.add_step(step)
                else:
                    self.add_raw_step(step)
                continue

            used_any = False
            if "select_option" in step:
                opt = _norm_select_option(step.get("select_option"))
                if opt is not None:
                    self.add_step({"op": "select_option", "index": int(opt)})
                    used_any = True
            if "target_type" in step:
                converted = convert_legacy_target_type_to_ops(step.get("target_type"))
                for c in converted:
                    self.add_step(c)
                    used_any = True
            if "action" in step:
                converted = convert_legacy_action_to_ops(step.get("action"))
                for c in converted:
                    self.add_step(c)
                    used_any = True

            if not used_any:
                self.add_raw_step(step)

    def value(self) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for r in self.rows:
            try:
                out.append(r.value())
            except Exception:
                continue
        return [s for s in out if isinstance(s, dict) and s]

class CardEffectsDialog(MessageBoxBase):
    """全局亚克力遮罩的高级特殊效果编辑弹窗"""
    def __init__(self, parent=None, *, base_name: str, config_key: str, display_name: str, is_enhance: bool):
        super().__init__(parent)
        self.base_name = str(base_name or "")
        self.config_key = str(config_key or base_name or "")
        self.display_name = str(display_name or base_name or "")
        self.is_enhance = bool(is_enhance)

        # 调整弹窗大小
        self.widget.setMinimumSize(920, 600)
        self.repo = ConfigRepository(get_config_path())

        # 设置底部按钮文本
        self.yesButton.setText("保存设置")
        self.cancelButton.setText("取消")

        self.viewLayout.setSpacing(15)

        # 标题
        title = SubtitleLabel(f"特殊效果 - {self.display_name}", self)
        self.viewLayout.addWidget(title)

        # 提示区域
        hint_card = CardWidget()
        hint_lay = QVBoxLayout(hint_card)
        hint_lay.setContentsMargins(15, 10, 15, 10)
        hint = BodyLabel(
            "💡 选择触发时机，并为每个触发时机配置操作序列。\n"
            "· 基础卡可配置通用触发；爆能档位可配置仅该档位生效的触发。\n"
            "· 爆能档位默认继承本体同触发效果；若配置了同类效果则以爆能档位覆盖。\n"
            "· 身材BUFF与攻击次数BUFF已拆分为两个独立操作；请分别配置。"
        )
        hint_lay.addWidget(hint)
        
        if self.is_enhance:
            enhance_notice = StrongBodyLabel("⚠️ 当前为爆能档位配置：可设置该爆能档位专属的触发效果。")
            enhance_notice.setStyleSheet("color: #D2691E;")
            hint_lay.addWidget(enhance_notice)
            
        self.viewLayout.addWidget(hint_card)

        # 触发时机多选区
        trig_card = CardWidget()
        trig_bar = QHBoxLayout(trig_card)
        trig_bar.setContentsMargins(15, 10, 15, 10)
        trig_bar.addWidget(StrongBodyLabel("请勾选需要的触发时机:"))
        
        self.trig_checks: Dict[str, CheckBox] = {}
        self.trig_groups: Dict[str, CardWidget] = {}
        self.trig_editors: Dict[str, TriggerEditor] = {}

        allowed = []
        for t in get_triggers():
            if not isinstance(t, dict):
                continue
            tid = str(t.get("id") or "")
            if not tid:
                continue
            allowed.append(t)

        for t in allowed:
            tid = str(t.get("id") or "")
            cb = CheckBox(str(t.get("label") or tid))
            cb.stateChanged.connect(lambda _v, x=tid: self._toggle_trigger(x))
            trig_bar.addWidget(cb)
            self.trig_checks[tid] = cb
            
        trig_bar.addStretch()
        self.viewLayout.addWidget(trig_card)

        # 丝滑滚动区域
        scroll = SmoothScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { background-color: transparent; border: none; }")
        scroll.viewport().setStyleSheet("background-color: transparent;")
        
        scroll_content = QWidget()
        scroll_content.setStyleSheet("QWidget { background-color: transparent; }")
        self.scroll_layout = QVBoxLayout(scroll_content)
        scroll.setWidget(scroll_content)
        self.viewLayout.addWidget(scroll)

        # 构建每个触发时机的编辑器卡片
        for t in allowed:
            tid = str(t.get("id") or "")
            ck = str(t.get("context_kind") or "")

            group = CardWidget()
            group_lay = QVBoxLayout(group)
            group_lay.setContentsMargins(15, 15, 15, 15)
            
            group_title = SubtitleLabel(f"🎯 {str(t.get('label') or tid)}")
            group_lay.addWidget(group_title)
            
            editor = TriggerEditor(trigger_id=tid, context_kind=ck)
            group_lay.addWidget(editor)

            self.scroll_layout.addWidget(group)
            self.trig_groups[tid] = group
            self.trig_editors[tid] = editor

        self.scroll_layout.addStretch()
        self._load_existing()

    def _key_for_trigger(self, trigger_id: str) -> str:
        if self.is_enhance:
            return self.config_key
        t = None
        for d in get_triggers():
            if str(d.get("id") or "") == str(trigger_id or ""):
                t = d
                break
        ck = str(t.get("context_kind") or "") if isinstance(t, dict) else ""
        if ck == CONTEXT_HAND_CARD:
            return self.config_key
        return self.base_name

    def _load_existing(self) -> None:
        cfg, parse_ok, err = self.repo.load_existing(allow_default_on_error=False)
        if cfg is None:
            QMessageBox.warning(self, "加载失败", f"config.json解析失败: {str(err or '')}")
            return

        effects = cfg.get("strategy", {}).get("effects", {})
        if not isinstance(effects, dict):
            effects = {}

        for tid, cb in list(self.trig_checks.items()):
            key = self._key_for_trigger(tid)
            card_eff = effects.get(key)
            if not isinstance(card_eff, dict):
                card_eff = {}
            steps = card_eff.get(tid)
            enabled = isinstance(steps, list) and any(isinstance(s, dict) for s in steps)
            cb.setChecked(bool(enabled))

            editor = self.trig_editors.get(tid)
            if editor is None:
                continue
            raw_steps = get_card_effect_steps(cfg, card_name=key, trigger=tid)
            editor.load_steps(list(raw_steps or []))

        for tid in list(self.trig_checks.keys()):
            self._toggle_trigger(tid)

    def _toggle_trigger(self, trigger_id: str) -> None:
        cb = self.trig_checks.get(trigger_id)
        group = self.trig_groups.get(trigger_id)
        if cb is None or group is None:
            return
        enabled = bool(cb.isChecked())
        group.setVisible(enabled)

        if enabled:
            editor = self.trig_editors.get(trigger_id)
            if editor is not None and not getattr(editor, "rows", None):
                try:
                    editor.add_step()
                except Exception:
                    pass

    # 重写 validate 方法，接管 MessageBoxBase 默认的确认逻辑
    def validate(self) -> bool:
        return self._save()

    def _save(self) -> bool:
        cfg, parse_ok, err = self.repo.load_existing(allow_default_on_error=False)
        if cfg is None:
            QMessageBox.warning(self, "保存失败", f"config.json解析失败: {str(err or '')}")
            return False

        strategy = cfg.get("strategy")
        if not isinstance(strategy, dict):
            strategy = {}
            cfg["strategy"] = strategy
        effects = strategy.get("effects")
        if not isinstance(effects, dict):
            effects = {}
            strategy["effects"] = effects

        for tid, cb in list(self.trig_checks.items()):
            key = self._key_for_trigger(tid)
            card_eff = effects.get(key)
            if not isinstance(card_eff, dict):
                card_eff = {}

            if cb.isChecked():
                editor = self.trig_editors.get(tid)
                steps = editor.value() if editor is not None else []
                steps = [s for s in steps if isinstance(s, dict) and s]
                if steps:
                    card_eff[tid] = steps
                elif tid in card_eff:
                    del card_eff[tid]
            else:
                if tid in card_eff:
                    del card_eff[tid]

            if card_eff:
                effects[key] = card_eff
            else:
                if key in effects:
                    del effects[key]

        res = self.repo.replace_with_snapshot(cfg, indent=4, ensure_ascii=False)
        if not res.ok:
            QMessageBox.warning(self, "保存失败", f"保存失败: {str(res.error or '')}")
            return False

        return True