#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Share/apply deck page. Fluent UI Refactored."""

from __future__ import annotations

# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false, reportIncompatibleMethodOverride=false

import base64
import json
import os
import shutil
import time
import zlib

from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

# ====== 引入 Fluent UI 现代组件 ======
from qfluentwidgets import (
    CardWidget, SubtitleLabel, BodyLabel, CaptionLabel,
    LineEdit, PushButton, PrimaryPushButton, SmoothScrollArea,
    FluentIcon as FIF
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
    normalize_deck_cards,
    resolve_runtime_card_paths,
)
from src.utils.card_filename import normalize_card_base_name, parse_card_filename


class SharePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        self.card_size = QSize(100, 140)
        self.cards_per_row = 4
        self.current_card_widgets = [] # 用于自适应瀑布流的缓存列表
        self.init_ui()

    def showEvent(self, event):
        """页面显示时自动刷新预览"""
        super().showEvent(event)
        self.refresh_preview()

    def init_ui(self):
        self.setObjectName("SharePage")
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(20, 20, 20, 20)

        # 标题
        title_label = SubtitleLabel("卡组应用与分享", self)
        main_layout.addWidget(title_label)

        # ==========================================
        # 卡片 1：卡组预览部分 (自适应瀑布流)
        # ==========================================
        preview_card = CardWidget(self)
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(15, 15, 15, 15)
        
        preview_title = BodyLabel("👀 当前工作区卡组预览:")
        preview_layout.addWidget(preview_title)

        self.preview_scroll_area = SmoothScrollArea()
        self.preview_scroll_area.setWidgetResizable(True)
        # 确保滚动区域背景和视口全透明
        self.preview_scroll_area.setStyleSheet("QScrollArea { background-color: transparent; border: none; }")
        self.preview_scroll_area.viewport().setStyleSheet("background-color: transparent;")
        
        self.preview_scroll_content = QWidget()
        self.preview_scroll_content.setStyleSheet("QWidget { background-color: transparent; }")
        self.preview_grid_layout = QGridLayout(self.preview_scroll_content)
        self.preview_grid_layout.setAlignment(Qt.AlignTop)
        
        self.preview_scroll_area.setWidget(self.preview_scroll_content)
        # 设置一个合适的固定高度，让底部操作区有空间
        self.preview_scroll_area.setFixedHeight(220) 

        preview_layout.addWidget(self.preview_scroll_area)
        main_layout.addWidget(preview_card)

        # ==========================================
        # 卡片 2：卡组应用部分
        # ==========================================
        apply_card = CardWidget(self)
        apply_layout = QHBoxLayout(apply_card)
        apply_layout.setContentsMargins(20, 15, 20, 15)
        apply_layout.setSpacing(15)

        apply_layout.addWidget(BodyLabel("输入分享码:"))
        
        self.share_code_input = LineEdit()
        self.share_code_input.setPlaceholderText("在此粘贴别人发给你的分享码...")
        apply_layout.addWidget(self.share_code_input, stretch=1)

        apply_btn = PrimaryPushButton(FIF.DOWNLOAD, "应用该卡组")
        apply_btn.clicked.connect(self.apply_share_code)
        apply_layout.addWidget(apply_btn)

        main_layout.addWidget(apply_card)

        # ==========================================
        # 卡片 3：卡组分享部分
        # ==========================================
        share_card = CardWidget(self)
        share_layout = QHBoxLayout(share_card)
        share_layout.setContentsMargins(20, 15, 20, 15)
        share_layout.setSpacing(15)

        share_layout.addWidget(BodyLabel("您的分享码:"))
        
        self.share_code_output = LineEdit()
        self.share_code_output.setReadOnly(True)
        self.share_code_output.setPlaceholderText("点击右侧按钮生成当前卡组的分享码")
        share_layout.addWidget(self.share_code_output, stretch=1)

        share_btn = PrimaryPushButton(FIF.SHARE, "生成")
        share_btn.clicked.connect(self.generate_share_code)
        share_layout.addWidget(share_btn)

        copy_btn = PushButton(FIF.COPY, "复制")
        copy_btn.clicked.connect(self.copy_share_code)
        share_layout.addWidget(copy_btn)

        main_layout.addWidget(share_card)
        main_layout.addStretch(1)

        # ==========================================
        # 底部操作按钮
        # ==========================================
        btn_layout = QHBoxLayout()
        back_btn = PushButton(FIF.RETURN, "返回主界面")
        back_btn.clicked.connect(lambda: getattr(self.parent, "stacked_widget", None) and self.parent.stacked_widget.setCurrentIndex(0))

        btn_layout.addStretch()
        btn_layout.addWidget(back_btn)
        main_layout.addLayout(btn_layout)

    # ====== 自适应排版逻辑 ======
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.adjust_card_layout()

    def adjust_card_layout(self):
        """当窗口拉伸时动态重新排布预览卡牌"""
        if not hasattr(self, 'preview_scroll_area') or not self.current_card_widgets:
            return
            
        scroll_width = self.preview_scroll_area.width() - 30
        new_cards_per_row = max(2, scroll_width // (self.card_size.width() + 40))
        
        if new_cards_per_row != self.cards_per_row:
            self.cards_per_row = new_cards_per_row
            row, col = 0, 0
            for widget in self.current_card_widgets:
                self.preview_grid_layout.addWidget(widget, row, col)
                col += 1
                if col >= self.cards_per_row:
                    col = 0
                    row += 1

    # ====== 业务逻辑区 (保留原样) ======
    def generate_share_code(self):
        try:
            card_files = []
            card_dir = get_card_cost_dir(ensure=True)
            if os.path.exists(card_dir):
                card_files = [f for f in os.listdir(card_dir) if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))]
            card_files = filter_non_evo_cards(card_files)
            card_refs = normalize_deck_cards(card_files)

            config_path = get_config_path()
            config_data = {}
            if os.path.exists(config_path):
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        config_data = json.load(f)
                except Exception:
                    config_data = {}

            strategy_config = (
                extract_strategy_config(config_data, cards=list(card_refs or []))
                if isinstance(config_data, dict) else {}
            )

            share_data = {
                "version": 3,
                "cards": card_refs,
                "strategy_config": strategy_config,
                "timestamp": int(time.time()),
            }

            json_data = json.dumps(share_data, ensure_ascii=False)
            compressed = zlib.compress(json_data.encode("utf-8"))
            share_code = base64.b64encode(compressed).decode("ascii")

            self.share_code_output.setText(share_code)
            if hasattr(self.parent, "log_output"):
                self.parent.log_output.append("[分享] 分享码已生成")

        except Exception as e:
            QMessageBox.warning(self, "错误", f"生成分享码失败: {str(e)}")

    def copy_share_code(self):
        if self.share_code_output.text():
            clipboard = QApplication.clipboard()
            clipboard.setText(self.share_code_output.text())
            if hasattr(self.parent, "log_output"):
                self.parent.log_output.append("[分享] 分享码已复制到剪贴板")
            QMessageBox.information(self, "成功", "分享码已复制到剪贴板！")

    def apply_share_code(self):
        try:
            if getattr(self.parent, "is_script_running", lambda: False)():
                QMessageBox.warning(self, "运行中", "脚本运行中，禁止应用分享码（会修改卡组/配置）。请先停止脚本后再操作。")
                return
        except Exception:
            pass

        share_code = self.share_code_input.text().strip()
        if not share_code:
            QMessageBox.warning(self, "警告", "请输入有效的分享码！")
            return

        try:
            compressed = base64.b64decode(share_code.encode("ascii"))
            json_data = zlib.decompress(compressed).decode("utf-8")
            share_data = json.loads(json_data)

            version = share_data.get("version", 1)
            if version not in [1, 2, 3]:
                raise ValueError("不支持的分享码版本")

            card_dir = get_card_cost_dir(ensure=True)
            os.makedirs(card_dir, exist_ok=True)

            for f in os.listdir(card_dir):
                os.remove(os.path.join(card_dir, f))

            source_dir = os.path.join(get_exe_dir(), "quanka")
            exact_index, stem_index = build_card_source_index(source_dir)
            variant_index = build_card_variant_index(source_dir)
            
            for card_file in filter_non_evo_cards(list(share_data.get("cards", []))):
                runtime_paths = resolve_runtime_card_paths(
                    source_dir, card_file,
                    exact_index=exact_index, stem_index=stem_index, variant_index=variant_index,
                )

                if not runtime_paths:
                    if hasattr(self.parent, "log_output"):
                        self.parent.log_output.append(f"[分享] 未找到卡片: {card_file}")
                    continue

                for src in runtime_paths:
                    if not os.path.exists(src): continue
                    dst = os.path.join(card_dir, os.path.basename(src))
                    shutil.copy2(src, dst)

            config_path = get_config_path()
            sc = share_data.get("strategy_config")
            if not isinstance(sc, dict) and isinstance(share_data.get("config"), dict):
                sc = extract_strategy_config(share_data["config"], cards=list(share_data.get("cards") or []))

            if isinstance(sc, dict) and sc:
                repo = ConfigRepository(config_path)
                existing, _, _ = repo.load_existing(allow_default_on_error=True)
                existing_cfg = existing if isinstance(existing, dict) else {}
                merged = apply_strategy_config(existing_cfg, strategy_config=sc)
                res = repo.replace_with_snapshot(merged, indent=4, ensure_ascii=False)
                if not res.ok: raise RuntimeError(res.error or "config write failed")

            if hasattr(self.parent, "config_page"): self.parent.config_page.refresh_config_display()
            if hasattr(self.parent, "card_priority_page"): self.parent.card_priority_page.refresh_card_priority()
            if hasattr(self.parent, "my_deck_page"): self.parent.my_deck_page.load_deck()

            self.refresh_preview()
            QMessageBox.information(self, "成功", "卡组和配置已成功应用！")
            
            if hasattr(self.parent, "log_output"):
                self.parent.log_output.append("[分享] 已成功应用分享码中的卡组和配置")

        except Exception as e:
            QMessageBox.warning(self, "错误", f"应用分享码失败: {str(e)}")

    def refresh_preview(self):
        """刷新卡组预览 (改用 Fluent UI 卡片)"""
        for i in reversed(range(self.preview_grid_layout.count())):
            if widget := self.preview_grid_layout.itemAt(i).widget():
                widget.deleteLater()
        self.current_card_widgets.clear()

        card_dir = get_card_cost_dir(ensure=True)
        if not os.path.exists(card_dir):
            no_card = CaptionLabel("卡组为空")
            no_card.setAlignment(Qt.AlignCenter)
            self.preview_grid_layout.addWidget(no_card, 0, 0)
            return

        card_files = [f for f in os.listdir(card_dir) if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))]
        card_files = filter_non_evo_cards(card_files)

        if not card_files:
            no_card = CaptionLabel("卡组为空")
            no_card.setAlignment(Qt.AlignCenter)
            self.preview_grid_layout.addWidget(no_card, 0, 0)
            return

        row, col = 0, 0
        for card_file in card_files:
            card_path = os.path.join(card_dir, card_file)

            # 使用带有悬浮阴影的卡片包装每一张预览图
            card_container = CardWidget()
            card_layout = QVBoxLayout(card_container)
            card_layout.setAlignment(Qt.AlignCenter)
            card_layout.setSpacing(5)
            card_layout.setContentsMargins(10, 10, 10, 10)

            # 卡牌图片
            from PyQt5.QtWidgets import QLabel
            card_label = QLabel()
            pixmap = QPixmap(card_path)
            if not pixmap.isNull():
                pixmap = pixmap.scaled(self.card_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                card_label.setPixmap(pixmap)
            card_label.setAlignment(Qt.AlignCenter)

            # 卡牌名字
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
            
            # 加入缓存并排列
            self.current_card_widgets.append(card_container)
            self.preview_grid_layout.addWidget(card_container, row, col)

            col += 1
            if col >= self.cards_per_row:
                col = 0
                row += 1