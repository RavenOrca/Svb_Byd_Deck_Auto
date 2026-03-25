#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Config page (parameters/settings). Fluent UI Refactored."""

from __future__ import annotations

from typing import Any

from PyQt5.QtCore import Qt as _Qt
from PyQt5.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

# ====== 引入 Fluent UI 现代组件 ======
from qfluentwidgets import (
    CardWidget, SubtitleLabel, BodyLabel, CaptionLabel,
    LineEdit, ComboBox, PushButton, PrimaryPushButton,
    SmoothScrollArea, SwitchButton, FluentIcon as FIF
)

from src.config.paths import get_config_path
from src.config.config_repository import ConfigRepository


# PyQt5 stubs vary across environments; keep Qt attribute access flexible.
Qt: Any = _Qt


class ConfigPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_widget: Any = parent
        self.config_data = self.load_config()
        self.init_ui()

    def init_ui(self):
        self.setObjectName("ConfigPage")
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # 标题
        title_label = SubtitleLabel("高级参数设置", self)
        main_layout.addWidget(title_label)

        # ====== 丝滑的滚动区域 ======
        self.scroll_area = SmoothScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { background-color: transparent; border: none; }")
        self.scroll_area.viewport().setStyleSheet("background-color: transparent;") # 确保全局背景透视
        
        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("ScrollContent")
        self.scroll_content.setStyleSheet("QWidget#ScrollContent { background-color: transparent; }")
        
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        self.scroll_layout.setSpacing(15)
        self.scroll_area.setWidget(self.scroll_content)
        main_layout.addWidget(self.scroll_area, stretch=1)

        # ==========================================
        # 卡片 1: 拖拽速度设置
        # ==========================================
        drag_card = CardWidget(self.scroll_content)
        drag_layout = QVBoxLayout(drag_card)
        drag_layout.setContentsMargins(20, 15, 20, 15)
        drag_layout.setSpacing(10)
        
        drag_layout.addWidget(BodyLabel("拖拽速度设置 (单位:秒)"))
        
        drag_grid = QGridLayout()
        drag_grid.setHorizontalSpacing(20)
        drag_grid.setVerticalSpacing(10)

        drag_range = [0.10, 0.13]  # 默认值
        if "game" in self.config_data and "human_like_drag_duration_range" in self.config_data["game"]:
            drag_range = self.config_data["game"]["human_like_drag_duration_range"]

        drag_grid.addWidget(BodyLabel("最小拖拽时间:"), 0, 0)
        self.min_drag_input = LineEdit()
        self.min_drag_input.setText(str(drag_range[0]))
        self.min_drag_input.setMaximumWidth(150)
        drag_grid.addWidget(self.min_drag_input, 0, 1)

        drag_grid.addWidget(BodyLabel("最大拖拽时间:"), 0, 2)
        self.max_drag_input = LineEdit()
        self.max_drag_input.setText(str(drag_range[1]))
        self.max_drag_input.setMaximumWidth(150)
        drag_grid.addWidget(self.max_drag_input, 0, 3)

        drag_layout.addLayout(drag_grid)
        
        drag_desc = CaptionLabel("💡 说明: 设置更小的值会使操作更快，但由于行为过于机械化，可能被检测为脚本。")
        drag_desc.setStyleSheet("color: #D2691E;")
        drag_layout.addWidget(drag_desc)
        
        self.scroll_layout.addWidget(drag_card)

        # ==========================================
        # 卡片 2: 运行与自动重启设置
        # ==========================================
        run_card = CardWidget(self.scroll_content)
        run_layout = QVBoxLayout(run_card)
        run_layout.setContentsMargins(20, 15, 20, 15)
        run_layout.setSpacing(15)
        
        run_layout.addWidget(BodyLabel("运行异常接管与总控制"))

        # 读取配置
        auto_restart_config = self.config_data.get("auto_restart", {})
        self.auto_restart_enabled = auto_restart_config.get("enabled", True)
        stage_timeout_seconds = auto_restart_config.get("stage_timeout", 300)
        self.stage_timeout = int(stage_timeout_seconds) // 60
        if self.stage_timeout <= 0:
            self.stage_timeout = 5
        try:
            self.max_restarts = int(auto_restart_config.get("max_restarts", 3))
        except Exception:
            self.max_restarts = 3

        run_settings = self.config_data.get("run_settings", {})
        try:
            self.max_run_duration_minutes = int(run_settings.get("max_run_duration", 0) or 0) // 60
        except Exception:
            self.max_run_duration_minutes = 0

        # 开关区域
        switch_layout = QHBoxLayout()
        switch_layout.addWidget(BodyLabel("启用自动重启保护功能:"))
        self.restart_enabled_switch = SwitchButton()
        self.restart_enabled_switch.setChecked(self.auto_restart_enabled)
        self.restart_enabled_switch.checkedChanged.connect(self.on_restart_enabled_changed)
        switch_layout.addWidget(self.restart_enabled_switch)
        switch_layout.addStretch(1)
        run_layout.addLayout(switch_layout)

        # 输入网格区域
        run_grid = QGridLayout()
        run_grid.setHorizontalSpacing(20)
        run_grid.setVerticalSpacing(15)

        run_grid.addWidget(BodyLabel("无新阶段自动重启时间 (分钟):"), 0, 0)
        self.restart_time_input = LineEdit()
        self.restart_time_input.setText(str(self.stage_timeout))
        self.restart_time_input.setMaximumWidth(150)
        self.restart_time_input.setEnabled(self.auto_restart_enabled)
        run_grid.addWidget(self.restart_time_input, 0, 1)

        run_grid.addWidget(BodyLabel("自动重启最大允许次数:"), 0, 2)
        self.restart_count_input = LineEdit()
        self.restart_count_input.setText(str(self.max_restarts))
        self.restart_count_input.setMaximumWidth(150)
        self.restart_count_input.setEnabled(self.auto_restart_enabled)
        run_grid.addWidget(self.restart_count_input, 0, 3)

        run_grid.addWidget(BodyLabel("脚本总控运行最大时长 (分钟):"), 1, 0)
        self.runtime_limit_input = LineEdit()
        self.runtime_limit_input.setText(str(self.max_run_duration_minutes))
        self.runtime_limit_input.setMaximumWidth(150)
        run_grid.addWidget(self.runtime_limit_input, 1, 1)

        run_layout.addLayout(run_grid)

        run_desc = CaptionLabel(
            "💡 说明: 当游戏卡死或长时间停留同一阶段触发重启；达到最大重启次数后停止脚本。\n"
            "总时长若设为 0 表示不限制；到达总时长后脚本不会立刻强退，会优雅地在当前对战结束后停止。"
        )
        run_desc.setStyleSheet("color: #D2691E;")
        run_layout.addWidget(run_desc)

        self.scroll_layout.addWidget(run_card)

        # ==========================================
        # 卡片 3: 出牌与换牌策略设置
        # ==========================================
        play_card = CardWidget(self.scroll_content)
        play_layout = QVBoxLayout(play_card)
        play_layout.setContentsMargins(20, 15, 20, 15)
        play_layout.setSpacing(10)
        
        play_layout.addWidget(BodyLabel("换牌策略偏好"))

        strategy_layout = QHBoxLayout()
        strategy_layout.addWidget(BodyLabel("选择开局换牌策略:"))
        self.strategy_combo = ComboBox()
        self.strategy_combo.addItems(["3费档次", "4费档次", "5费档次"])
        self.strategy_combo.setMinimumWidth(150)

        current_strategy = self.config_data.get("game", {}).get("card_replacement_strategy", "3费档次")
        index = self.strategy_combo.findText(current_strategy)
        if index >= 0:
            self.strategy_combo.setCurrentIndex(index)
        strategy_layout.addWidget(self.strategy_combo)
        
        strategy_layout.addSpacing(15)
        self.strategy_help_btn = PushButton(FIF.HELP, "策略详细说明")
        self.strategy_help_btn.clicked.connect(self.show_strategy_help)
        strategy_layout.addWidget(self.strategy_help_btn)
        strategy_layout.addStretch(1)
        
        play_layout.addLayout(strategy_layout)

        strategy_desc = CaptionLabel("💡 说明: 根据所选费用档次策略自动进行起手换牌。每次切换策略后，需重启脚本方能生效。")
        strategy_desc.setStyleSheet("color: #D2691E;")
        play_layout.addWidget(strategy_desc)

        self.scroll_layout.addWidget(play_card)
        self.scroll_layout.addStretch(1)

        # ==========================================
        # 底部操作按钮
        # ==========================================
        btn_layout = QHBoxLayout()
        self.save_btn = PrimaryPushButton(FIF.SAVE, "保存所有设置")
        self.save_btn.clicked.connect(self.save_config)
        #self.back_btn = PushButton(FIF.RETURN, "返回主界面")
        #self.back_btn.clicked.connect(self._go_back)

        btn_layout.addStretch()
        btn_layout.addWidget(self.save_btn)
        btn_layout.addSpacing(15)
        #btn_layout.addWidget(self.back_btn)
        btn_layout.addStretch()

        main_layout.addLayout(btn_layout)

    def _go_back(self) -> None:
        try:
            sw = getattr(self.parent_widget, "stacked_widget", None)
            if sw is not None and hasattr(sw, "setCurrentIndex"):
                sw.setCurrentIndex(0)
        except Exception:
            pass

    def on_restart_enabled_changed(self, isChecked):
        """处理自动重启功能启用/禁用状态变化"""
        self.restart_time_input.setEnabled(isChecked)
        self.restart_count_input.setEnabled(isChecked)

    def show_strategy_help(self):
        """显示换牌策略说明"""
        help_text = """
【换牌策略详细说明】

[ 3费档次 ]
• 最优：前三张牌组合为 [1, 2, 3]
• 次优：牌序为 [2, 3]
• 目标：确保3费时能准时打出展开

[ 4费档次 ]
• 最优：四张牌组合为 [1, 2, 3, 4]
• 次优：牌序为 [2, 3, 4] 或 [2, 2, 4]
• 目标：确保4费时能有效站场

[ 5费档次 ]
• 优先级组合（从高到低）：
  [2,3,4,5] > [2,3,3,5] > [2,2,3,5] > [2,2,2,5]
• 目标：起手找核心5费卡，确保5费关键回合的爆发
"""
        msg = QMessageBox()
        msg.setWindowTitle("换牌策略说明")
        msg.setText(help_text.strip())
        msg.setIcon(QMessageBox.Information)
        msg.exec_()

    def load_config(self):
        """加载配置文件"""
        config_path = get_config_path()
        cfg, _, _ = ConfigRepository(config_path).load_existing(allow_default_on_error=True)
        return cfg if isinstance(cfg, dict) else {}

    def save_config(self):
        """保存配置到文件"""
        try:
            if getattr(self.parent_widget, "is_script_running", lambda: False)():
                QMessageBox.warning(self, "运行中", "脚本运行中，禁止修改配置。请先停止脚本后再保存。")
                return
        except Exception:
            pass

        try:
            min_drag = float(self.min_drag_input.text())
            max_drag = float(self.max_drag_input.text())

            if min_drag < 0 or max_drag < 0:
                raise ValueError("拖拽时间不能为负数")
            if min_drag > max_drag:
                raise ValueError("最小拖拽时间不能大于最大拖拽时间")

            if "game" not in self.config_data:
                self.config_data["game"] = {}
            self.config_data["game"]["human_like_drag_duration_range"] = [min_drag, max_drag]
        except Exception as e:
            QMessageBox.warning(self, "输入错误", f"拖拽时间设置错误: {str(e)}")
            return

        try:
            if "auto_restart" not in self.config_data:
                self.config_data["auto_restart"] = {}
            self.config_data["auto_restart"]["enabled"] = self.restart_enabled_switch.isChecked()

            if self.restart_enabled_switch.isChecked():
                restart_time = int(self.restart_time_input.text())
                if restart_time < 1 or restart_time > 120:
                    raise ValueError("自动重启时间必须在1-120分钟之间")
                self.config_data["auto_restart"]["stage_timeout"] = restart_time * 60

                max_restarts = int(self.restart_count_input.text())
                if max_restarts < 1 or max_restarts > 20:
                    raise ValueError("自动重启最大次数必须在1-20之间")
                self.config_data["auto_restart"]["max_restarts"] = max_restarts

            self.config_data["auto_restart"].pop("output_timeout", None)
            self.config_data["auto_restart"].pop("match_timeout", None)

            if "stage_timeout" not in self.config_data["auto_restart"]:
                self.config_data["auto_restart"]["stage_timeout"] = 300
            if "max_restarts" not in self.config_data["auto_restart"]:
                self.config_data["auto_restart"]["max_restarts"] = 3
        except Exception as e:
            QMessageBox.warning(self, "输入错误", f"自动重启设置错误: {str(e)}")
            return

        try:
            runtime_limit = int(self.runtime_limit_input.text())
            if runtime_limit < 0 or runtime_limit > 10080:
                raise ValueError("脚本运行总时长必须在0-10080分钟之间")
            if "run_settings" not in self.config_data:
                self.config_data["run_settings"] = {}
            self.config_data["run_settings"]["max_run_duration"] = runtime_limit * 60
            self.config_data["run_settings"].pop("max_battle_count", None)
            self.config_data["run_settings"].pop("force_close", None)
        except Exception as e:
            QMessageBox.warning(self, "输入错误", f"脚本总时长设置错误: {str(e)}")
            return

        strategy = self.strategy_combo.currentText()
        if "game" not in self.config_data:
            self.config_data["game"] = {}
        self.config_data["game"]["card_replacement_strategy"] = strategy

        config_path = get_config_path()
        try:
            repo = ConfigRepository(config_path)
            res = repo.update(self.config_data, indent=4, ensure_ascii=False)
            if not res.ok:
                raise RuntimeError(res.error or "config write failed")

            if res.parse_ok:
                QMessageBox.information(self, "成功", "全局高级配置已保存！")
            else:
                QMessageBox.information(self, "成功", "全局高级配置已保存（原config.json解析失败，已自动重建）")
            try:
                log_output = getattr(self.parent_widget, "log_output", None)
                if log_output is not None and hasattr(log_output, "append"):
                    log_output.append("[配置] 高级参数设置已更新并保存至本地文件")
            except Exception:
                pass
        except Exception as e:
            QMessageBox.warning(self, "保存失败", f"保存配置文件时出错: {str(e)}")

    def refresh_config_display(self):
        """刷新整个配置页面的显示 (供外部调用联动)"""
        self.config_data = self.load_config()

        drag_range = [0.10, 0.13]
        if "game" in self.config_data and "human_like_drag_duration_range" in self.config_data["game"]:
            drag_range = self.config_data["game"]["human_like_drag_duration_range"]
        self.min_drag_input.setText(str(drag_range[0]))
        self.max_drag_input.setText(str(drag_range[1]))

        auto_restart_config = self.config_data.get("auto_restart", {})
        self.auto_restart_enabled = auto_restart_config.get("enabled", True)
        stage_timeout_seconds = auto_restart_config.get("stage_timeout", 300)
        self.stage_timeout = int(stage_timeout_seconds) // 60
        if self.stage_timeout <= 0:
            self.stage_timeout = 5
        self.max_restarts = auto_restart_config.get("max_restarts", 3)
        
        self.restart_enabled_switch.setChecked(self.auto_restart_enabled)
        self.restart_time_input.setText(str(self.stage_timeout))
        self.restart_count_input.setText(str(self.max_restarts))
        self.restart_time_input.setEnabled(self.auto_restart_enabled)
        self.restart_count_input.setEnabled(self.auto_restart_enabled)

        run_settings = self.config_data.get("run_settings", {})
        try:
            self.max_run_duration_minutes = int(run_settings.get("max_run_duration", 0) or 0) // 60
        except Exception:
            self.max_run_duration_minutes = 0
        self.runtime_limit_input.setText(str(self.max_run_duration_minutes))

        current_strategy = self.config_data.get("game", {}).get("card_replacement_strategy", "3费档次")
        index = self.strategy_combo.findText(current_strategy)
        if index >= 0:
            self.strategy_combo.setCurrentIndex(index)