#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Card selection page (Fluent UI Refactored)."""

from __future__ import annotations

import json
import os
import shutil

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QMessageBox,
    QVBoxLayout,
    QWidget,
    QInputDialog,
)

# ====== 引入 Fluent UI 现代组件 ======
from qfluentwidgets import (
    PushButton, PrimaryPushButton, ComboBox, SearchLineEdit,
    SubtitleLabel, BodyLabel, CheckBox, ToggleButton, 
    SmoothScrollArea, CardWidget, CaptionLabel
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
    resolve_source_card_path,
    save_deck_snapshot,
)
from src.utils.card_filename import (
    is_evo_card_name,
    normalize_card_base_name,
    parse_card_filename,
)


class CardSelectPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.deck_store = getattr(parent, "deck_store", None)
        self.current_page = 0
        self.selected_cards = []
        self.cards_per_row = 4
        self.card_size = QSize(100, 140)
        self.cost_filters = {} 
        self.all_cards = [] 
        self.filtered_cards = [] 
        self.card_categories = [] 
        self.current_category = None 
        if self.deck_store is not None:
            try:
                self.deck_store.decks_changed.connect(self._on_decks_changed)
            except Exception:
                self.deck_store = None
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20) # 增加呼吸感

        # 标题 (Fluent SubtitleLabel)
        title_label = SubtitleLabel("卡组选择 / 卡牌库")
        main_layout.addWidget(title_label)

        # 加载已保存卡组下拉框
        deck_layout = QHBoxLayout()
        deck_layout.addWidget(BodyLabel("已保存卡组:"))
        
        self.saved_decks_combo = ComboBox() # Fluent ComboBox
        self.saved_decks_combo.setMinimumWidth(200)
        self.saved_decks_combo.addItem("选择卡组", None)
        self.saved_decks_combo.currentIndexChanged.connect(self.load_saved_deck)
        #self.saved_decks_combo.currentIndexChanged.connect(self._execute_load_selected_deck)
        deck_layout.addWidget(self.saved_decks_combo)
        deck_layout.addStretch(1)

        self.refresh_saved_decks()
        main_layout.addLayout(deck_layout)

        # 加载已保存卡组下拉框
        deck_layout = QHBoxLayout()
        deck_layout.addWidget(BodyLabel("已保存卡组:"))
        
        self.saved_decks_combo = ComboBox() 
        self.saved_decks_combo.setMinimumWidth(200)
        # 【修复】：显式指定 userData=None
        self.saved_decks_combo.addItem("选择卡组", userData=None) 
        self.saved_decks_combo.currentIndexChanged.connect(self.load_saved_deck)
        deck_layout.addWidget(self.saved_decks_combo)
        deck_layout.addStretch(1)

        self.refresh_saved_decks()
        main_layout.addLayout(deck_layout)

        # 搜索框和分类选择
        search_layout = QHBoxLayout()

        self.category_combo = ComboBox()
        # 【修复】：显式指定 userData=None
        self.category_combo.addItem("所有分类", userData=None) 
        self.category_combo.setMinimumWidth(150)
        self.category_combo.currentIndexChanged.connect(self.on_category_changed)
        
        search_layout.addWidget(BodyLabel("分类:"))
        search_layout.addWidget(self.category_combo)
        search_layout.addSpacing(20)

        # 现代化的搜索框 (自带图标和清除按钮)
        self.search_input = SearchLineEdit()
        self.search_input.setPlaceholderText("搜索卡牌...")
        self.search_input.setMinimumWidth(250)
        self.search_input.textChanged.connect(self.on_search_text_changed)
        
        search_layout.addWidget(BodyLabel("搜索:"))
        search_layout.addWidget(self.search_input)
        search_layout.addStretch(1)

        main_layout.addLayout(search_layout)

        # 费用筛选栏
        self.init_cost_filter(main_layout)

        # 卡片显示区域
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

        # 翻页控制
        page_control_layout = QHBoxLayout()
        self.prev_btn = PushButton("上一页")
        self.prev_btn.clicked.connect(self.prev_page)
        self.page_label = BodyLabel("第 1 页")
        self.next_btn = PushButton("下一页")
        self.next_btn.clicked.connect(self.next_page)

        page_control_layout.addStretch()
        page_control_layout.addWidget(self.prev_btn)
        page_control_layout.addSpacing(15)
        page_control_layout.addWidget(self.page_label)
        page_control_layout.addSpacing(15)
        page_control_layout.addWidget(self.next_btn)
        page_control_layout.addStretch()
        main_layout.addLayout(page_control_layout)

        # 操作按钮
        btn_layout = QHBoxLayout()
        
        self.save_btn = PrimaryPushButton("保存 / 应用当前卡组")
        self.save_btn.clicked.connect(self.save_selection)
        
        self.save_as_btn = PushButton("另存为新卡组...")
        self.save_as_btn.clicked.connect(self.save_deck_as)
        
        #self.back_btn = PushButton("返回主界面")
        #self.back_btn.clicked.connect(lambda: getattr(self.parent, "stacked_widget", None) and self.parent.stacked_widget.setCurrentIndex(0))

        btn_layout.addStretch()
        btn_layout.addWidget(self.save_btn)
        btn_layout.addSpacing(10)
        btn_layout.addWidget(self.save_as_btn)
        btn_layout.addSpacing(10)
        #btn_layout.addWidget(self.back_btn)

        main_layout.addLayout(btn_layout)

        self.load_cards()

    def init_cost_filter(self, main_layout):
        """初始化费用筛选控件 (使用 ToggleButton)"""
        cost_filter_layout = QHBoxLayout()
        cost_filter_layout.addWidget(BodyLabel("费用筛选:"))

        # 添加0-10费选项
        for cost in range(0, 11):
            btn = ToggleButton(f"{cost}费")
            btn.setMinimumWidth(50)
            btn.clicked.connect(self.update_card_display)
            self.cost_filters[cost] = btn
            cost_filter_layout.addWidget(btn)

        # 添加"全部"按钮
        self.all_cost_btn = ToggleButton("全部")
        self.all_cost_btn.setChecked(True)
        self.all_cost_btn.clicked.connect(self.select_all_costs)
        cost_filter_layout.addWidget(self.all_cost_btn)

        cost_filter_layout.addStretch(1)
        main_layout.addLayout(cost_filter_layout)

    def load_cards(self):
        card_dir = os.path.join(get_exe_dir(), "quanka")
        self.all_cards = []
        self.card_categories = []

        if os.path.exists(card_dir):
            self.card_categories = [d for d in os.listdir(card_dir) if os.path.isdir(os.path.join(card_dir, d))]
            self.category_combo.clear()
            self.category_combo.addItem("所有分类", None)

            for category in sorted(self.card_categories):
                self.category_combo.addItem(category, userData=category)

            for root, _, files in os.walk(card_dir):
                for file in files:
                    if file.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                        if is_evo_card_name(file):
                            continue
                        rel_path = os.path.relpath(os.path.join(root, file), card_dir)
                        self.all_cards.append({
                            "path": rel_path,
                            "file": file,
                            "category": os.path.basename(root) if root != card_dir else None,
                        })

        self.all_cards.sort(key=lambda x: (self.get_card_cost(x["file"]), x["file"].lower()))
        self.filtered_cards = self.all_cards
        self.display_page(0)

    def on_category_changed(self, index):
        self.current_category = self.category_combo.itemData(index)
        self.update_card_display()

    def on_search_text_changed(self, text):
        self.update_card_display()

    def select_all_costs(self):
        sender = self.sender()
        if sender.isChecked():
            for cost, btn in self.cost_filters.items():
                btn.setChecked(False)
            self.update_card_display()
            sender.setChecked(True)

    def update_card_display(self):
        selected_costs = [cost for cost, btn in self.cost_filters.items() if btn.isChecked()]

        if self.sender() == self.all_cost_btn:
            pass
        elif selected_costs:
            self.all_cost_btn.setChecked(False)
        elif not selected_costs and self.sender() != self.all_cost_btn:
            self.all_cost_btn.setChecked(True)

        search_text = self.search_input.text().strip().lower()
        self.filtered_cards = []
        
        for card in self.all_cards:
            if self.current_category and card["category"] != self.current_category:
                continue
            if selected_costs and self.get_card_cost(card["file"]) not in selected_costs:
                continue
            if search_text and search_text not in card["file"].lower():
                continue
            self.filtered_cards.append(card)

        self.current_page = 0
        self.display_page(self.current_page)

    def get_card_cost(self, card_file):
        try:
            return int(card_file.split("_")[0])
        except Exception:
            return 0

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.adjust_card_layout()

    def adjust_card_layout(self):
        scroll_width = self.scroll_area.width() - 30
        self.cards_per_row = max(2, scroll_width // (self.card_size.width() + 40)) # 增加了卡片间距
        self.display_page(self.current_page)

    def display_page(self, page):
        self.current_page = page
        cards_per_page = self.cards_per_row * 3

        self.total_pages = max(1, (len(self.filtered_cards) + cards_per_page - 1) // cards_per_page)
        self.page_label.setText(f"第 {page+1} / {self.total_pages} 页")
        self.prev_btn.setEnabled(page > 0)
        self.next_btn.setEnabled(page < self.total_pages - 1)

        for i in reversed(range(self.grid_layout.count())):
            if widget := self.grid_layout.itemAt(i).widget():
                widget.deleteLater()

        start_index = page * cards_per_page
        end_index = min(start_index + cards_per_page, len(self.filtered_cards))

        row, col = 0, 0
        for i in range(start_index, end_index):
            card_data = self.filtered_cards[i]
            card_path = os.path.join(get_exe_dir(), "quanka", card_data["path"])

            # 使用 Fluent UI 的 CardWidget，自带悬浮阴影和圆角
            card_container = CardWidget()
            card_layout = QVBoxLayout(card_container)
            card_layout.setAlignment(Qt.AlignCenter)
            card_layout.setContentsMargins(10, 10, 10, 10)

            # 图片标签保持原样
            from PyQt5.QtWidgets import QLabel
            card_label = QLabel()
            pixmap = QPixmap(card_path)
            if not pixmap.isNull():
                pixmap = pixmap.scaled(self.card_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                card_label.setPixmap(pixmap)
            card_label.setAlignment(Qt.AlignCenter)
            card_label.mousePressEvent = lambda event, f=card_data["file"]: self.toggle_card_selection_by_click(f)

            try:
                _, _, base_name = parse_card_filename(card_data["file"])
                card_name = " ".join(normalize_card_base_name(str(base_name or "")).split("_"))
            except Exception:
                card_name = " ".join(card_data["file"].split("_", 1)[-1].rsplit(".", 1)[0].split("_"))
                
            # 卡牌名使用 CaptionLabel 显得更精致
            name_label = CaptionLabel(card_name)
            name_label.setAlignment(Qt.AlignCenter)
            name_label.setWordWrap(True)

            # 现代化的复选框
            checkbox = CheckBox("选中")
            checkbox.setChecked(card_data["file"] in self.selected_cards)
            checkbox.stateChanged.connect(lambda state, f=card_data["file"]: self.toggle_card_selection(f, state))

            card_layout.addWidget(card_label)
            card_layout.addWidget(name_label)
            card_layout.addWidget(checkbox, 0, Qt.AlignCenter)
            
            self.grid_layout.addWidget(card_container, row, col)

            col += 1
            if col >= self.cards_per_row:
                col = 0
                row += 1

    def toggle_card_selection(self, card_file, state):
        if state == Qt.Checked:
            if card_file not in self.selected_cards:
                if len(self.selected_cards) < 100:
                    self.selected_cards.append(card_file)
                else:
                    self.sender().setChecked(False)
                    QMessageBox.warning(self, "警告", "最多只能选择100张卡片！")
        else:
            if card_file in self.selected_cards:
                self.selected_cards.remove(card_file)

    def toggle_card_selection_by_click(self, card_file):
        if card_file in self.selected_cards:
            self.selected_cards.remove(card_file)
        else:
            if len(self.selected_cards) < 100:
                self.selected_cards.append(card_file)
            else:
                QMessageBox.warning(self, "警告", "最多只能选择100张卡片！")
        self.display_page(self.current_page)

    def prev_page(self):
        if self.current_page > 0:
            self.display_page(self.current_page - 1)

    def next_page(self):
        if self.current_page < self.total_pages - 1:
            self.display_page(self.current_page + 1)

    def save_selection(self):
        try:
            if getattr(self.parent, "is_script_running", lambda: False)():
                QMessageBox.warning(self, "运行中", "脚本运行中，禁止修改当前卡组。请先停止脚本后再保存卡组选择。")
                return
        except Exception:
            pass

        if not self.selected_cards:
            QMessageBox.warning(self, "警告", "请至少选择一张卡片！")
            return

        target_dir = get_card_cost_dir(ensure=True)
        os.makedirs(target_dir, exist_ok=True)

        for file in os.listdir(target_dir):
            file_path = os.path.join(target_dir, file)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                print(f"删除文件失败: {file_path} - {e}")

        success_count = 0
        selected_base_count = 0
        source_dir = os.path.join(get_exe_dir(), "quanka")
        exact_index, stem_index = build_card_source_index(source_dir)
        variant_index = build_card_variant_index(source_dir)
        
        for card_file in self.selected_cards:
            runtime_paths = resolve_runtime_card_paths(
                source_dir, card_file,
                exact_index=exact_index, stem_index=stem_index, variant_index=variant_index,
            )
            if runtime_paths:
                selected_base_count += 1
            for src in runtime_paths:
                if not os.path.exists(src):
                    continue
                dst = os.path.join(target_dir, os.path.basename(src))
                try:
                    shutil.copy2(src, dst)
                    success_count += 1
                except Exception as e:
                    pass

        if success_count > 0:
            # ====== 同步覆盖JSON ======
            current_deck_file = self.saved_decks_combo.itemData(self.saved_decks_combo.currentIndex())
            deck_name = self.saved_decks_combo.currentText()
            msg_extra = ""
            
            if current_deck_file and deck_name and deck_name != "选择卡组":
                try:
                    decks_dir = os.path.join(get_exe_dir(), "saved_decks")
                    save_deck_snapshot(
                        deck_name=deck_name, cards=list(self.selected_cards or []),
                        decks_dir=decks_dir, config_path=get_config_path(),
                    )
                    msg_extra = f"\n并已同步更新至存档: {deck_name}.json"
                    if self.deck_store is not None:
                        self.deck_store.refresh()
                    else:
                        self.refresh_saved_decks()
                except Exception as e:
                    print(f"同步更新 JSON 存档失败: {e}")
            # =======================================================

            QMessageBox.information(self, "成功", f"已应用 {selected_base_count} 张卡片到当前环境！{msg_extra}")
            if self.parent and hasattr(self.parent, "log_output"):
                self.parent.log_output.append(f"[卡组] 已应用 {selected_base_count} 张卡片 {msg_extra}")

            if hasattr(self.parent, "card_priority_page"):
                self.parent.card_priority_page.refresh_card_priority()
            if hasattr(self.parent, "my_deck_page"):
                self.parent.my_deck_page.load_deck()

    def load_saved_deck(self, index):
        try:
            if getattr(self.parent, "is_script_running", lambda: False)():
                QMessageBox.warning(self, "运行中", "脚本运行中，禁止切换卡组。请先停止脚本后再加载。")
                try:
                    self.saved_decks_combo.blockSignals(True)
                    self.saved_decks_combo.setCurrentIndex(0)
                finally:
                    self.saved_decks_combo.blockSignals(False)
                return
        except Exception:
            pass

        deck_file = self.saved_decks_combo.itemData(index)
        if not deck_file:
            return

        try:
            decks_dir = os.path.join(get_exe_dir(), "saved_decks")
            deck_path = os.path.join(decks_dir, deck_file)

            with open(deck_path, "r", encoding="utf-8") as f:
                deck_data = json.load(f)

            self.selected_cards = []
            source_dir = os.path.join(get_exe_dir(), "quanka")
            exact_index, stem_index = build_card_source_index(source_dir)

            for card_file in filter_non_evo_cards(list(deck_data.get("cards", []))):
                src = resolve_source_card_path(source_dir, card_file, exact_index=exact_index, stem_index=stem_index)
                if src and os.path.exists(src):
                    self.selected_cards.append(os.path.basename(src))

            self.display_page(self.current_page)
            
            # 配置策略同步
            sc = deck_data.get("strategy_config")
            if not isinstance(sc, dict) and isinstance(deck_data.get("config"), dict):
                sc = extract_strategy_config(deck_data["config"], cards=list(deck_data.get("cards") or []))

            if isinstance(sc, dict) and sc:
                config_path = get_config_path()
                repo = ConfigRepository(config_path)
                existing, _, _ = repo.load_existing(allow_default_on_error=True)
                existing_cfg = existing if isinstance(existing, dict) else {}
                merged = apply_strategy_config(existing_cfg, strategy_config=sc)
                res = repo.replace_with_snapshot(merged, ensure_ascii=False, indent=2)
                if not res.ok:
                    raise RuntimeError(res.error or "config write failed")

            QMessageBox.information(self, "成功", f"已在卡牌库选中卡组 '{deck_data.get('name')}'，点击下方保存即可应用！")

        except Exception as e:
            QMessageBox.warning(self, "错误", f"加载卡组失败: {str(e)}")

    def save_deck_as(self):
        if not self.selected_cards:
            QMessageBox.warning(self, "警告", "请至少选择一张卡片！")
            return

        deck_name, ok = QInputDialog.getText(self, "保存卡组", "请输入卡组名称:")
        if not ok or not deck_name.strip():
            return

        self.save_named_deck(deck_name.strip())

    def save_named_deck(self, deck_name):
        try:
            decks_dir = os.path.join(get_exe_dir(), "saved_decks")
            save_deck_snapshot(
                deck_name=deck_name, cards=list(self.selected_cards or []),
                decks_dir=decks_dir, config_path=get_config_path(),
            )
            QMessageBox.information(self, "成功", f"卡组 '{deck_name}' 已保存！")
            
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
                pass
        else:
            decks_dir = os.path.join(get_exe_dir(), "saved_decks")
            if os.path.exists(decks_dir):
                for file in os.listdir(decks_dir):
                    if file.endswith(".json"):
                        try:
                            with open(os.path.join(decks_dir, file), "r", encoding="utf-8") as f:
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
            pass

        self.saved_decks_combo.blockSignals(True)
        try:
            self.saved_decks_combo.clear()
            # 【修复】：显式指定 userData
            self.saved_decks_combo.addItem("选择卡组", userData=None)
            for display_name, filename in list(decks or []):
                self.saved_decks_combo.addItem(str(display_name), userData=filename)

            if current:
                idx = self.saved_decks_combo.findData(current)
                if idx >= 0:
                    self.saved_decks_combo.setCurrentIndex(idx)
        finally:
            self.saved_decks_combo.blockSignals(False)