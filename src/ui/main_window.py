#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Main PyQt window (Fluent UI Refactored).

This module contains the main window and wires pages + worker threads.
"""

from __future__ import annotations

import json
import os
import sys
import time

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QIcon
from PyQt5.QtGui import QIcon, QPainter, QPixmap, QColor
from qfluentwidgets import isDarkTheme
from PyQt5.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

# 引入 Fluent UI 组件
from qfluentwidgets import (
    FluentWindow, NavigationItemPosition, SubtitleLabel, BodyLabel, 
    StrongBodyLabel, LineEdit, ComboBox, SwitchButton, PrimaryPushButton, 
    PushButton, TextEdit, CardWidget, FluentIcon as FIF, setTheme, Theme
)

from src.config.paths import get_config_path
from src.config.config_repository import ConfigRepository
from src.ui.common import deep_update_dict, get_exe_dir
from src.ui.deck_store import DeckStore
from src.ui.pages.card_priority_page import CardPriorityPage
from src.ui.pages.card_select_page import CardSelectPage
from src.ui.pages.config_page import ConfigPage
from src.ui.pages.my_deck_page import MyDeckPage
from src.ui.pages.share_page import SharePage
from src.ui.workers.log_listener import LogListener
from src.ui.workers.script_runner import ScriptRunner


class HomeInterface(QWidget):
    """现代化的主控面板界面"""
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("HomeInterface")
        
        self.vbox = QVBoxLayout(self)
        self.vbox.setContentsMargins(20, 20, 20, 20)
        self.vbox.setSpacing(20)
        
        # === 卡片 1：设备与基础配置 ===
        self.setup_card = CardWidget(self)
        setup_layout = QVBoxLayout(self.setup_card)
        setup_layout.setContentsMargins(20, 20, 20, 20)
        setup_layout.setSpacing(15)
        
        setup_title = SubtitleLabel("设备与基础配置", self.setup_card)
        setup_layout.addWidget(setup_title)
        
        grid1 = QGridLayout()
        grid1.setVerticalSpacing(15)
        grid1.setHorizontalSpacing(20)
        
        grid1.addWidget(BodyLabel("服务器:"), 0, 0)
        self.server_combo = ComboBox()
        self.server_combo.addItems(["国服", "国际服"])
        self.server_combo.setFixedWidth(120)
        grid1.addWidget(self.server_combo, 0, 1)
        
        grid1.addWidget(BodyLabel("ADB 端口:"), 0, 2)
        self.adb_input = LineEdit()
        self.adb_input.setText("127.0.0.1:16384")
        self.adb_input.setFixedWidth(200)
        grid1.addWidget(self.adb_input, 0, 3)
        
        grid1.addWidget(BodyLabel("深色识别:"), 1, 0)
        self.deep_color_switch = SwitchButton()
        grid1.addWidget(self.deep_color_switch, 1, 1)
        
        grid1.addWidget(BodyLabel("庆典模式:"), 1, 2)
        self.gala_mode_switch = SwitchButton()
        grid1.addWidget(self.gala_mode_switch, 1, 3)
        
        grid1.addWidget(BodyLabel("启用空过:"), 1, 4)
        self.auto_pass_switch = SwitchButton()
        grid1.addWidget(self.auto_pass_switch, 1, 5)
        
        setup_layout.addLayout(grid1)
        self.vbox.addWidget(self.setup_card)
        
        # === 卡片 2：控制台与运行状态 ===
        self.control_card = CardWidget(self)
        control_layout = QHBoxLayout(self.control_card)
        control_layout.setContentsMargins(20, 20, 20, 20)
        
        status_layout = QVBoxLayout()
        status_layout.setSpacing(10)
        
        self.status_label = StrongBodyLabel("当前状态: 未连接")
        self.status_label.setStyleSheet("color: #FF5555;") 
        
        self.run_time_label = BodyLabel("运行时间: 00:00:00")
        self.battle_count_label = BodyLabel("对战次数: 0")
        
        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.run_time_label)
        status_layout.addWidget(self.battle_count_label)
        status_layout.addStretch(1)
        
        control_layout.addLayout(status_layout)
        
        btn_layout = QGridLayout()
        btn_layout.setHorizontalSpacing(15)
        btn_layout.setVerticalSpacing(15)
        
        self.connect_btn = PrimaryPushButton(FIF.LINK, "连接设备")
        self.start_btn = PushButton(FIF.PLAY, "开始运行")
        self.pause_btn = PushButton(FIF.PAUSE, "暂停运行")
        self.resume_btn = PushButton(FIF.PLAY, "恢复运行")
        self.stop_btn = PushButton(FIF.POWER_BUTTON, "停止运行")
        
        self.start_btn.setEnabled(False)
        self.pause_btn.setEnabled(False)
        self.resume_btn.setEnabled(False)
        self.stop_btn.setEnabled(False)
        
        btn_layout.addWidget(self.connect_btn, 0, 0)
        btn_layout.addWidget(self.start_btn, 0, 1)
        btn_layout.addWidget(self.pause_btn, 1, 0)
        btn_layout.addWidget(self.resume_btn, 1, 1)
        btn_layout.addWidget(self.stop_btn, 2, 0, 1, 2)
        
        control_layout.addLayout(btn_layout)
        self.vbox.addWidget(self.control_card)
        
        # === 区域 3：运行日志 ===
        log_title = SubtitleLabel("运行日志", self)
        self.vbox.addWidget(log_title)
        
        self.log_output = TextEdit(self)
        self.log_output.setReadOnly(True)
        self.vbox.addWidget(self.log_output, stretch=1)
    # =========================================================================
    # 新增：全局自定义背景图绘制 (带 Fluent 亚克力遮罩)
    # =========================================================================
    def paintEvent(self, event):
        # 1. 先让 FluentWindow 绘制原生的基础结构
        super().paintEvent(event)
        
        # 2. 检查图片是否存在
        bg_path = os.path.join(get_exe_dir(), "Image", "ui背景.jpg")
        if not os.path.exists(bg_path):
            return
            
        painter = QPainter(self)
        painter.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        
        pixmap = QPixmap(bg_path)
        if pixmap.isNull():
            return
            
        # 3. 保持比例缩放图片，使其完美覆盖整个窗口（类似网页的 object-fit: cover）
        scaled_pixmap = pixmap.scaled(
            self.size(), 
            Qt.KeepAspectRatioByExpanding, 
            Qt.SmoothTransformation
        )
        
        # 计算居中偏移量，保证画面中心不偏移
        x = (self.width() - scaled_pixmap.width()) // 2
        y = (self.height() - scaled_pixmap.height()) // 2
        
        # 将图片画在最底层
        painter.drawPixmap(x, y, scaled_pixmap)
        
        # 4. 【核心美化】：绘制自适应的半透明遮罩层
        if isDarkTheme():
            # 深色模式：叠加 85% (215/255) 不透明度的深灰色
            painter.fillRect(self.rect(), QColor(32, 32, 32, 215))
        else:
            # 浅色模式：叠加 85% 不透明度的纯白色
            painter.fillRect(self.rect(), QColor(243, 243, 243, 215))


class ShadowverseUI(FluentWindow):
    """主窗口 (继承自 FluentWindow)"""
    def __init__(self, run_main_script, command_queue, log_queue):
        super().__init__()
        # 默认使用系统主题 (白天/黑夜自动切换)
        setTheme(Theme.AUTO) 
        
        self._run_main_script = run_main_script
        self._command_queue = command_queue
        self._log_queue = log_queue

        # 显示启动弹窗
        if not self.show_startup_dialog():
            sys.exit(0)
            
        self.init_ui()

    def show_startup_dialog(self):
        """显示启动弹窗 (保持原有的免责声明逻辑)"""
        config_path = get_config_path()
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
                if config_data.get("agreed_to_disclaimer", False):
                    return True
            except Exception:
                pass

        dialog = QMessageBox()
        dialog.setWindowTitle("免责声明")
        dialog.setIcon(QMessageBox.Information)

        message = ""
        message += "<p><span style='color: red; font-weight: bold; font-size: 14pt;'>免责声明</span></p>"
        message += "<p>&nbsp;</p>"
        message += "<p><span style='color: red;'>本工具仅供<strong>个人学习研究</strong>使用，严禁用于任何<strong>商业盈利</strong>目的</span></p>"
        message += "<p><span style='color: red;'>使用本工具可能违反游戏用户协议，<strong>可能导致账号被封禁的严重后果</strong></span></p>"
        message += "<p><span style='color: red;'>开发者不对使用本工具造成的任何损失承担法律责任</span></p>"
        message += "<p>&nbsp;</p>"
        message += "<p><span style='color: red; font-weight: bold;'>本工具属于免费发布，禁止任何形式倒卖！！！</span></p>"

        dialog.setTextFormat(Qt.RichText)
        dialog.setText(message)

        checkbox = QCheckBox("同意一次后不再显示此弹窗")
        dialog.setCheckBox(checkbox)
        dialog.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
        dialog.button(QMessageBox.Yes).setText("同意")
        dialog.button(QMessageBox.No).setText("不同意")

        result = dialog.exec_()

        if result == QMessageBox.Yes:
            try:
                from src.utils.consent_utils import save_consent
                save_consent(persist_to_config=checkbox.isChecked())
            except Exception:
                pass
        return result == QMessageBox.Yes

    def init_ui(self):
        # 窗口基础设置
        self.setWindowTitle("影之诗自动对战脚本[完全免费]")
        self.resize(1050, 750)
        
        # 居中显示
        desktop = self.screen().availableGeometry()
        w, h = desktop.width(), desktop.height()
        self.move(w//2 - self.width()//2, h//2 - self.height()//2)

        self.script_thread = None
        self.run_time = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_run_time)

        self.current_turn = 0
        self.battle_count = 0
        self.turn_count = 0

        # 日志监听器
        self.log_listener = LogListener(self._log_queue, self)
        self.log_listener.log_signal.connect(self.append_log)
        self.log_listener.start()

        # Shared deck store
        self.deck_store = DeckStore(
            decks_dir=os.path.join(get_exe_dir(), "saved_decks"),
            parent=self,
        )

        self.setup_fluent_ui()

    def setup_fluent_ui(self):
        """配置左侧导航栏和堆叠页面"""
        
        # 1. 创建子页面
        self.home_interface = HomeInterface(self)
        self.card_select_page = CardSelectPage(self)
        self.my_deck_page = MyDeckPage(self)
        self.card_priority_page = CardPriorityPage(self)
        self.share_page = SharePage(self)
        self.config_page = ConfigPage(self)

        # ====== 修复点：强制给所有旧页面赋予唯一的 objectName ======
        self.card_select_page.setObjectName("CardSelectPage")
        self.my_deck_page.setObjectName("MyDeckPage")
        self.card_priority_page.setObjectName("CardPriorityPage")
        self.share_page.setObjectName("SharePage")
        self.config_page.setObjectName("ConfigPage")
        # =========================================================

        # 2. 将子页面添加到左侧导航栏
        self.addSubInterface(self.home_interface, FIF.HOME, '主控面板')
        self.addSubInterface(self.card_select_page, FIF.APPLICATION, '卡牌库')
        self.addSubInterface(self.my_deck_page, FIF.DOCUMENT, '我的卡组')
        self.addSubInterface(self.card_priority_page, FIF.ALIGNMENT, '卡牌设置')
        self.addSubInterface(self.share_page, FIF.SHARE, '卡组分享')
        
        # 参数设置放在左下角
        self.addSubInterface(self.config_page, FIF.SETTING, '高级设置', NavigationItemPosition.BOTTOM)

        # 3. 桥接 UI 控件到旧的业务逻辑变量名
        # 这样底层的 connect_device 等方法完全不需要重写！
        self.server_combo = self.home_interface.server_combo
        self.adb_input = self.home_interface.adb_input
        self.deep_color_checkbox = self.home_interface.deep_color_switch # Switch 兼容 isChecked()
        self.gala_mode_checkbox = self.home_interface.gala_mode_switch
        self.auto_pass_checkbox = self.home_interface.auto_pass_switch
        
        self.connect_btn = self.home_interface.connect_btn
        self.start_btn = self.home_interface.start_btn
        self.pause_btn = self.home_interface.pause_btn
        self.resume_btn = self.home_interface.resume_btn
        self.stop_btn = self.home_interface.stop_btn
        
        self.status_label = self.home_interface.status_label
        self.run_time_label = self.home_interface.run_time_label
        self.battle_count_label = self.home_interface.battle_count_label
        self.log_output = self.home_interface.log_output

        # 4. 绑定按钮点击事件
        self.connect_btn.clicked.connect(self.connect_device)
        self.start_btn.clicked.connect(self.start_script)
        self.pause_btn.clicked.connect(self.pause_script)
        self.resume_btn.clicked.connect(self.resume_script)
        self.stop_btn.clicked.connect(self.stop_script)

        # 5. 加载当前配置
        self.load_current_config()


    # =========================================================================
    # 以下业务逻辑代码完全保留你的原始版本，一行未动！
    # =========================================================================

    def load_current_config(self):
        config_path = get_config_path()
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)

                devices = config.get("devices", [])
                if devices:
                    last_device = devices[-1]
                    self.adb_input.setText(last_device["serial"])

                    if last_device.get("is_global", False):
                        self.server_combo.setCurrentText("国际服")
                    else:
                        self.server_combo.setCurrentText("国服")

                    self.deep_color_checkbox.setChecked(
                        last_device.get("screenshot_deep_color", False)
                    )
                    self.gala_mode_checkbox.setChecked(last_device.get("gala_mode", False))
                    
                    game_config = config.get("game", {})
                    self.auto_pass_checkbox.setChecked(
                        game_config.get("enable_auto_pass", False)
                    )
                else:
                    self.adb_input.setText("127.0.0.1:16384")
            except Exception as e:
                self.log_output.append(f"加载配置失败: {str(e)}")
                self.adb_input.setText("127.0.0.1:16384")
        else:
            self.adb_input.setText("127.0.0.1:16384")

    def connect_device(self):
        if self.is_script_running():
            QMessageBox.warning(
                self,
                "运行中",
                "脚本运行中，禁止修改设备/配置。请先停止脚本后再连接或修改设置。",
            )
            try:
                self.connect_btn.setEnabled(True)
            except Exception:
                pass
            return

        adb_port = self.adb_input.text()
        self.append_log(f"正在连接设备: {adb_port}...")
        self.connect_btn.setEnabled(False)

        is_global = self.server_combo.currentText() == "国际服"
        deep_color = self.deep_color_checkbox.isChecked()
        gala_mode = self.gala_mode_checkbox.isChecked()
        auto_pass = self.auto_pass_checkbox.isChecked()

        config_path = get_config_path()
        config = None

        try:
            repo = ConfigRepository(config_path)
            config, _, parse_err = repo.load_existing(allow_default_on_error=False)
            if config is None:
                self.append_log(f"更新配置文件失败: config.json解析错误: {str(parse_err or '')}")
                config = None

            device_update = {
                "name": f"模拟器-{adb_port}",
                "serial": adb_port,
                "is_global": is_global,
                "screenshot_deep_color": deep_color,
                "gala_mode": gala_mode,
            }

            if config is not None:
                base_device = {}
                try:
                    existing_devices = config.get("devices", [])
                    if isinstance(existing_devices, list):
                        for d in existing_devices:
                            if isinstance(d, dict) and d.get("serial") == adb_port:
                                base_device = dict(d)
                                break
                except Exception:
                    base_device = {}

                deep_update_dict(base_device, device_update)
                res = repo.update(
                    {"devices": [base_device], "game": {"enable_auto_pass": auto_pass}},
                    refuse_on_parse_error=True,
                    indent=4,
                    ensure_ascii=False,
                )
                if not res.ok:
                    raise RuntimeError(res.error or "config write failed")

                self.append_log(
                    f"设备设置已更新: 服务器={self.server_combo.currentText()}, "
                    f"深色识别={'开启' if deep_color else '关闭'}, "
                    f"庆典模式={'开启' if gala_mode else '关闭'}, "
                    f"启用空过={'开启' if auto_pass else '关闭'}"
                )
            else:
                self.append_log(
                    "设备设置未写入config.json（文件解析失败，请检查config.json格式是否为合法JSON）"
                )

        except Exception as e:
            self.append_log(f"更新配置文件失败: {str(e)}")

        self.script_thread = ScriptRunner(self._run_main_script, self._log_queue, self)
        self.script_thread.status_signal.connect(self.update_status)
        self.script_thread.stats_signal.connect(self.update_stats)

        self.start_btn.setEnabled(True)
        self.status_label.setText("当前状态: 已连接")
        self.status_label.setStyleSheet("color: #00AA00;") # 适配浅色模式的绿色

    def is_script_running(self) -> bool:
        try:
            return bool(self.script_thread is not None and self.script_thread.isRunning())
        except Exception:
            return False

    def append_log(self, message):
        self.log_output.append(message)
        self.log_output.verticalScrollBar().setValue(
            self.log_output.verticalScrollBar().maximum()
        )

        if "[对战开始]" in message:
            try:
                import re
                match = re.search(r"第(\d+)场对战", message)
                if match:
                    battle_count = int(match.group(1))
                    self.battle_count = battle_count
                    self.battle_count_label.setText(f"对战次数: {battle_count}")
            except Exception:
                pass

    def start_script(self):
        if self.script_thread and not self.script_thread.isRunning():
            self.script_thread.start()
            self.start_btn.setEnabled(False)
            self.pause_btn.setEnabled(True)
            self.resume_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.timer.start(1000)
            self.append_log("===== 脚本开始运行 =====")

    def pause_script(self):
        if self.script_thread and self.script_thread.isRunning():
            self._command_queue.put("p")
            self.status_label.setText("当前状态: 已暂停")
            self.status_label.setStyleSheet("color: #AAAA00;")
            self.pause_btn.setEnabled(False)
            self.resume_btn.setEnabled(True)
            self.timer.stop()
            self.append_log("[控制] 脚本已暂停")

    def resume_script(self):
        if self.script_thread and self.script_thread.isRunning():
            self._command_queue.put("r")
            self.status_label.setText("当前状态: 运行中")
            self.status_label.setStyleSheet("color: #00AA00;")
            self.pause_btn.setEnabled(True)
            self.resume_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
            self.timer.start(1000)
            self.append_log("[控制] 脚本已恢复")

    def stop_script(self):
        if self.script_thread and self.script_thread.isRunning():
            try:
                self._command_queue.put("e")
            except Exception:
                pass
            self.append_log("[控制] 已发送停止命令，等待脚本退出...")
            try:
                self.pause_btn.setEnabled(False)
                self.resume_btn.setEnabled(False)
                self.stop_btn.setEnabled(False)
            except Exception:
                pass

            self._force_stop_script_thread(timeout_ms=8000)

    def _force_stop_script_thread(self, timeout_ms: int = 8000) -> bool:
        if not (self.script_thread and self.script_thread.isRunning()):
            return True

        if self.script_thread.wait(max(200, int(timeout_ms))):
            return True

        self.append_log("[控制] 停止超时，尝试强制结束脚本线程...")
        try:
            self.script_thread.terminate()
        except Exception:
            pass

        if self.script_thread.wait(1500):
            self.append_log("[控制] 已强制结束脚本线程")
            return True

        self.append_log("[控制] 强制结束失败，请关闭程序后重试")
        return False

    def calculate_avg_turns(self):
        battle_count = int(self.battle_count_label.text().split()[-1]) if self.battle_count_label.text() else 0
        turn_count = int(self.turn_count_label.text()) if hasattr(self, 'turn_count_label') else 0
        return round(turn_count / battle_count, 2) if battle_count > 0 else 0

    def update_status(self, status):
        self.status_label.setText(f"当前状态: {status}")
        if status == "运行中":
            self.status_label.setStyleSheet("color: #00AA00;")
            self.pause_btn.setEnabled(True)
            self.resume_btn.setEnabled(False)
            self.stop_btn.setEnabled(True)
        elif status == "已暂停":
            self.status_label.setStyleSheet("color: #AAAA00;")
            self.pause_btn.setEnabled(False)
            self.resume_btn.setEnabled(True)
            self.stop_btn.setEnabled(True)
        else:
            self.status_label.setStyleSheet("color: #FF5555;")
            try:
                self.stop_btn.setEnabled(False)
                self.pause_btn.setEnabled(False)
                self.resume_btn.setEnabled(False)
                if self.script_thread is not None:
                    self.start_btn.setEnabled(True)
                self.timer.stop()
            except Exception:
                pass

    def update_stats(self, stats):
        run_time = stats.get("run_time", 0)
        hours = run_time // 3600
        minutes = (run_time % 3600) // 60
        seconds = run_time % 60
        self.run_time_label.setText(f"运行时间: {hours:02d}:{minutes:02d}:{seconds:02d}")

    def update_run_time(self):
        if self.script_thread and self.script_thread.isRunning():
            run_time = int(time.time() - self.script_thread.start_time)
            hours = run_time // 3600
            minutes = (run_time % 3600) // 60
            seconds = run_time % 60
            self.run_time_label.setText(f"运行时间: {hours:02d}:{minutes:02d}:{seconds:02d}")

    def closeEvent(self, event):
        if self.log_listener.isRunning():
            self.log_listener.stop()
            self.log_listener.wait(1000)

        if self.script_thread and self.script_thread.isRunning():
            try:
                self._command_queue.put("e")
            except Exception:
                pass
            self._force_stop_script_thread(timeout_ms=5000)

        event.accept()