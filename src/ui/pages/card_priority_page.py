#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Card priority and mode options page. (Fluent UI Refactored)"""

from __future__ import annotations

import os
from typing import Any

from PyQt5.QtCore import Qt as _Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QMessageBox,
    QVBoxLayout,
    QWidget,
    QDialog,
)

# ====== 引入 Fluent UI 现代组件 ======
from qfluentwidgets import (
    CardWidget, SubtitleLabel, BodyLabel, CaptionLabel,
    LineEdit, CheckBox, PushButton, PrimaryPushButton,
    SmoothScrollArea, FluentIcon as FIF
)

from src.config.paths import get_config_path
from src.config.paths import get_card_cost_dir
from src.config.config_repository import ConfigRepository
from src.config.effects_registry import get_triggers
from src.utils.card_filename import (
    is_evo_card_name,
    make_enhance_key,
    normalize_card_base_name,
    normalize_config_key,
    parse_card_filename,
)

# PyQt5 stubs vary across environments; keep Qt attribute access flexible.
Qt: Any = _Qt


class CardPriorityPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_widget: Any = parent
        self.config_data = self.load_config()
        self.card_widgets = []
        # Enhance rows share evolve priority with the base card row.
        self._base_evolve_priority_inputs = {}
        self._enhance_evolve_priority_views = {}
        self.init_ui()

    def _sync_enhance_evolve_priority_views(self, base_name: str, text: str) -> None:
        views = self._enhance_evolve_priority_views.get(str(base_name), [])
        for v in list(views):
            try:
                v.setText(text)
            except Exception:
                pass

    def init_ui(self):
        self.setObjectName("CardPriorityPage")
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # 标题区
        title_label = SubtitleLabel("卡牌策略与优先级设置", self)
        main_layout.addWidget(title_label)

        # 说明文字和帮助按钮 (放入一个漂亮的卡片中)
        header_card = CardWidget(self)
        desc_layout = QHBoxLayout(header_card)
        desc_layout.setContentsMargins(15, 10, 15, 10)
        
        desc_label = BodyLabel("💡 提示：在此为卡组中的卡片设置出牌优先级、进化优先级与强制留牌。需要配置特殊触发效果请点击“特殊效果...”。", self)
        desc_layout.addWidget(desc_label)
        desc_layout.addStretch()
        
        self.help_btn = PushButton(FIF.HELP, "配置说明帮助")
        self.help_btn.clicked.connect(self.show_card_settings_help)
        desc_layout.addWidget(self.help_btn)
        
        main_layout.addWidget(header_card)

        # ====== 滚动区域 ======
        self.scroll_area = SmoothScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { background-color: transparent; border: none; }")
        self.scroll_area.viewport().setStyleSheet("background-color: transparent;")
        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("ScrollContent")
        self.scroll_content.setStyleSheet("QWidget#ScrollContent { background-color: transparent; }")
        
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setSpacing(10) # 卡片之间的间距
        self.scroll_area.setWidget(self.scroll_content)
        main_layout.addWidget(self.scroll_area)

        # ====== 底部按钮区 ======
        btn_layout = QHBoxLayout()
        self.save_btn = PrimaryPushButton(FIF.SAVE, "保存所有设置")
        self.save_btn.clicked.connect(self.save_config)
        #不需要了
        #self.back_btn = PushButton(FIF.RETURN, "返回主界面")
        #self.back_btn.clicked.connect(self._go_back)
        
        btn_layout.addStretch()
        btn_layout.addWidget(self.save_btn)
        btn_layout.addSpacing(15)
        #btn_layout.addWidget(self.back_btn)
        btn_layout.addStretch()
        main_layout.addLayout(btn_layout)

        self.load_card_priority_settings()

    def _go_back(self) -> None:
        try:
            sw = getattr(self.parent_widget, "stacked_widget", None)
            if sw is not None and hasattr(sw, "setCurrentIndex"):
                sw.setCurrentIndex(0)
        except Exception:
            pass

    def _build_effects_tag(self, base_name: str, config_key: str, is_enhance: bool) -> str:
        try:
            from src.config.strategy_effects import get_card_effect_steps
        except Exception:
            return ""

        tags = []
        for t in get_triggers():
            tid = str(t.get("id") or "")
            short = str(t.get("short") or tid)
            if not tid:
                continue

            if tid == "on_play":
                key = str(config_key or base_name)
            else:
                if is_enhance:
                    continue
                key = str(base_name)

            steps = get_card_effect_steps(self.config_data, card_name=key, trigger=tid)
            if steps:
                tags.append(short)

        return "/".join(tags)

    def open_effects_editor(self, base_name: str, config_key: str, display_name: str, is_enhance: bool) -> None:
        try:
            from src.ui.pages.card_effects_editor import CardEffectsDialog
        except Exception as e:
            QMessageBox.warning(self, "错误", f"无法打开特殊效果编辑器: {str(e)}")
            return

        dlg = CardEffectsDialog(
            self,
            base_name=str(base_name or ""),
            config_key=str(config_key or base_name or ""),
            display_name=str(display_name or base_name or ""),
            is_enhance=bool(is_enhance),
        )
        res = dlg.exec_()
        if res == QDialog.Accepted:
            self.refresh_card_priority()

    def show_card_settings_help(self):
        help_text = """
【卡牌设置详细说明】

一、优先级设置
1. 出牌优先级（进化前/进化后）
   作用：控制出牌顺序，会根据进化是否解锁切换不同阶段的优先级。
   数值含义：数字越小优先级越高 (默认 999 最低)。
   示例：若“进化前=1、进化后=5”，则前期更倾向优先打出；进化解锁后优先级降低。

2. 进化优先级
   作用：控制进化/超进化时的选择顺序。
   数值含义：数字越小优先级越高 (默认 999 最低)。

二、留牌与特殊效果
1. 必留 (force_keep)
   作用：换牌阶段强制保留该基础卡（爆能档位共用）。

2. 特殊效果...
   作用：进入二级编辑器，按触发时机配置操作（出牌/攻击/进化等）。
"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("卡牌设置帮助")
        msg_box.setText(help_text.strip())
        msg_box.setIcon(QMessageBox.Information)
        msg_box.addButton(QMessageBox.Ok)
        msg_box.exec_()

    def load_config(self):
        config_path = get_config_path()
        cfg, _, _ = ConfigRepository(config_path).load_existing(allow_default_on_error=True)
        return cfg if isinstance(cfg, dict) else {}

    def load_card_priority_settings(self):
        # 清空现有内容
        for i in reversed(range(self.scroll_layout.count())):
            item = self.scroll_layout.itemAt(i)
            if item is None:
                continue
            widget = item.widget()
            if widget:
                widget.deleteLater()
                
        self.card_widgets = []
        self._base_evolve_priority_inputs = {}
        self._enhance_evolve_priority_views = {}

        card_dir = get_card_cost_dir(ensure=True)
        if not os.path.exists(card_dir):
            no_card_label = BodyLabel("未找到卡组卡片，请先在 '我的卡组' 页面配置工作区")
            no_card_label.setAlignment(Qt.AlignCenter)
            self.scroll_layout.addWidget(no_card_label)
            return

        card_files = [
            f for f in os.listdir(card_dir)
            if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
            and not is_evo_card_name(f)
        ]
        
        if not card_files:
            no_card_label = BodyLabel("当前卡组为空，请先添加卡片")
            no_card_label.setAlignment(Qt.AlignCenter)
            self.scroll_layout.addWidget(no_card_label)
            return

        entries = []
        for card_file in card_files:
            try:
                base_cost, enhance_costs, base_name = parse_card_filename(card_file)
            except Exception:
                base_cost, enhance_costs, base_name = 0, [], card_file.split("_", 1)[-1].rsplit(".", 1)[0]

            base_name = normalize_card_base_name(str(base_name or "").strip())
            if not base_name:
                continue
            enhance_costs = list(enhance_costs or [])

            entries.append({
                "file": card_file, "base_name": base_name,
                "config_key": normalize_config_key(base_name),
                "base_cost": int(base_cost or 0), "variant_cost": int(base_cost or 0),
                "is_enhance": False, "enhance_costs": enhance_costs,
            })
            for c in enhance_costs:
                entries.append({
                    "file": card_file, "base_name": base_name,
                    "config_key": normalize_config_key(make_enhance_key(base_name, c)),
                    "base_cost": int(base_cost or 0), "variant_cost": int(c),
                    "is_enhance": True, "enhance_costs": enhance_costs,
                })

        entries.sort(key=lambda e: (
            int(e.get("base_cost", 0)), str(e.get("base_name", "")),
            1 if bool(e.get("is_enhance")) else 0, int(e.get("variant_cost", 0)),
        ))

        for entry in entries:
            card_file = entry["file"]
            base_name = entry["base_name"]
            config_key = entry["config_key"]
            is_enhance = bool(entry.get("is_enhance"))
            variant_cost = int(entry.get("variant_cost", 0))

            # 使用 Fluent UI 的卡片容器包装每一行
            card_row = CardWidget()
            row_layout = QHBoxLayout(card_row)
            row_layout.setContentsMargins(15, 8, 15, 8)
            row_layout.setSpacing(12)

            # 图片
            from PyQt5.QtWidgets import QLabel
            card_label = QLabel()
            card_path = os.path.join(card_dir, card_file)
            pixmap = QPixmap(card_path)
            if not pixmap.isNull():
                pixmap = pixmap.scaled(60, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                card_label.setPixmap(pixmap)
            card_label.setAlignment(Qt.AlignCenter)
            row_layout.addWidget(card_label)

            # 名字
            display_name = f"{base_name} (爆能{variant_cost})" if is_enhance else f"{base_name}"
            name_label = BodyLabel(display_name)
            name_label.setMinimumWidth(160)
            row_layout.addWidget(name_label)

            high_priority = self.config_data.get("high_priority_cards", {}).get(config_key, {})

            # 出牌优先级（进化前）
            row_layout.addWidget(CaptionLabel("出牌(进化前):"))
            play_priority_pre_input = LineEdit()
            play_priority_pre_input.setPlaceholderText("999")
            play_priority_pre_input.setMaximumWidth(60)
            if isinstance(high_priority, dict):
                pre_priority = high_priority.get("priority_pre_evolution", high_priority.get("priority", ""))
                play_priority_pre_input.setText(str(pre_priority) if pre_priority != "" else "")
            row_layout.addWidget(play_priority_pre_input)

            # 出牌优先级（进化后）
            row_layout.addWidget(CaptionLabel("出牌(进化后):"))
            play_priority_post_input = LineEdit()
            play_priority_post_input.setPlaceholderText("999")
            play_priority_post_input.setMaximumWidth(60)
            if isinstance(high_priority, dict):
                post_priority = high_priority.get("priority_post_evolution", high_priority.get("priority", ""))
                play_priority_post_input.setText(str(post_priority) if post_priority != "" else "")
            row_layout.addWidget(play_priority_post_input)

            force_keep_checkbox = None
            evolve_priority_input = None
            evolve_priority_view = None

            if not is_enhance:
                # 必留
                row_layout.addSpacing(10)
                force_keep_checkbox = CheckBox("必留")
                base_cfg = self.config_data.get("high_priority_cards", {}).get(base_name, {})
                if isinstance(base_cfg, dict) and base_cfg.get("force_keep") is True:
                    force_keep_checkbox.setChecked(True)
                row_layout.addWidget(force_keep_checkbox)

                # 进化优先级
                row_layout.addWidget(CaptionLabel("进化优先级:"))
                evolve_priority_input = LineEdit()
                evolve_priority_input.setPlaceholderText("999")
                evolve_priority_input.setMaximumWidth(60)
                evolve_priority = self.config_data.get("evolve_priority_cards", {}).get(base_name, {})
                if isinstance(evolve_priority, dict):
                    evolve_priority_input.setText(str(evolve_priority.get("priority", "")))
                row_layout.addWidget(evolve_priority_input)

                self._base_evolve_priority_inputs[base_name] = evolve_priority_input
                evolve_priority_input.textChanged.connect(
                    lambda text, n=base_name: self._sync_enhance_evolve_priority_views(n, text)
                )
            else:
                row_layout.addSpacing(10)
                row_layout.addWidget(CaptionLabel("进化优先级(共用):"))
                evolve_priority_view = LineEdit()
                evolve_priority_view.setReadOnly(True)
                evolve_priority_view.setMaximumWidth(60)
                evolve_priority = self.config_data.get("evolve_priority_cards", {}).get(base_name, {})
                if isinstance(evolve_priority, dict):
                    evolve_priority_view.setText(str(evolve_priority.get("priority", "")))
                row_layout.addWidget(evolve_priority_view)

                self._enhance_evolve_priority_views.setdefault(base_name, []).append(evolve_priority_view)
                try:
                    base_input = self._base_evolve_priority_inputs.get(base_name)
                    if base_input is not None:
                        evolve_priority_view.setText(base_input.text())
                except Exception:
                    pass

            row_layout.addStretch(1)

            # 特殊效果 Tag 提示
            effects_tag = self._build_effects_tag(base_name, config_key, is_enhance)
            if effects_tag:
                tag_label = CaptionLabel(effects_tag)
                tag_label.setStyleSheet("color: #009FAA; font-weight: bold;") # 使用主题高亮色
                row_layout.addWidget(tag_label)

            # 特殊效果配置按钮
            effects_btn = PushButton(FIF.EDIT, "特殊效果...")
            effects_btn.clicked.connect(
                lambda _=False, b=base_name, k=config_key, d=display_name, enh=is_enhance: self.open_effects_editor(b, k, d, enh)
            )
            row_layout.addWidget(effects_btn)

            self.card_widgets.append({
                "card_name": base_name, "config_key": config_key, "is_enhance": is_enhance,
                "play_priority_pre": play_priority_pre_input, "play_priority_post": play_priority_post_input,
                "force_keep": force_keep_checkbox, "evolve_priority": evolve_priority_input,
                "evolve_priority_view": evolve_priority_view if is_enhance else None,
            })

            self.scroll_layout.addWidget(card_row)

        self.scroll_layout.addStretch()

    def refresh_card_priority(self):
        self.config_data = self.load_config()
        self.load_card_priority_settings()

    def save_config(self):
        try:
            if getattr(self.parent_widget, "is_script_running", lambda: False)():
                QMessageBox.warning(self, "运行中", "脚本运行中，禁止修改卡牌设置/配置。请先停止脚本后再保存。")
                return
        except Exception:
            pass

        high_priority_cards = {}
        evolve_priority_cards = {}
        
        for card in self.card_widgets:
            base_name = card.get("card_name", "")
            config_key = normalize_config_key(str(card.get("config_key") or base_name))
            is_enhance = bool(card.get("is_enhance"))

            name_for_msg = str(config_key or base_name)
            if is_enhance:
                try:
                    _b, _c = str(config_key).rsplit("@", 1)
                    if str(_b) == str(base_name):
                        name_for_msg = f"{base_name}(爆能{_c})"
                except Exception:
                    name_for_msg = str(config_key or base_name)

            play_pre_text = card["play_priority_pre"].text().strip()
            play_post_text = card["play_priority_post"].text().strip()
            
            if play_pre_text or play_post_text:
                pre_val, post_val = None, None
                if play_pre_text:
                    try:
                        pre_val = int(play_pre_text)
                        if pre_val < 0 or pre_val > 999: raise ValueError("必须在0-999之间")
                    except Exception as e:
                        QMessageBox.warning(self, "输入错误", f"'{name_for_msg}' 的出牌优先级(进化前)错误: {str(e)}")
                        return
                        
                if play_post_text:
                    try:
                        post_val = int(play_post_text)
                        if post_val < 0 or post_val > 999: raise ValueError("必须在0-999之间")
                    except Exception as e:
                        QMessageBox.warning(self, "输入错误", f"'{name_for_msg}' 的出牌优先级(进化后)错误: {str(e)}")
                        return

                if pre_val is None and post_val is not None: pre_val = post_val
                if post_val is None and pre_val is not None: post_val = pre_val

                high_priority_cards[config_key] = {
                    "priority_pre_evolution": pre_val,
                    "priority_post_evolution": post_val,
                }

            try:
                force_keep_widget = card.get("force_keep")
                force_keep_checked = bool(force_keep_widget is not None and force_keep_widget.isChecked())
            except Exception:
                force_keep_checked = False

            if force_keep_checked:
                base_cfg = high_priority_cards.get(base_name)
                if not isinstance(base_cfg, dict):
                    base_cfg = {}
                    high_priority_cards[base_name] = base_cfg
                base_cfg["force_keep"] = True

            evolve_widget = card.get("evolve_priority")
            if evolve_widget is not None:
                evolve_priority_text = evolve_widget.text().strip()
                if evolve_priority_text:
                    try:
                        priority = int(evolve_priority_text)
                        if priority < 0 or priority > 999: raise ValueError("必须在0-999之间")
                        evolve_priority_cards[base_name] = {"priority": priority}
                    except Exception as e:
                        QMessageBox.warning(self, "输入错误", f"'{base_name}' 的进化优先级错误: {str(e)}")
                        return

        config_path = get_config_path()
        repo = ConfigRepository(config_path)
        existing, parse_ok, parse_err = repo.load_existing(allow_default_on_error=False)
        
        if existing is None:
            QMessageBox.warning(self, "保存失败", f"config.json解析失败: {str(parse_err or '')}")
            return

        if high_priority_cards: existing["high_priority_cards"] = high_priority_cards
        elif "high_priority_cards" in existing: del existing["high_priority_cards"]

        if evolve_priority_cards: existing["evolve_priority_cards"] = evolve_priority_cards
        elif "evolve_priority_cards" in existing: del existing["evolve_priority_cards"]

        try:
            res = repo.replace_with_snapshot(existing, indent=4, ensure_ascii=False)
            if not res.ok: raise RuntimeError(res.error or "config write failed")
            
            QMessageBox.information(self, "成功", "卡牌设置已保存！")
            
            try:
                log_output = getattr(self.parent_widget, "log_output", None)
                if log_output is not None and hasattr(log_output, "append"):
                    log_output.append("[配置] 卡牌设置已更新")
            except Exception:
                pass
        except Exception as e:
            QMessageBox.warning(self, "保存失败", f"保存卡牌设置失败: {str(e)}")