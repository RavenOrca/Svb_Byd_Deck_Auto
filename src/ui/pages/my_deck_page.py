#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""My deck page (view/manage current deck). Fluent UI Refactored."""

from __future__ import annotations

import json
import os
import shutil

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

# ====== 引入 Fluent UI 现代组件 ======
from qfluentwidgets import (
    CardWidget, SubtitleLabel, BodyLabel, CaptionLabel,
    LineEdit, PushButton, PrimaryPushButton, ComboBox,
    SmoothScrollArea, RoundMenu, Action, FluentIcon as FIF
)

from src.config.paths import get_card_cost_dir, get_config_path
from src.config.config_repository import ConfigRepository
from src.ui.common import get_exe_dir
from src.ui.deck_io import (
    apply_strategy_config,
    build_card_variant_index,
    build_card_source_index,
    extract_strategy_config,
    filter_non_evo_cards,
    resolve_runtime_card_paths,
    save_deck_snapshot,
)
from src.utils.card_filename import normalize_card_base_name, parse_card_filename


class MyDeckPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.deck_store = getattr(parent, "deck_store", None)
        self.card_size = QSize(100, 140)  # 标准卡片尺寸
        self.cards_per_row = 4
        self.current_card_widgets = []    # 用于保存生成的卡片控件，实现自适应排版
        
        if self.deck_store is not None:
            try:
                self.deck_store.decks_changed.connect(self._on_decks_changed)
            except Exception:
                self.deck_store = None
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(20)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # 标题
        title_label = SubtitleLabel("我的卡组 / 当前工作区", self)
        main_layout.addWidget(title_label)

        # ====== 顶部管理控制台======
        control_card = CardWidget(self)
        control_layout = QVBoxLayout(control_card)
        control_layout.setContentsMargins(20, 15, 20, 15)
        control_layout.setSpacing(15)

        # 1. 保存当前卡组
        save_layout = QHBoxLayout()
        save_layout.addWidget(BodyLabel("保存当前配置:"))
        
        self.save_deck_name = LineEdit()
        self.save_deck_name.setPlaceholderText("输入想要保存的卡组名称...")
        self.save_deck_name.setMinimumWidth(200)
        save_layout.addWidget(self.save_deck_name)

        self.save_current_btn = PrimaryPushButton(FIF.SAVE, "保存到卡牌库")
        self.save_current_btn.clicked.connect(self.save_current_deck)
        save_layout.addWidget(self.save_current_btn)
        save_layout.addStretch(1)
        
        control_layout.addLayout(save_layout)

        # 2. 已保存卡组加载与管理
        deck_layout = QHBoxLayout()
        deck_layout.addWidget(BodyLabel("管理已存卡组:"))
        
        self.saved_decks_combo = ComboBox()
        self.saved_decks_combo.setMinimumWidth(200)
        # 【修复】：明确 userData=None
        self.saved_decks_combo.addItem("选择卡组", userData=None)
        deck_layout.addWidget(self.saved_decks_combo)

        self.load_deck_btn = PushButton(FIF.DOWNLOAD, "加载")
        self.load_deck_btn.clicked.connect(self.load_selected_deck)
        deck_layout.addWidget(self.load_deck_btn)

        self.delete_deck_btn = PushButton(FIF.DELETE, "删除")
        self.delete_deck_btn.clicked.connect(self.delete_selected_deck)
        deck_layout.addWidget(self.delete_deck_btn)
        deck_layout.addStretch(1)
        
        control_layout.addLayout(deck_layout)
        main_layout.addWidget(control_card)

        # ====== 说明文本 ======
        desc_label = BodyLabel("💡 提示：这里显示当前正在运行的卡组。右键点击单张卡牌可以将其从工作区移除。")
        main_layout.addWidget(desc_label)

        # ====== 卡片展示区 ======
        self.scroll_area = SmoothScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { background-color: transparent; border: none; }")
        
        self.scroll_content = QWidget()
        self.scroll_content.setObjectName("ScrollContent")
        self.scroll_content.setStyleSheet("QWidget#ScrollContent { background-color: transparent; }")
        
        self.grid_layout = QGridLayout(self.scroll_content)
        self.grid_layout.setAlignment(Qt.AlignTop)
        self.scroll_area.setWidget(self.scroll_content)

        main_layout.addWidget(self.scroll_area, stretch=1)

        # ====== 底部操作按钮 ======
        btn_layout = QHBoxLayout()
        #self.back_btn = PushButton("返回主界面")
        #self.back_btn.clicked.connect(lambda: getattr(self.parent, "stacked_widget", None) and self.parent.stacked_widget.setCurrentIndex(0))

        btn_layout.addStretch()
        #btn_layout.addWidget(self.back_btn)
        main_layout.addLayout(btn_layout)

        # 初始化数据
        self.refresh_saved_decks()
        self.load_deck()

    # ====== 新增：自适应瀑布流排版 ======
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.adjust_card_layout()

    def adjust_card_layout(self):
        """当窗口拉伸时，自动计算每行能放几张卡，并动态重排 (无需重新读取硬盘)"""
        if not hasattr(self, 'scroll_area') or not self.current_card_widgets:
            return
            
        scroll_width = self.scroll_area.width() - 30
        new_cards_per_row = max(2, scroll_width // (self.card_size.width() + 40))
        
        if new_cards_per_row != self.cards_per_row:
            self.cards_per_row = new_cards_per_row
            row, col = 0, 0
            # 重新排列现有的卡片控件
            for widget in self.current_card_widgets:
                self.grid_layout.addWidget(widget, row, col)
                col += 1
                if col >= self.cards_per_row:
                    col = 0
                    row += 1

    # ================= 业务逻辑区 =================

    def save_current_deck(self):
        deck_name = self.save_deck_name.text().strip()
        if not deck_name:
            QMessageBox.warning(self, "警告", "请输入卡组名称！")
            return

        card_dir = get_card_cost_dir(ensure=True)
        if not os.path.exists(card_dir):
            QMessageBox.warning(self, "警告", "当前卡组为空！")
            return

        card_files = [f for f in os.listdir(card_dir) if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))]
        card_files = filter_non_evo_cards(card_files)
        if not card_files:
            QMessageBox.warning(self, "警告", "当前卡组为空！")
            return

        try:
            decks_dir = os.path.join(get_exe_dir(), "saved_decks")
            save_deck_snapshot(
                deck_name=deck_name,
                cards=card_files,
                decks_dir=decks_dir,
                config_path=get_config_path(),
            )

            QMessageBox.information(self, "成功", f"卡组 '{deck_name}' 已保存！")
            if hasattr(self.parent, "log_output"):
                self.parent.log_output.append(f"[卡组] 已保存卡组 '{deck_name}'")

            self.save_deck_name.clear()

            if self.deck_store is not None:
                self.deck_store.refresh()
            else:
                self.refresh_saved_decks()

        except Exception as e:
            QMessageBox.warning(self, "错误", f"保存卡组失败: {str(e)}")

    def refresh_saved_decks(self, *, propagate: bool = True):
        decks = []
        if self.deck_store is not None:
            try:
                decks = list(self.deck_store.get_decks() or [])
            except Exception:
                decks = []
        else:
            decks_dir = os.path.join(get_exe_dir(), "saved_decks")
            if os.path.exists(decks_dir):
                for file in os.listdir(decks_dir):
                    if not file.endswith(".json"):
                        continue
                    deck_file = os.path.join(decks_dir, file)
                    try:
                        with open(deck_file, "r", encoding="utf-8") as f:
                            deck_data = json.load(f)
                        decks.append((deck_data.get("name", file[:-5]), file))
                    except Exception:
                        pass

        self._populate_saved_decks(decks)

    def _on_decks_changed(self):
        try:
            self.refresh_saved_decks(propagate=False)
        except Exception:
            pass

    def _populate_saved_decks(self, decks):
        if not hasattr(self, "saved_decks_combo"):
            return

        current = None
        try:
            current = self.saved_decks_combo.itemData(self.saved_decks_combo.currentIndex())
        except Exception:
            current = None

        self.saved_decks_combo.blockSignals(True)
        try:
            self.saved_decks_combo.clear()
            # 【修复】：下拉框数据绑定
            self.saved_decks_combo.addItem("选择卡组", userData=None)
            for display_name, filename in list(decks or []):
                self.saved_decks_combo.addItem(str(display_name), userData=filename)

            if current:
                idx = self.saved_decks_combo.findData(current)
                if idx >= 0:
                    self.saved_decks_combo.setCurrentIndex(idx)
        finally:
            self.saved_decks_combo.blockSignals(False)

    def load_selected_deck(self):
        try:
            if getattr(self.parent, "is_script_running", lambda: False)():
                QMessageBox.warning(self, "运行中", "脚本运行中，禁止切换卡组。请先停止脚本后再加载卡组。")
                return
        except Exception:
            pass

        deck_file = self.saved_decks_combo.itemData(self.saved_decks_combo.currentIndex())
        if not deck_file:
            QMessageBox.warning(self, "警告", "请在下拉列表中选择要加载的卡组！")
            return

        try:
            decks_dir = os.path.join(get_exe_dir(), "saved_decks")
            deck_path = os.path.join(decks_dir, deck_file)

            with open(deck_path, "r", encoding="utf-8") as f:
                deck_data = json.load(f)

            # 清空当前工作区卡组
            card_dir = get_card_cost_dir(ensure=True)
            for file in os.listdir(card_dir):
                file_path = os.path.join(card_dir, file)
                try:
                    if os.path.isfile(file_path):
                        os.unlink(file_path)
                except Exception:
                    pass

            # 复制新卡片
            source_dir = os.path.join(get_exe_dir(), "quanka")
            exact_index, stem_index = build_card_source_index(source_dir)
            variant_index = build_card_variant_index(source_dir)
            success_count = 0
            loaded_base_count = 0
            
            for card_file in filter_non_evo_cards(list(deck_data.get("cards", []))):
                runtime_paths = resolve_runtime_card_paths(
                    source_dir, card_file,
                    exact_index=exact_index, stem_index=stem_index, variant_index=variant_index,
                )
                if runtime_paths:
                    loaded_base_count += 1
                for src in runtime_paths:
                    if not os.path.exists(src):
                        continue
                    dst = os.path.join(card_dir, os.path.basename(src))
                    try:
                        shutil.copy2(src, dst)
                        success_count += 1
                    except Exception:
                        pass

            if success_count > 0:
                self.load_deck() # 刷新UI

                sc = deck_data.get("strategy_config")
                if not isinstance(sc, dict) and isinstance(deck_data.get("config"), dict):
                    sc = extract_strategy_config(deck_data["config"], cards=list(deck_data.get("cards") or []))

                if isinstance(sc, dict) and sc:
                    config_path = get_config_path()
                    repo = ConfigRepository(config_path)
                    existing, _, _ = repo.load_existing(allow_default_on_error=True)
                    existing_cfg = existing if isinstance(existing, dict) else {}
                    merged = apply_strategy_config(existing_cfg, strategy_config=sc)
                    repo.replace_with_snapshot(merged, ensure_ascii=False, indent=2)

                QMessageBox.information(self, "成功", f"已成功加载卡组 '{deck_data.get('name')}'，共 {loaded_base_count} 张卡片")
                
                if hasattr(self.parent, "card_priority_page"):
                    self.parent.card_priority_page.refresh_card_priority()

        except Exception as e:
            QMessageBox.warning(self, "错误", f"加载卡组失败: {str(e)}")

    def delete_selected_deck(self):
        deck_file = self.saved_decks_combo.itemData(self.saved_decks_combo.currentIndex())
        deck_name = self.saved_decks_combo.currentText()

        if not deck_file:
            QMessageBox.warning(self, "警告", "请选择要删除的卡组！")
            return

        reply = QMessageBox.question(
            self, "确认删除", f'确定要永久删除卡组 "{deck_name}" 吗？',
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                decks_dir = os.path.join(get_exe_dir(), "saved_decks")
                deck_path = os.path.join(decks_dir, deck_file)

                if os.path.exists(deck_path):
                    os.remove(deck_path)
                    QMessageBox.information(self, "成功", f"卡组 '{deck_name}' 已删除！")

                    if self.deck_store is not None:
                        self.deck_store.refresh()
                    else:
                        self.refresh_saved_decks()
            except Exception as e:
                QMessageBox.warning(self, "错误", f"删除卡组失败: {str(e)}")

    def load_deck(self):
        """将当前工作区目录中的卡片渲染到界面上"""
        # 清空网格和控件列表
        for i in reversed(range(self.grid_layout.count())):
            if widget := self.grid_layout.itemAt(i).widget():
                widget.deleteLater()
        self.current_card_widgets.clear()

        card_dir = get_card_cost_dir(ensure=True)
        if not os.path.exists(card_dir):
            return

        card_files = [f for f in os.listdir(card_dir) if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))]
        card_files = filter_non_evo_cards(card_files)

        if not card_files:
            return

        self.refresh_saved_decks()

        row, col = 0, 0
        for card_file in card_files:
            card_path = os.path.join(card_dir, card_file)

            # 使用 Fluent UI 的卡片容器
            card_container = CardWidget()
            card_layout = QVBoxLayout(card_container)
            card_layout.setAlignment(Qt.AlignCenter)
            card_layout.setSpacing(5)
            card_layout.setContentsMargins(10, 10, 10, 10)

            # 图片展示
            card_label = QLabel()
            pixmap = QPixmap(card_path)
            if not pixmap.isNull():
                pixmap = pixmap.scaled(self.card_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                card_label.setPixmap(pixmap)
            card_label.setAlignment(Qt.AlignCenter)
            
            # 绑定右键菜单事件
            card_label.setContextMenuPolicy(Qt.CustomContextMenu)
            card_label.customContextMenuRequested.connect(lambda pos, f=card_file: self.show_context_menu(pos, f))

            # 卡牌名字 (CaptionLabel)
            try:
                _, _, card_name = parse_card_filename(card_file)
            except Exception:
                card_name = card_file.split("_", 1)[-1].rsplit(".", 1)[0]
                
            card_name = " ".join(normalize_card_base_name(str(card_name or "")).split("_"))
            name_label = CaptionLabel(card_name)
            name_label.setAlignment(Qt.AlignCenter)
            name_label.setWordWrap(True)

            card_layout.addWidget(card_label)
            card_layout.addWidget(name_label)
            
            # 保存到缓存列表以供动态拉伸计算
            self.current_card_widgets.append(card_container)
            
            self.grid_layout.addWidget(card_container, row, col)

            col += 1
            if col >= self.cards_per_row:
                col = 0
                row += 1

    def show_context_menu(self, pos, card_file):
        """展示 Fluent 风格的圆角右键菜单"""
        menu = RoundMenu(parent=self)
        remove_action = Action(FIF.DELETE, "将卡牌移出当前卡组", self)
        remove_action.triggered.connect(lambda: self.remove_card(card_file))
        menu.addAction(remove_action)
        
        # 将局部坐标转换为全局屏幕坐标弹出
        sender = self.sender()
        menu.exec(sender.mapToGlobal(pos))

    def remove_card(self, card_file):
        card_path = os.path.join(get_card_cost_dir(ensure=True), card_file)
        if os.path.exists(card_path):
            try:
                os.remove(card_path)
                self.load_deck() # 重新刷新 UI
                
                if hasattr(self.parent, "card_priority_page"):
                    self.parent.card_priority_page.refresh_card_priority()
            except Exception as e:
                QMessageBox.warning(self, "错误", f"移除卡片失败: {str(e)}")